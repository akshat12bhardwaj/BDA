"""
Reusable, crop-agnostic feasibility-audit functions for Phase 2.

Each function takes a crop identifier as a parameter and returns a plain
dict of computed statistics — no crop names are hardcoded here, and no
scoring/ranking happens in this module. Scoring/selection judgment stays in
the Phase 2 notebook, where it can be documented alongside the evidence.
"""

from __future__ import annotations

import pandas as pd

from Code.utils.data_audit import load_mandi_file, parse_dates_fast


def mandi_feasibility_stats(mandi_crop_filename: str, apy_crop_name: str | None = None) -> dict:
    """Compute mandi-side feasibility metrics for one crop's CSV file."""
    df = load_mandi_file(mandi_crop_filename)
    dates = parse_dates_fast(df["Reported Date"])
    years = dates.dt.year.dropna()

    n = len(df)
    year_span = int(years.max() - years.min() + 1) if len(years) else 0
    years_with_data = int(years.nunique())
    continuity_ratio = round(years_with_data / year_span, 2) if year_span else 0.0

    min_price = df["Min Price (Rs./Quintal)"]
    max_price = df["Max Price (Rs./Quintal)"]
    modal_price = df["Modal Price (Rs./Quintal)"]
    arrivals = df["Arrivals (Tonnes)"]

    stats = {
        "mandi_crop": mandi_crop_filename[:-4] if mandi_crop_filename.endswith(".csv") else mandi_crop_filename,
        "apy_crop": apy_crop_name,
        "records": n,
        "date_min": dates.min(),
        "date_max": dates.max(),
        "years_with_data": years_with_data,
        "year_span": year_span,
        "continuity_ratio": continuity_ratio,
        "states": df["State Name"].nunique(),
        "districts": df["District Name"].nunique(),
        "markets": df["Market Name"].nunique(),
        "varieties": df["Variety"].nunique(),
        "price_missing_pct": round(modal_price.isna().mean() * 100, 3),
        "arrivals_missing_pct": round(arrivals.isna().mean() * 100, 3),
        "duplicate_rows": int(df.duplicated().sum()),
        "zero_price_rows": int((modal_price == 0).sum()),
        "min_gt_max_price_rows": int((min_price > max_price).sum()),
    }
    del df
    return stats


def apy_feasibility_stats(apy_df: pd.DataFrame, crop_name: str) -> dict:
    """Compute APY-side feasibility metrics for one crop, given the already-loaded full APY dataframe."""
    sub = apy_df[apy_df["crop_name"] == crop_name]
    n = len(sub)
    if n == 0:
        return {"apy_crop": crop_name, "apy_records": 0}
    return {
        "apy_crop": crop_name,
        "apy_records": n,
        "apy_years": sub["year"].nunique(),
        "apy_year_min": sub["year"].min(),
        "apy_year_max": sub["year"].max(),
        "apy_states": sub["state_name"].nunique(),
        "apy_districts": sub["district_name"].nunique(),
        "apy_seasons": sub["season"].nunique(),
        "apy_production_missing_pct": round(sub["production"].isna().mean() * 100, 2),
        "apy_yield_missing_pct": round(sub["yield"].isna().mean() * 100, 2),
        "apy_zero_production_pct": round((sub["production"] == 0).mean() * 100, 2),
        "apy_zero_yield_pct": round((sub["yield"] == 0).mean() * 100, 2),
    }
