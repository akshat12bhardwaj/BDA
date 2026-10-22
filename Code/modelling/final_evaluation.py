"""
Phase 8 — the single 2021-2022 test evaluation of the frozen selection (Decision Log D-42). Run once.

  selection  = SELECTED (Onion h=1: hgb_conservative, weather config); every other crop x horizon: persistence
  rows       = test-period examples (target Sunday 2021-01-03 .. 2022-12-25) eligible at their origin
  refits     = latest quarterly refit <= origin, trained on training_examples(ex, refit) (same rule as validation);
               the last refit is 2022-10-02, so no 2023+ (holdout) target can enter any fit
  comparison = selected approach vs persistence on identical rows, per target year 2021, 2022 and combined
  freeze     = freeze() records SHA-256 of the modelling code + registry before the run; run_test_evaluation()
               refuses to start if any of them changed, and refuses to run a second time
The 2023+ no-weather holdout is never evaluated here.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from Code.features.pipeline import FEATURE_DIR, SERIES
from Code.integration.pipeline import file_sha256
from Code.modelling import baselines as b
from Code.modelling import dataset as d
from Code.modelling import models as mo
from Code.modelling import uncertainty as u

log = logging.getLogger("phase8_test")
SELECTED = {("Onion", 1): ("hgb_conservative", "weather")}  # D-42; all other crop x horizon cells: persistence
TEST_YEARS = {"test_2021": ("2021-01-03", "2021-12-26"), "test_2022": ("2022-01-02", "2022-12-25")}
FROZEN_FILES = [Path("Code/modelling") / f for f in ["dataset.py", "models.py", "baselines.py", "uncertainty.py",
                                                      "final_evaluation.py"]] + [d.REGISTRY_PATH]
FREEZE = d.MODEL_DATA_DIR / "test_freeze_manifest.csv"
RESULTS_NAME = "test_results.csv"


def freeze(path: Path = FREEZE, files=FROZEN_FILES) -> pd.DataFrame:
    if Path(path).exists():
        raise d.ModellingError(f"{path} already exists; the freeze is written once")
    rows = [{"item": "file", "name": str(f), "value": file_sha256(f)} for f in files]
    rows += [{"item": "selection", "name": f"{c} h={h}", "value": f"{m} ({cfg})"} for (c, h), (m, cfg) in SELECTED.items()]
    rows.append({"item": "selection", "name": "all other crop x horizon", "value": "persistence"})
    for m, cfg in set(SELECTED.values()):
        params = mo.LEARNERS[m]().get_params()
        rows.append({"item": "settings", "name": m, "value": "; ".join(f"{k}={params[k]}" for k in sorted(params))})
    out = pd.DataFrame(rows)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def verify_freeze(path: Path = FREEZE) -> None:
    if not Path(path).exists():
        raise d.ModellingError("no freeze manifest; run freeze() before the test evaluation")
    fz = pd.read_csv(path)
    changed = [n for n, v in fz.loc[fz["item"] == "file", ["name", "value"]].itertuples(index=False) if file_sha256(n) != v]
    if changed:
        raise d.ModellingError(f"frozen files changed since the freeze: {changed}")
    want = {r.name: r.value for r in fz[fz["item"] == "selection"].itertuples()}
    have = {f"{c} h={h}": f"{m} ({cfg})" for (c, h), (m, cfg) in SELECTED.items()} | {"all other crop x horizon": "persistence"}
    if want != have:
        raise d.ModellingError("selection differs from the frozen selection")


def eval_rows(ex: pd.DataFrame) -> pd.DataFrame:
    ev = ex[(ex["period"] == "test") & ex["eligible_at_origin"]]
    year = pd.Series(pd.NA, index=ev.index, dtype=object)
    for name, (a, z) in TEST_YEARS.items():
        year[ev["target_sunday"].between(pd.Timestamp(a), pd.Timestamp(z))] = name
    if year.isna().any():
        raise d.ModellingError("test rows outside the test years")
    return ev.assign(test_year=year)


def predict(ex: pd.DataFrame, reg: pd.DataFrame, crop: str, h: int, schedule=None) -> tuple[pd.DataFrame, list]:
    """Predictions of the selected approach for every eligible test row (persistence or the frozen learner)."""
    ev = eval_rows(ex)
    approach = SELECTED.get((crop, h))
    base = pd.DataFrame({"crop": crop, "horizon_weeks": h, "experiment": "primary", "row": ev.index,
                         **{c: ev[c].astype(str).to_numpy() for c in SERIES if c != "crop"},
                         "period": ev["test_year"].to_numpy(), "y": ev[d.TARGET].to_numpy(),
                         "persistence": ev["origin_week_median"].to_numpy()}, index=ev.index)
    if approach is None:
        return base.assign(model="persistence", config="none", yhat=base["persistence"]), []
    model, config = approach
    schedule = d.refit_schedule() if schedule is None else schedule
    refit = d.refit_date_for(ev["origin_date"], schedule)
    yhat, log_rows = pd.Series(index=ev.index, dtype=float), []
    for r in sorted(refit.unique()):
        tr = d.training_examples(ex, r)
        if tr.empty or tr["target_sunday"].max() > r or tr["period"].eq("holdout_no_weather").any():
            raise d.ModellingError(f"invalid training set at refit {r.date()}")
        idx = refit.index[refit == r]
        if (ev.loc[idx, "origin_date"] < r).any():
            raise d.ModellingError("refit after origin")
        t0 = time.time()
        fitted = mo.make_model(model, config, reg).fit(tr)
        yhat[idx] = fitted.predict(ev.loc[idx])
        log_rows.append({"crop": crop, "horizon_weeks": h, "model": model, "config": config,
                         "refit_date": r.date().isoformat(), "n_train": len(tr),
                         "train_last_target_sunday": tr["target_sunday"].max().date().isoformat(),
                         "n_test": len(idx), "fit_seconds": round(time.time() - t0, 2)})
    return base.assign(model=model, config=config, yhat=yhat), log_rows


def score(p: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (crop, h, model, config), g in p.groupby(["crop", "horizon_weeks", "model", "config"], sort=True):
        for period, part in [(y, g[g["period"] == y]) for y in TEST_YEARS] + [("test_combined", g)]:
            m, pm = b.metrics(part["y"], part["yhat"]), b.metrics(part["y"], part["persistence"])
            rows.append({"crop": crop, "horizon_weeks": h, "approach": model, "config": config, "period": period,
                         "n_obs": m["n"], "n_series": part[["state", "district", "market", "variety"]].drop_duplicates().shape[0],
                         "mae": m["mae"], "rmse": m["rmse"], "mape_pct": m["mape_pct"],
                         "persistence_mae": pm["mae"], "persistence_rmse": pm["rmse"], "persistence_mape_pct": pm["mape_pct"],
                         "mae_improvement": pm["mae"] - m["mae"], "rel_mae_improvement_pct": 100 * (1 - m["mae"] / pm["mae"]),
                         "rmse_improvement": pm["rmse"] - m["rmse"], "mape_improvement_pp": pm["mape_pct"] - m["mape_pct"]})
    return pd.DataFrame(rows)


def run_test_evaluation(feature_dir: Path = FEATURE_DIR, out_dir: Path = d.MODEL_DATA_DIR, crops: list[str] | None = None,
                        expected: dict[str, str] | None = None, registry_path: Path = d.REGISTRY_PATH,
                        freeze_path: Path = FREEZE, b_reps: int = u.B) -> dict:
    out_dir = Path(out_dir)
    if (out_dir / RESULTS_NAME).exists():
        raise d.ModellingError("the test evaluation has already been run; it is run once (D-42)")
    verify_freeze(freeze_path)
    t0 = time.time()
    crops = crops or d.load_selected_crops()
    inputs = [Path(feature_dir) / f"features_{c.lower()}.parquet" for c in crops] + [Path(registry_path)]
    expected = d.phase7_expected_hashes() if expected is None else expected
    before = d.check_inputs(inputs, expected)
    reg = d.registry_columns(pd.read_csv(registry_path))
    preds, logs = [], []
    for crop, path in zip(crops, inputs):
        df = pd.read_parquet(path)
        d.validate_schema(df, reg, crop)
        last_date = df["reported_date"].max()
        by_h, _ = d.build_examples(df, reg)
        del df
        for h, ex in by_h.items():
            d.validate_examples(ex, last_date, d.feature_columns(reg, "weather"))
            p, lg = predict(ex, reg, crop, h)
            preds.append(p)
            logs += lg
        log.info("%s done (%.0fs)", crop, time.time() - t0)
        del by_h
    if d.check_inputs(inputs) != before:
        raise d.ModellingError("protected inputs changed during the test evaluation")
    p = pd.concat(preds, ignore_index=True)
    learned = p[p["model"] != "persistence"]
    boot = (u.bootstrap(learned, b_reps, periods=tuple(TEST_YEARS), combined="test_combined")
            if len(learned) else pd.DataFrame())
    prov = pd.DataFrame([{"key": k, "value": v} for k, v in {
        "decision": "D-42", "freeze_manifest_sha256": file_sha256(freeze_path), "freeze_verified": True,
        "test_target_sundays": "2021-01-03 .. 2022-12-25", "holdout_evaluated": False,
        "bootstrap": f"{b_reps} replicates, seed {u.SEED}, series and market clusters, percentile 95%",
        "seconds": round(time.time() - t0, 1)}.items()])
    tables = {"test_results": score(p), "test_bootstrap": boot, "test_refit_log": pd.DataFrame(logs), "test_provenance": prov}
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(out_dir / f"{name}.csv", index=False)
    log.info("test evaluation written in %.1fs", time.time() - t0)
    return tables | {"predictions": p}
