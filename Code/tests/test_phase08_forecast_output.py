"""
Phase 8 forecast-output contract and validation error-profile tests. Synthetic examples plus read-only checks
of existing validation artifacts; nothing is trained and no test-period or holdout data is used.
"""

import numpy as np
import pandas as pd
import pytest

from Code.modelling import dataset as m
from Code.modelling import error_profile as ep
from Code.modelling import forecast_output as fo
from Code.tests.test_phase08_dataset import build, daily

needs_preds = pytest.mark.skipif(not (ep.MAIN.exists() and ep.CONSERVATIVE.exists()),
                                 reason="validation prediction parquets are local, git-ignored artifacts")
ORIGIN = pd.Timestamp("2019-03-03")   # a Sunday


@pytest.fixture(scope="module")
def origins():
    df = pd.concat([daily("2018-01-01", 500), daily("2018-06-04", 300, market="N").assign(source_row=lambda x: x["source_row"] + 9000)],
                   ignore_index=True)
    return build(df)[1], df["reported_date"].max()


def table(origins, crop="Potato", learned=None):
    o, last = origins
    return fo.forecast_table(o.assign(crop=crop), crop, ORIGIN, last, learned)


# ---------------------------------------------------------------- contract
def test_persistence_rows_follow_the_contract(origins):
    f = table(origins)
    assert list(f.columns) == fo.COLUMNS and len(f) == 2 * 3                     # 2 series x 3 horizons
    assert (f["predicted_median_price_rs_per_quintal"] == f["origin_week_median_rs_per_quintal"]).all()
    assert (f["prediction_status"] == "ok").all() and (f["approach"] == "persistence").all()
    r = f[f["horizon_weeks"] == 4].iloc[0]
    assert r["origin_week_start"] == pd.Timestamp("2019-02-25") and r["target_week_start"] == pd.Timestamp("2019-03-25")
    assert r["target_week_end"] == pd.Timestamp("2019-03-31")
    assert not f["prediction_interval_available"].any()
    assert not any(k in c for c in f.columns for k in ("lower", "upper", "ci_"))
    n = f.set_index("market")
    assert n.loc["M", "in_primary_population"].all() and not n.loc["N", "in_primary_population"].any()


def test_learned_cell_without_an_artifact_is_null_not_invented(origins):
    f = table(origins, crop="Onion")
    h1 = f[f["horizon_weeks"] == 1]
    assert (h1["approach"] == "hgb_conservative").all() and (h1["feature_config"] == "weather").all()
    assert (h1["prediction_status"] == "model_artifact_unavailable").all()
    assert h1["predicted_median_price_rs_per_quintal"].isna().all()
    assert (f.loc[f["horizon_weeks"] != 1, "approach"] == "persistence").all()


def test_supplied_learned_predictions_are_mapped_and_missing_ones_flagged(origins):
    sup = pd.DataFrame({"state": "S", "district": "D", "market": ["M"], "variety": "V", "origin_date": ORIGIN,
                        "horizon_weeks": 1, "approach": "hgb_conservative", "model_version": "v-test",
                        "predicted_median_price_rs_per_quintal": 123.0})
    f = table(origins, crop="Onion", learned=sup).set_index(["market", "horizon_weeks"])
    assert f.loc[("M", 1), "predicted_median_price_rs_per_quintal"] == 123.0 and f.loc[("M", 1), "model_version"] == "v-test"
    assert f.loc[("N", 1), "prediction_status"] == "model_prediction_missing"
    with pytest.raises(m.ModellingError, match="another approach"):
        table(origins, crop="Onion", learned=sup.assign(horizon_weeks=2))      # D-42: Onion h=2 is persistence


@pytest.mark.parametrize("tamper, msg", [
    (lambda f: pd.concat([f, f.iloc[[0]]], ignore_index=True), "duplicate"),
    (lambda f: f.assign(origin_date=f["origin_date"] - pd.Timedelta(days=1)), "Sunday"),
    (lambda f: f.assign(target_week_start=f["target_week_start"] + pd.Timedelta(days=7)), "W\\+h"),
    (lambda f: f.assign(predicted_median_price_rs_per_quintal=-1.0), "status = ok"),
    (lambda f: f.assign(predicted_median_price_rs_per_quintal=f["predicted_median_price_rs_per_quintal"] * 1.1), "persistence price"),
    (lambda f: f.assign(approach="ridge"), "D-42"),
    (lambda f: f.assign(prediction_interval_available=True), "no prediction intervals"),
    (lambda f: f.assign(in_primary_population=True), "D-41"),
    (lambda f: f.assign(extra_ci_lower=1.0), "columns differ"),
    (lambda f: f.assign(crop=None), "null values"),
    (lambda f: f.assign(horizon_weeks=f["horizon_weeks"].astype(float)), "kind int"),
])
def test_contract_violations_are_rejected(origins, tamper, msg):
    f = table(origins)
    with pytest.raises(m.ModellingError, match=msg):
        fo.validate_forecasts(tamper(f))


def test_forecast_rows_never_depend_on_data_after_the_origin():
    df = daily("2018-01-01", 500)
    late = df["reported_date"] > ORIGIN
    changed = df.assign(**{"modal_price_rs_per_quintal": df["modal_price_rs_per_quintal"].where(~late, 1e6),
                           "arrivals_tonnes": df["arrivals_tonnes"].where(~late, 1e6)})
    a = fo.forecast_table(build(df)[1], "Potato", ORIGIN, df["reported_date"].max())
    b = fo.forecast_table(build(changed)[1], "Potato", ORIGIN, df["reported_date"].max())
    pd.testing.assert_frame_equal(a, b)                 # target-week outcomes changed; forecasts did not
    assert not set(a.columns) & {"target_median", "target_next_obs_price", "target_n", "y", "yhat"}


def test_invalid_origins_are_refused(origins):
    o, last = origins
    with pytest.raises(m.ModellingError, match="Sunday"):
        fo.forecast_table(o, "Onion", "2019-03-04", last)
    with pytest.raises(m.ModellingError, match="after the last reported date"):
        fo.forecast_table(o, "Onion", last + pd.Timedelta(days=(6 - last.dayofweek) % 7 + 7), last)


# ---------------------------------------------------------------- error profile
def _preds(period="val_2019"):
    rows = []
    for crop, h in [("Onion", 1), ("Potato", 1)]:
        for i in range(8):
            rows.append({"crop": crop, "horizon_weeks": h, "row": i, "period": period, "origin_date": ORIGIN,
                         "state": "S", "district": "D", "market": f"M{i % 2}", "variety": "V",
                         "y": 100.0 + i, "persistence": 100.0, "yhat": 90.0, "model": "calendar_climatology",
                         "config": "none", "experiment": "primary", "refit_date": ORIGIN, "weather_covered": True})
    main = pd.DataFrame(rows)
    cons = main[main["crop"] == "Onion"].assign(model="hgb_conservative", config="weather", yhat=lambda x: x["y"] * 1.25)
    return main, cons


def test_profile_uses_the_d42_approach_per_cell_and_exact_quantiles():
    main, cons = _preds()
    res = ep.selected_residuals(main, cons)
    assert set(zip(res["crop"], res["approach"])) == {("Onion", "hgb_conservative"), ("Potato", "persistence")}
    p = ep.profile(res).set_index(["crop", "period"])
    pot = p.loc[("Potato", "val_2019")]
    y = 100.0 + np.arange(8)
    assert pot["n_obs"] == 8 and pot["n_series"] == 2 and pot["max_series_share_pct"] == 50
    assert pot["ratio_error_q50"] == pytest.approx(np.quantile(y / 100 - 1, 0.5))
    assert pot["abs_error_rs_q90"] == pytest.approx(np.quantile(y - 100, 0.9))
    assert p.loc[("Onion", "val_2019"), "ratio_error_q50"] == pytest.approx(1 / 1.25 - 1)
    assert "NOT calibrated prediction intervals" in pot["label"]
    assert pot["error_profile_key"] == "phase8-error-profile-v1|Potato|h1|persistence"


def test_profile_refuses_test_or_holdout_rows():
    main, cons = _preds(period="test_2021")
    with pytest.raises(m.ModellingError, match="non-validation"):
        ep.selected_residuals(main, cons)


def test_profile_requires_learned_rows_to_match_persistence_rows():
    main, cons = _preds()
    with pytest.raises(m.ModellingError, match="same rows"):
        ep.selected_residuals(main, cons.iloc[1:])


def test_forecast_keys_resolve_to_profile_keys(origins):
    main, cons = _preds()
    keys = set(ep.profile(ep.selected_residuals(main, cons))["error_profile_key"])
    f = table(origins, crop="Onion")
    assert set(f.loc[f["horizon_weeks"] == 1, "error_profile_key"]) <= keys


def test_contract_document_lists_every_column_and_version():
    doc = open("Documentation/Forecast_Output_Contract.md", encoding="utf-8").read()
    assert fo.CONTRACT_VERSION in doc and fo.PROFILE_VERSION in doc
    missing = [c for c in fo.COLUMNS if f"`{c}`" not in doc]
    assert not missing, missing


# ---------------------------------------------------------------- existing validation artifacts (read-only)
@needs_preds
def test_real_profile_matches_validation_metrics_and_covers_all_cells(tmp_path):
    out = ep.run_error_profile(out_dir=tmp_path)
    p = out["forecast_error_profile"]
    assert len(p) == 9 * 3 and set(p["period"]) == {"val_2019", "val_2020", "val_combined"}
    mm = pd.concat([pd.read_csv(m.MODEL_DATA_DIR / "model_validation_metrics.csv"),
                    pd.read_csv(m.MODEL_DATA_DIR / "hgb_conservative_validation_metrics.csv")])
    mm = mm[(mm["experiment"] == "primary") & (mm["subset"] == "all")]
    for r in p.itertuples():
        if r.approach == "persistence":
            ref = mm[(mm["crop"] == r.crop) & (mm["horizon_weeks"] == r.horizon_weeks) & (mm["period"] == r.period)
                     & (mm["model"] == "calendar_climatology")].iloc[0]
            assert r.n_obs == ref["n"] and r.mae_rs_per_quintal == pytest.approx(ref["persistence_mae"])
        else:
            ref = mm[(mm["crop"] == r.crop) & (mm["horizon_weeks"] == r.horizon_weeks) & (mm["period"] == r.period)
                     & (mm["model"] == "hgb_conservative") & (mm["config"] == "weather")].iloc[0]
            assert r.n_obs == ref["n"] and r.mae_rs_per_quintal == pytest.approx(ref["mae"])
    prov = out["forecast_error_profile_provenance"].set_index("key")["value"]
    assert prov["test_results_used"] in (False, "False") and prov["holdout_used"] in (False, "False")
