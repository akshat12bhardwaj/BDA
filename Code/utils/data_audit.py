"""
Reusable, crop-agnostic dataset inspection helpers.

This module generalizes the audit logic that previously existed as
one-off, hardcoded scripts (Code/inspect_agriculture.py, Code/inspect_top.py):
instead of auditing a fixed list of crops, every function here accepts a
crop name / file path as a parameter so the same code can audit any of the
325 mandi commodity files or the APY dataset. It is read-only: nothing in
this module ever writes into Dataset/.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

MANDI_DIR = Path("Dataset/India Commodity Wise Mandi Dataset")

# Column names are not fully standardized across the 325 mandi files
# (e.g. "Arrivals (Tonnes)" vs "Arrivals", "Min Price (Rs./Quintal)" vs
# "Min Price"). This map normalizes the common variants seen during
# Phase 1 inspection.
MANDI_COLUMN_ALIASES = {
    "Arrivals (Tonnes)": "Arrivals (Tonnes)",
    "Arrivals": "Arrivals (Tonnes)",
    "Min Price (Rs./Quintal)": "Min Price (Rs./Quintal)",
    "Min Price": "Min Price (Rs./Quintal)",
    "Max Price (Rs./Quintal)": "Max Price (Rs./Quintal)",
    "Max Price": "Max Price (Rs./Quintal)",
    "Modal Price (Rs./Quintal)": "Modal Price (Rs./Quintal)",
    "Modal Price": "Modal Price (Rs./Quintal)",
}


def list_mandi_crop_files(mandi_dir: Path = MANDI_DIR) -> list[str]:
    """Return the sorted list of commodity CSV filenames (candidate crop universe)."""
    return sorted(f for f in os.listdir(mandi_dir) if f.lower().endswith(".csv"))


def load_mandi_file(crop_filename: str, mandi_dir: Path = MANDI_DIR,
                     nrows: int | None = None, **read_csv_kwargs) -> pd.DataFrame:
    """Load one mandi commodity CSV with column names normalized via MANDI_COLUMN_ALIASES."""
    path = mandi_dir / crop_filename
    df = pd.read_csv(path, nrows=nrows, **read_csv_kwargs)
    df = df.rename(columns=lambda c: MANDI_COLUMN_ALIASES.get(c, c))
    return df


def mandi_file_record_count(crop_filename: str, mandi_dir: Path = MANDI_DIR) -> int:
    """Cheaply count data rows (excluding header) without loading the file into pandas."""
    path = mandi_dir / crop_filename
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        count = sum(1 for _ in f)
    return max(count - 1, 0)


def basic_csv_profile(path: str | Path, nrows: int | None = None) -> dict:
    """Lightweight structural profile of any CSV: shape, dtypes, missingness, duplicates."""
    df = pd.read_csv(path, nrows=nrows)
    missing = df.isnull().sum()
    return {
        "path": str(path),
        "rows_loaded": len(df),
        "columns": list(df.columns),
        "dtypes": df.dtypes.astype(str).to_dict(),
        "missing_counts": missing.to_dict(),
        "missing_pct": (missing / len(df) * 100).round(2).to_dict() if len(df) else {},
        "duplicate_rows": int(df.duplicated().sum()),
    }


def parse_mixed_dates(series: pd.Series) -> pd.Series:
    """Parse a Reported Date column that may mix 'DD Mon YYYY' and 'YYYY-MM-DD' formats."""
    return pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=True)


# Within a single mandi file the date format was observed to be consistent
# (Phase 1 finding), but it differs *between* files. `pd.to_datetime(...,
# format="mixed")` handles this correctly but parses element-by-element and
# is too slow to run across dozens of multi-million-row files. Detecting the
# format once per file from a sample, then parsing the whole column with a
# single fixed format, is both correct (given the per-file consistency
# finding) and orders of magnitude faster.
_KNOWN_DATE_FORMATS = ["%d %b %Y", "%Y-%m-%d"]


def parse_dates_fast(series: pd.Series, sample_size: int = 200) -> pd.Series:
    """Detect the dominant date format from a sample, then parse the full column with it."""
    sample = series.dropna().head(sample_size)
    best_fmt, best_failures = None, len(sample) + 1
    for fmt in _KNOWN_DATE_FORMATS:
        failures = pd.to_datetime(sample, format=fmt, errors="coerce").isna().sum()
        if failures < best_failures:
            best_fmt, best_failures = fmt, failures
    parsed = pd.to_datetime(series, format=best_fmt, errors="coerce")
    # Fall back to the slower mixed-format parser only for rows the detected
    # format could not handle (keeps the common case fast).
    unparsed = parsed.isna() & series.notna()
    if unparsed.any():
        parsed.loc[unparsed] = parse_mixed_dates(series.loc[unparsed])
    return parsed
