"""
Phase 9 arrivals quality screen (proposed AQ-1) and arrivals bootstrap tests. Synthetic data only; the
screen must classify known cases, never modify its input, and respect the Phase 9 cutoff.
"""

import numpy as np
import pandas as pd
import pytest

from Code.modelling import arrivals as ar
from Code.modelling import arrivals_quality as aq
from Code.modelling import dataset as m
from Code.tests.test_phase09_arrivals import daily_arr


def series(values, start="2019-01-07", every=7, market="M"):
    """One reported day per week (Mondays) with the given arrivals."""
    df = daily_arr(start, every * len(values), market=market).iloc[::every].reset_index(drop=True)
    df["arrivals_tonnes"] = [float(v) for v in values]
    return df


def cls(df):
    return aq.screen(df).set_index("reported_date")["aq1_class"]


def test_isolated_thousandfold_spike_is_a_likely_unit_error():
    vals = [10] * 8 + [10_000] + [10] * 6
    c = cls(series(vals))
    assert c.iloc[8] == "likely_unit_error" and (c.drop(c.index[8]).iloc[4:] == "ok").all()


def test_tiny_value_among_normal_ones_is_a_low_unit_error():
    c = cls(series([50] * 8 + [0.05] + [50] * 6))
    assert c.iloc[8] == "likely_unit_error_low"


def test_sustained_level_change_is_not_called_an_error():
    c = cls(series([10] * 8 + [500] * 8))
    assert c.iloc[8] == "sustained_shift" and "likely_unit_error" not in set(c)


def test_moderate_reverting_spike_is_isolated_spike_and_short_history_is_unscreenable():
    c = cls(series([10] * 8 + [300] + [10] * 6))
    assert c.iloc[8] == "isolated_spike"
    assert (c.iloc[:4] == "unscreenable").all()          # fewer than 4 earlier reported weeks


def test_reference_is_not_inflated_by_an_earlier_error():
    # Phase 5's past-peak rule would let the second error pass (the first raises the peak); AQ-1 does not
    c = cls(series([10] * 8 + [10_000] + [10] * 3 + [9_000] + [10] * 6))
    assert c.iloc[8] == "likely_unit_error" and c.iloc[12] == "likely_unit_error"


def test_error_at_the_start_of_a_series_is_caught_by_the_forward_check_only():
    # like Faridkot 2002-12-13: an inflated first record has no history, but the following weeks are normal
    c = cls(series([100_000] + [10] * 10))
    assert c.iloc[0] == "likely_unit_error_forward_only" and (c.iloc[1:4] == "unscreenable").all()
    assert cls(series([0.01] + [10] * 10)).iloc[0] == "likely_unit_error_forward_only"


def test_placeholder_like_tiny_values_are_marked_and_low_side_signature_detected():
    s = aq.screen(series([100] * 8 + [0.1] + [100] * 6)).set_index("reported_date")
    assert s["aq1_class"].iloc[8] == "likely_unit_error_low" and bool(s["tiny_value"].iloc[8])
    assert bool(s["unit_factor_signature"].iloc[8])            # 0.1 / 100 = 1/1000


def test_unit_factor_signature_marks_power_of_ten_ratios():
    s = aq.screen(series([10] * 8 + [1000] + [10] * 6, every=7)).set_index("reported_date")
    assert bool(s["unit_factor_signature"].iloc[8])


def test_screen_never_modifies_input_and_respects_the_cutoff():
    df = series([10] * 120, start="2018-06-04")             # runs to 2020-08; extend past the cutoff below
    late = series([10] * 30 + [1e6], start="2021-01-04")
    both = pd.concat([df, late], ignore_index=True)
    before = both.copy()
    s = aq.screen(both)
    pd.testing.assert_frame_equal(both, before)
    assert s["reported_date"].max() <= ar.CUTOFF and len(s) == len(df)


# ---------------------------------------------------------------- bootstrap
def preds(n_series=40, gain=0.0, years=("val_2019", "val_2020")):
    rng = np.random.default_rng(0)
    rows = []
    for s in range(n_series):
        for period in years:
            for _ in range(5):
                y = 50.0 + s
                pers = y * np.exp(0.3 + rng.normal(0, 0.02))
                cand = y * np.exp(0.3 - gain + rng.normal(0, 0.02))
                rows.append({"crop": "Wheat", "horizon_weeks": 4, "period": period, "state": "S", "district": f"D{s % 5}",
                             "market": f"M{s}", "variety": "V", "y": y, "persistence": pers,
                             "calendar_adjusted_persistence": cand})
    return pd.DataFrame(rows)


def test_identical_candidate_gives_zero_and_a_known_gain_is_detected():
    p = preds()
    z = ar.bootstrap_log_mae(p.assign(calendar_adjusted_persistence=p["persistence"]), b=200)
    assert (z["log_mae_improvement"] == 0).all() and (z["ci_low"] == 0).all() and (z["ci_high"] == 0).all()
    r = ar.bootstrap_log_mae(preds(gain=0.1), b=500)
    s = r[(r["cluster"] == "series") & (r["period"] == "val_2019")].iloc[0]
    assert s["verdict"] == "better" and s["ci_low"] <= s["log_mae_improvement"] <= s["ci_high"]
    assert s["log_mae_improvement"] == pytest.approx(0.1, abs=0.02)


def test_bootstrap_is_reproducible_and_separates_years():
    a, b = ar.bootstrap_log_mae(preds(gain=0.05), b=300), ar.bootstrap_log_mae(preds(gain=0.05), b=300)
    pd.testing.assert_frame_equal(a, b)
    s = a[a["cluster"] == "series"].set_index("period")
    assert s.loc["val_2019", "n_obs"] + s.loc["val_2020", "n_obs"] == s.loc["val_combined", "n_obs"]
    assert a[a["cluster"] == "market"]["n_clusters"].max() == 40


def test_bootstrap_requires_paired_rows_and_enough_clusters():
    p = preds()
    with pytest.raises(m.ModellingError, match="identical rows"):
        ar.bootstrap_log_mae(p.assign(calendar_adjusted_persistence=np.where(p.index == 0, np.nan, p["persistence"])), b=10)
    few = ar.bootstrap_log_mae(preds(n_series=10), b=10)
    assert (few["verdict"] == "too_few_clusters").all()
