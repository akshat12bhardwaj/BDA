"""
Dashboard tests: the read-only data layer (Code/app/data.py) on the real frozen outputs, its boundaries, the numbers
the app states, and a Streamlit AppTest smoke run (skipped when streamlit is not installed, i.e. outside the venv).
"""

import re
from pathlib import Path

import pandas as pd
import pytest

from Code.app import data as d
from Code.integration.pipeline import file_sha256

APP = Path("Code/app/streamlit_app.py")
SOURCES = [d.PRICE_FILE, d.M8 / "hgb_conservative_validation_metrics.csv", d.M8 / "test_results.csv",
           d.M9 / "candidate_predictions.parquet", d.M9 / "candidate_selection.csv",
           d.M9 / "test_2021_2022" / "test_predictions.parquet", d.M9 / "test_2021_2022" / "test_metrics.csv",
           d.PC / "production_context_v1.csv", d.PC / "output_manifest.csv"]
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


def test_production_summary_never_merges_classes():
    s = d.production_summary(d.production_design())
    assert s.groupby(["crop", "source_apy_year", "apy_state"])["annual_comparability"].nunique().max() > 1   # kept apart
    assert not s.duplicated(["crop", "source_apy_year", "annual_comparability", "apy_state"]).any()


def test_numbers_stated_by_the_app_match_the_sources():
    src = APP.read_text(encoding="utf-8")
    test = d.price_metrics()["test"]
    onion = test[(test["crop"] == "Onion") & (test["horizon_weeks"] == 1)]
    assert (onion["approach"] == "hgb_conservative").all()
    assert onion.loc[onion["period"] == "test_combined", "rel_mae_improvement_pct"].item() < 0      # "did worse"
    others = test[~((test["crop"] == "Onion") & (test["horizon_weeks"] == 1))]
    assert (others["approach"] == "persistence").all()
    t = d.arrivals_metrics()["test"]
    cells = t[(t["population"] == "primary") & (t["period"] != "test_combined")]["rel_log_mae_improvement_pct"]
    assert len(cells) == 18 and (cells > 0).all() and "all 18" in src
    lo, hi = map(int, re.search(r"about (\d+)–(\d+)% lower log MAE", src).groups())
    assert lo <= cells.min() and cells.max() < hi + 1


def test_loaders_are_read_only():
    before = {p: file_sha256(p) for p in SOURCES}
    d.price_metrics(), d.arrivals_metrics(), d.production_design(), d.production_reserved_counts(), d.bigdata()
    assert before == {p: file_sha256(p) for p in SOURCES}
    for f in [APP, Path("Code/app/data.py")]:
        s = f.read_text(encoding="utf-8")
        assert not re.search(r"\.to_csv\(|\.to_parquet\(|open\([^)]*['\"][wa]", s), f


def test_app_degrades_gracefully_without_ignored_prediction_files(monkeypatch, tmp_path):
    """A fresh clone has no git-ignored parquet predictions: every tab must still render, with a notice."""
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    for name in ["PRICE_FILE", "ARRIVALS_VAL_FILE", "ARRIVALS_TEST_FILE"]:
        monkeypatch.setattr(d, name, tmp_path / f"absent_{name}.parquet")
    monkeypatch.setattr(d, "PREDICTION_FILES", {"price": [d.PRICE_FILE], "arrivals": [d.ARRIVALS_VAL_FILE, d.ARRIVALS_TEST_FILE]})
    assert len(d.missing_prediction_files("price")) == 1 and len(d.missing_prediction_files("arrivals")) == 2
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 6
    assert sum("not present in this checkout" in w.value for w in at.warning) == 2
    assert any("counts only" in m.value for m in at.markdown)                     # later tabs still rendered


def test_app_runs_every_tab_without_exceptions():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 6
    assert any("counts only" in m.value for m in at.markdown)
    at.selectbox(key="c_crop").select("Potato").run()
    at.selectbox(key="c_year").select("1997-1998").run()
    assert not at.exception and any("R13" in w.value for w in at.warning)
