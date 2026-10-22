"""
Phase 9 — weekly market-arrivals dataset, validation-only baselines, and the arrivals output contract.
Arrivals are supply-side market activity, NOT demand (A-02). Protocol: Documentation/Phase_09_Arrivals_Plan.md.

  target      = median of usable daily arrivals (tonnes per reported day) of a series in week W+h, h in {1,2,4}
  origin      = end of Sunday of week W (series-weeks with >= 1 usable arrivals record); same key/weeks as Phase 8
  gaps        = a day without a record is "not reported", never zero; a week without a usable record has no example
  eligibility = >= 365 distinct usable arrival dates on or before the origin (evaluation) / refit date (training)
  separation  = the input is truncated at CUTOFF (last validation target Sunday) before anything is computed,
                so no 2021+ row (test or holdout) is ever read in this phase
Reuses the Phase 8 helpers (weeks, periods, refits, input hashing, schema checks) without changing them.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from Code.features.pipeline import ARR, FEATURE_DIR, SERIES
from Code.integration.pipeline import file_sha256, frame_fingerprint
from Code.modelling import dataset as d
from Code.modelling.baselines import VALIDATION

log = logging.getLogger("phase9_arrivals")
OUT_DIR = Path("Processed_Data/modelling/phase09")
CUTOFF = pd.Timestamp("2020-12-27")
MIN_DATES = 365
K = SERIES + ["week_start"]
TARGET = "target_median_arrivals"
SEASON_WEEKS = 52
REPORT_BINS, REPORT_LABELS = [0, 2, 5, 7], ["1-2 days", "3-5 days", "6-7 days"]              # (0,2], (2,5], (5,7]
VOLUME_BINS, VOLUME_LABELS = [0, 10, 100, np.inf], ["<10 t/day", "10-100 t/day", ">=100 t/day"]  # [0,10), [10,100), [100,inf)


# ---------------------------------------------------------------- dataset
def build_arrivals_examples(df: pd.DataFrame, horizons=d.HORIZONS, cutoff=CUTOFF) -> tuple[dict, pd.DataFrame]:
    df = df[df["reported_date"] <= cutoff]
    d0 = df.assign(week_start=d.week_start(df["reported_date"]))
    u = (d0[d0["usable_arrivals"]].assign(_review=lambda x: x["arrivals_extreme_level"].eq("review"))
         .sort_values(SERIES + ["reported_date", "source_row"]))
    wk = (u.groupby(K, observed=True)
          .agg(week_median=(ARR, "median"), week_days=("reported_date", "nunique"), week_first=("reported_date", "min"),
               week_last=("reported_date", "max"), week_review=("_review", "max"))
          .reset_index().sort_values(K, ignore_index=True))
    g = wk.groupby(SERIES, observed=True)
    wk["n_usable_arrival_dates_to_origin"] = g["week_days"].cumsum()
    wk["eligible_full_history"] = g["week_days"].transform("sum") >= MIN_DATES     # reporting only
    price_weeks = d0.loc[d0["usable_modal_price"], K].drop_duplicates().assign(has_usable_price_in_origin_week=True)
    origins = (wk.rename(columns={"week_median": "origin_week_median_arrivals", "week_days": "origin_week_reported_days",
                                  "week_last": "anchor_date"})
               .drop(columns=["week_first", "week_review"])
               .merge(price_weeks, on=K, how="left", validate="1:1"))
    origins["has_usable_price_in_origin_week"] = origins["has_usable_price_in_origin_week"].notna()  # left-join marker
    origins["origin_date"] = origins["week_start"] + pd.Timedelta(days=6)
    origins["eligible_at_origin"] = origins["n_usable_arrival_dates_to_origin"] >= MIN_DATES
    first_ok = origins[origins["eligible_at_origin"]].groupby(SERIES, observed=True)["origin_date"].min()
    origins = origins.merge(first_ok.rename("eligible_from_origin").reset_index(), on=SERIES, how="left", validate="m:1")
    targets = wk[K + ["week_median", "week_days", "week_first", "week_last", "week_review"]].rename(columns={
        "week_median": TARGET, "week_days": "target_reported_days", "week_first": "target_first_date",
        "week_last": "target_last_date", "week_review": "target_has_review"})
    last_date = df["reported_date"].max()
    out = {}
    for h in horizons:
        ex = origins.merge(targets.assign(week_start=targets["week_start"] - pd.Timedelta(weeks=h)), on=K, how="inner", validate="1:1")
        ex["horizon_weeks"] = h
        ex["target_week_start"] = ex["week_start"] + pd.Timedelta(weeks=h)
        ex["target_sunday"] = ex["target_week_start"] + pd.Timedelta(days=6)
        ex["period"] = d.assign_period(ex["target_sunday"], last_date)
        ex["tw_month"] = (ex["target_week_start"] + pd.Timedelta(days=3)).dt.month
        out[h] = ex.sort_values(K, ignore_index=True)
    return out, origins


def validate_arrivals_examples(ex: pd.DataFrame, cutoff=CUTOFF) -> None:
    h = pd.to_timedelta(ex["horizon_weeks"] * 7, unit="D")
    checks = {
        "weeks Monday-Sunday, origin = Sunday": (ex["week_start"].dt.dayofweek == 0).all()
                                                and (ex["origin_date"] - ex["week_start"] == pd.Timedelta(days=6)).all(),
        "anchor inside the origin week": ex["anchor_date"].between(ex["week_start"], ex["origin_date"]).all(),
        "target week is W+h": (ex["target_week_start"] == ex["week_start"] + h).all(),
        "target data strictly after the origin": (ex["target_first_date"] > ex["origin_date"]).all(),
        "target data inside the target week": (ex["target_first_date"] >= ex["target_week_start"]).all()
                                              and (ex["target_last_date"] <= ex["target_sunday"]).all(),
        "no target after the cutoff (test/holdout never built)": (ex["target_sunday"] <= cutoff).all(),
        "period follows the target Sunday": ex["period"].isin(["train", "val_2019", "val_2020", d.OUTSIDE]).all(),
        "eligibility from dates up to the origin": (ex["eligible_at_origin"] == (ex["n_usable_arrival_dates_to_origin"] >= MIN_DATES)).all()
                                                   and (ex["eligible_at_origin"] == (ex["eligible_from_origin"] <= ex["origin_date"])).all(),
        "arrivals non-negative": (ex[TARGET] >= 0).all() and (ex["origin_week_median_arrivals"] >= 0).all(),
        "one example per series, origin, horizon": not ex.duplicated(K + ["horizon_weeks"]).any(),
    }
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise d.ModellingError(f"arrivals leakage/consistency checks failed: {failed}")


# ---------------------------------------------------------------- baselines (validation only)
def seasonal_naive(ex: pd.DataFrame, origins: pd.DataFrame) -> pd.Series:
    past = origins[SERIES + ["week_start", "origin_week_median_arrivals"]].rename(
        columns={"week_start": "_w", "origin_week_median_arrivals": "_s"})
    key = ex[SERIES].assign(_w=ex["target_week_start"] - pd.Timedelta(weeks=SEASON_WEEKS))
    if (key["_w"] > ex["week_start"]).any():
        raise d.ModellingError("seasonal-naive week after the origin week")
    return pd.Series(key.merge(past, on=SERIES + ["_w"], how="left", validate="m:1")["_s"].to_numpy(), index=ex.index)


class CalendarAdjustedPersistence:
    """(origin + 1) x exp(training median log((target + 1) / (origin + 1)) for the target month) - 1."""

    def fit(self, tr):
        lr = np.log1p(tr[TARGET]) - np.log1p(tr["origin_week_median_arrivals"])
        self.by_month = lr.groupby(tr["tw_month"]).median()
        return self

    def predict(self, ev):
        m = ev["tw_month"].map(self.by_month).fillna(0.0)
        return np.clip(np.expm1(np.log1p(ev["origin_week_median_arrivals"]) + m), 0, None).to_numpy()


def validation_predictions(ex: pd.DataFrame, origins: pd.DataFrame, crop: str, h: int) -> tuple[pd.DataFrame, list]:
    ev = ex[ex["period"].isin(VALIDATION) & ex["eligible_at_origin"]]
    if ev.empty:
        raise d.ModellingError("no validation examples")
    refit = d.refit_date_for(ev["origin_date"], d.refit_schedule())
    cal = pd.Series(np.nan, index=ev.index)
    log_rows = []
    for r in sorted(refit.unique()):
        tr = d.training_examples(ex, r)            # targets ended <= r; series eligible by r (D-41 analogue)
        if tr.empty or tr["target_sunday"].max() > r:
            raise d.ModellingError(f"invalid training set at refit {r.date()}")
        idx = refit.index[refit == r]
        cal[idx] = CalendarAdjustedPersistence().fit(tr).predict(ev.loc[idx])
        log_rows.append({"crop": crop, "horizon_weeks": h, "refit_date": r.date().isoformat(), "n_train": len(tr),
                         "train_last_target_sunday": tr["target_sunday"].max().date().isoformat(), "n_validation": len(idx)})
    p = pd.DataFrame({"crop": crop, "horizon_weeks": h, "period": ev["period"], "y": ev[TARGET],
                      **{c: ev[c].astype(str) for c in SERIES if c != "crop"}, "origin_date": ev["origin_date"],
                      "persistence": ev["origin_week_median_arrivals"], "seasonal_naive": seasonal_naive(ev, origins),
                      "calendar_adjusted_persistence": cal,
                      "reporting_segment": pd.cut(ev["origin_week_reported_days"], REPORT_BINS, labels=REPORT_LABELS).astype(str),
                      "volume_segment": pd.cut(ev["origin_week_median_arrivals"], VOLUME_BINS, labels=VOLUME_LABELS,
                                               right=False).astype(str)})
    return p, log_rows


def metrics(y: pd.Series, yhat: pd.Series) -> dict:
    e = yhat - y
    return {"n": int(len(y)), "log_mae": float((np.log1p(yhat) - np.log1p(y)).abs().mean()),
            "mae_t_per_day": float(e.abs().mean()), "median_ae_t_per_day": float(e.abs().median()),
            "wape_pct": float(100 * e.abs().sum() / y.sum()) if y.sum() > 0 else np.nan}


def score(p: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (crop, h), g in p.groupby(["crop", "horizon_weeks"], sort=True):
        segs = [("all", "all", g)] + [("reporting", s, g[g["reporting_segment"] == s]) for s in REPORT_LABELS] \
               + [("volume", s, g[g["volume_segment"] == s]) for s in VOLUME_LABELS]
        for seg_type, seg, gs in segs:
            for period, part in [(x, gs[gs["period"] == x]) for x in VALIDATION] + [("val_combined", gs)]:
                if part.empty:
                    continue
                for baseline in ["persistence", "seasonal_naive", "calendar_adjusted_persistence"]:
                    ok = part[baseline].notna()
                    m, pm = metrics(part.loc[ok, "y"], part.loc[ok, baseline]), metrics(part.loc[ok, "y"], part.loc[ok, "persistence"])
                    rows.append({"crop": crop, "horizon_weeks": h, "segment_type": seg_type, "segment": seg, "period": period,
                                 "baseline": baseline, "coverage": float(ok.mean()),
                                 "n_series": part.loc[ok, ["state", "district", "market", "variety"]].drop_duplicates().shape[0]}
                                | m | {"persistence_log_mae_same_rows": pm["log_mae"],
                                       "skill_log_mae_vs_persistence": 1 - m["log_mae"] / pm["log_mae"] if pm["log_mae"] else np.nan})
    return pd.DataFrame(rows)


def bootstrap_log_mae(p: pd.DataFrame, candidate: str = "calendar_adjusted_persistence", b: int | None = None,
                      levels=("series", "market")) -> pd.DataFrame:
    """
    Paired cluster bootstrap of the log-MAE improvement of `candidate` over persistence on identical validation
    rows. Whole series (or markets) are resampled, so repeated weekly rows of one series stay together; the
    resampling, seed and percentile interval follow uncertainty.py. Positive improvement = candidate better.
    """
    from Code.modelling import uncertainty as u
    b = u.B if b is None else b
    rows = []
    for (crop, h), g in p.groupby(["crop", "horizon_weeks"], sort=True):
        e = g.assign(n=1, e_cand=(np.log1p(g[candidate]) - np.log1p(g["y"])).abs(),
                     e_pers=(np.log1p(g["persistence"]) - np.log1p(g["y"])).abs())
        if e[candidate].isna().any():
            raise d.ModellingError("candidate predictions missing: comparison must be on identical rows")
        for period, part in [(x, e[e["period"] == x]) for x in VALIDATION] + [("val_combined", e)]:
            for level in levels:
                sums = part.groupby(u.CLUSTERS[level], sort=True)[["n", "e_cand", "e_pers"]].sum()
                arr = sums.to_numpy()

                def stat(t):
                    return (t[..., 2] - t[..., 1]) / t[..., 0], 100 * (1 - t[..., 1] / t[..., 2])
                imp, rel = stat(arr.sum(axis=0))
                row = {"crop": crop, "horizon_weeks": h, "period": period, "cluster": level, "candidate": candidate,
                       "n_obs": int(arr[:, 0].sum()), "n_clusters": len(sums), "log_mae_improvement": float(imp),
                       "rel_log_mae_improvement_pct": float(rel)}
                if len(sums) >= u.MIN_CLUSTERS:
                    w = u.bootstrap_weights(len(sums), b, np.random.default_rng(u._seed("arrivals", crop, h, period, level)))
                    ri, rr = stat(w @ arr)
                    lo, hi = np.percentile(ri, [2.5, 97.5])
                    row |= {"ci_low": float(lo), "ci_high": float(hi), "se": float(np.std(ri, ddof=1)),
                            "rel_ci_low": float(np.percentile(rr, 2.5)), "rel_ci_high": float(np.percentile(rr, 97.5)),
                            "verdict": "better" if lo > 0 else "worse" if hi < 0 else "inconclusive"}
                else:
                    row |= {"ci_low": np.nan, "ci_high": np.nan, "se": np.nan, "rel_ci_low": np.nan,
                            "rel_ci_high": np.nan, "verdict": "too_few_clusters"}
                rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- output contract phase9-arrivals-forecast-v1
CONTRACT_VERSION = "phase9-arrivals-forecast-v1"
APPROACH = "persistence"
SELECTION = "provisional: no Phase 9 selection decision"
TARGET_DEFINITION = ("median usable daily mandi arrivals in the target week, tonnes per reported day "
                     "(supply-side market activity proxy; not consumer demand)")
KEY = ["crop", "state", "district", "market", "variety", "origin_date", "horizon_weeks"]   # same as phase8-forecast-v1
SCHEMA = [  # (column, kind, nullable)
    ("contract_version", "str", False), ("crop", "str", False), ("state", "str", False), ("district", "str", False),
    ("market", "str", False), ("variety", "str", False), ("origin_week_start", "date", False), ("origin_date", "date", False),
    ("horizon_weeks", "int", False), ("target_week_start", "date", False), ("target_week_end", "date", False),
    ("predicted_median_daily_arrivals_tonnes", "float", False), ("target_definition", "str", False),
    ("approach", "str", False), ("selection_decision", "str", False), ("prediction_status", "str", False),
    ("in_primary_population", "bool", False), ("n_usable_arrival_dates_to_origin", "int", False),
    ("origin_week_reported_days", "int", False), ("origin_week_median_arrivals_tonnes", "float", False),
    ("anchor_date", "date", False), ("has_usable_price_in_origin_week", "bool", False),
    ("prediction_interval_available", "bool", False),
]
COLUMNS = [c for c, *_ in SCHEMA]


def arrivals_forecast_table(origins: pd.DataFrame, crop: str, origin_date, last_date, horizons=d.HORIZONS) -> pd.DataFrame:
    """Provisional persistence arrivals forecasts for one origin (batch over historical data; not a live service)."""
    origin = pd.Timestamp(origin_date)
    if origin.dayofweek != 6:
        raise d.ModellingError("origin_date must be a Sunday (end of the origin week)")
    if origin > pd.Timestamp(last_date):
        raise d.ModellingError("origin_date is after the last reported date of the input")
    o = origins[origins["origin_date"] == origin]
    parts = [pd.DataFrame({
        "contract_version": CONTRACT_VERSION, "crop": crop, **{c: o[c].astype(str).to_numpy() for c in SERIES if c != "crop"},
        "origin_week_start": o["week_start"].to_numpy(), "origin_date": o["origin_date"].to_numpy(), "horizon_weeks": h,
        "target_week_start": (o["week_start"] + pd.Timedelta(weeks=h)).to_numpy(),
        "target_week_end": (o["week_start"] + pd.Timedelta(weeks=h, days=6)).to_numpy(),
        "predicted_median_daily_arrivals_tonnes": o["origin_week_median_arrivals"].astype(float).to_numpy(),
        "target_definition": TARGET_DEFINITION, "approach": APPROACH, "selection_decision": SELECTION, "prediction_status": "ok",
        "in_primary_population": o["eligible_at_origin"].to_numpy(),
        "n_usable_arrival_dates_to_origin": o["n_usable_arrival_dates_to_origin"].astype(int).to_numpy(),
        "origin_week_reported_days": o["origin_week_reported_days"].astype(int).to_numpy(),
        "origin_week_median_arrivals_tonnes": o["origin_week_median_arrivals"].astype(float).to_numpy(),
        "anchor_date": o["anchor_date"].to_numpy(), "has_usable_price_in_origin_week": o["has_usable_price_in_origin_week"].to_numpy(),
        "prediction_interval_available": False}) for h in horizons]
    out = pd.concat(parts, ignore_index=True)[COLUMNS].sort_values(KEY, ignore_index=True)
    validate_arrivals_forecasts(out)
    return out


def validate_arrivals_forecasts(f: pd.DataFrame) -> None:
    if list(f.columns) != COLUMNS:
        raise d.ModellingError(f"columns differ from the contract: {sorted(set(f.columns) ^ set(COLUMNS))}")
    kinds = {"date": pd.api.types.is_datetime64_any_dtype, "int": pd.api.types.is_integer_dtype,
             "float": pd.api.types.is_float_dtype, "bool": pd.api.types.is_bool_dtype,
             "str": lambda s: s.map(lambda v: isinstance(v, str)).all()}
    for c, k, nullable in SCHEMA:
        if (not nullable and f[c].isna().any()) or not kinds[k](f[c]):
            raise d.ModellingError(f"column {c} violates kind {k} / nullability")
    h = pd.to_timedelta(f["horizon_weeks"] * 7, unit="D")
    checks = {
        "unique key": not f.duplicated(KEY).any(),
        "contract version": (f["contract_version"] == CONTRACT_VERSION).all(),
        "horizon in 1/2/4": f["horizon_weeks"].isin(d.HORIZONS).all(),
        "Sunday origin ending the origin week": (f["origin_date"].dt.dayofweek == 6).all()
                                                and (f["origin_date"] - f["origin_week_start"] == pd.Timedelta(days=6)).all(),
        "target week W+h": (f["target_week_start"] == f["origin_week_start"] + h).all()
                           and (f["target_week_end"] - f["target_week_start"] == pd.Timedelta(days=6)).all(),
        "anchor inside origin week": f["anchor_date"].between(f["origin_week_start"], f["origin_date"]).all(),
        "non-negative forecast equal to origin median (provisional persistence)": (f["predicted_median_daily_arrivals_tonnes"] >= 0).all()
            and np.allclose(f["predicted_median_daily_arrivals_tonnes"], f["origin_week_median_arrivals_tonnes"]),
        "approach and labels": (f["approach"] == APPROACH).all() and (f["selection_decision"] == SELECTION).all()
                               and (f["target_definition"] == TARGET_DEFINITION).all() and (f["prediction_status"] == "ok").all(),
        "eligibility rule": (f["in_primary_population"] == (f["n_usable_arrival_dates_to_origin"] >= MIN_DATES)).all(),
        "origin week reported": f["origin_week_reported_days"].between(1, 7).all(),
        "no intervals": (~f["prediction_interval_available"]).all(),
    }
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise d.ModellingError(f"arrivals contract checks failed: {failed}")


# ---------------------------------------------------------------- orchestration
def run_arrivals_baselines(feature_dir: Path = FEATURE_DIR, out_dir: Path = OUT_DIR, crops: list[str] | None = None,
                           expected: dict[str, str] | None = None, registry_path: Path = d.REGISTRY_PATH) -> dict:
    t0 = time.time()
    out_dir = Path(out_dir)
    for p in d.PROTECTED_DIRS:
        if out_dir.resolve().is_relative_to(p.resolve()):
            raise d.ModellingError(f"output directory {out_dir} is inside protected {p}")
    crops = crops or d.load_selected_crops()
    inputs = [Path(feature_dir) / f"features_{c.lower()}.parquet" for c in crops] + [Path(registry_path)]
    expected = d.phase7_expected_hashes() if expected is None else expected
    before = d.check_inputs(inputs, expected)
    reg = d.registry_columns(pd.read_csv(registry_path))
    preds, logs, manifest, counts, elig = [], [], [], [], []
    for crop, path in zip(crops, inputs):
        df = pd.read_parquet(path)
        d.validate_schema(df, reg, crop)
        by_h, origins = build_arrivals_examples(df)
        del df
        s = origins.groupby(SERIES, observed=True)
        elig.append({"crop": crop, "series_with_usable_arrivals_to_cutoff": s.ngroups,
                     "series_eligible_by_2018_12_30": int((origins.groupby(SERIES, observed=True)["eligible_from_origin"].min() <= "2018-12-30").sum()),
                     "series_eligible_by_2020_12_27": int(origins.loc[origins["eligible_at_origin"], SERIES].drop_duplicates().shape[0])})
        for h, ex in by_h.items():
            validate_arrivals_examples(ex)
            p, lg = validation_predictions(ex, origins, crop, h)
            preds.append(p)
            logs += lg
            manifest.append({"crop": crop, "horizon_weeks": h, "rows": len(ex), "max_target_sunday": ex["target_sunday"].max().date().isoformat(),
                             "content_sha256": frame_fingerprint(ex)})
            counts += [{"crop": crop, "horizon_weeks": h, "period": per, "examples": int((ex["period"] == per).sum()),
                        "examples_origin_eligible": int(((ex["period"] == per) & ex["eligible_at_origin"]).sum())}
                       for per in ["train", "val_2019", "val_2020", d.OUTSIDE]]
        log.info("%s done (%.0fs)", crop, time.time() - t0)
    if d.check_inputs(inputs) != before:
        raise d.ModellingError("protected inputs changed during the Phase 9 run")
    p = pd.concat(preds, ignore_index=True)
    prov = pd.DataFrame([{"key": k, "value": v} for k, v in {
        "input_cutoff": CUTOFF.date().isoformat(), "test_period_scored": False, "holdout_accessed": False,
        "target": TARGET_DEFINITION, "min_usable_arrival_dates": MIN_DATES, "models_fitted": "calendar month factors only",
        "seconds": round(time.time() - t0, 1)}.items()])
    tables = {"arrivals_input_fingerprints": pd.DataFrame([{"path": k, "sha256_before": v, "sha256_after": v,
                                                            "sha256_recorded_phase7": expected.get(k, "")} for k, v in before.items()]),
              "arrivals_dataset_manifest": pd.DataFrame(manifest), "arrivals_sample_counts": pd.DataFrame(counts),
              "arrivals_eligibility_summary": pd.DataFrame(elig), "arrivals_refit_log": pd.DataFrame(logs),
              "arrivals_baseline_metrics": score(p), "arrivals_provenance": prov}
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(out_dir / f"{name}.csv", index=False)
    return tables | {"predictions": p}
