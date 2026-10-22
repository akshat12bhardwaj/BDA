"""
Phase 8 — naive baselines, scored on the validation periods only (nothing is fitted).

Baselines (Phase_08_Modelling_Plan.md §D):
  persistence    = the origin week's median usable price (last known weekly median)
  seasonal_naive = the series' weekly median 52 weeks before the target week (only where it exists)
  next_obs       = secondary task: the anchor (last known) price predicts the next usable price after the origin

Evaluation population = examples eligible at their origin (D-41); review-sensitivity and the not-yet-eligible
population are reported separately. 2021-2022 (test) and 2023-24 (holdout) are refused until model
selection is frozen.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from Code.features.pipeline import FEATURE_DIR, SERIES
from Code.modelling import dataset as d

log = logging.getLogger("phase8_baselines")
VALIDATION = ["val_2019", "val_2020"]
SEASON_WEEKS = 52
RUNS = [("primary", "origin_eligible"), ("review_sensitivity", "origin_eligible"), ("primary", "not_origin_eligible")]


def validation_only(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame[frame["period"].isin(VALIDATION)]
    if out.empty:
        raise d.ModellingError("no validation examples")
    return out


def seasonal_naive(ex: pd.DataFrame, origins: pd.DataFrame) -> pd.Series:
    """Weekly median of the same series 52 weeks before the target week (dated well before the origin)."""
    past = origins[SERIES + ["week_start", "origin_week_median"]].rename(
        columns={"week_start": "_season_week", "origin_week_median": "_season"})
    key = ex[SERIES].assign(_season_week=ex["target_week_start"] - pd.Timedelta(weeks=SEASON_WEEKS))
    if (key["_season_week"] > ex["week_start"]).any():
        raise d.ModellingError("seasonal-naive week is after the origin week")
    got = key.merge(past, on=SERIES + ["_season_week"], how="left", validate="m:1")["_season"]
    return pd.Series(got.to_numpy(), index=ex.index)


def metrics(y: pd.Series, yhat: pd.Series) -> dict:
    e = yhat - y
    return {"n": int(len(y)), "mae": float(e.abs().mean()), "rmse": float(np.sqrt((e ** 2).mean())),
            "mape_pct": float((e.abs() / y).mean() * 100), "median_ape_pct": float((e.abs() / y).median() * 100)}


def evaluate_weekly(ex: pd.DataFrame, origins: pd.DataFrame, crop: str, h: int) -> pd.DataFrame:
    ev = validation_only(ex)
    ev = ev.assign(_seasonal=seasonal_naive(ev, origins))
    rows = []
    for experiment, population in RUNS:
        keep = ev["eligible_at_origin"] == (population == "origin_eligible")
        if experiment == "review_sensitivity":
            keep &= ~ev["target_has_review"]
        sub = ev[keep]
        for period, part in [("val_2019", sub[sub["period"] == "val_2019"]),
                             ("val_2020", sub[sub["period"] == "val_2020"]), ("val_combined", sub)]:
            base = {"crop": crop, "horizon_weeks": h, "experiment": experiment, "population": population, "period": period}
            if part.empty:
                continue
            y = part[d.TARGET]
            rows.append(base | {"baseline": "persistence", "coverage": 1.0} | metrics(y, part["origin_week_median"]))
            s = part["_seasonal"].notna()
            if s.any():
                rows.append(base | {"baseline": "seasonal_naive", "coverage": float(s.mean())}
                            | metrics(y[s], part.loc[s, "_seasonal"]))
                rows.append(base | {"baseline": "persistence_on_seasonal_subset", "coverage": float(s.mean())}
                            | metrics(y[s], part.loc[s, "origin_week_median"]))
    return pd.DataFrame(rows)


def evaluate_next_obs(origins: pd.DataFrame, last_date, crop: str) -> pd.DataFrame:
    """Next reported observation: period by the Sunday of the week holding that observation."""
    o = origins[origins["eligible_at_origin"] & origins["target_next_obs_price"].notna()]
    nxt = o["target_next_obs_date"]
    if (nxt <= o["origin_date"]).any():
        raise d.ModellingError("next observation is not after the origin")
    o = o.assign(period=d.assign_period(d.week_start(nxt) + pd.Timedelta(days=6), last_date))
    o = validation_only(o)
    gap = (o["target_next_obs_date"] - o["origin_date"]).dt.days
    rows = []
    for period, part in [("val_2019", o[o["period"] == "val_2019"]), ("val_2020", o[o["period"] == "val_2020"]),
                         ("val_combined", o)]:
        g = gap[part.index]
        rows.append({"crop": crop, "baseline": "last_known_price", "population": "origin_eligible", "period": period,
                     "median_days_ahead": float(g.median()), "p90_days_ahead": float(g.quantile(0.9))}
                    | metrics(part["target_next_obs_price"], part["origin_week_last"]))
    return pd.DataFrame(rows)


def run_baselines(feature_dir: Path = FEATURE_DIR, out_dir: Path = d.MODEL_DATA_DIR, crops: list[str] | None = None,
                  expected: dict[str, str] | None = None, registry_path: Path = d.REGISTRY_PATH) -> dict:
    t0 = time.time()
    crops = crops or d.load_selected_crops()
    inputs = [Path(feature_dir) / f"features_{c.lower()}.parquet" for c in crops] + [Path(registry_path)]
    expected = d.phase7_expected_hashes() if expected is None else expected
    before = d.check_inputs(inputs, expected)
    reg = d.registry_columns(pd.read_csv(registry_path))
    weekly, nxt = [], []
    for crop, path in zip(crops, inputs):
        df = pd.read_parquet(path)
        d.validate_schema(df, reg, crop)
        last_date = df["reported_date"].max()
        by_h, origins = d.build_examples(df, reg)
        for h, ex in by_h.items():
            d.validate_examples(ex, last_date, d.feature_columns(reg, "weather"))
            weekly.append(evaluate_weekly(ex, origins, crop, h))
        nxt.append(evaluate_next_obs(origins, last_date, crop))
        log.info("%s done", crop)
        del df, by_h, origins
    after = d.check_inputs(inputs)
    if before != after:
        raise d.ModellingError("protected inputs changed during baseline evaluation")
    tables = {"baseline_validation_metrics": pd.concat(weekly, ignore_index=True),
              "next_obs_validation_metrics": pd.concat(nxt, ignore_index=True)}
    if set(tables["baseline_validation_metrics"]["period"]) - {"val_2019", "val_2020", "val_combined"}:
        raise d.ModellingError("a non-validation period was scored")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(Path(out_dir) / f"{name}.csv", index=False)
    log.info("Phase 8 baselines written in %.1fs", time.time() - t0)
    return tables | {"seconds": round(time.time() - t0, 1)}
