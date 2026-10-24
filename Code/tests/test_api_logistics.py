"""
Routing and warehouse API tests on the built Phase 11 outputs: real road routes only, honest statuses, validation,
missing-output handling, and the warehouse data contract (no invented capacity, charges, suitability or contacts).
"""

import json
import re

import pandas as pd
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from Code.api import logistics as lg, main as api
from Code.routing import pipeline as pl, storage as st

pytestmark = pytest.mark.skipif(not (pl.OD.exists() and st.OUT.exists()), reason="routing outputs not built")
client = TestClient(api.app)
NASHIK, PUNE, LUDHIANA = "D:Maharashtra|Nashik", "D:Maharashtra|Pune", "D:Punjab|Ludhiana"


def get(url, status=200, **params):
    r = client.get(url, params=params)
    assert r.status_code == status, (url, r.status_code, r.text[:300])
    return r.json()


def test_routes_meta_states_sources_and_gaps():
    m = get("/api/routes")
    assert m["available"] is True and "OpenStreetMap" in m["attribution"] and m["snapshot_date"] == "2026-10-22"
    caps = {c["capability"]: c["status"] for c in m["capabilities"]}
    assert caps["Road network and road distances"] == "available" and caps["Travel time"] == "estimate"
    assert caps["Transport cost"] == "missing_data" and caps["Live traffic, closures, road condition"] == "missing_data"
    assert sum(m["pairs"].values()) == 46 * 45 and {s["road_class"] for s in m["speed_assumptions"]} >= {"motorway", "primary"}


def test_a_real_route_has_network_distance_geometry_and_labels():
    r = get("/api/routes/route", origin=NASHIK, dest=PUNE)
    assert r["status"] == "ok" and r["objective"] == "shortest"
    assert r["road_distance_km"] >= r["straight_line_km"] - r["origin_access_gap_km"] - r["dest_access_gap_km"]
    assert 150 < r["road_distance_km"] < 300 and 2 < r["travel_time_h"] < 8               # Nashik-Pune by road ~210 km
    assert "NOT a road distance" in r["labels"]["straight_line_km"] and "estimate" in r["labels"]["travel_time_h"]
    assert r["transport_cost"]["available"] is False
    assert set(r["alternatives"]) == {"shortest", "fastest"}
    assert r["alternatives"]["fastest"]["travel_time_h"] <= r["alternatives"]["shortest"]["travel_time_h"]
    if r["geometry"] is not None:                                                          # parquet is git-ignored
        g = r["geometry"]
        assert len(g) > 10 and all(len(p) == 2 for p in g)
        snap = pd.read_csv(pl.SNAP).set_index("node_id")
        assert abs(g[0][0] - snap.loc[NASHIK, "network_lat"]) < 1e-4 and abs(g[-1][1] - snap.loc[PUNE, "network_lon"]) < 1e-4
    f = get("/api/routes/route", origin=NASHIK, dest=PUNE, objective="fastest")
    assert f["travel_time_h"] <= r["travel_time_h"] + 1e-9


def test_route_validation_errors():
    get("/api/routes/route", 404, origin="D:Atlantis|Nowhere", dest=PUNE)
    get("/api/routes/route", 404, origin="M:Maharashtra|Nashik|Lasalgaon", dest=PUNE)      # markets are not verified nodes
    get("/api/routes/route", 422, origin=PUNE, dest=PUNE)
    get("/api/routes/route", 422, origin=NASHIK, dest=PUNE, objective="cheapest")          # no cost data -> no such objective
    get("/api/routes/route", 422, origin=NASHIK)


def test_unrouted_pairs_never_carry_numbers():
    od = pd.read_csv(pl.OD)
    bad = od[od["status"] != "ok"]
    for row in bad.head(3).itertuples():
        r = get("/api/routes/route", origin=row.origin_id, dest=row.dest_id, objective=row.objective)
        assert r["road_distance_km"] is None and r["travel_time_h"] is None and r["geometry"] is None


def test_missing_routing_outputs_give_503_and_honest_meta(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "OD", tmp_path / "absent.csv")
    lg.od.cache_clear()
    try:
        assert get("/api/routes")["available"] is False
        assert "not built" in get("/api/routes/route", 503, origin=NASHIK, dest=PUNE)["detail"]["message"]
    finally:
        lg.od.cache_clear()


def test_nodes_are_the_verified_district_points():
    n = get("/api/routes/nodes")
    assert len(n) == 46 and all(x["verification"] == "passed" and x["node_id"].startswith("D:") for x in n)
    assert {x["network_status"] for x in n} <= {"on_network", "endpoint_off_network"}


def test_warehouse_meta_and_contract():
    m = get("/api/warehouses")
    assert m["available"] is True and m["records"] > 0 and set(m["by_operator"]) <= st.OPERATORS
    fs = m["field_status"]
    assert fs["location"] == {"reported_unverified": m["records"]}                       # nothing claimed as verified
    for k in ("capacity", "charges", "suitability", "availability"):
        assert fs[k] == {"unknown": m["records"]}
    wh = pd.read_csv(st.OUT)
    st.validate(wh)
    assert wh[["capacity_total_t", "capacity_available_t", "storage_charge_rs_per_t_month"]].isna().all().all()
    assert not any(re.search(r"phone|mobile|email|contact", c) for c in wh.columns)


def test_warehouse_list_filters_and_detail():
    all_ = get("/api/warehouses/list")["records"]
    fci = get("/api/warehouses/list", operator="fci")["records"]
    assert fci and all(r["operator_class"] == "fci" for r in fci) and len(fci) < len(all_)
    word = fci[0]["name"].split()[0]
    assert all(word.lower() in r["name"].lower() for r in get("/api/warehouses/list", q=word)["records"])
    near = get("/api/warehouses/list", near=NASHIK, radius_km=150)["records"]
    assert all(r["road_distance_km"] <= 150 for r in near)
    assert [r["road_distance_km"] for r in near] == sorted(r["road_distance_km"] for r in near)
    crop = get("/api/warehouses/list", crop="potato")
    assert crop["records"] == [] and "unknown" in crop["note"]
    get("/api/warehouses/list", 404, near="D:Atlantis|Nowhere")
    get("/api/warehouses/list", 422, operator="private")
    d = get(f"/api/warehouses/{all_[0]['warehouse_id']}")
    assert d["fields"]["capacity"]["status"] == "unknown" and d["fields"]["capacity"]["values"]["capacity_total_t"] is None
    get("/api/warehouses/W:osm:pois:0", 404)


def test_route_nearby_warehouses_use_road_distance():
    r = get("/api/routes/route", origin=LUDHIANA, dest=NASHIK)
    for side in ("origin", "dest"):
        ds = [w["road_distance_km"] for w in r["nearby_warehouses"][side]]
        assert ds == sorted(ds) and all(x <= pl.WAREHOUSE_RADIUS_KM for x in ds)
    assert not re.search(r"[A-Za-z]:\\\\|bda-env", json.dumps(r))
