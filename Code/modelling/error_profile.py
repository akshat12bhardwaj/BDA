"""
Phase 8 empirical forecast-error profile (version phase8-error-profile-v1), from 2019-2020 VALIDATION
residuals only. The 2021-2022 test results are not read, and the 2023+ holdout is never touched.

For each crop x horizon, the residuals are those of the D-42 approach on origin-eligible validation rows
(primary experiment):
  persistence      -> y vs origin-week median (the `persistence` column of validation_predictions.parquet)
  hgb_conservative -> y vs yhat of the weather-config primary run (hgb_conservative_validation_predictions.parquet)
Reported per target year (2019, 2020) and combined:
  ratio_error  = actual / predicted - 1      (unitless; actual = predicted x (1 + ratio_error))
  abs_error    = |actual - predicted|        (Rs/quintal, nominal)
  abs_pct      = |actual - predicted| / actual x 100
These are EMPIRICAL VALIDATION-PERIOD ERROR QUANTILES, NOT CALIBRATED PREDICTION INTERVALS: their coverage
on new periods has not been tested, rows are pooled over dependent weeks and unequal series, and two
years are two market regimes.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from Code.integration.pipeline import file_sha256
from Code.modelling import dataset as d
from Code.modelling.baselines import VALIDATION
from Code.modelling.forecast_output import PROFILE_VERSION, SERIES_COLS, approach_for

MAIN = d.MODEL_DATA_DIR / "validation_predictions.parquet"
CONSERVATIVE = d.MODEL_DATA_DIR / "hgb_conservative_validation_predictions.parquet"
QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
LABEL = "empirical validation-period error quantiles (2019-2020); NOT calibrated prediction intervals"


def selected_residuals(main: pd.DataFrame, conservative: pd.DataFrame) -> pd.DataFrame:
    """One row per (crop, h, validation example) with actual y and the D-42 approach's prediction."""
    for name, p in [("main", main), ("conservative", conservative)]:
        if not p["period"].isin(VALIDATION).all():
            raise d.ModellingError(f"{name} predictions contain non-validation rows")
    # any primary run carries the persistence value for every evaluated row; take one run per (crop, h)
    base = main[(main["model"] == "calendar_climatology") & (main["experiment"] == "primary")]
    out = []
    for (crop, h), g in base.groupby(["crop", "horizon_weeks"], sort=True):
        approach, config = approach_for(crop, h)
        if approach == "persistence":
            r = g.assign(yhat=g["persistence"])
        else:
            r = conservative[(conservative["crop"] == crop) & (conservative["horizon_weeks"] == h)
                             & (conservative["model"] == approach) & (conservative["config"] == config)
                             & (conservative["experiment"] == "primary")]
            if sorted(r["row"]) != sorted(g["row"]):
                raise d.ModellingError(f"{crop} h={h}: learned residuals do not cover the same rows as persistence")
        out.append(r[["crop", "horizon_weeks", "row", "period", "origin_date"] + SERIES_COLS + ["y", "yhat"]]
                   .assign(approach=approach))
    res = pd.concat(out, ignore_index=True)
    if res.duplicated(["crop", "horizon_weeks", "row"]).any():
        raise d.ModellingError("duplicate residual rows")
    return res


def profile(res: pd.DataFrame) -> pd.DataFrame:
    e = res.assign(ratio_error=res["y"] / res["yhat"] - 1, abs_error=(res["y"] - res["yhat"]).abs())
    e = e.assign(abs_pct=100 * e["abs_error"] / e["y"])
    rows = []
    for (crop, h, approach), g in e.groupby(["crop", "horizon_weeks", "approach"], sort=True):
        for period, part in [(p, g[g["period"] == p]) for p in VALIDATION] + [("val_combined", g)]:
            if part.empty:
                continue
            per_series = part.groupby(SERIES_COLS).size()
            row = {"profile_version": PROFILE_VERSION, "error_profile_key": f"{PROFILE_VERSION}|{crop}|h{h}|{approach}",
                   "crop": crop, "horizon_weeks": h, "approach": approach, "period": period, "label": LABEL,
                   "n_obs": len(part), "n_series": len(per_series),
                   "max_series_share_pct": 100 * per_series.max() / len(part),
                   "mae_rs_per_quintal": part["abs_error"].mean(), "mape_pct": part["abs_pct"].mean()}
            for q in QUANTILES:
                row[f"ratio_error_q{int(q * 100):02d}"] = part["ratio_error"].quantile(q)
            for q in (0.50, 0.80, 0.90, 0.95):
                row[f"abs_error_rs_q{int(q * 100):02d}"] = part["abs_error"].quantile(q)
                row[f"abs_pct_error_q{int(q * 100):02d}"] = part["abs_pct"].quantile(q)
            rows.append(row)
    return pd.DataFrame(rows)


def run_error_profile(main_path: Path = MAIN, conservative_path: Path = CONSERVATIVE,
                      out_dir: Path = d.MODEL_DATA_DIR) -> dict:
    sha = {str(p): file_sha256(p) for p in (main_path, conservative_path)}
    res = selected_residuals(pd.read_parquet(main_path), pd.read_parquet(conservative_path))
    prof = profile(res)
    if {str(p): file_sha256(p) for p in (main_path, conservative_path)} != sha:
        raise d.ModellingError("prediction files changed while building the profile")
    prov = pd.DataFrame([{"key": k, "value": v} for k, v in {
        "profile_version": PROFILE_VERSION, "label": LABEL, "periods": "val_2019, val_2020, val_combined",
        "test_results_used": False, "holdout_used": False, "selection": "D-42 approach per crop x horizon",
        **{f"sha256 {Path(p).name}": s for p, s in sha.items()}}.items()])
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    prof.to_csv(Path(out_dir) / "forecast_error_profile.csv", index=False)
    prov.to_csv(Path(out_dir) / "forecast_error_profile_provenance.csv", index=False)
    return {"forecast_error_profile": prof, "forecast_error_profile_provenance": prov}
