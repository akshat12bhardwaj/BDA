"""
Phase 8 — paired cluster bootstrap of each model's improvement over persistence (validation rows only).

Input : Processed_Data/modelling/phase08/validation_predictions.parquet (written by models.run_models;
        every row holds the model prediction AND the persistence prediction for the same example)
Output: Processed_Data/modelling/phase08/bootstrap_improvement.csv, bootstrap_selection_check.csv,
        bootstrap_provenance.csv

Design (Phase_08_Modelling_Plan.md §K):
  unit        = a cluster of whole series: 'series' (state, district, market, variety) is the primary unit;
                'market' (state, district, market) keeps varieties of one market together as a sensitivity
  pairing     = a resampled cluster contributes all its rows, each with both predictions, so model and
                persistence always see the same rows; every model in a (crop, horizon, experiment, period)
                group is evaluated on the same bootstrap draws
  statistic   = example-weighted ratio of sums, as in models.score():
                  mae_improvement      = MAE(persistence) - MAE(model)          (Rs/quintal; > 0 = better)
                  rel_mae_improvement  = 100 * (1 - MAE(model) / MAE(persistence))   (%)
                  mape_improvement_pp  = MAPE(persistence) - MAPE(model)        (percentage points)
  interval    = percentile 95% over B replicates drawn with a fixed seed per group
  periods     = 2019 and 2020 resampled separately (a series appears in a year only if it has rows there);
                'combined' resamples clusters with both years' rows kept together
This measures uncertainty across series within one validation year. It says nothing about other years:
two years are two draws of market conditions, not a sample of regimes.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from Code.modelling import dataset as d
from Code.modelling.baselines import VALIDATION
from Code.integration.pipeline import file_sha256

log = logging.getLogger("phase8_uncertainty")
PREDICTIONS = d.MODEL_DATA_DIR / "validation_predictions.parquet"
B = 10_000  # 2,000 moved interval ends by up to 4.5% of their width and flipped one borderline verdict
SEED = 20261022
MIN_CLUSTERS = 30  # below this a percentile cluster bootstrap is not defensible; no interval is reported
# Bonferroni-style cut-off for the 108 per-year primary comparisons (6 model/configs x 9 crop-horizons x 2 years).
# The exact two-sided value is 3.50 (one-sided 3.31); 3.55 is kept as first used and is slightly more conservative
# (audit, Phase_08_Modelling_Plan.md §M.1). Extreme bootstrap percentiles would be too noisy for this.
Z_BONFERRONI = 3.55
CLUSTERS = {"series": ["state", "district", "market", "variety"], "market": ["state", "district", "market"]}
GROUP = ["crop", "horizon_weeks", "experiment"]
MODEL = ["model", "config"]
SUMS = ["n", "abs_model", "abs_persistence", "ape_model", "ape_persistence"]


def cluster_sums(g: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Per-cluster row count and sums of absolute / absolute-percentage errors for model and persistence."""
    e = g.assign(abs_model=(g["yhat"] - g["y"]).abs(), abs_persistence=(g["persistence"] - g["y"]).abs())
    e = e.assign(ape_model=e["abs_model"] / e["y"], ape_persistence=e["abs_persistence"] / e["y"], n=1)
    return e.groupby(cols, sort=True)[SUMS].sum()


def improvements(tot: np.ndarray) -> dict[str, np.ndarray]:
    """tot[..., SUMS] -> improvement statistics (positive = the model has lower error)."""
    n, am, ap, pm, pp = (tot[..., i] for i in range(5))
    with np.errstate(divide="ignore", invalid="ignore"):
        return {"mae_improvement": (ap - am) / n,
                "rel_mae_improvement_pct": np.where(ap > 0, 100 * (1 - am / ap), np.nan),
                "mape_improvement_pp": 100 * (pp - pm) / n}


def bootstrap_weights(n_clusters: int, b: int, rng: np.random.Generator) -> np.ndarray:
    """b x n_clusters multiplicities: each replicate draws n_clusters clusters with replacement."""
    return rng.multinomial(n_clusters, np.full(n_clusters, 1 / n_clusters), size=b)


def summarise(sums: pd.DataFrame, weights: np.ndarray | None) -> dict:
    point = improvements(sums.to_numpy().sum(axis=0))
    out = {"n_obs": int(sums["n"].sum()), "n_clusters": len(sums)}
    reps = improvements(weights @ sums.to_numpy()) if weights is not None else None
    for k, v in point.items():
        out[k] = float(v)
        lo, hi = (np.nanpercentile(reps[k], [2.5, 97.5]) if reps is not None else (np.nan, np.nan))
        out[f"{k}_ci_low"], out[f"{k}_ci_high"] = float(lo), float(hi)
    lo, hi = out["mae_improvement_ci_low"], out["mae_improvement_ci_high"]
    out["verdict"] = ("too_few_clusters" if reps is None else "better" if lo > 0 else "worse" if hi < 0 else "inconclusive")
    se = float(np.std(reps["mae_improvement"], ddof=1)) if reps is not None else np.nan
    out["mae_improvement_se"] = se
    out["better_after_bonferroni"] = bool(reps is not None and se > 0 and out["mae_improvement"] / se > Z_BONFERRONI)
    return out


def _seed(*parts) -> list[int]:
    return [SEED] + [int.from_bytes(str(p).encode(), "little") % (2 ** 32) for p in parts]


def bootstrap(preds: pd.DataFrame, b: int = B, levels=tuple(CLUSTERS), periods=tuple(VALIDATION),
              combined: str = "val_combined") -> pd.DataFrame:
    """periods/combined default to validation; the frozen test evaluation passes its own year labels."""
    if not preds["period"].isin(periods).all():
        raise d.ModellingError("bootstrap input contains non-validation rows" if periods == tuple(VALIDATION)
                               else f"bootstrap input contains rows outside {periods}")
    rows = []
    for key, g in preds.groupby(GROUP, sort=True):
        for period, gp in [(p, g[g["period"] == p]) for p in periods] + [(combined, g)]:
            if gp.empty:  # a group with rows in only one validation year
                continue
            models = list(gp.groupby(MODEL, sort=True))
            ref_rows = np.sort(models[0][1]["row"].to_numpy())
            for _, gm in models:  # pairing: every model scored on exactly the same examples
                if not np.array_equal(np.sort(gm["row"].to_numpy()), ref_rows):
                    raise d.ModellingError(f"{key} {period}: models are not evaluated on identical rows")
            for level in levels:
                cols = CLUSTERS[level]
                ref = cluster_sums(models[0][1], cols).index
                w = (bootstrap_weights(len(ref), b, np.random.default_rng(_seed(*key, period, level)))
                     if len(ref) >= MIN_CLUSTERS else None)
                for (model, config), gm in models:
                    s = cluster_sums(gm, cols)
                    if not s.index.equals(ref):
                        raise d.ModellingError("cluster sets differ between models")
                    rows.append(dict(zip(GROUP, key)) | {"period": period, "cluster": level, "model": model,
                                                         "config": config} | summarise(s, w))
    return pd.DataFrame(rows)


def selection_check(res: pd.DataFrame) -> pd.DataFrame:
    """For each primary candidate: is the MAE improvement interval above zero in BOTH validation years?"""
    r = res[(res["experiment"] == "primary") & res["period"].isin(VALIDATION)]
    out = []
    for (crop, h, model, config), g in r.groupby(["crop", "horizon_weeks", "model", "config"]):
        row = {"crop": crop, "horizon_weeks": h, "model": model, "config": config}
        for level in CLUSTERS:
            v = g[g["cluster"] == level].set_index("period")["verdict"]
            row[f"verdict_2019_{level}"], row[f"verdict_2020_{level}"] = v.get("val_2019"), v.get("val_2020")
            row[f"better_both_years_{level}"] = bool((v.reindex(VALIDATION) == "better").all())
            bf = g[g["cluster"] == level].set_index("period")["better_after_bonferroni"]
            row[f"better_both_years_bonferroni_{level}"] = bool(bf.reindex(VALIDATION).fillna(False).all())
        out.append(row)
    return pd.DataFrame(out)


def quarterly_stability(preds: pd.DataFrame) -> pd.DataFrame:
    """Improvement per refit quarter (descriptive only: 9 blocks inside two years, not a sample of regimes)."""
    e = preds.assign(am=(preds["yhat"] - preds["y"]).abs(), ap=(preds["persistence"] - preds["y"]).abs())
    q = e.groupby(GROUP + MODEL + ["refit_date"])[["am", "ap"]].agg(["sum", "size"])
    out = pd.DataFrame({"n_obs": q[("am", "size")], "mae_improvement": (q[("ap", "sum")] - q[("am", "sum")]) / q[("am", "size")],
                        "rel_mae_improvement_pct": 100 * (1 - q[("am", "sum")] / q[("ap", "sum")])})
    return out.reset_index()


# Pre-specified in Phase_08_Modelling_Plan.md §L.2 before the conservative model was fitted.
Z_SELECTION = 3.58       # two-sided Bonferroni, 144 per-year primary comparisons (8 model/configs x 9 x 2)
MIN_REL_IMPROVEMENT = 2.0


def selection_proposal(res: pd.DataFrame, quarterly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply criteria L.2 (1-4) to every candidate; persistence stays unless one candidate passes all four."""
    per = res[res["period"].isin(VALIDATION)].set_index(GROUP + ["period", "cluster"] + MODEL)
    cand_rows = []
    for (crop, h, model, config), _ in res[res["experiment"] == "primary"].groupby(["crop", "horizon_weeks"] + MODEL):
        def get(exp, period, level):
            k = (crop, h, exp, period, level, model, config)
            return per.loc[k] if k in per.index else None
        yrs = [(p, get("primary", p, "series"), get("primary", p, "market")) for p in VALIDATION]
        sens = [get("review_sensitivity", p, "series") for p in VALIDATION]
        q = quarterly[(quarterly["crop"] == crop) & (quarterly["horizon_weeks"] == h) & (quarterly["experiment"] == "primary")
                      & (quarterly["model"] == model) & (quarterly["config"] == config)]
        row = {"crop": crop, "horizon_weeks": h, "model": model, "config": config}
        for p, s, _ in yrs:
            y = p[-4:]
            row |= {f"rel_mae_impr_{y}": s["rel_mae_improvement_pct"], f"mae_impr_{y}": s["mae_improvement"],
                    f"ci_{y}": f"[{s['mae_improvement_ci_low']:.1f}, {s['mae_improvement_ci_high']:.1f}]",
                    f"z_{y}": s["mae_improvement"] / s["mae_improvement_se"]}
        row["c1_ci_above_zero_both_years_series_and_market"] = all(s["verdict"] == "better" and m["verdict"] == "better" for _, s, m in yrs)
        row["c2_bonferroni_both_years"] = all(s["mae_improvement"] / s["mae_improvement_se"] > Z_SELECTION for _, s, _ in yrs)
        row["c3_practical_both_years"] = all(s["rel_mae_improvement_pct"] >= MIN_REL_IMPROVEMENT for _, s, _ in yrs)
        row["c4_review_sensitivity"] = all(s is not None for s in sens) and all(
            s["verdict"] == "better" and s["rel_mae_improvement_pct"] >= MIN_REL_IMPROVEMENT for s in sens)
        row["quarters_positive"] = f"{int((q['mae_improvement'] > 0).sum())}/{len(q)}"
        row["passes_all"] = all(row[c] for c in ["c1_ci_above_zero_both_years_series_and_market", "c2_bonferroni_both_years",
                                                  "c3_practical_both_years", "c4_review_sensitivity"])
        cand_rows.append(row)
    cand = pd.DataFrame(cand_rows)
    props = []
    for (crop, h), g in cand.groupby(["crop", "horizon_weeks"]):
        ok = g[g["passes_all"]].assign(worst=lambda x: x[["rel_mae_impr_2019", "rel_mae_impr_2020"]].min(axis=1))
        best = ok.sort_values("worst", ascending=False).iloc[0] if len(ok) else None
        near = g.assign(worst=g[["rel_mae_impr_2019", "rel_mae_impr_2020"]].min(axis=1)).sort_values("worst", ascending=False).iloc[0]
        props.append({"crop": crop, "horizon_weeks": h,
                      "proposed": "persistence" if best is None else f"{best['model']} ({best['config']})",
                      "candidates_passing_all": int(g["passes_all"].sum()),
                      "best_worst_year_candidate": f"{near['model']} ({near['config']})",
                      "its_rel_mae_impr_2019": near["rel_mae_impr_2019"], "its_rel_mae_impr_2020": near["rel_mae_impr_2020"]})
    return cand, pd.DataFrame(props)


def run_uncertainty(pred_path: Path = PREDICTIONS, out_dir: Path = d.MODEL_DATA_DIR, b: int = B,
                    prefix: str = "bootstrap") -> dict:
    t0 = time.time()
    sha = file_sha256(pred_path)
    preds = pd.read_parquet(pred_path)
    res = bootstrap(preds, b)
    if file_sha256(pred_path) != sha:
        raise d.ModellingError("prediction file changed during the bootstrap")
    prov = pd.DataFrame([{"key": k, "value": v} for k, v in {
        "predictions_sha256": sha, "replicates": b, "seed": SEED, "interval": "percentile 2.5-97.5",
        "min_clusters": MIN_CLUSTERS, "clusters": "; ".join(f"{k}={'+'.join(v)}" for k, v in CLUSTERS.items()),
        "aggregation": "example-weighted ratio of sums (as models.score)", "periods": "val_2019, val_2020, val_combined",
        "models_fitted": "none"}.items()])
    tables = {f"{prefix}_improvement": res, f"{prefix}_selection_check": selection_check(res), f"{prefix}_provenance": prov}
    for name, frame in tables.items():
        frame.to_csv(Path(out_dir) / f"{name}.csv", index=False)
    log.info("bootstrap written in %.1fs", time.time() - t0)
    return tables | {"seconds": round(time.time() - t0, 1)}


SELECTION_SOURCES = [("bootstrap", PREDICTIONS),
                     ("hgb_conservative_bootstrap", d.MODEL_DATA_DIR / "hgb_conservative_validation_predictions.parquet")]


def run_selection(out_dir: Path = d.MODEL_DATA_DIR, sources=SELECTION_SOURCES) -> dict:
    """Combine saved bootstrap results of every run and apply §L.2; writes new files only."""
    res = pd.concat([pd.read_csv(Path(out_dir) / f"{p}_improvement.csv") for p, _ in sources], ignore_index=True)
    if res.duplicated(GROUP + ["period", "cluster"] + MODEL).any():
        raise d.ModellingError("the same model/config appears in more than one bootstrap source")
    quarterly = pd.concat([quarterly_stability(pd.read_parquet(path)) for _, path in sources], ignore_index=True)
    cand, props = selection_proposal(res, quarterly)
    tables = {"selection_candidates": cand, "selection_proposal": props, "selection_quarterly_stability": quarterly}
    for name, frame in tables.items():
        frame.to_csv(Path(out_dir) / f"{name}.csv", index=False)
    return tables
