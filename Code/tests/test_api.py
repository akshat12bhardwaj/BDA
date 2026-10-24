"""
Read-only API tests (Code/api/main.py) on the real frozen outputs: filters, validation, missing-data handling, and
that no endpoint can expose reserved production values, 2023+ data, or invented route / warehouse records.
"""

import json
import re

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from Code.api import main as api
from Code.app import data as d
from Code.integration.pipeline import file_sha256
from Code.tests.test_app import SOURCES

pytestmark = pytest.mark.skipif(not all(p.exists() for p in SOURCES), reason="frozen outputs not present locally")
client = TestClient(api.app)
SERIES = {"state": "", "district": "", "market": "", "variety": ""}


def get(url, status=200, **params):
    r = client.get(url, params=params)
    assert r.status_code == status, (url, r.status_code, r.text[:300])
    return r.json()


def all_responses():
    """One call to every endpoint, with the first valid series for the prediction endpoints."""
    ps = get("/api/outlook/prices/series-options", crop="Onion", horizon=1)[0]
    ars = get("/api/outlook/arrivals/series-options", crop="Wheat", horizon=4)[0]
    keys = ["state", "district", "market", "variety"]
    return {
        "health": get("/api/health"), "meta": get("/api/meta"), "overview": get("/api/overview", crop="Potato"),
        "weekly": get("/api/markets/weekly", crop="Onion", state="Maharashtra"),
        "states": get("/api/markets/states", crop="Wheat"), "yearly": get("/api/markets/yearly", crop="Onion", states="Gujarat,Karnataka"),
        "top": get("/api/markets/top-districts", crop="Potato", year="2015-2016"),
        "production": get("/api/production", crop="Potato", year="1997-1998", basis="whole_year_row", quality="ok,annotated,review"),
        "reserved": get("/api/production/reserved"), "price_summary": get("/api/outlook/prices/summary"),
        "price_series": get("/api/outlook/prices/series", crop="Onion", horizon=1, **{k: ps[k] for k in keys}),
        "arrivals_summary": get("/api/outlook/arrivals/summary"),
        "arrivals_series": get("/api/outlook/arrivals/series", crop="Wheat", horizon=4, period="test_2022", **{k: ars[k] for k in keys}),
        "locations": get("/api/locations"), "climate": get("/api/locations/0/climate"),
        "routes": get("/api/routes"), "warehouses": get("/api/warehouses"), "about": get("/api/about"),
        "route_nodes": get("/api/routes/nodes"), "warehouse_list": get("/api/warehouses/list")}


def test_health_and_meta_state_the_boundaries():
    h = get("/api/health")
    assert h == {"status": "ok", "market_history_end": "2020-06-30", "production_values_end": "2018-2019", "live_data": False}
    m = get("/api/meta")
    assert m["crops"] == d.CROPS and m["horizons"] == [1, 2, 4] and m["verified_locations"] == 46
    assert max(m["production_years"]) == d.DESIGN_END and not set(m["production_years"]) & set(d.RESERVED)
    assert max(m["market_years"]) <= d.LATEST_FULL_YEAR


def test_overview_matches_the_tested_calculation():
    o = get("/api/overview", crop="Onion")
    assert o["state"] == get("/api/meta")["states_by_crop"]["Onion"][0]                 # default: top state
    assert o["kpis"] == d.overview_kpis(d.weekly_state(), "Onion", o["state"])
    assert o["reports_processed"] == 2624379 and o["coverage"]["pipeline_cross_check_passed"] is True
    assert o["coverage"]["last_week"] <= "2020-06-30"
    get("/api/overview", 404, crop="Onion", state="Atlantis")
    get("/api/overview", 422, crop="Tomato")


def test_markets_filters_and_validation():
    w = get("/api/markets/weekly", crop="Onion", state="Maharashtra")
    assert w and max(r["week_start"][:10] for r in w) <= "2020-06-30"
    s = get("/api/markets/states", crop="Onion", year="2010-2011")
    assert s[0]["arrivals_tonnes"] >= s[-1]["arrivals_tonnes"] and {r["agri_year"] for r in s} == {"2010-2011"}
    y = get("/api/markets/yearly", crop="Onion", states="Gujarat,Karnataka")
    assert {r["state"] for r in y} == {"Gujarat", "Karnataka"}
    get("/api/markets/states", 422, crop="Onion", year="2010")
    get("/api/markets/weekly", 404, crop="Wheat", state="Atlantis")


def test_production_never_exposes_reserved_years():
    for year in d.RESERVED + ("2022-2023",):
        body = get("/api/production", 403, crop="Onion", year=year)
        assert "reserved" in json.dumps(body)
    p = get("/api/production", crop="Potato", year="1997-1998", basis="whole_year_row", quality="ok,annotated,review")
    assert p["provider_query_pending"] is True and p["rows"] and all(r["pq_class"] in ("ok", "annotated", "review") for r in p["rows"])
    r = get("/api/production/reserved")
    assert {c["source_apy_year"] for c in r["counts"]} == set(d.RESERVED)
    assert not any(k in c for c in r["counts"] for k in ("production_tonnes", "area_ha", "yield_t_per_ha"))


def test_outlook_endpoints_serve_only_stored_results():
    ps = get("/api/outlook/prices/summary")
    assert ps["baseline_kept"] == 8 and ps["cases"] == 9 and ps["onion_1w_test_change_pct"] < 0
    opt = get("/api/outlook/prices/series-options", crop="Potato", horizon=2)[0]
    s = get("/api/outlook/prices/series", crop="Potato", horizon=2, **{k: opt[k] for k in SERIES})
    assert {r["period"] for r in s} <= d.PRICE_PERIODS and max(r["origin_date"][:10] for r in s) <= "2020-12-27"
    get("/api/outlook/prices/series", 404, crop="Potato", horizon=2, **SERIES)
    get("/api/outlook/prices/series-options", 422, crop="Potato", horizon=3)
    a = get("/api/outlook/arrivals/summary")
    assert a["cells"] == 18 and a["cells_better"] == 18
    get("/api/outlook/arrivals/series", 422, crop="Wheat", horizon=4, period="holdout_2023", **SERIES)


def test_missing_prediction_files_give_a_clear_503(monkeypatch, tmp_path):
    monkeypatch.setattr(d, "PREDICTION_FILES", {"price": [tmp_path / "absent.parquet"], "arrivals": [tmp_path / "absent2.parquet"]})
    for url, params in [("/api/outlook/prices/series-options", {"crop": "Onion", "horizon": 1}),
                        ("/api/outlook/arrivals/series-options", {"crop": "Onion", "horizon": 1})]:
        body = get(url, 503, **params)
        assert "not present" in body["detail"]["message"]
    assert get("/api/meta")["predictions_available"] == {"price": False, "arrivals": False}
    assert get("/api/outlook/prices/summary")["cases"] == 9                         # tracked metrics still served


def test_locations_are_verified_points():
    locs = get("/api/locations")
    assert len(locs) == 46 and all(-90 <= l["latitude"] <= 90 and -180 <= l["longitude"] <= 180 for l in locs)
    assert "weather_file" not in locs[0]                                             # no local paths exposed
    c = get("/api/locations/3/climate")
    assert c["kind"] == "historical" and [m["month"] for m in c["months"]] == list(range(1, 13))
    get("/api/locations/46/climate", 404)
    act = get("/api/locations/activity", crop="Onion")
    assert len(act) == 46 and sum(a["mandi_records"] is not None for a in act) == 42
    assert all(a["year"] == d.LATEST_FULL_YEAR for a in act) and "weather_file" not in act[0]


def test_no_endpoint_exposes_restricted_data_and_all_are_read_only():
    before = {p: file_sha256(p) for p in SOURCES}
    bodies = all_responses()
    text = json.dumps(bodies)
    # no 2023+ dates in the data, except the OSM snapshot / retrieval stamps of the routing inputs
    data_only = json.dumps({k: v for k, v in bodies.items() if k not in ("routes", "warehouses", "warehouse_list", "route_nodes")})
    assert not re.search(r"20(2[3-9]|[3-9]\d)-\d\d-\d\d", data_only)
    assert not re.search(r"[A-Za-z]:\\|bda-env|AppData", text)                         # no local paths
    assert not re.search(r"holdout", json.dumps({k: v for k, v in bodies.items() if k != "about"}))
    prod_years = {r.get("source_apy_year") for r in bodies["production"]["rows"]} - {None}
    assert bodies["production"]["year"] <= d.DESIGN_END and not prod_years & set(d.RESERVED)
    assert before == {p: file_sha256(p) for p in SOURCES}
