"""
Validation checks for collected weather data. Every check is reported, not
silently corrected — questionable values are flagged for a human/future
phase to decide on, never auto-"fixed" here.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_BASE_COLUMNS = {"state", "district", "date", "latitude", "longitude"}

# Loose sanity bounds for India, used only to flag physically implausible
# values — never to silently alter them.
PLAUSIBLE_RANGES = {
    "temperature_2m_mean": (-10, 55),
    "temperature_2m_max": (-5, 55),
    "temperature_2m_min": (-15, 45),
    "rain_sum": (0, 1000),
    "relative_humidity_2m_mean": (0, 100),
    "wind_speed_10m_mean": (0, 150),
    "et0_fao_evapotranspiration": (0, 25),
}


def validate_weather_dataset(df: pd.DataFrame, expected_start: str, expected_end: str,
                              variables: list[str]) -> dict:
    report = {"rows": len(df)}

    missing_cols = REQUIRED_BASE_COLUMNS - set(df.columns)
    report["missing_required_columns"] = sorted(missing_cols)

    missing_var_cols = [v for v in variables if v not in df.columns]
    report["missing_variable_columns"] = missing_var_cols

    if len(df) == 0 or missing_cols:
        report["date_range_ok"] = False
        report["duplicate_dates"] = None
        report["missing_dates_count"] = None
        report["expected_observations"] = len(pd.date_range(expected_start, expected_end, freq="D"))
        report["actual_observations"] = 0
        report["missing_value_counts"] = {}
        report["out_of_range_counts"] = {}
        report["coordinate_valid"] = False
        return report

    expected_days = pd.date_range(expected_start, expected_end, freq="D")
    actual_dates = pd.to_datetime(df["date"])

    report["date_range_ok"] = bool(
        actual_dates.min() >= pd.Timestamp(expected_start) - pd.Timedelta(days=1)
        and actual_dates.max() <= pd.Timestamp(expected_end) + pd.Timedelta(days=1)
    )
    report["duplicate_dates"] = int(actual_dates.duplicated().sum())
    report["missing_dates_count"] = int(len(expected_days) - actual_dates.nunique())
    report["expected_observations"] = len(expected_days)
    report["actual_observations"] = len(df)

    report["missing_value_counts"] = {v: int(df[v].isna().sum()) for v in variables if v in df.columns}

    out_of_range = {}
    for v, (lo, hi) in PLAUSIBLE_RANGES.items():
        if v in df.columns:
            n_bad = int(((df[v] < lo) | (df[v] > hi)).sum())
            if n_bad:
                out_of_range[v] = n_bad
    report["out_of_range_counts"] = out_of_range

    lat, lon = df["latitude"].iloc[0], df["longitude"].iloc[0]
    report["coordinate_valid"] = bool(-90 <= lat <= 90 and -180 <= lon <= 180)
    report["latitude"] = float(lat)
    report["longitude"] = float(lon)

    return report
