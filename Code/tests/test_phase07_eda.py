"""
Phase 7 EDA tests: synthetic checks of the summary functions + reconciliation of the real EDA
tables with the Phase 6 feature files. Real-output tests are skipped until run_eda() has run.
"""

import numpy as np
import pandas as pd
import pytest

from Code.eda import analysis as e
from Code.features import pipeline as f6
from Code.cleaning import pipeline as c5

needs_outputs = pytest.mark.skipif(not (e.EDA_DIR / "input_fingerprints.csv").exists(),
                                   reason="run Code/eda/analysis.py:run_eda() first")
CROPS = ["Onion", "Potato", "Wheat"]


def frame(rows):
    """rows: (market, date, modal, arrivals, usable_price, usable_arr, price_flag)."""
    df = pd.DataFrame(rows, columns=["market", "reported_date", f6.MODAL, f6.ARR, "usable_modal_price",
                                     "usable_arrivals", "price_extreme_level"])
    df["reported_date"] = pd.to_datetime(df["reported_date"])
    return df.assign(crop="Onion", state="S", district="D", variety="V", arrivals_extreme_level="none",
                     dup_status="unique")


def test_masks_and_distribution_denominators():
    df = frame([("M", "2010-01-01", 100, 1, True, True, "none"),
                ("M", "2010-01-02", np.nan, 2, False, True, "none"),
                ("M", "2010-01-03", 900, 3, True, True, "review"),
                ("M", "2010-01-04", 5000, 4, False, False, "scale_error_suspected")])
    ms = e.masks(df)
    assert [int(ms[k].sum()) for k in ["all_rows", "price_present", "usable_price", "usable_price_excl_review"]] == [4, 3, 2, 1]
    d = pd.DataFrame(e.distribution(df, f6.MODAL, ms, ["all_rows", "usable_price"], "Onion")).set_index("sample")
    assert d.loc["all_rows", "rows_in_sample"] == 4 and d.loc["all_rows", "non_missing"] == 3   # NaN not dropped silently
    assert d.loc["usable_price", "p50"] == 500


def test_seasonal_index_removes_level_and_needs_min_obs():
    days = pd.date_range("2010-01-01", "2010-12-31")
    rows = [("A", d, (200 if d.month == 6 else 100), 1, True, True, "none") for d in days]
    rows += [("B", d, (2000 if d.month == 6 else 1000), 1, True, True, "none") for d in days]   # 10x level
    rows += [("C", d, 1e6, 1, True, True, "none") for d in days[:5]]                           # too few obs
    df = frame(rows)
    s = e.seasonal_index(df, e.masks(df)["usable_price"], f6.MODAL, "Onion", "usable_price").set_index("month")
    assert s.loc[6, "median_rel"] == 2.0 and s.loc[1, "median_rel"] == 1.0                   # same pattern, any level
    assert s["rows"].sum() == 2 * len(days)                                                    # C excluded (< 20 obs)
    assert list(s.index) == list(range(1, 13))


def test_within_series_correlation_never_mixes_series():
    days = pd.date_range("2010-01-01", periods=80)
    rows = [("A", d, 100 + i, 50 - i, True, True, "none") for i, d in enumerate(days)]      # perfectly negative
    rows += [("B", d, 1000 + i, 10 + i, True, True, "none") for i, d in enumerate(days)]    # perfectly positive
    df = frame(rows)
    r = e.within_series_spearman(df, e.masks(df)["usable_price"], f6.MODAL, f6.ARR)
    assert sorted(r.round(6).tolist()) == [-1.0, 1.0]


def test_horizon_feasibility_hand_case():
    df = frame([("M", "2010-01-01", 1, 1, True, True, "none"), ("M", "2010-01-02", 1, 1, True, True, "none"),
                ("M", "2010-01-09", 1, 1, True, True, "none")])
    h = e.horizon_feasibility(df, "Onion", horizons=(1, 7), tol=1).set_index("horizon_days")
    assert h.loc[1, "share_exact_day_observed"] == pytest.approx(1 / 3)      # only 01-01 -> 01-02
    assert h.loc[7, "share_exact_day_observed"] == pytest.approx(1 / 3)      # only 01-02 -> 01-09
    assert h.loc[7, "share_observed_within_pm1d"] == pytest.approx(2 / 3)    # 01-01 -> 01-08 ~ 01-09


def test_weekly_feasibility_crosses_year_boundary():
    # Mon 2012-12-24 week, Wed 2013-01-02 (next week, new year), nothing two weeks later
    df = frame([("M", "2012-12-24", 1, 1, True, True, "none"), ("M", "2013-01-02", 1, 1, True, True, "none"),
                ("M", "2013-01-03", 1, 1, True, True, "none")])
    w = e.weekly_feasibility(df, "Onion", horizons=(1, 2)).set_index("horizon_weeks")
    assert w.loc[1, "origin_series_weeks"] == 2                                # two distinct weeks
    assert w.loc[1, "share_target_week_observed"] == 0.5 and w.loc[2, "share_target_week_observed"] == 0


def test_split_evidence_counts_earlier_history_by_calendar_year():
    df = frame([("A", "2010-05-01", 1, 1, True, True, "none"), ("A", "2011-05-01", 1, 1, True, True, "none"),
                ("B", "2011-06-01", 1, 1, True, True, "none")])
    df["wx_rain_sum_30d"] = [1.0, np.nan, np.nan]
    df["apy_production_tonnes_lag2"] = np.nan
    s = e.split_evidence(df, "Onion").set_index("year")
    assert s.loc[2011, "series_active"] == 2 and s.loc[2011, "series_with_earlier_history"] == 1
    assert s.loc[2010, "share_rows_with_weather_features"] == 1.0


# ---------------------------------------------------------------- real outputs
@needs_outputs
def test_inputs_unchanged():
    m6 = pd.read_csv(f6.AUDIT_DIR / "output_manifest.csv").set_index("file")
    for crop in CROPS:
        name = f"features_{crop.lower()}.parquet"
        assert f6.frame_fingerprint(pd.read_parquet(f6.FEATURE_DIR / name)) == m6.loc[name, "content_sha256"]
    assert pd.read_csv(e.EDA_DIR / "input_fingerprints.csv")["unchanged"].all()


@needs_outputs
@pytest.mark.parametrize("crop", CROPS)
def test_summaries_reconcile_with_feature_tables(crop):
    df = pd.read_parquet(f6.FEATURE_DIR / f"features_{crop.lower()}.parquet",
                         columns=f6.SERIES + ["reported_date", f6.MODAL, f6.ARR, "usable_modal_price", "usable_arrivals",
                                              "price_extreme_level", "arrivals_extreme_level", "dup_status"])
    ms = e.masks(df)
    sd = pd.read_csv(e.EDA_DIR / "sample_definitions.csv").query("crop == @crop").set_index("sample")
    for s, m in ms.items():
        assert sd.loc[s, "rows"] == m.sum(), s
    se = pd.read_csv(e.EDA_DIR / "series_summary.csv").query("crop == @crop")
    assert se["rows"].sum() == len(df) and se["usable_price_rows"].sum() == ms["usable_price"].sum()
    assert len(se) == df.groupby(f6.SERIES, observed=True).ngroups
    y = pd.read_csv(e.EDA_DIR / "yearly_profile.csv").query("crop == @crop")
    assert y.query("sample == 'usable_price'")["rows"].sum() == ms["usable_price"].sum()
    assert set(y["year"]) == set(df["reported_date"].dt.year)
    dist = pd.read_csv(e.EDA_DIR / "distribution_summary.csv").query("crop == @crop and sample == 'price_present'")
    assert dist["rows_in_sample"].item() == df[f6.MODAL].notna().sum()
    conf = pd.read_csv(e.EDA_DIR / "conflict_distribution.csv").query("crop == @crop")["conflict_rows"].sum()
    assert conf == (df["dup_status"] == "conflict_unresolved").sum()                 # conflicts kept visible


@needs_outputs
def test_conflicts_and_flags_match_phase5_audit():
    q = pd.read_csv(e.EDA_DIR / "quality_readiness.csv")
    conf = q[q["metric"] == "conflict_unresolved rows"].set_index("crop")["value"].astype(int)
    s5 = pd.read_csv(c5.AUDIT_DIR / "cleaning_summary.csv").query("rule_id == 'R03'").set_index("crop")["affected_rows"]
    assert (conf.sort_index() == s5.sort_index()).all() and conf.sum() == 338
    miss = q[q["metric"].str.startswith("missing % (predictor)")]
    assert miss["denominator"].str.startswith("all ").all() and miss["value"].astype(float).between(0, 100).all()


@needs_outputs
def test_seasonal_and_horizon_tables_are_complete():
    s = pd.read_csv(e.EDA_DIR / "seasonal_index.csv")
    assert (s.groupby(["crop", "variable", "sample"])["month"].apply(sorted).apply(lambda m: m == list(range(1, 13)))).all()
    h = pd.read_csv(e.EDA_DIR / "horizon_feasibility.csv")
    assert set(h["horizon_days"]) == {1, 7, 14, 30} and h["share_exact_day_observed"].between(0, 1).all()
