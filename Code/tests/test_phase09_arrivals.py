"""
Phase 9 arrivals tests: weekly target construction, gaps-are-not-zero, usable-row policy, origin-safe
eligibility, chronology and leakage, holdout separation by input cutoff, training-only fitting, metrics,
the phase9-arrivals-forecast-v1 contract and its key compatibility with phase8-forecast-v1.
"""

import numpy as np
import pandas as pd
import pytest

from Code.integration.pipeline import file_sha256
from Code.modelling import arrivals as ar
from Code.modelling import dataset as m
from Code.modelling import forecast_output as fo
from Code.tests.test_phase08_dataset import REG, build, daily, frame

needs_outputs = pytest.mark.skipif(not (ar.OUT_DIR / "arrivals_baseline_metrics.csv").exists(),
                                   reason="run Code/modelling/arrivals.py:run_arrivals_baselines() first")


def arr_frame(rows, market="M"):
    """rows: (date, arrivals[, usable_arrivals, usable_price])."""
    f = frame([(r[0], 100.0, r[3] if len(r) > 3 else True) for r in rows], market)
    f["arrivals_tonnes"] = [float(r[1]) for r in rows]
    f["usable_arrivals"] = [r[2] if len(r) > 2 else True for r in rows]
    return f


def daily_arr(start, n, market="M", base=10.0):
    t = np.arange(n)
    f = daily(start, n, market=market)
    f["arrivals_tonnes"] = base + 5 * np.sin(2 * np.pi * t / 365.25) * base / 10 + (t * 7 % 5)
    return f


def build_arr(df, **kw):
    by_h, origins = ar.build_arrivals_examples(df, **kw)
    for ex in by_h.values():
        ar.validate_arrivals_examples(ex)
    return by_h, origins


# ---------------------------------------------------------------- target construction
def test_weekly_median_per_reported_day_and_alignment():
    df = arr_frame([("2010-03-03", 4), ("2010-03-07", 6), ("2010-03-08", 10), ("2010-03-09", 30), ("2010-03-12", 20)])
    by_h, o = build_arr(df)
    e = by_h[1].iloc[0]
    assert e["origin_week_median_arrivals"] == 5 and e["origin_week_reported_days"] == 2
    assert e[ar.TARGET] == 20 and e["target_reported_days"] == 3          # median of 10, 30, 20, not the sum 60
    assert e["target_first_date"] > e["origin_date"] == pd.Timestamp("2010-03-07")


def test_gaps_are_not_zero_and_genuine_zeros_are_kept():
    df = arr_frame([("2010-03-03", 5), ("2010-03-17", 0), ("2010-03-24", 8)])   # week of 03-08 unreported
    by_h, _ = build_arr(df)
    assert pd.Timestamp("2010-03-01") not in set(by_h[1]["week_start"])        # no example from a missing target week
    e2 = by_h[2].set_index("week_start").loc[pd.Timestamp("2010-03-01")]
    assert e2[ar.TARGET] == 0                                                 # the reported zero stays zero


def test_unusable_arrivals_never_enter_targets_or_origins():
    df = arr_frame([("2010-03-03", 5), ("2010-03-04", 9e6, False), ("2010-03-10", 7), ("2010-03-11", 9e6, False)])
    by_h, o = build_arr(df)
    assert o["origin_week_median_arrivals"].max() == 7 and by_h[1].iloc[0][ar.TARGET] == 7


def test_eligibility_counts_usable_arrival_dates_up_to_the_origin_even_without_prices():
    df = daily_arr("2010-01-04", 400)
    df["usable_modal_price"] = False                        # arrivals reported, prices not usable
    df["modal_price_rs_per_quintal"] = np.nan
    _, o = build_arr(df)
    o = o.set_index("week_start")
    first = o.index[o["eligible_at_origin"]].min()
    assert o.loc[first, "n_usable_arrival_dates_to_origin"] >= 365 > o.loc[first - pd.Timedelta(weeks=1), "n_usable_arrival_dates_to_origin"]
    assert not o["has_usable_price_in_origin_week"].any()


def test_future_rows_change_neither_origin_features_nor_eligibility():
    base = daily_arr("2016-01-04", 900)
    cut = pd.Timestamp("2017-03-05")
    late = base["reported_date"] > cut
    tampered = base.assign(arrivals_tonnes=base["arrivals_tonnes"].where(~late, 1e7),
                           usable_arrivals=base["usable_arrivals"] & ~(late & (base.index % 2 == 0)))
    cols = ["origin_week_median_arrivals", "origin_week_reported_days", "n_usable_arrival_dates_to_origin",
            "eligible_at_origin", "anchor_date"]
    a = build_arr(base)[1].query("origin_date <= @cut").set_index("week_start")[cols]
    b = build_arr(tampered)[1].query("origin_date <= @cut").set_index("week_start")[cols]
    pd.testing.assert_frame_equal(a, b)


# ---------------------------------------------------------------- separation and leakage
def test_input_cutoff_keeps_test_and_holdout_out_of_every_dataset():
    by_h, o = build_arr(daily_arr("2018-01-01", 2200))      # runs into 2024
    assert o["origin_date"].max() <= ar.CUTOFF
    for ex in by_h.values():
        assert ex["target_sunday"].max() <= ar.CUTOFF and not ex["period"].isin(["test", "holdout_no_weather"]).any()


@pytest.mark.parametrize("tamper", [
    lambda e: e.assign(target_first_date=e["origin_date"]),
    lambda e: e.assign(anchor_date=e["origin_date"] + pd.Timedelta(days=1)),
    lambda e: e.assign(target_week_start=e["target_week_start"] + pd.Timedelta(days=7)),
    lambda e: e.assign(target_sunday=e["target_sunday"] + pd.Timedelta(days=700), target_last_date=e["target_last_date"] + pd.Timedelta(days=700)),
    lambda e: e.assign(eligible_at_origin=True),
    lambda e: e.assign(**{ar.TARGET: -1.0}),
    lambda e: pd.concat([e, e.iloc[[0]]]),
])
def test_injected_leakage_is_rejected(tamper):
    ex = build_arr(daily_arr("2018-01-01", 500))[0][1]
    with pytest.raises(m.ModellingError, match="checks failed"):
        ar.validate_arrivals_examples(tamper(ex))


def test_calendar_factor_is_fitted_on_training_rows_only():
    df = daily_arr("2016-01-04", 1820)
    by_h, o = build_arr(df)
    ex = by_h[1]
    p1, lg = ar.validation_predictions(ex, o, "Onion", 1)
    late = ex["target_first_date"] > pd.Timestamp("2019-06-30")
    p2, _ = ar.validation_predictions(ex.assign(**{ar.TARGET: ex[ar.TARGET].where(~late, ex[ar.TARGET] * 50)}), o, "Onion", 1)
    early = p1.index[ex.loc[p1.index, "origin_date"] < pd.Timestamp("2019-07-07")]
    assert np.allclose(p1.loc[early, "calendar_adjusted_persistence"], p2.loc[early, "calendar_adjusted_persistence"])
    assert (pd.to_datetime(pd.DataFrame(lg)["train_last_target_sunday"]) <= pd.to_datetime(pd.DataFrame(lg)["refit_date"])).all()
    assert set(p1["period"]) == {"val_2019", "val_2020"}


def test_seasonal_naive_uses_the_series_week_52_weeks_back():
    by_h, o = build_arr(daily_arr("2016-01-04", 1820))
    ev = by_h[2][by_h[2]["period"] == "val_2019"]
    s = ar.seasonal_naive(ev, o)
    want = (ev["target_week_start"] - pd.Timedelta(weeks=52)).map(o.set_index("week_start")["origin_week_median_arrivals"])
    assert np.allclose(s, want)


# ---------------------------------------------------------------- metrics
def test_metrics_hand_calculated_and_zero_safe():
    r = ar.metrics(pd.Series([0.0, 10.0]), pd.Series([1.0, 12.0]))
    assert r["mae_t_per_day"] == 1.5 and r["wape_pct"] == pytest.approx(30.0)
    assert r["log_mae"] == pytest.approx((np.log(2) + abs(np.log(13) - np.log(11))) / 2)
    assert np.isnan(ar.metrics(pd.Series([0.0]), pd.Series([1.0]))["wape_pct"])


def test_scores_separate_years_and_segments():
    by_h, o = build_arr(daily_arr("2016-01-04", 1820))
    p, _ = ar.validation_predictions(by_h[1], o, "Onion", 1)
    s = ar.score(p)
    a = s[(s["segment"] == "all") & (s["baseline"] == "persistence")].set_index("period")
    assert a.loc["val_2019", "n"] + a.loc["val_2020", "n"] == a.loc["val_combined", "n"]
    seg = s[(s["segment_type"] == "reporting") & (s["period"] == "val_combined") & (s["baseline"] == "persistence")]
    assert seg["n"].sum() == a.loc["val_combined", "n"]
    assert (s.loc[s["baseline"] == "persistence", "skill_log_mae_vs_persistence"] == 0).all()


# ---------------------------------------------------------------- contract
def test_arrivals_contract_and_key_compatibility_with_price_contract():
    df = daily_arr("2018-01-01", 500)
    last = df["reported_date"].max()
    origin = pd.Timestamp("2019-03-03")
    a = ar.arrivals_forecast_table(build_arr(df)[1], "Potato", origin, last)
    assert list(a.columns) == ar.COLUMNS and ar.KEY == fo.KEY
    assert "not consumer demand" in a["target_definition"].iloc[0] and not a["prediction_interval_available"].any()
    p = fo.forecast_table(build(df)[1].assign(crop="Potato"), "Potato", origin, last)
    j = p.merge(a, on=ar.KEY, how="inner", suffixes=("_price", "_arr"), validate="1:1")
    assert len(j) == len(a) == len(p)
    assert (j["target_week_start_price"] == j["target_week_start_arr"]).all()


@pytest.mark.parametrize("tamper", [
    lambda f: pd.concat([f, f.iloc[[0]]], ignore_index=True),
    lambda f: f.assign(origin_date=f["origin_date"] - pd.Timedelta(days=1)),
    lambda f: f.assign(predicted_median_daily_arrivals_tonnes=-1.0),
    lambda f: f.assign(target_definition="demand"),
    lambda f: f.assign(prediction_interval_available=True),
    lambda f: f.assign(in_primary_population=False),          # the series has > 365 dates by this origin
    lambda f: f.assign(extra=1),
])
def test_arrivals_contract_violations_are_rejected(tamper):
    df = daily_arr("2018-01-01", 500)
    a = ar.arrivals_forecast_table(build_arr(df)[1], "Potato", "2019-03-03", df["reported_date"].max())
    with pytest.raises(m.ModellingError):
        ar.validate_arrivals_forecasts(tamper(a))


# ---------------------------------------------------------------- end to end
def test_run_is_reproducible_and_never_scores_test_or_holdout(tmp_path):
    df = pd.concat([daily_arr("2016-01-04", 2600), daily_arr("2016-01-04", 2600, market="N", base=100.0)
                    .assign(source_row=lambda x: x["source_row"] + 10_000)], ignore_index=True)
    (tmp_path / "f").mkdir()
    path = tmp_path / "f" / "features_onion.parquet"
    df.to_parquet(path, index=False)
    exp = {str(path): file_sha256(path)}
    a = ar.run_arrivals_baselines(tmp_path / "f", tmp_path / "a", ["Onion"], exp)
    b = ar.run_arrivals_baselines(tmp_path / "f", tmp_path / "b", ["Onion"], exp)
    for name in ["arrivals_baseline_metrics", "arrivals_dataset_manifest", "arrivals_sample_counts", "arrivals_refit_log"]:
        assert (tmp_path / "a" / f"{name}.csv").read_bytes() == (tmp_path / "b" / f"{name}.csv").read_bytes()
    assert set(a["arrivals_baseline_metrics"]["period"]) == {"val_2019", "val_2020", "val_combined"}
    assert (pd.to_datetime(a["arrivals_dataset_manifest"]["max_target_sunday"]) <= ar.CUTOFF).all()
    assert file_sha256(path) == exp[str(path)]
    with pytest.raises(m.ModellingError, match="protected"):
        ar.run_arrivals_baselines(tmp_path / "f", m.FEATURE_DIR / "x", ["Onion"], exp)


@needs_outputs
def test_real_outputs_cover_validation_only():
    mt = pd.read_csv(ar.OUT_DIR / "arrivals_baseline_metrics.csv")
    assert set(mt["period"]) == {"val_2019", "val_2020", "val_combined"} and set(mt["crop"]) == {"Onion", "Potato", "Wheat"}
    man = pd.read_csv(ar.OUT_DIR / "arrivals_dataset_manifest.csv")
    assert (pd.to_datetime(man["max_target_sunday"]) <= ar.CUTOFF).all()
    prov = pd.read_csv(ar.OUT_DIR / "arrivals_provenance.csv").set_index("key")["value"]
    assert prov["test_period_scored"] in (False, "False") and prov["holdout_accessed"] in (False, "False")
