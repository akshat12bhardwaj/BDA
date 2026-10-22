"""
Phase 8 forecast output contract (version phase8-forecast-v1; Documentation/Forecast_Output_Contract.md).

Builds forecast rows for one forecast origin from the origins table of dataset.build_examples() and checks
them against the contract. This is a batch interface over historical data, NOT a live forecasting service:
  - persistence cells (D-42: every crop x horizon except Onion h=1) are computed here, with no model;
  - the learned cell (Onion h=1, hgb_conservative) has no saved fitted model, so its price is filled only
    from externally supplied, versioned predictions; otherwise status = model_artifact_unavailable and the
    price is null. Nothing is trained here.
No prediction intervals are produced: prediction_interval_available is always False, and the empirical
validation error profile (error_profile.py) is referenced by key instead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from Code.modelling import dataset as d
from Code.modelling.final_evaluation import SELECTED

CONTRACT_VERSION = "phase8-forecast-v1"
PROFILE_VERSION = "phase8-error-profile-v1"
DECISION = "D-42"
SERIES_COLS = ["state", "district", "market", "variety"]
KEY = ["crop"] + SERIES_COLS + ["origin_date", "horizon_weeks"]
STATUSES = ("ok", "model_artifact_unavailable", "model_prediction_missing")

# (column, kind, nullable, unit, description); kind: str | date | int | float | bool
SCHEMA = [
    ("contract_version", "str", False, "-", "always phase8-forecast-v1"),
    ("crop", "str", False, "-", "Onion / Potato / Wheat"),
    ("state", "str", False, "-", "series key (D-33)"),
    ("district", "str", False, "-", "series key (D-33)"),
    ("market", "str", False, "-", "series key (D-33)"),
    ("variety", "str", False, "-", "series key (D-33)"),
    ("origin_week_start", "date", False, "date", "Monday of the origin week W"),
    ("origin_date", "date", False, "date", "Sunday of week W; forecast made at the end of this day"),
    ("horizon_weeks", "int", False, "weeks", "1, 2 or 4"),
    ("target_week_start", "date", False, "date", "Monday of week W+h"),
    ("target_week_end", "date", False, "date", "Sunday of week W+h"),
    ("predicted_median_price_rs_per_quintal", "float", True, "Rs/quintal (nominal)",
     "forecast of the median usable modal price in the target week; null unless prediction_status = ok"),
    ("approach", "str", False, "-", "persistence or hgb_conservative, fixed by D-42"),
    ("feature_config", "str", False, "-", "none (persistence) or weather"),
    ("selection_decision", "str", False, "-", "always D-42"),
    ("model_version", "str", True, "-", "version of the supplied learned predictions; null for persistence"),
    ("prediction_status", "str", False, "-", "ok / model_artifact_unavailable / model_prediction_missing"),
    ("in_primary_population", "bool", False, "-", ">= 365 distinct usable price dates on or before the origin (D-41)"),
    ("n_usable_price_dates_to_origin", "int", False, "days", "distinct usable price dates dated <= origin"),
    ("origin_week_usable_price_count", "int", False, "rows", "usable price rows in week W (>= 1)"),
    ("origin_week_median_rs_per_quintal", "float", False, "Rs/quintal (nominal)", "median usable modal price in week W"),
    ("anchor_date", "date", False, "date", "last usable price date in week W"),
    ("weather_covered", "bool", False, "-", "all weather predictors present on the anchor row"),
    ("prediction_interval_available", "bool", False, "-", "always False: no validated interval method exists"),
    ("error_profile_key", "str", False, "-", "row key into forecast_error_profile.csv (empirical, not an interval)"),
]
COLUMNS = [c for c, *_ in SCHEMA]


def approach_for(crop: str, h: int) -> tuple[str, str]:
    return SELECTED.get((crop, h), ("persistence", "none"))


def forecast_table(origins: pd.DataFrame, crop: str, origin_date, last_date, learned: pd.DataFrame | None = None,
                   horizons=d.HORIZONS) -> pd.DataFrame:
    """
    Forecast rows for every series with >= 1 usable price in the week ending origin_date (a Sunday).
    `learned` (optional): columns SERIES_COLS + origin_date, horizon_weeks, approach, model_version,
    predicted_median_price_rs_per_quintal - only for D-42 learned cells.
    """
    origin = pd.Timestamp(origin_date)
    if origin.dayofweek != 6:
        raise d.ModellingError("origin_date must be a Sunday (end of the origin week)")
    if origin > pd.Timestamp(last_date):
        raise d.ModellingError("origin_date is after the last reported date of the input")
    o = origins[origins["origin_date"] == origin]
    if learned is not None:
        bad = learned[[approach_for(crop, h)[0] != a for h, a in zip(learned["horizon_weeks"], learned["approach"])]]
        if len(bad):
            raise d.ModellingError("learned predictions supplied for a cell D-42 assigns to another approach")
    rows = []
    for h in horizons:
        approach, config = approach_for(crop, h)
        f = pd.DataFrame({
            "contract_version": CONTRACT_VERSION, "crop": crop,
            **{c: o[c].astype(str).to_numpy() for c in SERIES_COLS},
            "origin_week_start": o["week_start"].to_numpy(), "origin_date": o["origin_date"].to_numpy(),
            "horizon_weeks": h,
            "target_week_start": (o["week_start"] + pd.Timedelta(weeks=h)).to_numpy(),
            "target_week_end": (o["week_start"] + pd.Timedelta(weeks=h, days=6)).to_numpy(),
            "approach": approach, "feature_config": config, "selection_decision": DECISION,
            "in_primary_population": o["eligible_at_origin"].to_numpy(),
            "n_usable_price_dates_to_origin": o["n_usable_dates_to_origin"].astype(int).to_numpy(),
            "origin_week_usable_price_count": o["origin_week_n"].astype(int).to_numpy(),
            "origin_week_median_rs_per_quintal": o["origin_week_median"].astype(float).to_numpy(),
            "anchor_date": o["anchor_date"].to_numpy(), "weather_covered": o["weather_covered"].astype(bool).to_numpy(),
            "prediction_interval_available": False,
            "error_profile_key": f"{PROFILE_VERSION}|{crop}|h{h}|{approach}"})
        if approach == "persistence":
            f["predicted_median_price_rs_per_quintal"] = f["origin_week_median_rs_per_quintal"]
            f["model_version"], f["prediction_status"] = None, "ok"
        elif learned is None:
            f["predicted_median_price_rs_per_quintal"] = np.nan
            f["model_version"], f["prediction_status"] = None, "model_artifact_unavailable"
        else:
            lk = SERIES_COLS + ["origin_date", "horizon_weeks"]
            sup = learned[(learned["horizon_weeks"] == h)][lk + ["model_version", "predicted_median_price_rs_per_quintal"]]
            sup = sup.assign(origin_date=pd.to_datetime(sup["origin_date"]))
            f = f.merge(sup, on=lk, how="left", validate="1:1")
            f["prediction_status"] = np.where(f["predicted_median_price_rs_per_quintal"].notna(), "ok", "model_prediction_missing")
        rows.append(f[COLUMNS])
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=COLUMNS)
    out = out.sort_values(KEY, ignore_index=True)
    validate_forecasts(out)
    return out


def validate_forecasts(f: pd.DataFrame) -> None:
    """Raise unless every row satisfies the phase8-forecast-v1 contract."""
    if list(f.columns) != COLUMNS:
        raise d.ModellingError(f"columns differ from the contract: {sorted(set(f.columns) ^ set(COLUMNS))}")
    kinds = {c: k for c, k, *_ in SCHEMA}
    for c, nullable in [(c, n) for c, _, n, *_ in SCHEMA]:
        if not nullable and f[c].isna().any():
            raise d.ModellingError(f"null values in non-nullable column {c}")
    for c, k in kinds.items():
        ok = {"date": pd.api.types.is_datetime64_any_dtype, "int": pd.api.types.is_integer_dtype,
              "float": pd.api.types.is_float_dtype, "bool": pd.api.types.is_bool_dtype,
              "str": lambda s: s.dropna().map(lambda v: isinstance(v, str)).all()}[k](f[c])
        if not ok:
            raise d.ModellingError(f"column {c} is not of kind {k}")
    if f.duplicated(KEY).any():
        raise d.ModellingError("duplicate forecast key")
    h = pd.to_timedelta(f["horizon_weeks"] * 7, unit="D")
    price = f["predicted_median_price_rs_per_quintal"]
    expected = [approach_for(c, hw) for c, hw in zip(f["crop"], f["horizon_weeks"])]
    checks = {
        "contract version": (f["contract_version"] == CONTRACT_VERSION).all(),
        "horizon in 1/2/4": f["horizon_weeks"].isin(d.HORIZONS).all(),
        "origin is a Sunday ending the origin week": (f["origin_date"].dt.dayofweek == 6).all()
                                                     and (f["origin_date"] - f["origin_week_start"] == pd.Timedelta(days=6)).all(),
        "target week is W+h, Monday-Sunday": (f["target_week_start"] == f["origin_week_start"] + h).all()
                                             and (f["target_week_end"] - f["target_week_start"] == pd.Timedelta(days=6)).all(),
        "anchor inside the origin week": f["anchor_date"].between(f["origin_week_start"], f["origin_date"]).all(),
        "approach and feature config follow D-42": [(a, c) for a, c in zip(f["approach"], f["feature_config"])] == expected,
        "decision reference": (f["selection_decision"] == DECISION).all(),
        "status values": f["prediction_status"].isin(STATUSES).all(),
        "price present and > 0 exactly when status = ok": ((f["prediction_status"] == "ok") == (price.notna() & (price > 0))).all(),
        "persistence price equals the origin-week median": np.allclose(
            price[f["approach"] == "persistence"], f.loc[f["approach"] == "persistence", "origin_week_median_rs_per_quintal"]),
        "persistence has no model version": f.loc[f["approach"] == "persistence", "model_version"].isna().all(),
        "primary population follows D-41 at the origin": (f["in_primary_population"] ==
                                                          (f["n_usable_price_dates_to_origin"] >= d.MIN_USABLE_DATES)).all(),
        "origin week has a usable price": (f["origin_week_usable_price_count"] >= 1).all(),
        "no prediction intervals": (~f["prediction_interval_available"]).all(),
        "error profile key matches the row": (f["error_profile_key"] == PROFILE_VERSION + "|" + f["crop"] + "|h"
                                              + f["horizon_weeks"].astype(str) + "|" + f["approach"]).all(),
    }
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise d.ModellingError(f"forecast contract checks failed: {failed}")
