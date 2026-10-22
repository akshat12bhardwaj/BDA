"""
Phase 8 bootstrap tests: pairing, whole-cluster resampling, reproducibility, interval calculation,
identical predictions, validation-year separation and the small-cluster guard.
"""

import numpy as np
import pandas as pd
import pytest

from Code.modelling import dataset as m
from Code.modelling import uncertainty as u

needs_outputs = pytest.mark.skipif(not (m.MODEL_DATA_DIR / "bootstrap_improvement.csv").exists(),
                                   reason="run Code/modelling/uncertainty.py:run_uncertainty() first")


def preds(n_series=40, per_series=5, model_err=10.0, pers_err=20.0, years=("val_2019", "val_2020"), seed=0):
    """Two models on identical rows: 'cand' (abs error model_err ± noise) and 'same' (= persistence)."""
    rng = np.random.default_rng(seed)
    recs, row = [], 0
    for s in range(n_series):
        for period in years:
            for _ in range(per_series):
                y = 1000.0 + 50 * s
                noise = rng.normal(0, 2)
                recs.append({"row": row, "period": period, "state": "S", "district": f"D{s % 7}", "market": f"M{s}",
                             "variety": "V", "y": y, "persistence": y + pers_err, "cand": y + model_err + noise})
                row += 1
    base = pd.DataFrame(recs).assign(crop="Onion", horizon_weeks=1, experiment="primary")
    a = base.assign(model="cand", config="weather", yhat=base["cand"])
    b = base.assign(model="same", config="none", yhat=base["persistence"])
    return pd.concat([a, b], ignore_index=True).drop(columns="cand")


def get(res, model, period, level="series"):
    return res[(res["model"] == model) & (res["period"] == period) & (res["cluster"] == level)].iloc[0]


def test_identical_predictions_give_exactly_zero():
    r = get(u.bootstrap(preds(), b=200), "same", "val_2019")
    for k in ["mae_improvement", "rel_mae_improvement_pct", "mape_improvement_pp"]:
        assert r[k] == 0 and r[f"{k}_ci_low"] == 0 and r[f"{k}_ci_high"] == 0
    assert r["verdict"] == "inconclusive"


def test_known_improvement_and_interval_bounds():
    p = preds()
    r = get(u.bootstrap(p, b=500), "cand", "val_2019")
    g = p[(p["model"] == "cand") & (p["period"] == "val_2019")]
    want = (g["persistence"] - g["y"]).abs().mean() - (g["yhat"] - g["y"]).abs().mean()
    assert r["mae_improvement"] == pytest.approx(want)
    assert r["mae_improvement_ci_low"] <= r["mae_improvement"] <= r["mae_improvement_ci_high"]
    assert r["verdict"] == "better" and 8 < r["mae_improvement_ci_low"]
    assert r["mae_improvement_se"] > 0 and r["better_after_bonferroni"]       # a 10 Rs/q gain with tiny noise
    assert r["rel_mae_improvement_pct"] == pytest.approx(100 * want / (g["persistence"] - g["y"]).abs().mean())


def test_resampling_keeps_clusters_whole_and_matches_an_explicit_resample():
    p = preds(n_series=35)
    g = p[(p["model"] == "cand") & (p["period"] == "val_2019")]
    sums = u.cluster_sums(g, u.CLUSTERS["series"])
    w = u.bootstrap_weights(len(sums), 3, np.random.default_rng(1))
    assert (w.sum(axis=1) == len(sums)).all()
    fast = u.improvements(w @ sums.to_numpy())["mae_improvement"]
    keys = list(sums.index)
    for i in range(3):   # rebuild replicate i row by row: each drawn series contributes ALL of its rows
        parts = [g[(g[u.CLUSTERS["series"]].apply(tuple, axis=1) == keys[c])] for c in np.repeat(np.arange(len(keys)), w[i])]
        r = pd.concat(parts)
        assert fast[i] == pytest.approx((r["persistence"] - r["y"]).abs().mean() - (r["yhat"] - r["y"]).abs().mean())


def test_pairing_is_enforced():
    p = preds()
    bad = p.drop(p[(p["model"] == "cand")].index[:1])
    with pytest.raises(m.ModellingError, match="identical rows"):
        u.bootstrap(bad, b=50)


def test_reproducible_with_fixed_seed():
    a, b = u.bootstrap(preds(seed=3), b=300), u.bootstrap(preds(seed=3), b=300)
    pd.testing.assert_frame_equal(a, b)


def test_validation_years_are_resampled_separately():
    p = preds()
    p = p[~((p["period"] == "val_2020") & p["market"].isin(["M0", "M1"]))]   # two series absent in 2020
    res = u.bootstrap(p, b=100)
    n19, n20, nc = (get(res, "cand", per) for per in ["val_2019", "val_2020", "val_combined"])
    assert n19["n_obs"] + n20["n_obs"] == nc["n_obs"]
    assert n19["n_clusters"] == 40 and n20["n_clusters"] == 38 and nc["n_clusters"] == 40


def test_market_clusters_group_varieties():
    p = preds()
    p = pd.concat([p, p.assign(variety="W", row=p["row"] + 10_000)], ignore_index=True)   # 2 varieties per market
    res = u.bootstrap(p, b=50)
    assert get(res, "cand", "val_2019", "series")["n_clusters"] == 80
    assert get(res, "cand", "val_2019", "market")["n_clusters"] == 40


def test_too_few_clusters_gives_no_interval():
    r = get(u.bootstrap(preds(n_series=10), b=50), "cand", "val_2019")
    assert r["verdict"] == "too_few_clusters" and np.isnan(r["mae_improvement_ci_low"])
    assert r["mae_improvement"] > 0   # the point estimate is still reported


def test_non_validation_rows_are_refused():
    with pytest.raises(m.ModellingError, match="non-validation"):
        u.bootstrap(preds(years=("val_2019", "test")), b=10)


def _res_with(rel19, rel20, sens=True, n_series=40):
    """Bootstrap results for one candidate whose model error is persistence error x (1 - rel/100)."""
    out = []
    for exp in ["primary"] + (["review_sensitivity"] if sens else []):
        for period, rel in [("val_2019", rel19), ("val_2020", rel20)]:
            p = preds(n_series=n_series, model_err=20.0 * (1 - rel / 100), years=(period,))
            out.append(u.bootstrap(p.assign(experiment=exp), b=300))
    return pd.concat(out, ignore_index=True)


def test_selection_requires_all_four_criteria():
    q = pd.DataFrame(columns=u.GROUP + u.MODEL + ["refit_date", "n_obs", "mae_improvement", "rel_mae_improvement_pct"])
    cand, prop = u.selection_proposal(_res_with(10, 10), q)
    c = cand.set_index("model").loc["cand"]
    assert c["passes_all"] and prop.iloc[0]["proposed"] == "cand (weather)"
    assert not cand.set_index("model").loc["same", "passes_all"]                    # identical to persistence
    cand, prop = u.selection_proposal(_res_with(10, 1.0), q)                       # significant but < 2% in 2020
    assert not cand.set_index("model").loc["cand", "c3_practical_both_years"] and prop.iloc[0]["proposed"] == "persistence"
    cand, _ = u.selection_proposal(_res_with(10, 10, sens=False), q)               # no review-sensitivity run
    assert not cand.set_index("model").loc["cand", "c4_review_sensitivity"]


def test_quarterly_stability_reconciles_with_the_overall_improvement():
    p = preds().assign(refit_date=lambda x: np.where(x["row"] % 3 == 0, "2019-01-06", "2019-04-07"))
    p = p[p["period"] == "val_2019"]
    q = u.quarterly_stability(p)
    c = q[q["model"] == "cand"]
    g = p[p["model"] == "cand"]
    overall = (g["persistence"] - g["y"]).abs().mean() - (g["yhat"] - g["y"]).abs().mean()
    assert (c["mae_improvement"] * c["n_obs"]).sum() / c["n_obs"].sum() == pytest.approx(overall)
    assert (q.loc[q["model"] == "same", "mae_improvement"] == 0).all()


@needs_outputs
def test_real_bootstrap_matches_model_metrics():
    bs = pd.read_csv(m.MODEL_DATA_DIR / "bootstrap_improvement.csv")
    mm = pd.read_csv(m.MODEL_DATA_DIR / "model_validation_metrics.csv")
    mm = mm[mm["subset"] == "all"].set_index(["crop", "horizon_weeks", "experiment", "period", "model", "config"])
    s = bs[bs["cluster"] == "series"].set_index(mm.index.names)
    j = s.join(mm[["n", "mae", "persistence_mae"]], how="inner")
    assert len(j) == len(s) == len(mm)
    assert (j["n_obs"] == j["n"]).all()
    assert np.allclose(j["mae_improvement"], j["persistence_mae"] - j["mae"])
    assert set(bs["period"]) == {"val_2019", "val_2020", "val_combined"}
