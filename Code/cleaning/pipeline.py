"""
Phase 5 — Data Cleaning for the selected crops (Onion, Potato, Wheat).

Input : Processed_Data/integration/mandi_integrated_<crop>.parquet (Phase 4, immutable)
Output: Processed_Data/cleaned/mandi_cleaned_<crop>.parquet
        Processed_Data/cleaning_audit/*.csv

Every rule is reversible from the Phase 4 file through `source_row`:
  R01 identical copies of one observation key -> one row kept, copies listed in the audit
  R03 conflicting versions of one key         -> all kept, flagged, excluded from usable views
  R04 zero / negative / non-finite prices     -> set missing, reason kept in <field>_status
  R08 modal outside [min, max]                -> flagged, excluded from usable_modal_price
  R09 price far from a trailing reference     -> review flag (10x) / suspected scale error (50x)
  R10 zero arrivals                           -> kept as 0 (genuine zero is not missing)
  R12 arrivals far above the market's past peak -> review flag (10x) / suspected entry error (100x)
Weather and APY gaps are coverage limits from Phase 4 and are never imputed here.
No value is invented: values are only kept, flagged, or set to missing.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from Code.integration.pipeline import (MANDI_KEY, MANDI_VALUES, OUT_DIR as INTEGRATION_DIR,
                                       IntegrationError, file_sha256, frame_fingerprint,
                                       load_selected_crops)
from Code.weather.config import DAILY_VARIABLES

log = logging.getLogger("phase5_cleaning")

CLEAN_DIR = Path("Processed_Data/cleaned")
AUDIT_DIR = Path("Processed_Data/cleaning_audit")
PRICES = ["min_price_rs_per_quintal", "max_price_rs_per_quintal", "modal_price_rs_per_quintal"]
MODAL, ARR = "modal_price_rs_per_quintal", "arrivals_tonnes"
MARKET = ["state", "district", "market"]

# Unit-mix-up factors: Rs/tonne vs Rs/quintal = 10x, Rs/kg vs Rs/quintal = 100x (D-29).
PRICE_REVIEW_RATIO, PRICE_SCALE_RATIO = 10.0, 50.0
PRICE_REF_WINDOW = "30D"
# Reference is the market's own past-365-day MAXIMUM, so seasonal harvest peaks (e.g. April wheat
# procurement) are compared with last year's peak, not a near-zero off-season median (D-30).
ARR_REVIEW_RATIO, ARR_ERROR_RATIO = 10.0, 100.0
ARR_REF_WINDOW, ARR_REF_MIN_OBS = "365D", 10

ADDED_COLUMNS = {
    "dup_status": "unique | exact_copies_collapsed | conflict_unresolved (key = state, district, market, variety, group, date)",
    "n_identical_copies": "number of identical Phase 4 rows this row represents (1 = no copies)",
    "min_price_status": "ok | missing_in_source | zero_set_missing | negative_set_missing | nonfinite_set_missing",
    "max_price_status": "same categories as min_price_status",
    "modal_price_status": "same categories as min_price_status",
    "arrivals_status": "ok | zero_retained | missing_in_source | negative_set_missing | nonfinite_set_missing",
    "min_gt_max": "min and max both present and min > max",
    "modal_outside_range": "modal, min and max present and modal outside [min, max]",
    "price_ratio_to_ref": "largest price/reference or reference/price ratio across present price fields "
                          "(reference = trailing 30-day median of the crop's national daily median modal price)",
    "price_extreme_level": "none | review (>=10x) | scale_error_suspected (>=50x) | no_reference",
    "arrivals_ratio_to_ref": "arrivals / maximum of the same market's arrivals over the previous 365 days",
    "arrivals_extreme_level": "none | review (>=10x past max) | entry_error_suspected (>=100x past max) | insufficient_history",
    "usable_modal_price": "modal present and not conflict / outside-range / min>max / suspected scale error",
    "usable_arrivals": "arrivals present and not conflict / suspected entry error",
}


class CleaningError(IntegrationError):
    """Raised when a Phase 5 rule or reconciliation check fails."""


# ---------------------------------------------------------------- diagnostics
def duplicate_structure(df: pd.DataFrame) -> pd.DataFrame:
    """Per-row key-group size, number of distinct value versions, and copy rank (by source_row)."""
    vhash = pd.util.hash_pandas_object(df[MANDI_VALUES], index=False).to_numpy()
    work = df[MANDI_KEY + ["source_row"]].assign(_v=vhash)
    g = work.groupby(MANDI_KEY, observed=True, dropna=False)
    out = pd.DataFrame(index=df.index)
    out["key_size"] = g["_v"].transform("size").to_numpy()
    out["n_versions"] = g["_v"].transform("nunique").to_numpy()
    gv = work.sort_values("source_row").groupby(MANDI_KEY + ["_v"], observed=True, dropna=False)
    out["copy_rank"] = gv.cumcount().reindex(df.index).to_numpy()
    out["n_identical"] = gv["_v"].transform("size").reindex(df.index).to_numpy()
    return out


def quality_metrics(df: pd.DataFrame, crop: str, stage: str) -> list[dict]:
    """Same metric set before and after cleaning (prices/arrivals read as stored)."""
    ds = duplicate_structure(df)
    mn, mx, md = (df[c] for c in PRICES)
    both = mn.notna() & mx.notna()
    m = {
        "rows": len(df),
        "distinct_observation_keys": int(df[MANDI_KEY].drop_duplicates().shape[0]),
        "rows_sharing_a_key": int((ds["key_size"] > 1).sum()),
        "redundant_identical_copies": int((ds["copy_rank"] > 0).sum()),
        "conflicting_key_groups": int(df.loc[ds["n_versions"] > 1, MANDI_KEY].drop_duplicates().shape[0]),
        "rows_in_conflicting_groups": int((ds["n_versions"] > 1).sum()),
        "min_gt_max": int((both & (mn > mx)).sum()),
        "modal_lt_min": int((md.notna() & mn.notna() & (md < mn)).sum()),
        "modal_gt_max": int((md.notna() & mx.notna() & (md > mx)).sum()),
        "unparsed_dates": int(df["reported_date"].isna().sum()),
        "first_date": str(df["reported_date"].min().date()),
        "last_date": str(df["reported_date"].max().date()),
        "weather_missing_rows (coverage, not quality)": int(df[DAILY_VARIABLES[0]].isna().sum()),
        "apy_annual_unavailable_rows (coverage, not quality)": int((~df["apy_annual_available"]).sum()),
    }
    for c in MANDI_VALUES:
        v = df[c]
        m[f"{c}: missing"] = int(v.isna().sum())
        m[f"{c}: zero"] = int((v == 0).sum())
        m[f"{c}: negative"] = int((v < 0).sum())
        m[f"{c}: non_finite"] = int(np.isinf(v).sum())
        m[f"{c}: dtype"] = str(v.dtype)
    m[f"{ARR}: p99.9"] = float(df[ARR].quantile(0.999))
    m[f"{ARR}: max"] = float(df[ARR].max())
    m[f"{MODAL}: p99.9"] = float(md.quantile(0.999))
    m[f"{MODAL}: max"] = float(md.max())
    return [{"crop": crop, "stage": stage, "metric": k, "value": v} for k, v in m.items()]


# ---------------------------------------------------------------- rules
def value_status(v: pd.Series, zero_is_missing: bool) -> tuple[pd.Series, pd.Series]:
    """Return (cleaned values, status). Zero prices -> missing; zero arrivals stay 0."""
    status = np.select(
        [v.isna(), np.isinf(v), v < 0, v == 0],
        ["missing_in_source", "nonfinite_set_missing", "negative_set_missing",
         "zero_set_missing" if zero_is_missing else "zero_retained"], "ok")
    bad = np.isin(status, ["nonfinite_set_missing", "negative_set_missing", "zero_set_missing"])
    return v.mask(bad), pd.Series(pd.Categorical(status), index=v.index)


def trailing_price_reference(df: pd.DataFrame) -> pd.Series:
    """Crop's national daily median modal price, then a trailing 30-day median (past + same day only)."""
    daily = df.loc[df[MODAL].notna()].groupby("reported_date")[MODAL].median().sort_index()
    ref = daily.rolling(PRICE_REF_WINDOW).median()
    return df["reported_date"].map(ref)


def trailing_market_arrivals(df: pd.DataFrame) -> pd.Series:
    """Maximum of the same market's arrivals over the previous 365 days (strictly before the date)."""
    s = df[MARKET + ["reported_date", ARR]].sort_values(MARKET + ["reported_date"])
    # Integer group ids that increase down the sorted frame: grouped-rolling output is ordered by
    # group id, then row order, which is then exactly s's order (categorical keys do not guarantee it).
    gid = s.groupby(MARKET, observed=True, sort=False).ngroup().to_numpy()
    if (np.diff(gid) < 0).any():
        raise CleaningError("market groups are not contiguous after sorting")
    r = (s.set_index("reported_date")[ARR].groupby(gid)
          .rolling(ARR_REF_WINDOW, closed="left", min_periods=ARR_REF_MIN_OBS).max())
    if len(r) != len(s) or not (r.index.get_level_values(0).to_numpy() == gid).all():
        raise CleaningError("trailing arrivals reference misaligned")
    return pd.Series(r.to_numpy(), index=s.index).reindex(df.index)


def clean_crop(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply R01-R12 to one crop's Phase 4 table. Returns (cleaned, removed identical copies)."""
    if "dup_status" in df.columns:
        raise CleaningError("input already carries Phase 5 columns; clean only Phase 4 integration output")
    ds = duplicate_structure(df)
    df = df.copy()

    # R01/R03: collapse identical copies (same key AND identical values); keep conflicts.
    df["dup_status"] = pd.Categorical(np.select(
        [ds["key_size"] == 1, ds["n_versions"] == 1], ["unique", "exact_copies_collapsed"], "conflict_unresolved"))
    df["n_identical_copies"] = ds["n_identical"].astype("int16")
    redundant = ds["copy_rank"].to_numpy() > 0
    removed = df.loc[redundant, ["source_row", "crop"] + MANDI_KEY + MANDI_VALUES + ["dup_status"]]
    df = df.loc[~redundant].copy()

    # R04-R06, R10-R11: field-level value status.
    for c, name in zip(PRICES, ["min_price_status", "max_price_status", "modal_price_status"]):
        df[c], df[name] = value_status(df[c], zero_is_missing=True)
    df[ARR], df["arrivals_status"] = value_status(df[ARR], zero_is_missing=False)

    # R07/R08: internal consistency on the values that remain.
    mn, mx, md = (df[c] for c in PRICES)
    df["min_gt_max"] = (mn > mx).fillna(False).to_numpy(dtype=bool)
    df["modal_outside_range"] = ((md < mn) | (md > mx)).fillna(False).to_numpy(dtype=bool)

    # R09: price level against a leakage-safe trailing reference.
    ref = trailing_price_reference(df)
    ratios = pd.concat([np.maximum(df[c] / ref, ref / df[c]) for c in PRICES], axis=1)
    df["price_ratio_to_ref"] = ratios.max(axis=1, skipna=True)
    df["price_extreme_level"] = pd.Categorical(np.select(
        [ref.isna() | (ref <= 0), df["price_ratio_to_ref"] >= PRICE_SCALE_RATIO,
         df["price_ratio_to_ref"] >= PRICE_REVIEW_RATIO],
        ["no_reference", "scale_error_suspected", "review"], "none"))

    # R12: arrivals against the same market's own past.
    aref = trailing_market_arrivals(df)
    df["arrivals_ratio_to_ref"] = (df[ARR] / aref.where(aref > 0)).astype("float64")
    df["arrivals_extreme_level"] = pd.Categorical(np.select(
        [aref.isna() | (aref <= 0), df["arrivals_ratio_to_ref"] >= ARR_ERROR_RATIO,
         df["arrivals_ratio_to_ref"] >= ARR_REVIEW_RATIO],
        ["insufficient_history", "entry_error_suspected", "review"], "none"))

    conflict = df["dup_status"] == "conflict_unresolved"
    df["usable_modal_price"] = (md.notna() & ~conflict & ~df["modal_outside_range"] & ~df["min_gt_max"]
                                & (df["price_extreme_level"] != "scale_error_suspected")).to_numpy(dtype=bool)
    df["usable_arrivals"] = (df[ARR].notna() & ~conflict
                             & (df["arrivals_extreme_level"] != "entry_error_suspected")).to_numpy(dtype=bool)
    return df.sort_values("source_row").reset_index(drop=True), removed


# ---------------------------------------------------------------- audit
DECISIONS = [
    ("R01", "Identical copies of one observation", "same key and identical arrivals/min/max/modal",
     "keep one row (lowest source_row; copies are identical so the choice carries no information), "
     "record n_identical_copies, list removed source_rows", "copies double-count arrivals; nothing is lost"),
    ("R02", "Same key, prices agree, arrivals differ", "observed 0 times in all three crops",
     "would be treated as R03", "kept as an explicit category for completeness"),
    ("R03", "Conflicting versions of one key", "same key, arrivals identical, prices differ",
     "keep every version, dup_status=conflict_unresolved, exclude from usable_modal_price/usable_arrivals, "
     "list in review_records.csv", "no field identifies the correct quote (possibly ungraded lots); "
                                  "averaging or choosing would invent a price"),
    ("R04", "Zero price (min/max/modal)", "price == 0",
     "set missing, <field>_status=zero_set_missing", "positive arrivals cannot trade at Rs 0; every min>max "
     "case disappears once zeros are missing, i.e. zero is a 'not reported' placeholder"),
    ("R05", "Negative or non-finite price", "price < 0 or +-inf",
     "set missing with status", "physically impossible; observed 0 times"),
    ("R06", "Missing price in source", "NaN in Phase 4", "kept missing", "never imputed in Phase 5"),
    ("R07", "Min price > max price", "both present after R04", "flag min_gt_max, exclude from usable_modal_price",
     "internally inconsistent record"),
    ("R08", "Modal outside [min, max]", "all present after R04", "flag modal_outside_range, value kept, "
     "excluded from usable_modal_price", "one of the three numbers is wrong but which one is unknown"),
    ("R09", "Price far from trailing reference", "max(price/ref, ref/price) >= 10 (review) or >= 50 "
     "(scale_error_suspected); ref = trailing 30-day median of the national daily median modal",
     "value kept; scale_error_suspected excluded from usable_modal_price; review rows stay usable",
     "10x / 100x match Rs/tonne and Rs/kg unit mix-ups; reference uses only past and same-day data"),
    ("R10", "Zero arrivals", "arrivals == 0", "kept as 0, arrivals_status=zero_retained",
     "a genuine zero is information, not a missing value"),
    ("R11", "Missing / negative / non-finite arrivals", "NaN, < 0, inf", "missing / set missing with status",
     "observed 0 times"),
    ("R12", "Arrivals far above the market's own past peak", "arrivals / maximum of the same market's "
     "arrivals in the previous 365 days >= 10 (review) or >= 100 (entry_error_suspected); needs >= 10 past "
     "observations", "value kept; entry_error_suspected excluded from usable_arrivals",
     "a first trial against the trailing median flagged genuine April wheat procurement peaks; a past-peak "
     "reference keeps seasonal peaks, while kg-vs-tonne (1000x) entries still stand far above it"),
    ("R13", "Weather / APY gaps", "Phase 4 coverage (no location, outside 2001-2022, no APY row)",
     "untouched, reported separately", "coverage limits, not data errors; no imputation (D-17, D-19)"),
    ("R14", "Dates", "Phase 4 parsed every date", "validated, unchanged", "0 unparsed"),
]


def rule_summary(raw: pd.DataFrame, cleaned: pd.DataFrame, removed: pd.DataFrame, crop: str) -> list[dict]:
    rows = []

    def add(rule, affected_rows, treatment, groups=None, removed_rows=0, set_missing=0, flagged=0,
            excl_modal=0, excl_arr=0):
        rows.append({"crop": crop, "rule_id": rule, "rows_before": len(raw), "affected_rows": int(affected_rows),
                     "affected_groups": groups, "treatment": treatment, "rows_removed": int(removed_rows),
                     "values_set_missing": int(set_missing), "rows_flagged_retained": int(flagged),
                     "rows_excluded_from_usable_modal_price": int(excl_modal),
                     "rows_excluded_from_usable_arrivals": int(excl_arr), "rows_after": len(cleaned)})

    exact = cleaned["dup_status"] == "exact_copies_collapsed"
    conf = cleaned["dup_status"] == "conflict_unresolved"
    add("R01", exact.sum() + len(removed), "collapse identical copies",
        groups=int(exact.sum()), removed_rows=len(removed))
    add("R02", 0, "none observed", groups=0)
    add("R03", conf.sum(), "retain + flag + exclude",
        groups=int(cleaned.loc[conf, MANDI_KEY].drop_duplicates().shape[0]), flagged=conf.sum(),
        excl_modal=(conf & cleaned[MODAL].notna()).sum(), excl_arr=(conf & cleaned[ARR].notna()).sum())
    for status, rule in [("zero_set_missing", "R04"), ("negative_set_missing", "R05"),
                         ("nonfinite_set_missing", "R05"), ("missing_in_source", "R06")]:
        for f in ["min", "max", "modal"]:
            n = (cleaned[f"{f}_price_status"] == status).sum()
            add(rule, n, f"{f} price: {status}", set_missing=n if rule != "R06" else 0)
    add("R07", cleaned["min_gt_max"].sum(), "flag + exclude", flagged=cleaned["min_gt_max"].sum(),
        excl_modal=(cleaned["min_gt_max"] & cleaned[MODAL].notna()).sum())
    add("R08", cleaned["modal_outside_range"].sum(), "flag + exclude", flagged=cleaned["modal_outside_range"].sum(),
        excl_modal=cleaned["modal_outside_range"].sum())
    for lvl in ["review", "scale_error_suspected", "no_reference"]:
        n = (cleaned["price_extreme_level"] == lvl).sum()
        add("R09", n, f"price_extreme_level={lvl}", flagged=n,
            excl_modal=n if lvl == "scale_error_suspected" else 0)
    add("R10", (cleaned["arrivals_status"] == "zero_retained").sum(), "zero arrivals retained")
    for status in ["missing_in_source", "negative_set_missing", "nonfinite_set_missing"]:
        n = (cleaned["arrivals_status"] == status).sum()
        add("R11", n, f"arrivals: {status}", set_missing=n if status != "missing_in_source" else 0)
    for lvl in ["review", "entry_error_suspected", "insufficient_history"]:
        n = (cleaned["arrivals_extreme_level"] == lvl).sum()
        add("R12", n, f"arrivals_extreme_level={lvl}", flagged=n,
            excl_arr=n if lvl == "entry_error_suspected" else 0)
    add("R13", cleaned[DAILY_VARIABLES[0]].isna().sum(), "weather missing (coverage) - untouched")
    add("R13", (~cleaned["apy_annual_available"]).sum(), "APY annual unavailable (coverage) - untouched")
    add("R14", cleaned["reported_date"].isna().sum(), "unparsed dates")
    return rows


def missingness(raw: pd.DataFrame, cleaned: pd.DataFrame, crop: str) -> pd.DataFrame:
    kind = {c: "measurement" for c in MANDI_VALUES}
    kind.update({c: "weather coverage" for c in DAILY_VARIABLES})
    kind.update({c: "APY / reference coverage" for c in ["apy_state", "apy_district", "apy_year",
                                                           "apy_year_lag1", "market_code"]})
    cols = [c for c in raw.columns if c in cleaned.columns]
    return pd.DataFrame({"crop": crop, "column": cols,
                         "category": [kind.get(c, "key / identifier") for c in cols],
                         "missing_before": raw[cols].isna().sum().to_numpy(),
                         "missing_after": cleaned[cols].isna().sum().to_numpy(),
                         "rows_before": len(raw), "rows_after": len(cleaned)})


# ---------------------------------------------------------------- orchestration
def run_cleaning(in_dir: Path = INTEGRATION_DIR, clean_dir: Path = CLEAN_DIR, audit_dir: Path = AUDIT_DIR,
                 crops: list[str] | None = None) -> dict:
    t0 = time.time()
    crops = crops or load_selected_crops()
    if not set(crops) <= {"Onion", "Potato", "Wheat"}:
        raise CleaningError(f"Only Onion/Potato/Wheat are in scope, got {crops}")
    clean_dir, audit_dir = Path(clean_dir), Path(audit_dir)
    if Path(in_dir).resolve() in (clean_dir.resolve(), audit_dir.resolve()):
        raise CleaningError("cleaning must read Phase 4 outputs, not its own outputs")
    clean_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    inputs = [Path(in_dir) / f"mandi_integrated_{c.lower()}.parquet" for c in crops]
    before = {str(p): file_sha256(p) for p in inputs}
    metrics, summary, miss, review, removed_all, manifest = [], [], [], [], [], []

    for crop, path in zip(crops, inputs):
        raw = pd.read_parquet(path)
        if set(raw["crop"].astype(str)) != {crop}:
            raise CleaningError(f"{path.name} contains crops other than {crop}")
        metrics += quality_metrics(raw, crop, "before")
        cleaned, removed = clean_crop(raw)

        if len(cleaned) + len(removed) != len(raw):
            raise CleaningError(f"{crop}: rows do not reconcile {len(cleaned)} + {len(removed)} != {len(raw)}")
        if cleaned["source_row"].duplicated().any():
            raise CleaningError(f"{crop}: source_row duplicated after cleaning")
        if cleaned[MANDI_KEY].duplicated().sum() != (
                cleaned["dup_status"] == "conflict_unresolved").sum() - cleaned.loc[
                cleaned["dup_status"] == "conflict_unresolved", MANDI_KEY].drop_duplicates().shape[0]:
            raise CleaningError(f"{crop}: repeated keys remain outside conflict groups")

        metrics += quality_metrics(cleaned, crop, "after")
        summary += rule_summary(raw, cleaned, removed, crop)
        miss.append(missingness(raw, cleaned, crop))
        removed_all.append(removed.assign(review_reason="R01 removed identical copy"))
        flag_cols = ["dup_status", "min_gt_max", "modal_outside_range", "price_extreme_level",
                     "arrivals_extreme_level", "price_ratio_to_ref", "arrivals_ratio_to_ref"]
        reasons = {
            "R03 conflict_unresolved": cleaned["dup_status"] == "conflict_unresolved",
            "R07 min_gt_max": cleaned["min_gt_max"],
            "R08 modal_outside_range": cleaned["modal_outside_range"],
            "R09 price scale_error_suspected": cleaned["price_extreme_level"] == "scale_error_suspected",
            "R09 price review": cleaned["price_extreme_level"] == "review",
            "R12 arrivals entry_error_suspected": cleaned["arrivals_extreme_level"] == "entry_error_suspected",
            "R12 arrivals review": cleaned["arrivals_extreme_level"] == "review",
        }
        for reason, mask in reasons.items():
            if mask.any():
                review.append(cleaned.loc[mask, ["source_row", "crop"] + MANDI_KEY + MANDI_VALUES + flag_cols]
                              .assign(review_reason=reason))

        out = clean_dir / f"mandi_cleaned_{crop.lower()}.parquet"
        cleaned.to_parquet(out, index=False)
        reopened = pd.read_parquet(out)
        manifest.append({"file": out.name, "grain": "one row per distinct (key, values) observation; "
                         "conflicting versions kept as separate rows", "rows": len(reopened),
                         "columns": reopened.shape[1], "content_sha256": frame_fingerprint(reopened)})
        log.info("%s: %d -> %d rows (%d identical copies removed)", crop, len(raw), len(cleaned), len(removed))
        del raw, cleaned, reopened

    after = {p: file_sha256(Path(p)) for p in before}
    fp = pd.DataFrame([{"path": p, "sha256_before": before[p], "sha256_after": after[p],
                        "unchanged": before[p] == after[p]} for p in before])
    tables = {
        "quality_metrics_before_after.csv": pd.DataFrame(metrics),
        "cleaning_summary.csv": pd.DataFrame(summary),
        "cleaning_decisions.csv": pd.DataFrame(DECISIONS, columns=["rule_id", "anomaly", "detection", "treatment",
                                                                    "reason_and_evidence"]),
        "added_columns.csv": pd.DataFrame(list(ADDED_COLUMNS.items()), columns=["column", "meaning"]),
        "missingness_before_after.csv": pd.concat(miss, ignore_index=True),
        "review_records.csv": pd.concat(review, ignore_index=True),
        "removed_identical_copies.csv": pd.concat(removed_all, ignore_index=True),
        "phase4_input_fingerprints.csv": fp,
        "output_manifest.csv": pd.DataFrame(manifest),
    }
    for name, frame in tables.items():
        frame.to_csv(audit_dir / name, index=False)
    if not fp["unchanged"].all():
        raise CleaningError("Phase 4 integration outputs changed during cleaning")
    log.info("Phase 5 cleaning finished in %.1fs", time.time() - t0)
    return {k.removesuffix(".csv"): v for k, v in tables.items()} | {"seconds": round(time.time() - t0, 1)}
