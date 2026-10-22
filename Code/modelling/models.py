"""
Phase 8 — calendar benchmarks and first tabular models, scored on the validation years only.

Every model is refitted at each quarterly refit date that serves a validation origin, on
training_examples(ex, refit) (targets ended <= refit, D-41 eligibility judged at the refit date), and
predicts only the origin-eligible validation examples assigned to that refit. 2021-2022 (test) and
the 2023-24 holdout are never scored here; no target dated after 2020-12-27 can enter any fit.

Models (Phase_08_Modelling_Plan.md §D, §I):
  calendar_climatology        target-week month only -> training median price of that month (crop level);
                              the only truly calendar-only forecast
  calendar_adjusted_persist.  last weekly median x exp(training median log change for the target month);
                              uses a historical price, so it is NOT calendar-only
  ridge / hgb                 predict log(target / origin-week median) from the origin-time features
Feature preparation is row-wise and deterministic (no fitted state); learned preprocessing (Ridge's
imputer and scaler) lives inside the model pipeline and is fitted on training rows only.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from Code.features.pipeline import FEATURE_DIR, IMD_SEASON, SERIES
from Code.modelling import baselines as b
from Code.modelling import dataset as d

log = logging.getLogger("phase8_models")
VAL_LAST_TARGET = pd.Timestamp("2020-12-27")
SEASONS = sorted(set(IMD_SEASON.values()))
LEARNERS = {
    "ridge": lambda: make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                                   Ridge(alpha=1.0)),
    # early_stopping would hold out a random split of the training rows; off keeps fitting time-ordered
    "hgb": lambda: HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, max_leaf_nodes=31,
                                                 min_samples_leaf=100, l2_regularization=1.0,
                                                 early_stopping=False, random_state=0),
    # the single pre-specified regularized variant (Phase_08_Modelling_Plan.md §L); hgb above is the control
    "hgb_conservative": lambda: HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                                              min_samples_leaf=1000, l2_regularization=10.0,
                                                              early_stopping=False, random_state=0),
}
# (model, feature config, experiment); calendar models ignore the feature config
RUNS = [("calendar_climatology", "none", "primary"), ("calendar_adjusted_persistence", "none", "primary"),
        ("ridge", "weather", "primary"), ("ridge", "no_weather", "primary"),
        ("hgb", "weather", "primary"), ("hgb", "no_weather", "primary"),
        ("calendar_adjusted_persistence", "none", "review_sensitivity"),
        ("ridge", "weather", "review_sensitivity"), ("hgb", "weather", "review_sensitivity")]
CONSERVATIVE_RUNS = [("hgb_conservative", "weather", "primary"), ("hgb_conservative", "no_weather", "primary"),
                     ("hgb_conservative", "weather", "review_sensitivity")]


# ---------------------------------------------------------------- features (row-wise, no fitted state)
def _price_cols(cols):
    return [c for c in cols if (c.startswith("modal_") and not any(s in c for s in ("pct_change", "days_ago", "_count")))
            or c in ("min_price_prev_obs", "max_price_prev_obs", "origin_week_last")]


def _heavy_cols(cols):
    return [c for c in cols if (c.startswith("arrivals_") and not any(s in c for s in ("days_ago", "_count")))
            or c in ("origin_week_arrivals_sum", "apy_production_tonnes_lag2", "apy_area_ha_lag2")]


def design_matrix(frame: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Origin-time features in a scale-free form: prices relative to the origin-week median, heavy-tailed
    quantities on a signed log scale, IMD season one-hot over its fixed categories. Each row depends only
    on itself, so no information can pass between training and validation rows here.
    """
    if "origin_week_median" not in cols:
        raise d.ModellingError("origin_week_median is required as the price anchor")
    X = frame[[c for c in cols if c != "imd_season"]].astype(float)
    ref = frame["origin_week_median"].astype(float)
    pc, hc = _price_cols(cols), _heavy_cols(cols)
    X[pc] = X[pc].div(ref, axis=0)
    X[hc] = np.sign(X[hc]) * np.log1p(X[hc].abs())
    X["origin_week_median"] = np.log(ref)
    for s in SEASONS:
        X[f"imd_season_{s}"] = (frame["imd_season"] == s).astype(float) if "imd_season" in cols else 0.0
    return X


def log_ratio(frame: pd.DataFrame) -> pd.Series:
    return np.log(frame[d.TARGET] / frame["origin_week_median"])


# ---------------------------------------------------------------- models
class CalendarClimatology:
    """Calendar-only: the training median target price for the target week's month (crop level)."""

    def fit(self, tr):
        self.by_month = tr.groupby("tw_month")[d.TARGET].median()
        self.overall = float(tr[d.TARGET].median())
        return self

    def predict(self, ev):
        return ev["tw_month"].map(self.by_month).fillna(self.overall).to_numpy()


class CalendarAdjustedPersistence:
    """Persistence x training median price change for the target month (uses the origin-week price)."""

    def fit(self, tr):
        self.by_month = log_ratio(tr).groupby(tr["tw_month"]).median()
        return self

    def predict(self, ev):
        return (ev["origin_week_median"] * np.exp(ev["tw_month"].map(self.by_month).fillna(0.0))).to_numpy()


class Tabular:
    def __init__(self, learner: str, cols: list[str]):
        self.model, self.cols = LEARNERS[learner](), cols

    def fit(self, tr):
        self.model.fit(design_matrix(tr, self.cols), log_ratio(tr))
        return self

    def predict(self, ev):
        return ev["origin_week_median"].to_numpy() * np.exp(self.model.predict(design_matrix(ev, self.cols)))


def make_model(name: str, config: str, reg: pd.DataFrame):
    if name == "calendar_climatology":
        return CalendarClimatology()
    if name == "calendar_adjusted_persistence":
        return CalendarAdjustedPersistence()
    return Tabular(name, d.feature_columns(reg, config))


# ---------------------------------------------------------------- validation loop
def validation_predictions(ex: pd.DataFrame, reg: pd.DataFrame, crop: str, h: int, runs=RUNS,
                           schedule=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Refit every run at each refit date that serves a validation origin; predict only those origins."""
    schedule = d.refit_schedule() if schedule is None else schedule
    ev_all = ex[ex["period"].isin(b.VALIDATION) & ex["eligible_at_origin"]]
    refit = d.refit_date_for(ev_all["origin_date"], schedule)
    preds, log_rows = [], []
    for r in sorted(refit.unique()):
        tr_all = d.training_examples(ex, r)
        if tr_all.empty:
            continue
        if tr_all["target_sunday"].max() > min(r, VAL_LAST_TARGET):
            raise d.ModellingError("a training target ends after the refit date or inside the test period")
        ev_r = ev_all[refit == r]
        if (ev_r["origin_date"] < r).any() or (tr_all["target_sunday"].max() >= ev_r["target_first_date"].min()):
            raise d.ModellingError("refit gap violated")
        for name, config, experiment in runs:
            tr = tr_all if experiment == "primary" else tr_all[~tr_all["target_has_review"]]
            ev = ev_r if experiment == "primary" else ev_r[~ev_r["target_has_review"]]
            t0 = time.time()
            model = make_model(name, config, reg).fit(tr)
            fit_s = time.time() - t0
            yhat = model.predict(ev)
            preds.append(pd.DataFrame({"crop": crop, "horizon_weeks": h, "model": name, "config": config,
                                       "experiment": experiment, "refit_date": r, "row": ev.index,
                                       **{c: ev[c].astype(str).to_numpy() for c in SERIES if c != "crop"},
                                       "origin_date": ev["origin_date"].to_numpy(),
                                       "period": ev["period"].to_numpy(), "weather_covered": ev["weather_covered"].to_numpy(),
                                       "y": ev[d.TARGET].to_numpy(), "persistence": ev["origin_week_median"].to_numpy(),
                                       "yhat": yhat}))
            log_rows.append({"crop": crop, "horizon_weeks": h, "model": name, "config": config, "experiment": experiment,
                             "refit_date": r.date().isoformat(), "n_train": len(tr),
                             "n_train_not_yet_origin_eligible": int((~tr["eligible_at_origin"]).sum()),
                             "train_last_target_sunday": tr["target_sunday"].max().date().isoformat(),
                             "n_validation": len(ev), "fit_seconds": round(fit_s, 2)})
    p = pd.concat(preds, ignore_index=True)
    if not np.isfinite(p["yhat"]).all():
        raise d.ModellingError("non-finite predictions")
    return p, pd.DataFrame(log_rows)


def score(preds: pd.DataFrame) -> pd.DataFrame:
    """Example-weighted metrics per model on identical rows, with persistence skill on the same rows."""
    rows = []
    keys = ["crop", "horizon_weeks", "model", "config", "experiment"]
    for k, g in preds.groupby(keys, sort=True):
        for subset, gs in [("all", g), ("weather_covered", g[g["weather_covered"]])]:
            for period, part in [("val_2019", gs[gs["period"] == "val_2019"]),
                                 ("val_2020", gs[gs["period"] == "val_2020"]), ("val_combined", gs)]:
                if part.empty:
                    continue
                m, p = b.metrics(part["y"], part["yhat"]), b.metrics(part["y"], part["persistence"])
                rows.append(dict(zip(keys, k)) | {"subset": subset, "period": period} | m
                            | {"persistence_mae": p["mae"], "persistence_mape_pct": p["mape_pct"],
                               "skill_mae_vs_persistence": 1 - m["mae"] / p["mae"]})
    return pd.DataFrame(rows)


def select_models(metrics: pd.DataFrame) -> pd.DataFrame:
    """
    Validation-only proposal per crop x horizon (primary experiment, all eligible rows): a candidate must
    beat persistence on MAE in BOTH 2019 and 2020; among those, the highest worst-year skill wins.
    Otherwise persistence is kept. Nothing here looks at 2021-2022.
    """
    m = metrics[(metrics["experiment"] == "primary") & (metrics["subset"] == "all")]
    s = m.pivot_table(index=["crop", "horizon_weeks", "model", "config"], columns="period",
                      values="skill_mae_vs_persistence").reset_index()
    s["worst_year_skill"] = s[["val_2019", "val_2020"]].min(axis=1)
    rows = []
    for (crop, h), g in s.groupby(["crop", "horizon_weeks"]):
        ok = g[g["worst_year_skill"] > 0].sort_values(["worst_year_skill", "val_combined"], ascending=False)
        best = ok.iloc[0] if len(ok) else None
        rows.append({"crop": crop, "horizon_weeks": h,
                     "proposed": "persistence" if best is None else f"{best['model']} ({best['config']})",
                     "skill_2019": np.nan if best is None else best["val_2019"],
                     "skill_2020": np.nan if best is None else best["val_2020"],
                     "skill_combined": np.nan if best is None else best["val_combined"],
                     "candidates_beating_persistence_both_years": len(ok)})
    return pd.DataFrame(rows)


def run_models(feature_dir: Path = FEATURE_DIR, out_dir: Path = d.MODEL_DATA_DIR, crops: list[str] | None = None,
               expected: dict[str, str] | None = None, registry_path: Path = d.REGISTRY_PATH, runs=RUNS,
               prefix: str = "model") -> dict:
    """prefix names the outputs, so a separate experiment never overwrites the main run's files."""
    t0 = time.time()
    crops = crops or d.load_selected_crops()
    inputs = [Path(feature_dir) / f"features_{c.lower()}.parquet" for c in crops] + [Path(registry_path)]
    expected = d.phase7_expected_hashes() if expected is None else expected
    before = d.check_inputs(inputs, expected)
    reg = d.registry_columns(pd.read_csv(registry_path))
    preds, logs, feats = [], [], None
    for crop, path in zip(crops, inputs):
        df = pd.read_parquet(path)
        d.validate_schema(df, reg, crop)
        last_date = df["reported_date"].max()
        by_h, _ = d.build_examples(df, reg)
        del df
        if feats is None:
            feats = pd.DataFrame([{"model_family": "ridge/hgb", "config": c, "column": col} for c in ("weather", "no_weather")
                                  for col in design_matrix(by_h[1].head(1), d.feature_columns(reg, c)).columns])
        for h, ex in by_h.items():
            d.validate_examples(ex, last_date, d.feature_columns(reg, "weather"))
            p, lg = validation_predictions(ex, reg, crop, h, runs)
            preds.append(p)
            logs.append(lg)
            log.info("%s h=%d done (%.0fs)", crop, h, time.time() - t0)
        del by_h
    if d.check_inputs(inputs) != before:
        raise d.ModellingError("protected inputs changed during model evaluation")
    p = pd.concat(preds, ignore_index=True)
    metrics = score(p)
    tables = {f"{prefix}_validation_metrics": metrics, f"{prefix}_refit_log": pd.concat(logs, ignore_index=True),
              f"{prefix}_selection_validation": select_models(metrics), f"{prefix}_features": feats}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(Path(out_dir) / f"{name}.csv", index=False)
    # validation rows only (git-ignored parquet); input to the paired bootstrap in uncertainty.py
    pred_name = "validation_predictions" if prefix == "model" else f"{prefix}_validation_predictions"
    p.to_parquet(Path(out_dir) / f"{pred_name}.parquet", index=False)
    log.info("Phase 8 models written in %.1fs", time.time() - t0)
    return tables | {"predictions": p, "seconds": round(time.time() - t0, 1)}
