"""
Phase 8 model tests: calendar benchmarks, row-wise feature preparation, training-only fitting,
refit cutoffs and gaps, origin-safe evaluation, 2019/2020 separation, metrics, selection rule,
and consistency of the real model manifests with the baseline populations.
Synthetic series run into 2022 so that any use of the test period would be detected.
"""

import numpy as np
import pandas as pd
import pytest

from Code.modelling import dataset as m
from Code.modelling import models as mo
from Code.tests.test_phase08_dataset import REG, build, frame

needs_outputs = pytest.mark.skipif(not (m.MODEL_DATA_DIR / "model_validation_metrics.csv").exists(),
                                   reason="run Code/modelling/models.py:run_models() first")
SMALL_RUNS = [("calendar_climatology", "none", "primary"), ("calendar_adjusted_persistence", "none", "primary"),
              ("ridge", "weather", "primary"), ("hgb", "no_weather", "primary"),
              ("ridge", "weather", "review_sensitivity")]


def seasonal(start="2016-01-04", days=2400, level=1000.0, market="M", review_every=0):
    t = np.arange(days)
    price = level * (1 + 0.3 * np.sin(2 * np.pi * t / 365.25)) + t * 0.2 + (t * 37 % 11)
    rows = [(pd.Timestamp(start) + pd.Timedelta(days=int(i)), float(p), True,
             bool(review_every) and i % review_every == 0) for i, p in zip(t, price)]
    return frame(rows, market)


@pytest.fixture(scope="module")
def ex():
    df = pd.concat([seasonal(), seasonal(level=2000.0, market="N", review_every=50)], ignore_index=True)
    df["source_row"] = range(len(df))
    return build(df, horizons=(1,))[0][1]


@pytest.fixture(scope="module")
def preds(ex):
    return mo.validation_predictions(ex, REG, "Onion", 1, SMALL_RUNS)


# ---------------------------------------------------------------- calendar features and benchmarks
def test_calendar_fields_are_known_at_the_origin(ex):
    mid = ex["target_week_start"] + pd.Timedelta(days=3)
    assert (ex["tw_month"] == mid.dt.month).all()
    assert (ex["target_week_start"] == ex["week_start"] + pd.Timedelta(weeks=1)).all()   # fixed by the origin and h
    for cfg in m.CONFIGS:
        assert not any(c.startswith("target_") for c in m.feature_columns(REG, cfg))


def test_calendar_climatology_uses_only_the_target_month(ex):
    tr = ex[ex["target_sunday"] <= "2018-12-30"]
    cal = mo.CalendarClimatology().fit(tr)
    pd.testing.assert_series_equal(cal.by_month, tr.groupby("tw_month")[m.TARGET].median())
    ev = ex[ex["period"] == "val_2019"]
    scrambled = ev.assign(**{c: -1.0 for c in ["origin_week_median", "origin_week_last", m.TARGET]})
    assert np.array_equal(cal.predict(ev), cal.predict(scrambled))


def test_calendar_adjusted_persistence_is_last_median_times_training_monthly_change(ex):
    tr = ex[ex["target_sunday"] <= "2018-12-30"]
    c = mo.CalendarAdjustedPersistence().fit(tr)
    ev = ex[ex["period"] == "val_2019"].head(5)
    want = ev["origin_week_median"] * np.exp(ev["tw_month"].map(np.log(tr[m.TARGET] / tr["origin_week_median"]).groupby(tr["tw_month"]).median()))
    assert np.allclose(c.predict(ev), want)


# ---------------------------------------------------------------- features and fitting
def test_design_matrix_is_row_wise_and_scale_free(ex):
    cols = m.feature_columns(REG, "weather")
    X = mo.design_matrix(ex, cols)
    one = mo.design_matrix(ex.iloc[[7]], cols)
    pd.testing.assert_frame_equal(X.iloc[[7]], one)
    assert np.allclose(X["origin_week_last"], ex["origin_week_last"] / ex["origin_week_median"])
    assert np.allclose(X["origin_week_median"], np.log(ex["origin_week_median"]))
    assert X.filter(like="imd_season_").sum(axis=1).eq(1).all()
    assert not set(X.columns) & (set(m.RESERVED) | set(m.META) | {m.TARGET})


def test_preprocessing_is_fitted_on_training_rows_only(ex):
    cols = m.feature_columns(REG, "weather")
    tr = m.training_examples(ex, "2018-10-07")
    model = mo.Tabular("ridge", cols).fit(tr)
    imputer = model.model.named_steps["simpleimputer"]
    assert np.allclose(imputer.statistics_, mo.design_matrix(tr, cols).median().to_numpy(), equal_nan=True)


def test_future_targets_cannot_change_any_validation_prediction(ex, preds):
    p, _ = preds
    # inflate every target dated after 2019-06-30 (incl. all of 2020-2022): earlier predictions must not move
    late = ex["target_first_date"] > pd.Timestamp("2019-06-30")
    p2, _ = mo.validation_predictions(ex.assign(**{m.TARGET: ex[m.TARGET].where(~late, ex[m.TARGET] * 10)}),
                                      REG, "Onion", 1, SMALL_RUNS)
    early = p["refit_date"] <= pd.Timestamp("2019-04-07")       # refits whose training ends before the change
    assert np.allclose(p.loc[early, "yhat"], p2.loc[early, "yhat"])


# ---------------------------------------------------------------- refits, gaps, eligibility, periods
def test_refit_log_respects_cutoffs_gaps_and_never_reaches_the_test_period(ex, preds):
    p, lg = preds
    assert (pd.to_datetime(lg["train_last_target_sunday"]) <= pd.to_datetime(lg["refit_date"])).all()
    assert (pd.to_datetime(lg["train_last_target_sunday"]) <= mo.VAL_LAST_TARGET).all()
    assert set(p["period"]) == {"val_2019", "val_2020"}           # test-period rows exist in ex but are never scored
    assert {"test"} <= set(ex["period"])
    origin = ex.loc[p["row"], "origin_date"].to_numpy()
    assert (p["refit_date"].to_numpy() <= origin).all()


def test_only_origin_eligible_rows_are_evaluated_and_training_uses_refit_eligibility(ex, preds):
    p, lg = preds
    assert ex.loc[p["row"], "eligible_at_origin"].all()
    first = lg[lg["model"] == "ridge"].iloc[0]
    assert first["n_train"] == len(m.training_examples(ex, first["refit_date"]))


def test_review_sensitivity_drops_review_targets_from_training_and_evaluation(ex, preds):
    p, lg = preds
    s = p[p["experiment"] == "review_sensitivity"]
    assert not ex.loc[s["row"], "target_has_review"].any() and ex.loc[p["row"], "target_has_review"].any()
    prim = lg[(lg["model"] == "ridge") & (lg["experiment"] == "primary")]["n_train"].to_numpy()
    sens = lg[(lg["model"] == "ridge") & (lg["experiment"] == "review_sensitivity")]["n_train"].to_numpy()
    assert (sens < prim).all()


def test_scores_separate_2019_and_2020_and_use_identical_rows_for_persistence(preds):
    p, _ = preds
    s = mo.score(p)
    r = s[(s["model"] == "ridge") & (s["experiment"] == "primary") & (s["subset"] == "all")].set_index("period")
    assert r.loc["val_2019", "n"] + r.loc["val_2020", "n"] == r.loc["val_combined", "n"]
    g = p[(p["model"] == "ridge") & (p["experiment"] == "primary") & (p["period"] == "val_2019")]
    assert r.loc["val_2019", "mae"] == pytest.approx((g["yhat"] - g["y"]).abs().mean())
    assert r.loc["val_2019", "skill_mae_vs_persistence"] == pytest.approx(
        1 - r.loc["val_2019", "mae"] / (g["persistence"] - g["y"]).abs().mean())


def test_selection_requires_beating_persistence_in_both_years():
    rows = []
    for model, s19, s20 in [("one_year_wonder", 0.50, -0.05), ("steady", 0.05, 0.04), ("worse", -0.1, -0.1)]:
        for period, sk in [("val_2019", s19), ("val_2020", s20), ("val_combined", (s19 + s20) / 2)]:
            rows.append({"crop": "Onion", "horizon_weeks": 1, "model": model, "config": "weather", "experiment": "primary",
                         "subset": "all", "period": period, "skill_mae_vs_persistence": sk})
    sel = mo.select_models(pd.DataFrame(rows)).iloc[0]
    assert sel["proposed"] == "steady (weather)" and sel["candidates_beating_persistence_both_years"] == 1
    none = mo.select_models(pd.DataFrame([r for r in rows if r["model"] != "steady"])).iloc[0]
    assert none["proposed"] == "persistence"


def test_conservative_hgb_is_more_regularized_and_control_is_unchanged():
    ctrl, cons = mo.LEARNERS["hgb"]().get_params(), mo.LEARNERS["hgb_conservative"]().get_params()
    assert (ctrl["learning_rate"], ctrl["max_leaf_nodes"], ctrl["min_samples_leaf"], ctrl["l2_regularization"]) == (0.1, 31, 100, 1.0)
    assert cons["learning_rate"] < ctrl["learning_rate"] and cons["max_leaf_nodes"] < ctrl["max_leaf_nodes"]
    assert cons["min_samples_leaf"] > ctrl["min_samples_leaf"] and cons["l2_regularization"] > ctrl["l2_regularization"]
    for p in (ctrl, cons):
        assert p["early_stopping"] is False and p["random_state"] == 0 and p["max_iter"] == 200


def test_prefixed_run_writes_separate_files(tmp_path, ex):
    from Code.integration.pipeline import file_sha256
    df = pd.concat([seasonal(days=2100), seasonal(level=2000.0, market="N", days=2100)], ignore_index=True)
    df["source_row"] = range(len(df))
    (tmp_path / "f").mkdir()
    path = tmp_path / "f" / "features_onion.parquet"
    df.to_parquet(path, index=False)
    out = tmp_path / "out"
    mo.run_models(tmp_path / "f", out, ["Onion"], {str(path): file_sha256(path)},
                  runs=[("hgb_conservative", "weather", "primary")], prefix="exp")
    names = sorted(x.name for x in out.iterdir())
    assert "exp_validation_metrics.csv" in names and "exp_validation_predictions.parquet" in names
    assert not any(n.startswith("model_") or n == "validation_predictions.parquet" for n in names)
    assert set(pd.read_parquet(out / "exp_validation_predictions.parquet")["period"]) <= {"val_2019", "val_2020"}


# ---------------------------------------------------------------- real manifests (cheap; CSVs only)
@needs_outputs
def test_real_model_populations_match_the_baseline_populations():
    mm = pd.read_csv(m.MODEL_DATA_DIR / "model_validation_metrics.csv")
    bb = pd.read_csv(m.MODEL_DATA_DIR / "baseline_validation_metrics.csv")
    for exp in ["primary", "review_sensitivity"]:
        base = bb[(bb["baseline"] == "persistence") & (bb["experiment"] == exp) & (bb["population"] == "origin_eligible")]
        base = base.set_index(["crop", "horizon_weeks", "period"])["n"]
        for (model, config), g in mm[(mm["experiment"] == exp) & (mm["subset"] == "all")].groupby(["model", "config"]):
            got = g.set_index(["crop", "horizon_weeks", "period"])["n"]
            assert got.sort_index().equals(base.loc[got.index].sort_index()), (exp, model, config)
            assert np.allclose(g["persistence_mape_pct"], bb.set_index(["crop", "horizon_weeks", "period", "baseline", "experiment", "population"])
                               .loc[[(c, h, p, "persistence", exp, "origin_eligible") for c, h, p in got.index], "mape_pct"])


@needs_outputs
def test_real_refit_log_never_trains_on_test_targets():
    lg = pd.read_csv(m.MODEL_DATA_DIR / "model_refit_log.csv")
    assert (pd.to_datetime(lg["train_last_target_sunday"]) <= pd.to_datetime(lg["refit_date"])).all()
    assert pd.to_datetime(lg["train_last_target_sunday"]).max() <= mo.VAL_LAST_TARGET
    mm = pd.read_csv(m.MODEL_DATA_DIR / "model_validation_metrics.csv")
    n = lg.groupby(["crop", "horizon_weeks", "model", "config", "experiment"])["n_validation"].sum()
    comb = mm[(mm["subset"] == "all") & (mm["period"] == "val_combined")].set_index(n.index.names)["n"]
    assert n.sort_index().equals(comb.loc[n.index].sort_index())
