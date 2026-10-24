"""
Steps 11b/11c pipeline: verified nodes -> OSM major-road graph -> all-pairs shortest and fastest routes -> manifest.

Every output is computed on the road network from the pinned snapshot; nothing is estimated from straight lines.
Pairs that cannot be routed get status `no_route` or `endpoint_off_network` and no numbers.

Run:  python -B -m Code.routing.pipeline build    (about 5 minutes; needs the snapshot from Code.routing.osm fetch)
      python -B -m Code.routing.pipeline check    (offline rebuild; the OD matrix must reproduce byte for byte)
"""

from __future__ import annotations

import hashlib
import json
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import LineString

from Code.integration.pipeline import file_sha256
from Code.routing import network as nw, nodes as nd, osm, storage as st
from Code.routing.router import edge_sum, haversine_km, path, shortest_from

VERSION = "v1"
OUT = nd.OUT
OD = OUT / f"od_matrix_{VERSION}.csv"
SNAP = OUT / f"node_snap_{VERSION}.csv"
SPEEDS = OUT / f"speed_assumptions_{VERSION}.csv"
GEOMETRY = OUT / f"route_geometry_{VERSION}.parquet"         # git-ignored (Processed_Data/**/*.parquet); rebuildable
MANIFEST = OUT / f"routing_manifest_{VERSION}.csv"
NODE_WAREHOUSE = OUT / f"node_warehouse_{VERSION}.csv"
WAREHOUSE_RADIUS_KM = 150.0     # node -> warehouse road distances kept up to this network distance
MAX_ACCESS_GAP_KM = 10.0        # a point farther than this from the major-road core is not routed
SIMPLIFY_DEG = 0.0005           # ~50 m; display geometry only, distances use the full-resolution path
OBJECTIVES = {"shortest": "dist", "fastest": "time"}
PROVIDER = f"self-built graph: OSM motorway-to-tertiary roads, Geofabrik India zones snapshot {osm.SNAPSHOT} (data to 2026-10-22)"


def _xyz(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def snap_points(lat: np.ndarray, lon: np.ndarray, g: nw.Graph) -> tuple[np.ndarray, np.ndarray]:
    """Nearest two-way vertex of the strongly connected core, and the straight-line access gap to it (km).
    Joining at a one-way carriageway would force a detour to the next turn-around, so those vertices are skipped."""
    core = np.flatnonzero(g.in_core & g.two_way)
    _, j = cKDTree(_xyz(g.lat[core], g.lon[core])).query(_xyz(lat, lon))
    v = core[j]
    return v, haversine_km(lat, lon, g.lat[v], g.lon[v])


def snap_nodes(nodes: pd.DataFrame, g: nw.Graph) -> pd.DataFrame:
    """Each node's network vertex (straight-line access gap, reported separately and never added to road distance)."""
    v, gap = snap_points(nodes["latitude"].to_numpy(), nodes["longitude"].to_numpy(), g)
    return pd.DataFrame({"node_id": nodes["node_id"], "vertex": v, "network_lat": g.lat[v].round(7), "network_lon": g.lon[v].round(7),
                         "access_gap_km": gap.round(3),
                         "status": np.where(gap <= MAX_ACCESS_GAP_KM, "on_network", "endpoint_off_network")})


def all_routes(nodes: pd.DataFrame, snap: pd.DataFrame, g: nw.Graph, wh_vertex: np.ndarray | None = None):
    weights = {"dist": g.dist, "time": g.time}
    od, geoms, to_wh = [], [], {}
    pos = dict(zip(nodes["node_id"], zip(nodes["latitude"], nodes["longitude"])))
    for o in snap.itertuples():
        for objective, w in OBJECTIVES.items():
            cost, pred = shortest_from(weights[w], int(o.vertex)) if o.status == "on_network" else (None, None)
            if cost is not None and wh_vertex is not None:
                to_wh[(o.node_id, objective)] = cost[wh_vertex]
            for d in snap.itertuples():
                if d.node_id == o.node_id:
                    continue
                straight = float(haversine_km(*pos[o.node_id], *pos[d.node_id]))
                row = {"origin_id": o.node_id, "dest_id": d.node_id, "objective": objective, "status": "ok",
                       "road_distance_km": np.nan, "travel_time_h": np.nan, "straight_line_km": round(straight, 3),
                       "origin_access_gap_km": o.access_gap_km, "dest_access_gap_km": d.access_gap_km,
                       "motorway_trunk_share_pct": np.nan, "maxspeed_tagged_share_pct": np.nan, "provider": PROVIDER}
                seq = None
                if o.status != "on_network" or d.status != "on_network":
                    row["status"] = "endpoint_off_network"
                else:
                    seq = path(pred, int(o.vertex), int(d.vertex))
                    if seq is None:
                        row["status"] = "no_route"
                if seq is not None:
                    a, b = np.asarray(seq[:-1]), np.asarray(seq[1:])
                    km = np.asarray(g.dist[a, b]).ravel()
                    cls = np.asarray(g.road_class[a, b]).ravel() - 1
                    tagged = np.asarray(g.speed_tagged[a, b]).ravel() - 1
                    row.update(road_distance_km=round(float(km.sum()), 3), travel_time_h=round(edge_sum(g.time, seq), 3),
                               motorway_trunk_share_pct=round(float(100 * km[cls <= 3].sum() / km.sum()), 1),
                               maxspeed_tagged_share_pct=round(float(100 * km[tagged > 0].sum() / km.sum()), 1))
                    # sanity (plan §8): road distance between the snapped vertices >= their straight-line distance
                    sv = float(haversine_km(g.lat[seq[0]], g.lon[seq[0]], g.lat[seq[-1]], g.lon[seq[-1]]))
                    if row["road_distance_km"] + 1e-6 < sv:
                        raise ValueError(f"road shorter than straight line: {o.node_id} -> {d.node_id}")
                    line = LineString(np.column_stack([g.lon[seq], g.lat[seq]])).simplify(SIMPLIFY_DEG)
                    geoms.append({"origin_id": o.node_id, "dest_id": d.node_id, "objective": objective,
                                  "coordinates": json.dumps(np.round(np.asarray(line.coords)[:, ::-1], 5).tolist(), separators=(",", ":"))})
                od.append(row)
        print(f"routed from {o.node_id}", flush=True)
    return pd.DataFrame(od), pd.DataFrame(geoms), to_wh


def node_warehouse(snap: pd.DataFrame, wh: pd.DataFrame, gap: np.ndarray, to_wh: dict) -> pd.DataFrame:
    """Road distance (shortest objective) and estimated time (fastest objective) from each node to nearby facilities."""
    rows = []
    for o in snap.itertuples():
        if (o.node_id, "shortest") not in to_wh:
            continue
        km, h = to_wh[(o.node_id, "shortest")], to_wh[(o.node_id, "fastest")]
        for k in np.flatnonzero((km <= WAREHOUSE_RADIUS_KM) & (gap <= MAX_ACCESS_GAP_KM)):
            rows.append({"node_id": o.node_id, "warehouse_id": wh["warehouse_id"].iat[k], "road_distance_km": round(float(km[k]), 3),
                         "travel_time_h": round(float(h[k]), 3), "node_access_gap_km": o.access_gap_km,
                         "warehouse_access_gap_km": round(float(gap[k]), 3)})
    cols = ["node_id", "warehouse_id", "road_distance_km", "travel_time_h", "node_access_gap_km", "warehouse_access_gap_km"]
    return pd.DataFrame(rows, columns=cols).sort_values(["node_id", "road_distance_km", "warehouse_id"]).reset_index(drop=True)


def _csv(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, lineterminator="\n")


def build_outputs() -> dict:
    nodes = nd.load_nodes()
    g = nw.build_graph(nw.load_lines())
    snap = snap_nodes(nodes, g)
    wh = pd.read_csv(st.OUT) if st.OUT.exists() else None
    wv, wgap = snap_points(wh["latitude"].to_numpy(), wh["longitude"].to_numpy(), g) if wh is not None else (None, None)
    od, geoms, to_wh = all_routes(nodes, snap, g, wv)
    speeds = pd.DataFrame({"road_class": nw.CLASSES, "assumed_kmh": [nw.ASSUMED_SPEED_KMH[c] for c in nw.CLASSES],
                           "basis": "assumption: free-flow goods vehicle; capped by OSM maxspeed where tagged; not observed"})
    out = {"g": g, OD: _csv(od), SNAP: _csv(snap.drop(columns="vertex")), SPEEDS: _csv(speeds), "geoms": geoms}
    if wh is not None:
        out[NODE_WAREHOUSE] = _csv(node_warehouse(snap, wh, wgap, to_wh))
    return out


def build() -> None:
    out = build_outputs()
    texts = [p for p in (OD, SNAP, SPEEDS, NODE_WAREHOUSE) if p in out]
    for p in texts:
        p.write_bytes(out[p].encode())
    out["geoms"].to_parquet(GEOMETRY, index=False)
    sha = lambda t: hashlib.sha256(t.encode()).hexdigest()
    rows = [{"kind": "input", "item": f"osm/{r['zone']}/{r['member']}", "value": r["member_sha256"], "note": r["url"]}
            for r in osm.read_snapshot()]
    rows += [{"kind": "input", "item": str(p).replace("\\", "/"), "value": file_sha256(p), "note": n}
             for p, n in ((nd.NODES, "verified nodes"), (st.OUT, "warehouse table")) if p.exists()]
    rows += [{"kind": "parameter", "item": k, "value": v, "note": ""} for k, v in
             {"road_classes": ",".join(nw.CLASSES), "max_access_gap_km": MAX_ACCESS_GAP_KM, "simplify_deg": SIMPLIFY_DEG,
              "algorithm": "Dijkstra (scipy.sparse.csgraph), directed, OSM oneway respected; endpoints join at the nearest two-way core vertex", "licence": osm.LICENCE}.items()]
    rows += [{"kind": "graph", "item": k, "value": round(v, 3) if isinstance(v, float) else v, "note": ""} for k, v in out["g"].stats.items()]
    rows += [{"kind": "output", "item": str(p).replace("\\", "/"), "value": sha(out[p]), "note": f"{out[p].count(chr(10)) - 1} rows"}
             for p in texts]
    rows += [{"kind": "output", "item": str(GEOMETRY).replace("\\", "/"), "value": file_sha256(GEOMETRY), "note": f"{len(out['geoms'])} routes; git-ignored"}]
    pd.DataFrame(rows).to_csv(MANIFEST, index=False, lineterminator="\n")
    print("wrote", ", ".join(str(p) for p in [*texts, GEOMETRY, MANIFEST]))


def check() -> None:
    osm.verify_snapshot()
    out = build_outputs()
    for p in (x for x in (OD, SNAP, SPEEDS, NODE_WAREHOUSE) if x in out):
        if p.read_bytes() != out[p].encode():
            raise ValueError(f"{p} does not reproduce from the pinned snapshot")
    print("routing outputs reproduce byte for byte")


if __name__ == "__main__":
    {"build": build, "check": check}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit("usage: build | check"))()
