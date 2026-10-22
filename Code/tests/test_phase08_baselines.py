"""
Phase 8 baseline tests: hand-calculated metrics, seasonal-naive lookup, next-observation scoring,
and the guarantee that the 2021-2022 test and 2023-24 holdout periods are never scored.
"""

import numpy as np
import pandas as pd
import pytest

from Code.modelling import baselines as b
from Code.modelling import dataset as m
from Code.tests.test_phase08_dataset import REG, build, daily

needs_outputs = pytest.mark.skipif(not (m.MODEL_DATA_DIR / "baseline_validation_metrics.csv").exists(),
                                   reason="run Code/modelling/baselines.py:run_baselines() first")


def test_metrics_hand_calculated():
    r = b.metrics(pd.Series([100.0, 200.0]), pd.Series([110.0, 180.0]))
    assert r["n"] == 2 and r["mae"] == 15 and r["rmse"] == pytest.approx(np.sqrt(250)) and r["mape_pct"] == pytest.approx(10)


def test_persistence_and_seasonal_naive_use_only_past_weeks():
    by_h, origins = build(daily("2017-01-02", 171 * 7))        # whole weeks; daily price rises by 1 each day
    ex = by_h[2]
    ev = b.validation_only(ex)
    s = b.seasonal_naive(ev, origins)
    o = origins.set_index("week_start")["origin_week_median"]
    want = (ev["target_week_start"] - pd.Timedelta(weeks=52)).map(o)
    pd.testing.assert_series_equal(s, want, check_names=False)
    assert ((ev["target_week_start"] - pd.Timedelta(weeks=52)) < ev["week_start"]).all()
    # a linear trend of +1/day: persistence misses by exactly 7*h days of drift on the weekly medians
    res = b.evaluate_weekly(ex, origins, "Onion", 2)
    p = res[(res["baseline"] == "persistence") & (res["period"] == "val_combined") & (res["experiment"] == "primary")
            & (res["population"] == "origin_eligible")].iloc[0]
    assert p["mae"] == pytest.approx(14)


def test_test_and_holdout_periods_are_never_scored():
    by_h, origins = build(daily("2017-01-02", 2300))           # runs into 2023
    ex = by_h[1]
    assert {"test", "holdout_no_weather"} <= set(ex["period"])
    res = b.evaluate_weekly(ex, origins, "Onion", 1)
    assert set(res["period"]) == {"val_2019", "val_2020", "val_combined"}
    with pytest.raises(m.ModellingError, match="no validation"):
        b.validation_only(ex[ex["period"] == "test"])


def test_validation_years_reported_separately_and_combined():
    by_h, origins = build(daily("2017-01-02", 1500))
    res = b.evaluate_weekly(by_h[1], origins, "Onion", 1)
    p = res[(res["baseline"] == "persistence") & (res["experiment"] == "primary") & (res["population"] == "origin_eligible")]
    n = p.set_index("period")["n"]
    assert n["val_2019"] + n["val_2020"] == n["val_combined"] and n["val_2019"] > 0 and n["val_2020"] > 0


def test_next_observation_baseline():
    by_h, origins = build(daily("2017-01-02", 1500))
    r = b.evaluate_next_obs(origins, pd.Timestamp("2021-02-09"), "Onion").set_index("period")
    # anchor = Sunday price, next obs = Monday price, +1 per day
    assert r.loc["val_combined", "mae"] == pytest.approx(1) and r.loc["val_combined", "median_days_ahead"] == 1


@needs_outputs
def test_real_baseline_tables_cover_validation_only():
    w = pd.read_csv(m.MODEL_DATA_DIR / "baseline_validation_metrics.csv")
    assert set(w["period"]) == {"val_2019", "val_2020", "val_combined"}
    assert set(w["crop"]) == {"Onion", "Potato", "Wheat"} and set(w["horizon_weeks"]) == set(m.HORIZONS)
    p = w[(w["baseline"] == "persistence") & (w["experiment"] == "primary") & (w["population"] == "origin_eligible")]
    n = p.pivot_table(index=["crop", "horizon_weeks"], columns="period", values="n")
    assert (n["val_2019"] + n["val_2020"] == n["val_combined"]).all()
