"""
Step 11b: the road graph, built from the pinned OSM snapshot (Code/routing/osm.py).

Scope: OSM motorway, trunk, primary, secondary and tertiary roads and their links. Tertiary roads are included because
many direct district-to-district links are tagged tertiary (without them, e.g., Yamuna Nagar -> Ambala detoured 108 km
instead of ~61 km). Residential, service and track roads are left out, so a point joins the graph at its nearest
two-way vertex; that access gap is reported separately and never added to the road distance.

Travel time uses ASSUMED free-flow speeds for a loaded goods vehicle per road class, capped by the OSM `maxspeed` tag
where one exists. These are labelled assumptions, not observed speeds: no traffic, stops, tolls or road condition.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix

from Code.routing import osm
from Code.routing.router import build_csr, haversine_km, largest_strong_component

# km/h; labelled assumptions (goods vehicle, free flow). Upgrade path: a sourced speed table (RQ-3 / 11e).
ASSUMED_SPEED_KMH = {"motorway": 65, "motorway_link": 30, "trunk": 55, "trunk_link": 30, "primary": 45,
                     "primary_link": 25, "secondary": 35, "secondary_link": 25, "tertiary": 30, "tertiary_link": 20}
CLASSES = list(ASSUMED_SPEED_KMH)


@dataclass
class Graph:
    lat: np.ndarray            # per vertex
    lon: np.ndarray
    dist: csr_matrix           # km
    time: csr_matrix           # hours
    road_class: csr_matrix     # index into CLASSES + 1 (sparse value 0 means "no edge")
    speed_tagged: csr_matrix   # 1 + whether the edge speed came from an OSM maxspeed tag
    in_core: np.ndarray        # vertex in the largest strongly connected component
    two_way: np.ndarray        # vertex on a two-way road (safe join point: not one carriageway of a divided road)
    stats: dict


def load_lines(zones=osm.ZONES):
    """Major-road polylines across zones, de-duplicated by OSM way id (zones overlap at their borders)."""
    seen: set[int] = set()
    out = []
    for zone in zones:
        z = osm.zone_dir(zone)
        a = osm.read_dbf(z / "gis_osm_roads_free_1.dbf", ["osm_id", "fclass", "oneway", "maxspeed"])
        ids = a["osm_id"].astype(np.int64)
        keep = np.isin(a["fclass"], CLASSES) & ~np.isin(ids, np.fromiter(seen, np.int64, len(seen)))
        seen.update(ids[keep].tolist())
        for i, pts in osm.read_polylines(z / "gis_osm_roads_free_1.shp", keep):
            out.append((pts, a["fclass"][i], a["oneway"][i], int(a["maxspeed"][i] or 0)))
    return out


def build_graph(lines) -> Graph:
    pts = np.concatenate([p for p, *_ in lines])
    line = np.repeat(np.arange(len(lines)), [len(p) for p, *_ in lines])
    # Ways meet where they share an OSM node; shared vertices carry identical coordinates (7 decimals).
    key = np.round(pts * 1e7).astype(np.int64)
    uniq, vid = np.unique(key, axis=0, return_inverse=True)
    vid = vid.ravel()
    same = line[1:] == line[:-1]
    a, b, ln = vid[:-1][same], vid[1:][same], line[:-1][same]
    lon, lat = uniq[:, 0] / 1e7, uniq[:, 1] / 1e7
    km = haversine_km(lat[a], lon[a], lat[b], lon[b])
    ok = (a != b) & (km > 0)
    a, b, ln, km = a[ok], b[ok], ln[ok], km[ok]
    cls = np.array([CLASSES.index(c) for _, c, _, _ in lines])[ln]
    assumed = np.array([ASSUMED_SPEED_KMH[c] for c in CLASSES])[cls]
    tag = np.array([m for *_, m in lines])[ln]
    speed = np.where(tag > 0, np.minimum(tag, assumed), assumed)
    hours = km / speed
    oneway = np.array([o for _, _, o, _ in lines])[ln]
    fwd, rev = oneway != "T", oneway != "F"           # B = both directions, F = digitised direction, T = reverse
    u = np.concatenate([a[fwd], b[rev]])
    v = np.concatenate([b[fwd], a[rev]])
    pick = lambda x: np.concatenate([x[fwd], x[rev]])
    n = len(uniq)
    dist = build_csr(n, u, v, pick(km))
    time = build_csr(n, u, v, pick(hours))
    road_class = build_csr(n, u, v, pick(cls + 1.0))
    speed_tagged = build_csr(n, u, v, pick((tag > 0) + 1.0))
    core = largest_strong_component(dist)
    two_way = np.zeros(n, bool)
    two_way[a[oneway == "B"]] = two_way[b[oneway == "B"]] = True
    stats = {"lines": len(lines), "vertices": n, "directed_edges": int(dist.nnz), "core_vertices": int(core.sum()),
             "major_road_km": float(km.sum()), "edges_with_maxspeed_tag_pct": float(100 * (tag > 0).mean())}
    stats["two_way_core_vertices"] = int((core & two_way).sum())
    return Graph(lat, lon, dist, time, road_class, speed_tagged, core, two_way, stats)
