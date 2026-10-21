"""
Phase 6 feature tests: hand-calculated synthetic cases + checks on the real feature outputs.
Real-output tests are skipped until Code/features/pipeline.py:run_features() has run.
"""

import numpy as np
import pandas as pd
import pytest

from Code.cleaning import pipeline as c5
from Code.features import pipeline as f6
from Code.integration import pipeline as p4

needs_outputs = pytest.mark.skipif(not (f6.AUDIT_DIR / "output_manifest.csv").exists(),
                                   reason="run Code/features/pipeline.py:run_features() first")
CROPS = ["Onion", "Potato", "Wheat"]
D0 = pd.Timestamp("2010-03-01")
EMPTY_WX = pd.DataFrame(columns=["weather_state", "weather_district", "reported_date"]).astype(
    {"reported_date": "datetime64[ns]"})
EMPTY_APY = f6.apy_lag_table(pd.DataFrame(columns=["crop", "state", "district", "apy_year", "production_tonnes",
                                                   "area_ha", "yield_t_per_ha"]), "Onion")


def mk(rows):
    """rows: (source_row, market, day_offset, modal, arrivals[, usable_modal, usable_arrivals])."""
    recs = []
    for r in rows:
        sr, m, off, modal, arr = r[:5]
        um = r[5] if len(r) > 5 else True
        ua = r[6] if len(r) > 6 else True
        recs.append({"source_row": sr, "crop": "Onion", "state": "S", "district": "D", "market": m,
                     "variety": "V", "commodity_group": "G", "reported_date": D0 + pd.Timedelta(days=off),
                     "market_code": 1, f6.MODAL: modal, f6.MIN: modal - 10, f6.MAX: modal + 10, f6.ARR: arr,
                     "usable_modal_price": um, "usable_arrivals": ua, "dup_status": "unique",
                     "price_extreme_level": "none", "arrivals_extreme_level": "none",
                     "weather_match": "no_weather_location", "weather_state": None, "weather_district": None,
                     "apy_state": None, "apy_district": None, "apy_year": "2009-2010"})
    return pd.DataFrame(recs)


def feats(rows):
    return f6.build_features(mk(rows), EMPTY_WX, EMPTY_APY).set_index("source_row")


# ---------------------------------------------------------------- hand-calculated
def test_lags_previous_observation_vs_calendar_day():
    f = feats([(0, "M", 0, 100, 1), (1, "M", 2, 110, 2), (2, "M", 3, 121, 3), (3, "M", 9, 133, 4)])
    assert pd.isna(f.loc[0, "modal_prev_obs"])                                   # no history
    assert f.loc[1, "modal_prev_obs"] == 100 and f.loc[1, "modal_prev_obs_days_ago"] == 2
    assert pd.isna(f.loc[1, "modal_lag_1d"])                                     # day 1 not reported
    assert f.loc[2, "modal_lag_1d"] == 110                                       # day 2 reported
    assert f.loc[3, "modal_prev_obs"] == 121 and f.loc[3, "modal_prev_obs_days_ago"] == 6
    assert f.loc[3, "modal_lag_7d"] == 110 and pd.isna(f.loc[3, "modal_lag_1d"])  # exact days only
    assert f.loc[2, "modal_pct_change_prev_obs"] == pytest.approx(0.10)          # 110/100 - 1
    assert f.loc[3, "arrivals_change_prev_obs"] == 1                             # 3 - 2
    assert f.loc[1, "min_price_prev_obs"] == 90 and f.loc[1, "max_price_prev_obs"] == 110


def test_calendar_windows_exclude_today_and_old_observations():
    f = feats([(0, "M", 0, 100, 1), (1, "M", 25, 200, 1), (2, "M", 28, 300, 1), (3, "M", 31, 400, 1)])
    # window for day 31: [day 1, day 31) -> days 25 and 28 only (day 0 is 31 days back)
    assert f.loc[3, "modal_roll30d_count"] == 2 and f.loc[3, "modal_roll30d_mean"] == 250
    assert f.loc[3, "modal_roll7d_count"] == 2                                   # [24, 31)
    assert f.loc[3, "modal_roll90d_count"] == 3 and f.loc[3, "modal_roll90d_median"] == 200
    assert f.loc[3, "modal_roll30d_std"] == pytest.approx(np.std([200, 300], ddof=1))
    assert f.loc[0, "modal_roll90d_count"] == 0 and pd.isna(f.loc[0, "modal_roll90d_mean"])
    assert pd.isna(f.loc[1, "modal_roll90d_std"])                                # std needs >= 2 values


def test_series_boundaries_are_never_crossed():
    f = feats([(0, "A", 0, 100, 1), (1, "B", 1, 999, 9), (2, "A", 2, 120, 2), (3, "B", 3, 888, 8)])
    assert f.loc[2, "modal_prev_obs"] == 100 and f.loc[2, "modal_roll7d_count"] == 1
    assert f.loc[3, "modal_prev_obs"] == 999 and f.loc[3, "arrivals_prev_obs"] == 9
    assert pd.isna(f.loc[1, "modal_prev_obs"])


def test_unsorted_input_gives_identical_features():
    rows = [(i, "AB"[i % 2], (i * 7) % 23, 100 + i, 1 + i) for i in range(30)]
    a = feats(rows)
    b = feats(list(reversed(rows)))
    pd.testing.assert_frame_equal(a.sort_index(), b.sort_index())


def test_ineligible_rows_and_same_day_conflicts_never_enter_history():
    f = feats([(0, "M", 0, 100, 1),
               (1, "M", 1, 5000, 500, False, False),        # unusable (e.g. suspected scale/entry error)
               (2, "M", 2, 150, 2, False, False),           # conflict pair on day 2 (both unusable)
               (3, "M", 2, 170, 2, False, False),
               (4, "M", 3, 120, 3)])
    assert f.loc[4, "modal_prev_obs"] == 100 and f.loc[4, "modal_roll7d_count"] == 1
    assert f.loc[4, "arrivals_prev_obs"] == 1 and pd.isna(f.loc[4, "modal_lag_1d"])
    assert f.loc[3, "modal_prev_obs"] == 100                 # its same-day twin is not history
    assert f.loc[1, "modal_prev_obs"] == 100                 # ineligible rows still receive features


def test_targets_and_future_values_cannot_leak():
    rows = [(i, "M", i, 100 + i, 1 + i) for i in range(40)]
    base = feats(rows)
    changed = [(i, "M", i, (1e6 if i >= 20 else 100 + i), (1e6 if i >= 20 else 1 + i)) for i in range(40)]
    alt = feats(changed)
    hist_cols = [c for c in base.columns if c.startswith(("modal_", "arrivals_", "min_price_prev", "max_price_prev"))
                 and c not in (f6.MODAL, f6.ARR)]
    pd.testing.assert_frame_equal(base.loc[:20, hist_cols], alt.loc[:20, hist_cols])  # day 20 itself included


def test_weather_windows_require_full_coverage_and_true_previous_day():
    days = pd.date_range("2001-01-01", periods=12)
    panel = pd.DataFrame({"weather_state": "S", "weather_district": "D", "reported_date": days,
                          **{c: np.arange(12, dtype=float) for c, *_ in f6.WEATHER_SPECS}})
    wx = f6.weather_window_features(panel).set_index("reported_date")
    assert pd.isna(wx.loc["2001-01-01", "wx_rain_prev1d"]) and wx.loc["2001-01-02", "wx_rain_prev1d"] == 0
    assert pd.isna(wx.loc["2001-01-07", "wx_rain_sum_7d"])                    # only 6 prior days
    assert wx.loc["2001-01-08", "wx_rain_sum_7d"] == sum(range(7))            # days 1..7 -> values 0..6
    assert wx["wx_rain_sum_30d"].isna().all()


def test_registry_separates_targets_from_predictors():
    reg = f6.feature_registry()
    pred = set(reg.loc[reg["role"] == "predictor", "feature"])
    for bad in ["source_row", "reported_date", f6.MODAL, f6.ARR, "usable_modal_price", "dup_status",
                "price_extreme_level", "temperature_2m_mean"]:
        assert bad not in pred
    assert set(reg.loc[reg["role"] == "target", "feature"]) == {f6.MODAL, f6.MIN, f6.MAX, f6.ARR}
    assert not reg["feature"].duplicated().any()
    with pytest.raises(f6.FeatureError):
        f6.build_features(feats([(0, "M", 0, 100, 1)]).reset_index(), EMPTY_WX, EMPTY_APY)


# ---------------------------------------------------------------- real outputs
@needs_outputs
def test_phase4_and_phase5_outputs_unchanged():
    m5 = pd.read_csv(c5.AUDIT_DIR / "output_manifest.csv").set_index("file")
    for crop in CROPS:
        name = f"mandi_cleaned_{crop.lower()}.parquet"
        assert p4.frame_fingerprint(pd.read_parquet(c5.CLEAN_DIR / name)) == m5.loc[name, "content_sha256"]
    m4 = pd.read_csv(p4.OUT_DIR / "audit" / "output_manifest.csv").set_index("file")
    assert p4.frame_fingerprint(pd.read_parquet(p4.OUT_DIR / "weather_daily_panel.parquet")) == \
        m4.loc["weather_daily_panel.parquet", "content_sha256"]
    assert pd.read_csv(f6.AUDIT_DIR / "input_fingerprints.csv")["unchanged"].all()


@needs_outputs
@pytest.mark.parametrize("crop", CROPS)
def test_feature_table_preserves_rows_and_targets(crop):
    cl = pd.read_parquet(c5.CLEAN_DIR / f"mandi_cleaned_{crop.lower()}.parquet")
    ft = pd.read_parquet(f6.FEATURE_DIR / f"features_{crop.lower()}.parquet")
    assert len(ft) == len(cl) and (ft["source_row"].to_numpy() == cl["source_row"].to_numpy()).all()
    assert set(ft["crop"].astype(str)) == {crop}
    for col in [f6.MODAL, f6.MIN, f6.MAX, f6.ARR, "reported_date", "usable_modal_price", "usable_arrivals"]:
        pd.testing.assert_series_equal(ft[col], cl[col], check_names=False)
    reg = f6.feature_registry()
    assert set(ft.columns) <= set(reg["feature"].str.split(" / ").explode())
    first = ft.groupby(f6.SERIES, observed=True)["reported_date"].transform("min") == ft["reported_date"]
    assert ft.loc[first, "modal_prev_obs"].isna().all()                    # no history on a series' first day
    sc = f6.spot_check(ft, cl, n=100, seed=7)
    assert sc["match"].all(), sc[~sc["match"]].head()


@needs_outputs
def test_validation_report_all_passed():
    v = pd.read_csv(f6.AUDIT_DIR / "validation_report.csv")
    assert v["passed"].all() and set(v["crop"]) == set(CROPS) | {"all"}


@needs_outputs
def test_rerun_is_reproducible(tmp_path):
    f6.run_features(feature_dir=tmp_path / "f", audit_dir=tmp_path / "a", crops=["Wheat"])
    a = pd.read_csv(tmp_path / "a" / "output_manifest.csv").set_index("file")
    b = pd.read_csv(f6.AUDIT_DIR / "output_manifest.csv").set_index("file")
    assert a.loc["features_wheat.parquet", "content_sha256"] == b.loc["features_wheat.parquet", "content_sha256"]
