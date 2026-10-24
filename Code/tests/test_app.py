"""
Data-layer tests: the read-only loaders (Code/app/data.py) behind the FastAPI service, on the real frozen outputs,
their boundaries, and the headline numbers the API serves. UI behaviour is tested in frontend/src/test/.
"""

import re
from pathlib import Path

import pandas as pd
import pytest

from Code.app import data as d
from Code.integration.pipeline import file_sha256

API = Path("Code/api/main.py")
UI = Path("frontend/src")
SOURCES = [d.PRICE_FILE, d.M8 / "hgb_conservative_validation_metrics.csv", d.M8 / "test_results.csv",
           d.M9 / "candidate_predictions.parquet", d.M9 / "candidate_selection.csv",
           d.M9 / "test_2021_2022" / "test_predictions.parquet", d.M9 / "test_2021_2022" / "test_metrics.csv",
           d.PC / "production_context_v1.csv", d.PC / "output_manifest.csv", d.BD / "weekly_state_spark.csv",
           d.BD / "top_districts_spark.csv", d.LOCATIONS]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in SOURCES), reason="frozen outputs not present locally")


def test_price_loaders_filter_and_stay_in_validation():
    s = d.price_series("Potato", 2)
    assert list(s.columns) == d.SERIES + ["origins"] and 0 < len(s) <= 200 and s["origins"].is_monotonic_decreasing
    p = d.price_predictions("Potato", 2, tuple(s.iloc[0][d.SERIES]))
    assert list(p.columns) == ["origin_date", "period", "observed", "persistence", "hgb_conservative"]
    assert set(p["period"]) <= d.PRICE_PERIODS and p["origin_date"].max() <= d.PRICE_LAST_ORIGIN
    assert len(p) == s.iloc[0]["origins"]


def test_arrivals_loaders_filter_and_periods():
    s = d.arrivals_series("Onion", 4)
    a = d.arrivals_predictions("Onion", 4, tuple(s.iloc[0][d.SERIES]))
    assert set(a["period"]) <= d.ARRIVAL_PERIODS and {"test_2021", "test_2022"} & set(a["period"])
    assert (a.loc[a["period"].str.startswith("test"), "period"].value_counts().sum()) == s.iloc[0]["test_weeks"]


def test_production_values_only_in_design_window_and_reserved_counts_match_manifest():
    p = d.production_design()
    assert p["source_apy_year"].max() == d.DESIGN_END and not p["source_apy_year"].isin(d.RESERVED).any()
    assert len(p) == 27531
    r = d.production_reserved_counts()
    assert set(r["source_apy_year"]) == set(d.RESERVED) and "production_tonnes" not in r.columns
    assert int(r.drop(columns=["crop", "source_apy_year"]).to_numpy().sum()) == 4163


def test_numbers_shown_by_the_app_come_from_the_sources():
    """The headline facts hold in the source files, and the API / UI compute them instead of hard-coding them."""
    src = API.read_text(encoding="utf-8")
    ui = " ".join(f.read_text(encoding="utf-8") for f in UI.rglob("*.tsx") if "test" not in f.parts)
    test = d.price_metrics()["test"]
    onion = test[(test["crop"] == "Onion") & (test["horizon_weeks"] == 1)]
    assert (onion["approach"] == "hgb_conservative").all()
    assert onion.loc[onion["period"] == "test_combined", "rel_mae_improvement_pct"].item() < 0      # model was worse
    assert int((test.drop_duplicates(["crop", "horizon_weeks"])["approach"] == "persistence").sum()) == 8
    t = d.arrivals_metrics()["test"]
    cells = t[(t["population"] == "primary") & (t["period"] != "test_combined")]["rel_log_mae_improvement_pct"]
    assert len(cells) == 18 and (cells > 0).all()
    assert "rel_mae_improvement_pct" in src and "rel_log_mae_improvement_pct" in src
    assert not re.search(r"\b18 of 18\b|\b2\.3[–-]13\.5|\b[18] of 9\b", src + ui)   # computed, never typed in


def test_market_history_and_locations_stay_historical_and_verified():
    ws = d.weekly_state()
    assert ws["week_start"].max() <= d.SPARK_END and set(ws["crop"]) == set(d.CROPS)
    s = d.state_year_summary(ws, "Onion")
    mh = ws[(ws["crop"] == "Onion") & (ws["state"] == "Maharashtra") & (ws["agri_year"] == d.LATEST_FULL_YEAR)]
    row = s[(s["state"] == "Maharashtra") & (s["agri_year"] == d.LATEST_FULL_YEAR)].iloc[0]
    assert row["arrivals_tonnes"] == pytest.approx(mh["arrivals_tonnes_sum"].sum())
    assert row["typical_price"] == pytest.approx(mh["modal_price_median"].median()) and row["weeks"] == mh["week_start"].nunique()
    assert d.agri_year(pd.Series(pd.to_datetime(["2019-06-30", "2019-07-01"]))).tolist() == ["2018-2019", "2019-2020"]
    assert d.top_districts()["apy_year"].max() <= d.LATEST_FULL_YEAR
    locs = d.verified_locations()
    assert len(locs) == 46 and locs[["latitude", "longitude"]].notna().all().all()
    clim = d.location_climate(locs.iloc[0]["weather_file"])
    assert list(clim["month"]) == list(range(1, 13)) and (clim["rain_mm"] >= 0).all()


def test_loaders_are_read_only():
    before = {p: file_sha256(p) for p in SOURCES}
    d.price_metrics(), d.arrivals_metrics(), d.production_design(), d.production_reserved_counts(), d.bigdata()
    d.weekly_state(), d.top_districts(), d.location_climate(d.verified_locations().iloc[0]["weather_file"])
    assert before == {p: file_sha256(p) for p in SOURCES}
    for f in [API, Path("Code/app/data.py")]:
        s = f.read_text(encoding="utf-8")
        assert not re.search(r"\.to_csv\(|\.to_parquet\(|open\([^)]*['\"][wa]", s), f

