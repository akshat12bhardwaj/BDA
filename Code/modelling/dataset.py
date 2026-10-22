"""
Phase 8 — leakage-safe weekly price-forecasting dataset (no model is fitted here).

Input : Processed_Data/features/features_<crop>.parquet and
        Processed_Data/features_audit/feature_registry.csv (Phase 6, immutable)
Output: Processed_Data/modelling/phase08/*.csv (manifests, sample counts, provenance).
        The datasets themselves are rebuilt in memory by build_examples(); their content
        hashes are recorded so every rebuild can be checked.

Contract (Decision Log D-38..D-41, Documentation/Phase_08_Modelling_Plan.md):
  week        = Monday..Sunday; forecast origin = end of the Sunday of week W
  target      = median usable modal price of the series in week W+h, h in {1, 2, 4}
  predictors  = Phase 6 features of the anchor row (last usable-price row of week W; they use data
                dated before the anchor date), week-W aggregates (rows dated <= origin) and
                calendar fields of the target week; nothing dated after the origin
  period      = decided by the target week's Sunday; a refit at T trains only on targets ending <= T
  population  = time-safe D-41 (>= 365 distinct usable price dates):
                evaluation - counted on or before the example's origin (eligible_at_origin);
                training   - counted on or before the refit date (eligible_from_origin <= refit date).
                The full-history count is kept for reporting only, never for selection.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from Code.features.pipeline import ARR, AUDIT_DIR, FEATURE_DIR, MAX, MIN, MODAL, SERIES, FeatureError
from Code.integration.pipeline import file_sha256, frame_fingerprint, load_selected_crops

log = logging.getLogger("phase8_dataset")

MODEL_DATA_DIR = Path("Processed_Data/modelling/phase08")
REGISTRY_PATH = AUDIT_DIR / "feature_registry.csv"
PHASE7_FINGERPRINTS = Path("Processed_Data/eda/input_fingerprints.csv")
PROTECTED_DIRS = [Path(p) for p in ["Dataset", "Processed_Data/integration", "Processed_Data/cleaned",
                                    "Processed_Data/cleaning_audit", "Processed_Data/features",
                                    "Processed_Data/features_audit", "Processed_Data/eda",
                                    "Processed_Data/weather", "Outputs", "Notebooks"]]

HORIZONS = (1, 2, 4)
MIN_USABLE_DATES = 365  # D-41
# (name, first target Sunday, last target Sunday); None = last reported date of the crop's input
PERIODS = [("train", "2002-01-06", "2018-12-30"),
           ("val_2019", "2019-01-06", "2019-12-29"),
           ("val_2020", "2020-01-05", "2020-12-27"),
           ("test", "2021-01-03", "2022-12-25"),
           ("holdout_no_weather", "2023-01-01", None)]
OUTSIDE = "outside"  # targets before 2002 or in the final, partial week
WEATHER_PERIODS = ["train", "val_2019", "val_2020", "test"]  # weather ends 2022-12-31
CONFIGS = ("weather", "no_weather")
EXPERIMENTS = ("primary", "review_sensitivity")
POPULATIONS = ("origin_eligible", "not_origin_eligible", "all")
TRAIN_POPULATIONS = ("eligible_by_refit", "eligible_at_origin", "all")
ROLES = {"identifier", "target", "eligibility_flag", "audit_only", "predictor"}

K = SERIES + ["week_start"]
ORIGIN_WEEK_PREDICTORS = ["origin_week_median", "origin_week_last", "origin_week_n",
                          "origin_week_arrivals_sum", "origin_week_arrivals_n"]
TARGET_CALENDAR = ["tw_month", "tw_week_of_year", "tw_month_sin", "tw_month_cos"]
META = K + ["origin_date", "anchor_date", "anchor_source_row", "horizon_weeks", "target_week_start",
            "target_sunday", "target_first_date", "target_last_date", "target_n", "target_has_review",
            "n_usable_dates_to_origin", "eligible_at_origin", "eligible_from_origin", "eligible_full_history",
            "weather_covered", "period"]
TARGET = "target_median"
# Columns that must exist in the input and may never be predictors, whatever the registry says.
RESERVED = SERIES + ["reported_date", "source_row", MODAL, MIN, MAX, ARR, "usable_modal_price",
                     "usable_arrivals", "price_extreme_level"]


class ModellingError(FeatureError):
    """Raised when a Phase 8 dataset rule, leakage check or input check fails."""


# ---------------------------------------------------------------- registry and schema
def registry_columns(registry: pd.DataFrame) -> pd.DataFrame:
    """One row per column with its role; the registry lists 'month_sin / month_cos' as one entry."""
    rows = [(c.strip(), r) for f, r in zip(registry["feature"], registry["role"]) for c in str(f).split(" / ")]
    out = pd.DataFrame(rows, columns=["column", "role"])
    if out["column"].duplicated().any():
        raise ModellingError(f"duplicate registry columns: {out.loc[out['column'].duplicated(), 'column'].tolist()}")
    if not set(out["role"]) <= ROLES:
        raise ModellingError(f"unknown registry roles: {sorted(set(out['role']) - ROLES)}")
    bad = out.loc[out["column"].isin(RESERVED) & (out["role"] == "predictor"), "column"].tolist()
    if bad:
        raise ModellingError(f"registry marks reserved columns as predictors: {bad}")
    return out


def feature_columns(reg: pd.DataFrame, config: str) -> list[str]:
    if config not in CONFIGS:
        raise ModellingError(f"unknown feature config {config!r}")
    p = reg.loc[reg["role"] == "predictor", "column"].tolist()
    if config == "no_weather":
        p = [c for c in p if not c.startswith("wx_")]
    return p + ORIGIN_WEEK_PREDICTORS + TARGET_CALENDAR


def validate_schema(df: pd.DataFrame, reg: pd.DataFrame, crop: str) -> None:
    cols, expected = set(df.columns), set(reg["column"])
    if cols != expected:
        raise ModellingError(f"{crop}: columns differ from the registry; missing {sorted(expected - cols)}, "
                             f"unexpected {sorted(cols - expected)}")
    if not set(RESERVED) <= cols:
        raise ModellingError(f"{crop}: required columns missing: {sorted(set(RESERVED) - cols)}")
    if set(df["crop"].astype(str).unique()) != {crop}:
        raise ModellingError(f"{crop}: unexpected crop values {sorted(df['crop'].astype(str).unique())}")
    if not pd.api.types.is_datetime64_any_dtype(df["reported_date"]):
        raise ModellingError(f"{crop}: reported_date is not a datetime column")
    for c in ["usable_modal_price", "usable_arrivals"]:
        if not pd.api.types.is_bool_dtype(df[c]):
            raise ModellingError(f"{crop}: {c} is not boolean")
    up = df.loc[df["usable_modal_price"], MODAL]
    if up.isna().any() or (up <= 0).any():
        raise ModellingError(f"{crop}: usable modal prices must be present and > 0 (Phase 5 contract)")


# ---------------------------------------------------------------- weeks and periods
def week_start(dates: pd.Series) -> pd.Series:
    d = dates.dt.normalize()
    return d - pd.to_timedelta(d.dt.dayofweek, unit="D")


def assign_period(target_sunday: pd.Series, last_date: pd.Timestamp) -> pd.Series:
    out = pd.Series(OUTSIDE, index=target_sunday.index, dtype=object)
    for name, a, b in PERIODS:
        end = pd.Timestamp(last_date) if b is None else pd.Timestamp(b)
        out[target_sunday.between(pd.Timestamp(a), end)] = name
    return out


def refit_schedule(start: str = "2002-01-01", end: str = "2024-12-31") -> pd.DatetimeIndex:
    """First Sunday of every calendar quarter (quarterly expanding-window refits)."""
    q = pd.date_range(start, end, freq="QS")
    return q + pd.to_timedelta((6 - q.dayofweek) % 7, unit="D")


def refit_date_for(origin_dates: pd.Series, schedule: pd.DatetimeIndex) -> pd.Series:
    """Latest scheduled refit on or before each origin; the model used at an origin never saw later targets."""
    i = schedule.searchsorted(origin_dates.to_numpy(), side="right") - 1
    if (i < 0).any():
        raise ModellingError("an origin precedes the first scheduled refit")
    return pd.Series(schedule[i], index=origin_dates.index)


def training_examples(ex: pd.DataFrame, refit_date, population: str = "eligible_by_refit") -> pd.DataFrame:
    """
    Expanding window: in-period examples whose whole target week ended by the refit date.
    Default population (D-41, time-safe): series that had >= 365 usable dates by the refit date, including
    their earlier weeks. eligible_from_origin <= refit date is decided by data dated <= refit date only.
    """
    if population not in TRAIN_POPULATIONS:
        raise ModellingError(f"unknown training population {population!r}")
    r = pd.Timestamp(refit_date)
    keep = (ex["target_sunday"] <= r) & (ex["period"] != OUTSIDE)
    if population == "eligible_by_refit":
        keep &= ex["eligible_from_origin"] <= r
    elif population == "eligible_at_origin":
        keep &= ex["eligible_at_origin"]
    return ex[keep]


# ---------------------------------------------------------------- dataset construction
def build_examples(df: pd.DataFrame, reg: pd.DataFrame, horizons=HORIZONS) -> tuple[dict, pd.DataFrame]:
    """Return ({h: examples with an observed target}, origins) for one crop's feature table."""
    predictors = reg.loc[reg["role"] == "predictor", "column"].tolist()
    wx = [c for c in predictors if c.startswith("wx_")]
    last_date = df["reported_date"].max()
    d = df.assign(week_start=week_start(df["reported_date"]))
    up = (d[d["usable_modal_price"]].assign(_review=lambda x: x["price_extreme_level"].eq("review"))
          .sort_values(SERIES + ["reported_date", "source_row"]))

    wk = (up.groupby(K, observed=True)
          .agg(week_median=(MODAL, "median"), week_n=(MODAL, "size"), week_dates=("reported_date", "nunique"),
               week_first=("reported_date", "min"), week_last=("reported_date", "max"), week_review=("_review", "max"),
               week_first_price=(MODAL, "first"))
          .reset_index().sort_values(K, ignore_index=True))
    by_series = wk.groupby(SERIES, observed=True)
    # Distinct usable dates up to each origin; weeks partition dates, so the cumulative sum counts each date once.
    wk["n_usable_dates_to_origin"] = by_series["week_dates"].cumsum()
    wk["eligible_full_history"] = by_series["week_dates"].transform("sum") >= MIN_USABLE_DATES
    # Secondary task (D-38): the next usable price after the origin = first price of the series' next reported week.
    wk["target_next_obs_date"] = by_series["week_first"].shift(-1)
    wk["target_next_obs_price"] = by_series["week_first_price"].shift(-1)

    anchor = (up.groupby(K, observed=True).tail(1)
              .rename(columns={"reported_date": "anchor_date", "source_row": "anchor_source_row",
                               MODAL: "origin_week_last"})[K + ["anchor_date", "anchor_source_row", "origin_week_last"] + predictors])
    arr = (d[d["usable_arrivals"]].groupby(K, observed=True)
           .agg(origin_week_arrivals_sum=(ARR, "sum"), origin_week_arrivals_n=(ARR, "size")).reset_index())
    origins = (wk.rename(columns={"week_median": "origin_week_median", "week_n": "origin_week_n"})
               .drop(columns=["week_dates", "week_first", "week_last", "week_review", "week_first_price"])
               .merge(anchor, on=K, how="left", validate="1:1")
               .merge(arr, on=K, how="left", validate="1:1"))
    origins["origin_week_arrivals_n"] = origins["origin_week_arrivals_n"].fillna(0).astype(int)  # a count, not imputation
    origins["origin_date"] = origins["week_start"] + pd.Timedelta(days=6)
    origins["eligible_at_origin"] = origins["n_usable_dates_to_origin"] >= MIN_USABLE_DATES
    # First origin (Sunday) with >= 365 usable dates. Only ever compared with a cutoff, never a predictor:
    # "eligible_from_origin <= c" is true exactly when the dates on or before c already reach the threshold.
    first_ok = origins[origins["eligible_at_origin"]].groupby(SERIES, observed=True)["origin_date"].min()
    origins = origins.merge(first_ok.rename("eligible_from_origin").reset_index(), on=SERIES, how="left", validate="m:1")
    origins["weather_covered"] = origins[wx].notna().all(axis=1) if wx else False

    targets = wk[K + ["week_median", "week_n", "week_first", "week_last", "week_review"]].rename(columns={
        "week_median": TARGET, "week_n": "target_n", "week_first": "target_first_date",
        "week_last": "target_last_date", "week_review": "target_has_review"})
    out = {}
    for h in horizons:
        t = targets.assign(week_start=targets["week_start"] - pd.Timedelta(weeks=h))
        ex = origins.merge(t, on=K, how="inner", validate="1:1")
        ex["horizon_weeks"] = h
        ex["target_week_start"] = ex["week_start"] + pd.Timedelta(weeks=h)
        ex["target_sunday"] = ex["target_week_start"] + pd.Timedelta(days=6)
        ex["period"] = assign_period(ex["target_sunday"], last_date)
        mid = ex["target_week_start"] + pd.Timedelta(days=3)  # Thursday names the week's month (ISO convention)
        ex["tw_month"] = mid.dt.month
        ex["tw_week_of_year"] = mid.dt.isocalendar().week.astype(int).to_numpy()
        ex["tw_month_sin"] = np.sin(2 * np.pi * (ex["tw_month"] - 1) / 12)
        ex["tw_month_cos"] = np.cos(2 * np.pi * (ex["tw_month"] - 1) / 12)
        ex = ex[META + ORIGIN_WEEK_PREDICTORS + TARGET_CALENDAR + predictors + [TARGET]]
        out[h] = ex.sort_values(K, ignore_index=True)
    return out, origins


def validate_examples(ex: pd.DataFrame, last_date, feature_cols: list[str]) -> None:
    """Raise if any example could use information from after its forecast origin."""
    h = pd.to_timedelta(ex["horizon_weeks"] * 7, unit="D")
    reserved = set(RESERVED) | set(META) | {TARGET}
    checks = {
        "week starts on Monday": (ex["week_start"].dt.dayofweek == 0).all(),
        "origin is the Sunday of week W": ((ex["origin_date"] - ex["week_start"]) == pd.Timedelta(days=6)).all()
                                          and (ex["origin_date"].dt.dayofweek == 6).all(),
        "anchor row lies in week W, at or before the origin": ex["anchor_date"].between(ex["week_start"], ex["origin_date"]).all(),
        "target week is W+h": (ex["target_week_start"] == ex["week_start"] + h).all(),
        "target data strictly after the origin": (ex["target_first_date"] > ex["origin_date"]).all(),
        "target data inside the target week": (ex["target_first_date"] >= ex["target_week_start"]).all()
                                              and (ex["target_last_date"] <= ex["target_sunday"]).all(),
        "period follows the target Sunday": (ex["period"] == assign_period(ex["target_sunday"], last_date)).all(),
        "eligibility uses only dates up to the origin": (ex["eligible_at_origin"] == (ex["n_usable_dates_to_origin"] >= MIN_USABLE_DATES)).all()
                                                        and (ex.groupby(SERIES + ["horizon_weeks"], observed=True)["n_usable_dates_to_origin"].diff().fillna(0) >= 0).all(),
        "eligible_from_origin agrees with every origin count": (ex["eligible_at_origin"] == (ex["eligible_from_origin"] <= ex["origin_date"])).all(),
        "one example per series, origin and horizon": not ex.duplicated(K + ["horizon_weeks"]).any(),
        "predictors exist": set(feature_cols) <= set(ex.columns),
        "no target, identifier or audit column among predictors": not (set(feature_cols) & reserved)
                                                                  and not any(c.startswith("target_") for c in feature_cols),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise ModellingError(f"leakage/consistency checks failed: {failed}")


def select(ex: pd.DataFrame, reg: pd.DataFrame, config: str, experiment: str = "primary",
           population: str = "origin_eligible") -> pd.DataFrame:
    """The modelling view for one feature config, experiment (D-39) and population (D-41)."""
    if experiment not in EXPERIMENTS or population not in POPULATIONS:
        raise ModellingError(f"unknown experiment/population: {experiment!r}, {population!r}")
    cols = feature_columns(reg, config)
    keep = ex["period"].isin(WEATHER_PERIODS if config == "weather" else WEATHER_PERIODS + ["holdout_no_weather"])
    if experiment == "review_sensitivity":
        keep &= ~ex["target_has_review"]
    if population != "all":
        keep &= ex["eligible_at_origin"] == (population == "origin_eligible")
    return ex.loc[keep, META + cols + [TARGET]]


# ---------------------------------------------------------------- reporting
def sample_counts(ex: pd.DataFrame, origins: pd.DataFrame, last_date, crop: str, h: int) -> pd.DataFrame:
    o_period = assign_period(origins["week_start"] + pd.Timedelta(weeks=h, days=6), last_date)
    rows = []
    for p in [name for name, _, _ in PERIODS] + [OUTSIDE]:
        e = ex[ex["period"] == p]
        el = e["eligible_at_origin"]
        rows.append({"crop": crop, "horizon_weeks": h, "period": p,
                     "origin_series_weeks": int((o_period == p).sum()),
                     "examples_target_observed": len(e),
                     "examples_origin_eligible": int(el.sum()),
                     "examples_not_origin_eligible": int((~el).sum()),
                     "examples_full_history_eligible": int(e["eligible_full_history"].sum()),
                     "examples_full_history_but_not_origin_eligible": int((e["eligible_full_history"] & ~el).sum()),
                     "examples_origin_eligible_review_sensitivity": int((el & ~e["target_has_review"]).sum()),
                     "examples_origin_eligible_weather_covered": int((el & e["weather_covered"]).sum()),
                     "series_origin_eligible": int(e.loc[el, SERIES].drop_duplicates().shape[0])})
    return pd.DataFrame(rows)


def training_population(ex: pd.DataFrame, crop: str, h: int) -> pd.DataFrame:
    """Training examples at the two selection/test refit cutoffs under each D-41 training population."""
    rows = []
    for cutoff in ["2018-12-30", "2020-12-27"]:
        n = {p: len(training_examples(ex, cutoff, p)) for p in TRAIN_POPULATIONS}
        rows.append({"crop": crop, "horizon_weeks": h, "refit_cutoff": cutoff, "training_examples_all": n["all"],
                     "eligible_at_origin": n["eligible_at_origin"], "eligible_by_refit": n["eligible_by_refit"],
                     "recovered_by_refit_rule": n["eligible_by_refit"] - n["eligible_at_origin"]})
    return pd.DataFrame(rows)


def eligibility_summary(origins: pd.DataFrame, crop: str) -> pd.DataFrame:
    series = origins.groupby(SERIES, observed=True).agg(total=("n_usable_dates_to_origin", "max"))
    first_ok = origins[origins["eligible_at_origin"]].groupby(SERIES, observed=True)["origin_date"].min()
    rows = [{"crop": crop, "measure": "series with >= 1 usable price", "value": len(series)},
            {"crop": crop, "measure": f"series with >= {MIN_USABLE_DATES} usable dates over the full input (retrospective, reporting only)",
             "value": int((series["total"] >= MIN_USABLE_DATES).sum())}]
    for label, cutoff in [("2018-12-30 (end of train)", "2018-12-30"), ("2020-12-27 (end of validation)", "2020-12-27"),
                          ("2022-12-25 (end of test)", "2022-12-25")]:
        rows.append({"crop": crop, "measure": f"series origin-eligible by {label}",
                     "value": int((first_ok <= pd.Timestamp(cutoff)).sum())})
    rows.append({"crop": crop, "measure": "series origin-eligible at any origin", "value": len(first_ok)})
    return pd.DataFrame(rows)


def check_inputs(paths: list[Path], expected: dict[str, str] | None = None) -> dict[str, str]:
    """SHA-256 of each protected input; raise if one differs from its recorded value."""
    got = {str(p): file_sha256(Path(p)) for p in paths}
    bad = [p for p, s in got.items() if expected and p in expected and expected[p] != s]
    if bad:
        raise ModellingError(f"protected inputs differ from their recorded hashes: {bad}")
    return got


def phase7_expected_hashes() -> dict[str, str]:
    fp = pd.read_csv(PHASE7_FINGERPRINTS)
    return {str(Path(p)): s for p, s in zip(fp["path"], fp["sha256_after"])}


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# ---------------------------------------------------------------- orchestration
def run_build(feature_dir: Path = FEATURE_DIR, out_dir: Path = MODEL_DATA_DIR, crops: list[str] | None = None,
              expected: dict[str, str] | None = None, registry_path: Path = REGISTRY_PATH) -> dict:
    """Build and check every crop × horizon dataset; write manifests only. Fits nothing."""
    t0 = time.time()
    out_dir = Path(out_dir)
    for p in PROTECTED_DIRS:
        if out_dir.resolve().is_relative_to(p.resolve()):
            raise ModellingError(f"output directory {out_dir} is inside protected {p}")
    crops = crops or load_selected_crops()
    inputs = [Path(feature_dir) / f"features_{c.lower()}.parquet" for c in crops] + [Path(registry_path)]
    expected = phase7_expected_hashes() if expected is None else expected
    missing = [str(p) for p in inputs[:-1] if str(p) not in expected]
    if missing:
        raise ModellingError(f"no recorded hash for inputs: {missing}")
    before = check_inputs(inputs, expected)
    reg = registry_columns(pd.read_csv(registry_path))

    manifest, counts, elig, train_pop = [], [], [], []
    for crop, path in zip(crops, inputs):
        df = pd.read_parquet(path)
        validate_schema(df, reg, crop)
        last_date = df["reported_date"].max()
        by_h, origins = build_examples(df, reg)
        elig.append(eligibility_summary(origins, crop))
        for h, ex in by_h.items():
            validate_examples(ex, last_date, feature_columns(reg, "weather"))
            counts.append(sample_counts(ex, origins, last_date, crop, h))
            train_pop.append(training_population(ex, crop, h))
            manifest.append({"crop": crop, "horizon_weeks": h, "input_last_date": last_date.date().isoformat(),
                             "rows": len(ex), "columns": ex.shape[1], "content_sha256": frame_fingerprint(ex)})
        log.info("%s done", crop)
        del df, by_h, origins

    after = check_inputs(inputs)
    fp = pd.DataFrame([{"path": p, "sha256_before": before[p], "sha256_after": after[p],
                        "sha256_recorded_phase7": expected.get(p, ""), "unchanged": before[p] == after[p]}
                       for p in before])
    out_dir.mkdir(parents=True, exist_ok=True)
    fp.to_csv(out_dir / "input_fingerprints.csv", index=False)
    if not fp["unchanged"].all():
        raise ModellingError("protected inputs changed during the build")

    periods = pd.DataFrame([{"period": n, "first_target_sunday": a, "last_target_sunday": b or "last input date",
                             "weather_config": n in WEATHER_PERIODS, "no_weather_config": True} for n, a, b in PERIODS])
    feats = pd.DataFrame([{"config": c, "column": col,
                           "source": "phase6_registry" if col in set(reg["column"]) else
                           "origin_week" if col in ORIGIN_WEEK_PREDICTORS else "target_week_calendar"}
                          for c in CONFIGS for col in feature_columns(reg, c)])
    prov = pd.DataFrame([{"key": k, "value": v} for k, v in {
        "git_head": _git_head(), "python": platform.python_version(), "pandas": pd.__version__,
        "numpy": np.__version__, "horizons_weeks": " ".join(map(str, HORIZONS)),
        "min_usable_dates": MIN_USABLE_DATES,
        "eligibility": "evaluation: dates <= origin; training: dates <= refit date; full-history count reporting only",
        "week": "Monday-Sunday; origin = end of Sunday",
        "refits": "first Sunday of each quarter; train on targets ending <= refit date",
        "registry_sha256": before[str(Path(registry_path))], "models_fitted": "none"}.items()])
    tables = {"input_fingerprints": fp, "dataset_manifest": pd.DataFrame(manifest),
              "sample_counts": pd.concat(counts, ignore_index=True),
              "eligibility_summary": pd.concat(elig, ignore_index=True),
              "training_population": pd.concat(train_pop, ignore_index=True),
              "split_definition": periods, "feature_columns": feats, "provenance": prov}
    for name, frame in tables.items():
        frame.to_csv(out_dir / f"{name}.csv", index=False)
    log.info("Phase 8 dataset manifests written in %.1fs", time.time() - t0)
    return tables | {"seconds": round(time.time() - t0, 1)}
