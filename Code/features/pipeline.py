"""
Phase 6 — Feature Engineering for the selected crops (Onion, Potato, Wheat).

Input : Processed_Data/cleaned/mandi_cleaned_<crop>.parquet (Phase 5, immutable)
        Processed_Data/integration/weather_daily_panel.parquet, apy_annual.csv (Phase 4, immutable)
Output: Processed_Data/features/features_<crop>.parquet (one row per Phase 5 row, same source_row)
        Processed_Data/features_audit/*.csv

Feature contract (Decision Log D-32..D-37):
  series        = (crop, state, district, market, variety); never crossed by any feature
  information   = every predictor for a row dated t uses only data dated strictly before t
                  (the row's own price/arrivals and anything later are never inputs)
  price history = rows with usable_modal_price; arrivals history = rows with usable_arrivals (Phase 5)
  windows       = calendar-day windows ('7D' = the 7 calendar days before t); lags are either
                  exact calendar-day lags (t-1, t-7) or explicitly "previous available observation"
  missing       = nothing is imputed, forward-filled or zero-filled; short history -> NaN
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from Code.cleaning.pipeline import CLEAN_DIR, CleaningError
from Code.integration.pipeline import OUT_DIR as INTEGRATION_DIR, file_sha256, frame_fingerprint, load_selected_crops

log = logging.getLogger("phase6_features")

FEATURE_DIR = Path("Processed_Data/features")
AUDIT_DIR = Path("Processed_Data/features_audit")
SERIES = ["crop", "state", "district", "market", "variety"]
MODAL, MIN, MAX, ARR = ("modal_price_rs_per_quintal", "min_price_rs_per_quintal",
                        "max_price_rs_per_quintal", "arrivals_tonnes")
WINDOWS = [7, 30, 90]
CAL_LAGS = [1, 7]
# Weather inputs from the Phase 4 panel: (source column, short name, aggregation, windows in days)
WEATHER_SPECS = [("temperature_2m_mean", "temp_mean", "mean", [7, 30]),
                 ("temperature_2m_max", "temp_max", "mean", [7]),
                 ("rain_sum", "rain", "sum", [7, 30, 90]),
                 ("relative_humidity_2m_mean", "rh_mean", "mean", [7]),
                 ("et0_fao_evapotranspiration", "et0", "sum", [30])]
APY_LAG_YEARS = 2  # see D-36: lag-1 APY is not yet published for much of each agricultural year
IMD_SEASON = {1: "winter", 2: "winter", 3: "pre_monsoon", 4: "pre_monsoon", 5: "pre_monsoon",
              6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon",
              10: "post_monsoon", 11: "post_monsoon", 12: "post_monsoon"}

# Phase 5 columns carried into the feature table (identifiers, targets, view flags, audit keys).
CARRY = {
    "identifier": ["source_row", "crop", "state", "district", "market", "variety", "commodity_group",
                   "reported_date", "market_code"],
    "target": [MODAL, MIN, MAX, ARR],
    "eligibility_flag": ["usable_modal_price", "usable_arrivals"],
    "audit_only": ["dup_status", "price_extreme_level", "arrivals_extreme_level", "weather_match",
                   "weather_state", "weather_district", "apy_state", "apy_district", "apy_year"],
}


class FeatureError(CleaningError):
    """Raised when a Phase 6 rule or validation fails."""


# ---------------------------------------------------------------- building blocks
def series_order(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Sort by series, date, source_row; return the sorted frame and contiguous integer series ids."""
    s = df.sort_values(SERIES + ["reported_date", "source_row"]).reset_index(drop=True)
    gid = s.groupby(SERIES, observed=True, sort=False).ngroup().to_numpy()
    if (np.diff(gid) < 0).any():
        raise FeatureError("series are not contiguous after sorting")
    return s, gid


def trailing_window_stats(s: pd.DataFrame, gid: np.ndarray, values: pd.Series, days: int,
                          stats: list[str]) -> pd.DataFrame:
    """
    Calendar-day window over the `days` days strictly before each row's date, within its series.
    `values` is NaN for ineligible rows, so they never contribute. closed='left' excludes every row
    dated t (including the row itself and same-day conflict rows).
    """
    r = (pd.Series(values.to_numpy(), index=s["reported_date"]).groupby(gid)
         .rolling(f"{days}D", closed="left", min_periods=0).agg(stats))
    if len(r) != len(s) or not (r.index.get_level_values(0).to_numpy() == gid).all():
        raise FeatureError("rolling result misaligned with series order")
    return r.reset_index(drop=True)


def previous_observations(s: pd.DataFrame, gid: np.ndarray, eligible: pd.Series,
                          cols: list[str]) -> pd.DataFrame:
    """
    For each row: the latest eligible observation of its series dated strictly before the row's
    date (`prev1_*`), its date, and the eligible observation before that (`prev2_*`).
    """
    hist = s.loc[eligible, ["reported_date"] + cols].assign(_g=gid[eligible.to_numpy()])
    if hist.duplicated(["_g", "reported_date"]).any():
        raise FeatureError("eligible history has two rows for one series-date")
    for c in cols:
        hist[f"prev2_{c}"] = hist.groupby("_g")[c].shift(1)   # eligible obs before this one
    hist = hist.rename(columns={c: f"prev1_{c}" for c in cols} | {"reported_date": "prev1_date"})
    left = pd.DataFrame({"_g": gid, "reported_date": s["reported_date"].to_numpy(), "_pos": np.arange(len(s))})
    out = pd.merge_asof(left.sort_values("reported_date"), hist.sort_values("prev1_date"),
                        left_on="reported_date", right_on="prev1_date", by="_g",
                        allow_exact_matches=False, direction="backward")
    return out.sort_values("_pos").reset_index(drop=True)


def calendar_lag(s: pd.DataFrame, gid: np.ndarray, eligible: pd.Series, col: str, days: int) -> np.ndarray:
    """Value reported by the same series exactly `days` calendar days earlier (NaN if not reported)."""
    hist = pd.DataFrame({"_g": gid[eligible.to_numpy()], "reported_date": s.loc[eligible, "reported_date"]
                         + pd.Timedelta(days=days), "v": s.loc[eligible, col].to_numpy()})
    left = pd.DataFrame({"_g": gid, "reported_date": s["reported_date"].to_numpy()})
    out = left.merge(hist, on=["_g", "reported_date"], how="left", validate="m:1")
    if len(out) != len(s):
        raise FeatureError("calendar lag changed row count")
    return out["v"].to_numpy()


def history_features(s: pd.DataFrame, gid: np.ndarray, target: str, eligible: pd.Series,
                     prefix: str, extra_prev: list[str], change: str) -> dict[str, np.ndarray]:
    feats: dict[str, np.ndarray] = {}
    prev = previous_observations(s, gid, eligible, [target] + extra_prev)
    feats[f"{prefix}_prev_obs"] = prev[f"prev1_{target}"].to_numpy()
    feats[f"{prefix}_prev_obs_days_ago"] = (s["reported_date"] - prev["prev1_date"]).dt.days.to_numpy(dtype="float64")
    for c, short in zip(extra_prev, ["min", "max"]):
        feats[f"{short}_price_prev_obs"] = prev[f"prev1_{c}"].to_numpy()
    p1, p2 = prev[f"prev1_{target}"], prev[f"prev2_{target}"]
    if change == "pct":       # prices are > 0 after Phase 5 (zeros set missing), so the ratio is valid
        feats[f"{prefix}_pct_change_prev_obs"] = (p1 / p2 - 1).to_numpy()
    else:                     # arrivals may be a genuine 0: percentage change is undefined there
        feats[f"{prefix}_change_prev_obs"] = (p1 - p2).to_numpy()
    for d in CAL_LAGS:
        feats[f"{prefix}_lag_{d}d"] = calendar_lag(s, gid, eligible, target, d)
    vals = s[target].where(eligible)
    for w in WINDOWS:
        st = trailing_window_stats(s, gid, vals, w, ["mean", "median", "std", "count"])
        for k in ["mean", "median", "std", "count"]:
            feats[f"{prefix}_roll{w}d_{k}"] = st[k].to_numpy()
    return feats


def weather_window_features(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Trailing weather at the panel's own (location, date) grain: the previous day's value and
    windows over the `w` days strictly before the date. A window is computed only when all `w`
    days exist (min_periods = w), so windows that start before 2001-01-01 or reach past
    2022-12-31 stay NaN instead of being partially filled.
    """
    p = panel.sort_values(["weather_state", "weather_district", "reported_date"]).reset_index(drop=True)
    gid = p.groupby(["weather_state", "weather_district"], sort=False).ngroup().to_numpy()
    out = p[["weather_state", "weather_district", "reported_date"]].copy()
    for col, short, agg, windows in WEATHER_SPECS:
        ser = pd.Series(p[col].to_numpy(), index=p["reported_date"]).groupby(gid)
        out[f"wx_{short}_prev1d"] = ser.shift(1).to_numpy()
        prev_ok = (p["reported_date"] - pd.Series(p["reported_date"]).groupby(gid).shift(1)).dt.days.eq(1)
        out.loc[~prev_ok.to_numpy(), f"wx_{short}_prev1d"] = np.nan   # only a true previous calendar day
        for w in windows:
            r = ser.rolling(f"{w}D", closed="left", min_periods=w).agg(agg)
            if not (r.index.get_level_values(0).to_numpy() == gid).all():
                raise FeatureError("weather rolling misaligned")
            out[f"wx_{short}_{agg}_{w}d"] = r.to_numpy()
    # keep only rows that are real days in the panel: the merge below is m:1 on this key
    return out


def apy_lag_table(apy_annual: pd.DataFrame, crop: str) -> pd.DataFrame:
    a = apy_annual[apy_annual["crop"] == crop]
    return a.rename(columns={"state": "apy_state", "district": "apy_district",
                             "apy_year": f"apy_year_lag{APY_LAG_YEARS}",
                             "production_tonnes": f"apy_production_tonnes_lag{APY_LAG_YEARS}",
                             "area_ha": f"apy_area_ha_lag{APY_LAG_YEARS}",
                             "yield_t_per_ha": f"apy_yield_t_per_ha_lag{APY_LAG_YEARS}"})[
        ["apy_state", "apy_district", f"apy_year_lag{APY_LAG_YEARS}", f"apy_production_tonnes_lag{APY_LAG_YEARS}",
         f"apy_area_ha_lag{APY_LAG_YEARS}", f"apy_yield_t_per_ha_lag{APY_LAG_YEARS}"]]


# ---------------------------------------------------------------- per crop
def build_features(cleaned: pd.DataFrame, wx: pd.DataFrame, apy_lag: pd.DataFrame) -> pd.DataFrame:
    """Row-preserving feature table for one crop (same rows and source_row as Phase 5)."""
    if any(c.startswith("modal_roll") for c in cleaned.columns):
        raise FeatureError("input already contains Phase 6 features; build from Phase 5 output only")
    n0 = len(cleaned)
    s, gid = series_order(cleaned)
    out = s[[c for cols in CARRY.values() for c in cols]].copy()

    # time features: known in advance for any date
    d = s["reported_date"]
    out["year"] = d.dt.year.astype("int16")
    out["month"] = d.dt.month.astype("int8")
    out["quarter"] = d.dt.quarter.astype("int8")
    out["day_of_week"] = d.dt.dayofweek.astype("int8")
    out["month_sin"] = np.sin(2 * np.pi * (out["month"] - 1) / 12)
    out["month_cos"] = np.cos(2 * np.pi * (out["month"] - 1) / 12)
    out["agri_year_start"] = (d.dt.year - (d.dt.month < 7)).astype("int16")      # July-June (D-19)
    out["imd_season"] = pd.Categorical(out["month"].map(IMD_SEASON))

    out = out.assign(**history_features(s, gid, MODAL, s["usable_modal_price"], "modal",
                                        [MIN, MAX], change="pct"))
    out = out.assign(**history_features(s, gid, ARR, s["usable_arrivals"], "arrivals", [], change="abs"))

    # weather: Phase 4 exact-location policy (weather_state/district set only for matched districts)
    out["weather_state"] = out["weather_state"].astype(object)
    out["weather_district"] = out["weather_district"].astype(object)
    out = out.merge(wx, on=["weather_state", "weather_district", "reported_date"], how="left", validate="m:1")

    # APY annual context, lagged two agricultural years (constant within district x agricultural year)
    out[f"apy_year_lag{APY_LAG_YEARS}"] = (out["agri_year_start"] - APY_LAG_YEARS).astype(str) + "-" + (
        out["agri_year_start"] - APY_LAG_YEARS + 1).astype(str)
    for c in ["apy_state", "apy_district"]:
        out[c] = out[c].astype(object)
    out = out.merge(apy_lag, on=["apy_state", "apy_district", f"apy_year_lag{APY_LAG_YEARS}"],
                    how="left", validate="m:1")

    if len(out) != n0 or out["source_row"].duplicated().any():
        raise FeatureError(f"row count changed or source_row duplicated ({n0} -> {len(out)})")
    for c in ["state", "district", "market", "variety", "weather_state", "weather_district",
              "apy_state", "apy_district", "apy_year", f"apy_year_lag{APY_LAG_YEARS}"]:
        out[c] = out[c].astype("category")
    return out.sort_values("source_row").reset_index(drop=True)


# ---------------------------------------------------------------- registry
def feature_registry() -> pd.DataFrame:
    R = []

    def add(name, role, task, definition, inputs, window, missing, available="yes - uses only data dated < t",
            leakage="computed from rows dated strictly before t within the same series", group="series"):
        R.append({"feature": name, "role": role, "task": task, "definition": definition, "inputs": inputs,
                  "grouping": group, "window_or_lag": window, "missing_value_behaviour": missing,
                  "available_at_prediction_time": available, "leakage_risk_and_safeguard": leakage})

    for c in CARRY["identifier"]:
        add(c, "identifier", "-", "key / traceability column (source_row links to Phase 4/5 rows)", c, "-",
            "never missing (market_code may be missing, Phase 4 D-22)", "not a model input",
            "row ids and dates must not be used as predictors", "-")
    for c in CARRY["target"]:
        add(c, "target", "price" if "price" in c else "market arrivals (supply-side activity, not demand)",
            "the row's own same-day value (Phase 5 cleaned)", c, "-", "missing where Phase 5 set/kept missing",
            "no - observed on day t", "never used as an input to any feature for the same or earlier rows", "-")
    for c in CARRY["eligibility_flag"]:
        add(c, "eligibility_flag", "price" if "modal" in c else "arrivals",
            "Phase 5 usable view; decides which rows enter history and which targets are valid", c, "-",
            "never missing", "not a model input", "filter only", "-")
    for c in CARRY["audit_only"]:
        add(c, "audit_only", "-", "Phase 4/5 diagnostic or join key", c, "-", "as in Phase 4/5",
            "not a model input", "post-cleaning diagnostics describe the target row itself", "-")

    t = "all"
    add("year", "predictor", t, "calendar year of reported_date", "reported_date", "-", "never missing",
        "yes - calendar", "deterministic from the date", "-")
    add("month", "predictor", t, "calendar month 1-12", "reported_date", "-", "never missing", "yes - calendar",
        "deterministic", "-")
    add("quarter", "predictor", t, "calendar quarter 1-4", "reported_date", "-", "never missing", "yes - calendar",
        "deterministic", "-")
    add("day_of_week", "predictor", t, "0=Monday..6=Sunday (reporting differs by weekday)", "reported_date", "-",
        "never missing", "yes - calendar", "deterministic", "-")
    add("month_sin / month_cos", "predictor", t, "sin/cos(2*pi*(month-1)/12): cyclical month (Dec next to Jan)",
        "month", "-", "never missing", "yes - calendar", "deterministic", "-")
    add("agri_year_start", "predictor", t, "start year of the July-June agricultural year (APY convention, D-19)",
        "reported_date", "-", "never missing", "yes - calendar", "deterministic", "-")
    add("imd_season", "predictor", t, "IMD meteorological season: winter Jan-Feb, pre_monsoon Mar-May, "
        "monsoon Jun-Sep, post_monsoon Oct-Dec (not a crop harvest calendar)", "month", "-", "never missing",
        "yes - calendar", "deterministic", "-")

    for prefix, task, tgt, elig in [("modal", "price", MODAL, "usable_modal_price"),
                                    ("arrivals", "market arrivals", ARR, "usable_arrivals")]:
        miss = "NaN when the series has no eligible observation before t; never filled"
        add(f"{prefix}_prev_obs", "predictor", task, f"{tgt} of the latest eligible ({elig}) observation of the "
            "series dated before t (previous AVAILABLE observation, not previous calendar day)", f"{tgt}, {elig}",
            "previous observation", miss)
        add(f"{prefix}_prev_obs_days_ago", "predictor", task, "calendar days between t and that previous "
            "observation (exposes irregular reporting)", "reported_date", "previous observation", miss)
        if prefix == "modal":
            for short, col in [("min", MIN), ("max", MAX)]:
                add(f"{short}_price_prev_obs", "predictor", task, f"{col} of the same previous eligible observation",
                    f"{col}, {elig}", "previous observation", miss + "; also NaN if that row's value is missing")
            add("modal_pct_change_prev_obs", "predictor", task, "prev_obs / second-previous eligible obs - 1 "
                "(both before t; prices > 0 after Phase 5)", tgt, "previous two observations",
                "NaN with < 2 eligible observations before t")
        else:
            add("arrivals_change_prev_obs", "predictor", task, "prev_obs - second-previous eligible obs (tonnes); "
                "absolute because genuine zero arrivals make % change undefined", tgt, "previous two observations",
                "NaN with < 2 eligible observations before t")
        for dlag in CAL_LAGS:
            add(f"{prefix}_lag_{dlag}d", "predictor", task, f"{tgt} reported by the series exactly {dlag} calendar "
                f"day(s) before t, if eligible", f"{tgt}, {elig}", f"calendar lag {dlag} day(s)",
                "NaN if the series did not report an eligible value on that exact day (no carry-forward)")
        for w in WINDOWS:
            for k in ["mean", "median", "std", "count"]:
                add(f"{prefix}_roll{w}d_{k}", "predictor", task,
                    f"{k} of eligible {tgt} values dated in [t-{w} days, t) (calendar window, t excluded)",
                    f"{tgt}, {elig}", f"{w} calendar days before t",
                    "count = 0 and other stats NaN when the window is empty; std needs >= 2 values")

    for col, short, agg, windows in WEATHER_SPECS:
        wk = dict(group="weather location (Phase 4 exact state+district)",
                  leakage="computed on the Phase 4 daily panel strictly before t; same-day weather excluded")
        add(f"wx_{short}_prev1d", "predictor", "price / arrivals / supply", f"{col} on calendar day t-1",
            col, "calendar lag 1 day", "NaN without a weather location (73-75% of rows) or before 2001-01-02 / "
            "after 2023-01-01", **wk)
        for w in windows:
            add(f"wx_{short}_{agg}_{w}d", "predictor", "price / arrivals / supply", f"{agg} of {col} over the {w} "
                f"calendar days before t", col, f"{w} calendar days before t",
                "NaN without a location or unless all w days lie inside 2001-01-01..2022-12-31", **wk)
    for c, desc in [("apy_production_tonnes", "production"), ("apy_area_ha", "area"), ("apy_yield_t_per_ha", "yield")]:
        add(f"{c}_lag{APY_LAG_YEARS}", "predictor", "supply / price context", f"APY annual {desc} of the record's "
            f"APY district for agricultural year agri_year_start-{APY_LAG_YEARS} (Phase 4 apy_annual.csv)",
            "apy_annual.csv via apy_state, apy_district", f"{APY_LAG_YEARS} agricultural years",
            "NaN where no APY district, no annual row, or ambiguous annual value (D-20)",
            available=f"assumed yes (A-19): APY for year Y is assumed published before year Y+{APY_LAG_YEARS} starts",
            leakage="lag 2, not lag 1: lag-1 data is published months into the year (D-36); constant within "
                    "district x agricultural year, so it is context, not a daily observation",
            group="crop x APY district")
    add(f"apy_year_lag{APY_LAG_YEARS}", "audit_only", "-", "APY year label joined", "agri_year_start", "-", "never missing",
        "not a model input", "-", "-")
    return pd.DataFrame(R)


# ---------------------------------------------------------------- validation helpers
def spot_check(features: pd.DataFrame, cleaned: pd.DataFrame, n: int = 200, seed: int = 0) -> pd.DataFrame:
    """Brute-force recomputation of history features for sampled rows (strictly-past, same series only)."""
    rng = np.random.default_rng(seed)
    f = features.set_index("source_row")
    c = cleaned.copy()
    idx = rng.choice(len(c), size=min(n, len(c)), replace=False)
    groups = c.groupby(SERIES, observed=True).indices
    rows = []
    for i in idx:
        r = c.iloc[i]
        ser = c.iloc[groups[tuple(r[k] for k in SERIES)]]
        past = ser[ser["reported_date"] < r["reported_date"]]
        pm = past[past["usable_modal_price"]].sort_values("reported_date")
        pa = past[past["usable_arrivals"]].sort_values("reported_date")
        win = pm[pm["reported_date"] >= r["reported_date"] - pd.Timedelta(days=30)][MODAL]
        lag7 = pm[pm["reported_date"] == r["reported_date"] - pd.Timedelta(days=7)][MODAL]
        exp = {"modal_prev_obs": pm[MODAL].iloc[-1] if len(pm) else np.nan,
               "modal_roll30d_mean": win.mean() if len(win) else np.nan,
               "modal_roll30d_count": float(len(win)),
               "modal_lag_7d": lag7.iloc[0] if len(lag7) else np.nan,
               "arrivals_prev_obs": pa[ARR].iloc[-1] if len(pa) else np.nan}
        got = f.loc[r["source_row"]]
        for k, v in exp.items():
            rows.append({"source_row": r["source_row"], "feature": k, "expected": v, "got": got[k],
                         "match": bool((pd.isna(v) and pd.isna(got[k])) or np.isclose(v, got[k]))})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- orchestration
def run_features(clean_dir: Path = CLEAN_DIR, integration_dir: Path = INTEGRATION_DIR,
                 feature_dir: Path = FEATURE_DIR, audit_dir: Path = AUDIT_DIR,
                 crops: list[str] | None = None) -> dict:
    t0 = time.time()
    crops = crops or load_selected_crops()
    if not set(crops) <= {"Onion", "Potato", "Wheat"}:
        raise FeatureError(f"Only Onion/Potato/Wheat are in scope, got {crops}")
    feature_dir, audit_dir = Path(feature_dir), Path(audit_dir)
    feature_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    inputs = [Path(clean_dir) / f"mandi_cleaned_{c.lower()}.parquet" for c in crops] + [
        Path(integration_dir) / "weather_daily_panel.parquet", Path(integration_dir) / "apy_annual.csv"]
    before = {str(p): file_sha256(p) for p in inputs}

    wx = weather_window_features(pd.read_parquet(Path(integration_dir) / "weather_daily_panel.parquet"))
    apy = pd.read_csv(Path(integration_dir) / "apy_annual.csv")
    registry = feature_registry()
    stats, counts, manifest, checks = [], [], [], []

    for crop in crops:
        cleaned = pd.read_parquet(Path(clean_dir) / f"mandi_cleaned_{crop.lower()}.parquet")
        if set(cleaned["crop"].astype(str)) != {crop}:
            raise FeatureError(f"{crop}: input contains other crops")
        feats = build_features(cleaned, wx, apy_lag_table(apy, crop))
        path = feature_dir / f"features_{crop.lower()}.parquet"
        feats.to_parquet(path, index=False)
        reopened = pd.read_parquet(path)

        counts.append({"crop": crop, "input_rows": len(cleaned), "output_rows": len(reopened),
                       "series": int(cleaned.groupby(SERIES, observed=True).ngroups),
                       "input_columns": cleaned.shape[1], "output_columns": reopened.shape[1],
                       "rows_with_usable_modal_target": int(cleaned["usable_modal_price"].sum()),
                       "rows_with_usable_arrivals_target": int(cleaned["usable_arrivals"].sum())})
        for col in reopened.columns:
            v = reopened[col]
            num = pd.api.types.is_numeric_dtype(v) and not pd.api.types.is_bool_dtype(v)
            stats.append({"crop": crop, "column": col, "dtype": str(v.dtype), "non_missing": int(v.notna().sum()),
                          "missing_pct": round(float(v.isna().mean() * 100), 3),
                          "min": float(v.min()) if num and v.notna().any() else None,
                          "median": float(v.median()) if num and v.notna().any() else None,
                          "max": float(v.max()) if num and v.notna().any() else None})
        sc = spot_check(reopened, cleaned)
        checks += [
            {"crop": crop, "check": "row count preserved (input == output)", "passed": len(reopened) == len(cleaned)},
            {"crop": crop, "check": "same source_row set as Phase 5",
             "passed": set(reopened["source_row"]) == set(cleaned["source_row"])},
            {"crop": crop, "check": "registry covers every output column",
             "passed": set(reopened.columns) <= set(registry["feature"].str.split(" / ").explode())},
            {"crop": crop, "check": f"brute-force spot check of history features ({len(sc)} comparisons)",
             "passed": bool(sc["match"].all())},
            {"crop": crop, "check": "no history feature present before the series' first eligible observation",
             "passed": bool(reopened.loc[reopened["modal_roll90d_count"] == 0, "modal_roll90d_mean"].isna().all())},
            {"crop": crop, "check": "same-day weather columns not carried as predictors",
             "passed": not any(c in reopened.columns for c in ["temperature_2m_mean", "rain_sum"])},
        ]
        manifest.append({"file": path.name, "grain": "one row per Phase 5 row (source_row)", "rows": len(reopened),
                         "columns": reopened.shape[1], "content_sha256": frame_fingerprint(reopened)})
        log.info("%s: %d rows, %d columns", crop, len(reopened), reopened.shape[1])
        del cleaned, feats, reopened

    after = {p: file_sha256(Path(p)) for p in before}
    fp = pd.DataFrame([{"path": p, "sha256_before": before[p], "sha256_after": after[p],
                        "unchanged": before[p] == after[p]} for p in before])
    checks.append({"crop": "all", "check": "Phase 4/5 inputs unchanged during run", "passed": bool(fp["unchanged"].all())})
    tables = {"feature_registry.csv": registry, "row_counts.csv": pd.DataFrame(counts),
              "feature_statistics.csv": pd.DataFrame(stats), "validation_report.csv": pd.DataFrame(checks),
              "input_fingerprints.csv": fp, "output_manifest.csv": pd.DataFrame(manifest)}
    for name, frame in tables.items():
        frame.to_csv(audit_dir / name, index=False)
    if not all(c["passed"] for c in checks):
        raise FeatureError(f"validation failed: {[c for c in checks if not c['passed']]}")
    log.info("Phase 6 finished in %.1fs", time.time() - t0)
    return {k.removesuffix(".csv"): v for k, v in tables.items()} | {"seconds": round(time.time() - t0, 1)}
