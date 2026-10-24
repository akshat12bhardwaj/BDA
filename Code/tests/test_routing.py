"""
Phase 11a-c tests: node identifiers and verification, shapefile reading, graph construction and Dijkstra on synthetic
inputs, and the real OD outputs' invariants (when built). No test makes a network call.
"""

import struct

import numpy as np
import pandas as pd
import pytest

from Code.routing import network as nw, nodes as nd, osm, router as r


# ---------------------------------------------------------------- algorithms on a synthetic graph
def _g(edges, n):
    u, v, w = (np.array(x) for x in zip(*edges))
    return r.build_csr(n, u, v, w.astype(float))


def test_dijkstra_known_shortest_path_and_unreachable():
    g = _g([(0, 1, 1), (1, 2, 1), (0, 2, 5), (2, 3, 1)], 5)          # node 4 is isolated
    dist, pred = r.shortest_from(g, 0)
    assert dist[3] == 3 and r.path(pred, 0, 3) == [0, 1, 2, 3]
    assert np.isinf(dist[4]) and r.path(pred, 0, 4) is None
    assert r.path(pred, 0, 0) == [0] and r.edge_sum(g, [0, 1, 2, 3]) == 3


def test_removing_an_edge_changes_the_route_and_oneway_is_respected():
    full = [(0, 1, 1), (1, 2, 1), (0, 2, 5)]
    assert r.path(r.shortest_from(_g(full, 3), 0)[1], 0, 2) == [0, 1, 2]
    assert r.path(r.shortest_from(_g([e for e in full if e[:2] != (1, 2)], 3), 0)[1], 0, 2) == [0, 2]
    assert r.path(r.shortest_from(_g(full, 3), 2)[1], 2, 0) is None         # directed: no edge back


def test_parallel_edges_keep_the_minimum_and_weights_must_be_positive():
    g = _g([(0, 1, 4), (0, 1, 2), (0, 1, 3)], 2)
    assert g[0, 1] == 2
    with pytest.raises(ValueError):
        _g([(0, 1, 0)], 2)


def test_strong_component_and_haversine():
    g = _g([(0, 1, 1), (1, 0, 1), (1, 2, 1)], 3)                      # 2 is reachable but cannot return
    assert r.largest_strong_component(g).tolist() == [True, True, False]
    assert r.haversine_km(19.99727, 73.79096, 18.52043, 73.85674) == pytest.approx(164.3, abs=0.5)   # Nashik-Pune


def test_graph_joins_ways_at_shared_vertices_and_applies_speeds():
    pts = lambda *xy: np.array(xy, float)
    lines = [(pts((73.0, 19.0), (73.1, 19.0)), "primary", "B", 0),
             (pts((73.1, 19.0), (73.2, 19.0)), "motorway", "F", 50),       # one-way, maxspeed 50 < assumed 65
             (pts((80.0, 25.0), (80.1, 25.0)), "secondary", "B", 0)]      # disconnected fragment
    g = nw.build_graph(lines)
    a, b, c = (int(np.flatnonzero((np.isclose(g.lon, x)) & np.isclose(g.lat, 19.0))[0]) for x in (73.0, 73.1, 73.2))
    dist, pred = r.shortest_from(g.dist, a)
    assert r.path(pred, a, c) == [a, b, c] and np.isinf(r.shortest_from(g.dist, c)[0][a])
    km = r.haversine_km(19.0, 73.1, 19.0, 73.2)
    assert g.time[b, c] == pytest.approx(km / 50) and g.time[a, b] == pytest.approx(r.haversine_km(19, 73, 19, 73.1) / 45)
    assert g.speed_tagged[b, c] == 2 and g.in_core.sum() == 2         # only the two-way primary pair is strongly connected
    assert g.two_way[a] and g.two_way[b] and not g.two_way[c]          # c is only on a one-way road: never a join point


# ---------------------------------------------------------------- shapefile reading
def _dbf(path, rows):
    fields = [("osm_id", 10), ("fclass", 28)]
    hlen, rlen = 32 + 32 * len(fields) + 1, 1 + sum(n for _, n in fields)
    out = struct.pack("<BBBBIHH20x", 3, 26, 10, 24, len(rows), hlen, rlen)
    for name, n in fields:
        out += name.encode().ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([n, 0]) + b"\0" * 14
    out += b"\r" + b"".join(b" " + b"".join(str(v).encode().ljust(n) for v, (_, n) in zip(row, fields)) for row in rows)
    path.write_bytes(out)


def _shp(path, polylines):
    recs = b""
    for i, pts in enumerate(polylines, 1):
        body = struct.pack("<i4dii", 3, 0, 0, 0, 0, 1, len(pts)) + struct.pack("<i", 0) + np.asarray(pts, "<f8").tobytes()
        recs += struct.pack(">ii", i, len(body) // 2) + body
    path.write_bytes(struct.pack(">i20xi", 9994, (100 + len(recs)) // 2) + struct.pack("<ii4d32x", 1000, 3, 0, 0, 0, 0) + recs)


def test_dbf_and_polyline_readers(tmp_path):
    _dbf(tmp_path / "t.dbf", [(11, "primary"), (12, "residential")])
    a = osm.read_dbf(tmp_path / "t.dbf", ["osm_id", "fclass"])
    assert a["fclass"].tolist() == ["primary", "residential"] and a["osm_id"].tolist() == ["11", "12"]
    _shp(tmp_path / "t.shp", [[(73.0, 19.0), (73.1, 19.1)], [(1, 1), (2, 2)]])
    got = list(osm.read_polylines(tmp_path / "t.shp", np.array([True, False])))
    assert len(got) == 1 and got[0][0] == 0 and got[0][1].tolist() == [[73.0, 19.0], [73.1, 19.1]]
    with pytest.raises(KeyError):
        osm.read_dbf(tmp_path / "t.dbf", ["maxspeed"])


# ---------------------------------------------------------------- node table (11a)
def test_node_ids_are_stable_and_reject_the_separator():
    assert nd.node_id("D", "Maharashtra", "Nashik") == "D:Maharashtra|Nashik"
    with pytest.raises(ValueError):
        nd.node_id("M", "A|B", "C")


needs_nodes = pytest.mark.skipif(not nd.RESOLUTION.exists(), reason="Phase 4 outputs not present")


@needs_nodes
def test_district_nodes_are_verified_and_reproducible():
    n = nd.district_nodes()
    assert len(n) == 46 and n["node_id"].is_unique and (n["verification"] == "passed").all()
    assert (n["geocoder_admin1"] == n["state"]).all() and n[["latitude", "longitude"]].notna().all().all()
    m = nd.market_nodes()
    assert len(m) == 2657 and m["latitude"].isna().all() and (m["verification"] == "unresolved").all()
    nd.check()                                                       # files on disk equal a fresh rebuild


@needs_nodes
@pytest.mark.parametrize("change, msg", [
    (lambda df: df.assign(latitude=df["latitude"].where(df.index != 0, 99.0)), "differs from its geocoder evidence"),
    (lambda df: df.assign(latitude=df["latitude"].where(df.index != 0, np.nan)), "without coordinates"),
    (lambda df: pd.concat([df, df.iloc[[0]]]), "not a one-to-one merge|duplicate"),
])
def test_node_validation_rejects_bad_coordinates_and_duplicates(tmp_path, monkeypatch, change, msg):
    bad = tmp_path / "res.csv"
    change(pd.read_csv(nd.RESOLUTION)).to_csv(bad, index=False)
    monkeypatch.setattr(nd, "RESOLUTION", bad)
    with pytest.raises(Exception, match=msg):
        nd.district_nodes()


# ---------------------------------------------------------------- real routing outputs (11b/c), when built
from Code.routing import pipeline as pl  # noqa: E402

needs_od = pytest.mark.skipif(not pl.OD.exists(), reason="routing outputs not built")


@needs_od
def test_od_matrix_invariants():
    od = pd.read_csv(pl.OD)
    nodes = pd.read_csv(nd.NODES)
    assert len(od) == 46 * 45 * 2 and set(od["objective"]) == {"shortest", "fastest"}
    assert set(od["origin_id"]) <= set(nodes["node_id"]) and set(od["status"]) <= {"ok", "no_route", "endpoint_off_network"}
    ok = od[od["status"] == "ok"]
    bad = od[od["status"] != "ok"]
    assert bad[["road_distance_km", "travel_time_h"]].isna().all().all()            # no numbers without a route
    # road >= straight line between the points, allowing for the reported access gaps at both ends
    assert (ok["road_distance_km"] + ok["origin_access_gap_km"] + ok["dest_access_gap_km"] >= ok["straight_line_km"] - 1e-6).all()
    s, f = (ok[ok["objective"] == k].set_index(["origin_id", "dest_id"]) for k in ("shortest", "fastest"))
    j = s.join(f, lsuffix="_s", rsuffix="_f", how="inner")
    assert (j["road_distance_km_s"] <= j["road_distance_km_f"] + 1e-6).all()      # shortest is never longer
    assert (j["travel_time_h_f"] <= j["travel_time_h_s"] + 1e-6).all()            # fastest is never slower
    detour = ok["road_distance_km"] / ok["straight_line_km"]
    assert detour.median() < 1.6 and (ok["travel_time_h"] > 0).all()


# ---------------------------------------------------------------- warehouse contract (11e storage)
from Code.routing import storage as st  # noqa: E402


@pytest.mark.parametrize("name, layer, op", [
    ("Food Corporation of India", "landuse_a", "fci"), ("FCI Godown, Chutia", "buildings_a", "fci"),
    ("Central Warehousing Corporation - Kalamboli", "landuse_a", "cwc"), ("Odisha State Warehousing Corporation Warehouse", "pois_a", "swc"),
    ("Santimoyee Cold Storage", "landuse_a", "cold_storage"),
    ("FCI Colony", "landuse_a", None), ("FCI Road", "pois", None), ("Pranav Indane Godown", "buildings_a", None),
    ("M/S K.K. Warehousing corporation", "landuse_a", None), ("Ave Maria Cold Storage", "pois", None), ("", "pois", None)])
def test_storage_name_rules(name, layer, op):
    assert st.classify(name, layer) == op


def _record(**kw):
    r = {c: None for c in st.COLUMNS}
    r.update(warehouse_id="W:test:1", name="FCI Test", latitude=19.0, longitude=73.0, operator_class="fci", facility_type="warehouse",
             name_status="reported_unverified", location_status="reported_unverified", operator_status="derived",
             facility_status="derived", suitability_status="unknown", capacity_status="unknown", charges_status="unknown",
             availability_status="unknown", source="test", licence="ODbL")
    r.update(kw)
    return pd.DataFrame([r], columns=st.COLUMNS)


def test_contract_accepts_a_valid_record_and_known_values_with_sources():
    st.validate(_record())
    st.validate(_record(capacity_status="verified", capacity_total_t=5000, capacity_available_t=1200, capacity_as_of="2026-10-01",
                        verified_on="2026-10-02"))


@pytest.mark.parametrize("kw, msg", [
    ({"capacity_total_t": 5000}, "status is unknown"),                                 # a value without a source
    ({"capacity_status": "verified", "capacity_total_t": 10}, "verified value without verified_on"),
    ({"capacity_status": "reported_unverified", "capacity_total_t": 10, "capacity_available_t": 20}, "exceeds total"),
    ({"capacity_status": "reported_unverified", "capacity_total_t": -1}, "negative"),
    ({"latitude": 51.5}, "outside India"),
    ({"source": None}, "without source"),
    ({"location_status": "guessed"}, "outside"),
    ({"operator_class": "private"}, "vocabulary"),
])
def test_contract_rejects_violations(kw, msg):
    with pytest.raises(ValueError, match=msg):
        st.validate(_record(**kw))


def test_contract_rejects_duplicates_and_wrong_columns():
    with pytest.raises(ValueError, match="duplicated"):
        st.validate(pd.concat([_record(), _record()], ignore_index=True))
    with pytest.raises(ValueError, match="columns"):
        st.validate(_record().assign(phone="123"))


def test_dedupe_keeps_distinct_sites_and_merges_double_mapping():
    df = pd.DataFrame({"warehouse_id": ["a", "b", "c"], "operator_class": ["fci"] * 3, "latitude": [19.0, 19.001, 19.2],
                       "longitude": [73.0, 73.0, 73.0], "coord_method": ["OSM point", "centroid of OSM area", "OSM point"]})
    assert sorted(st._dedupe(df)["warehouse_id"]) == ["b", "c"]                       # area kept over the point 110 m away


needs_wh = pytest.mark.skipif(not st.OUT.exists(), reason="warehouse table not built")


@needs_wh
def test_built_warehouse_table_meets_the_contract():
    wh = st.validate(pd.read_csv(st.OUT))
    assert len(wh) > 0 and (wh["location_status"] == "reported_unverified").all() and wh["verified_on"].isna().all()
    for k in ("suitability", "capacity", "charges", "availability"):
        assert (wh[f"{k}_status"] == "unknown").all()
