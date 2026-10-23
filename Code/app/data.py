"""
Read-only data layer for the dashboard (spec: Documentation/BigData_and_Dashboard_Spec.md §6). Plain pandas, so it is
testable without Streamlit. Every loader enforces its own boundary:
  - price predictions: validation only (2019-2020, origin <= 2020-12-27); test = the published one-time metrics only;
  - arrivals predictions: validation 2019-2020 and the one-time 2021-2022 test; nothing later;
  - production context: values only for source years <= 2018-19 (D-47); reserved 2019-20 .. 2021-22 as counts only,
    taken from the Phase 10 output manifest; 2022-23 does not exist in the product;
  - no 2023+ holdout row exists in any source, and none is ever read.
Nothing here writes a file, trains, refits or re-scores anything.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

M8 = Path("Processed_Data/modelling/phase08")
M9 = Path("Processed_Data/modelling/phase09_models")
PC = Path("Processed_Data/production_context")
BD = Path("Processed_Data/bigdata")
SERIES = ["state", "district", "market", "variety"]
CROPS = ["Onion", "Potato", "Wheat"]
HORIZONS = [1, 2, 4]
PRICE_PERIODS = {"val_2019", "val_2020"}
PRICE_LAST_ORIGIN = pd.Timestamp("2020-12-27")
ARRIVAL_PERIODS = {"val_2019", "val_2020", "test_2021", "test_2022"}
DESIGN_END = "2018-2019"
RESERVED = ("2019-2020", "2020-2021", "2021-2022")
PRODUCTION_VALUES = ["production_tonnes", "area_ha", "yield_t_per_ha"]


class BoundaryError(RuntimeError):
    pass


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise BoundaryError(msg)


# ---------------------------------------------------------------- prices (Phase 8, D-42)
PRICE_FILE = M8 / "hgb_conservative_validation_predictions.parquet"
ARRIVALS_VAL_FILE = M9 / "candidate_predictions.parquet"
ARRIVALS_TEST_FILE = M9 / "test_2021_2022" / "test_predictions.parquet"
# These three are git-ignored (*.parquet). The test file is written only by the one-time 2021-2022 arrivals test
# (run-once guard), so a fresh clone cannot regenerate it; the app then shows metrics only.
PREDICTION_FILES = {"price": [PRICE_FILE], "arrivals": [ARRIVALS_VAL_FILE, ARRIVALS_TEST_FILE]}


def missing_prediction_files(kind: str) -> list[str]:
    return [p.as_posix() for p in PREDICTION_FILES[kind] if not p.exists()]


def price_series(crop: str, horizon: int, top: int = 200) -> pd.DataFrame:
    """The series with the most validation origins, for the selector."""
    df = pq.read_table(PRICE_FILE, columns=SERIES + ["origin_date"],
                       filters=[("crop", "=", crop), ("horizon_weeks", "=", horizon), ("experiment", "=", "primary"),
                                ("config", "=", "no_weather")]).to_pandas()
    return df.groupby(SERIES).size().rename("origins").reset_index().sort_values(
        ["origins"] + SERIES, ascending=[False] + [True] * 4).head(top).reset_index(drop=True)


def price_predictions(crop: str, horizon: int, series: tuple, config: str = "no_weather") -> pd.DataFrame:
    """Observed weekly median price, persistence and the conservative-HGB prediction for one series (validation)."""
    filters = [("crop", "=", crop), ("horizon_weeks", "=", horizon), ("experiment", "=", "primary"),
               ("config", "=", config)] + [(c, "=", v) for c, v in zip(SERIES, series)]
    df = pq.read_table(PRICE_FILE, columns=["origin_date", "period", "y", "persistence", "yhat"],
                       filters=filters).to_pandas().sort_values("origin_date").reset_index(drop=True)
    _check(set(df["period"]) <= PRICE_PERIODS, f"price rows outside validation: {set(df['period'])}")
    _check(df.empty or df["origin_date"].max() <= PRICE_LAST_ORIGIN, "price origin after the validation cutoff")
    return df.rename(columns={"y": "observed", "yhat": "hgb_conservative"})


def price_metrics() -> dict[str, pd.DataFrame]:
    """Validation skill of conservative HGB vs persistence, and the published one-time 2021-2022 test (D-42)."""
    v = pd.read_csv(M8 / "hgb_conservative_validation_metrics.csv")
    v = v[(v["experiment"] == "primary") & (v["subset"] == "all")]
    val = v.assign(rel_mae_improvement_pct=100 * v["skill_mae_vs_persistence"])[
        ["crop", "horizon_weeks", "config", "period", "n", "mae", "persistence_mae", "rel_mae_improvement_pct"]]
    test = pd.read_csv(M8 / "test_results.csv")[["crop", "horizon_weeks", "approach", "config", "period", "n_obs", "mae",
                                                 "persistence_mae", "rel_mae_improvement_pct"]]
    _check(set(test["period"]) <= {"test_2021", "test_2022", "test_combined"}, "unexpected Phase 8 test period")
    return {"validation": val.reset_index(drop=True), "test": test}


# ---------------------------------------------------------------- arrivals (Phase 9, D-45)
def arrivals_metrics() -> dict[str, pd.DataFrame]:
    sel = pd.read_csv(M9 / "candidate_selection.csv")
    test = pd.read_csv(M9 / "test_2021_2022" / "test_metrics.csv")
    _check(set(test["period"]) <= {"test_2021", "test_2022", "test_combined"}, "unexpected Phase 9 test period")
    return {"selection": sel, "test": test}


def arrivals_series(crop: str, horizon: int, top: int = 200) -> pd.DataFrame:
    df = pq.read_table(ARRIVALS_TEST_FILE, columns=SERIES,
                       filters=[("crop", "=", crop), ("horizon_weeks", "=", horizon),
                                ("population", "=", "primary")]).to_pandas()
    return df.groupby(SERIES).size().rename("test_weeks").reset_index().sort_values(
        ["test_weeks"] + SERIES, ascending=[False] + [True] * 4).head(top).reset_index(drop=True)


def arrivals_predictions(crop: str, horizon: int, series: tuple) -> pd.DataFrame:
    """Observed arrivals, persistence and conservative HGB for one series: validation 2019-2020 and test 2021-2022.
    The stored examples carry no date, so rows are numbered in their stored order within each period."""
    f = [("crop", "=", crop), ("horizon_weeks", "=", horizon), ("population", "=", "primary")] + \
        [(c, "=", v) for c, v in zip(SERIES, series)]
    cols = ["period", "row", "y", "persistence", "hgb_conservative"]
    val = pq.read_table(ARRIVALS_VAL_FILE, columns=cols,
                        filters=f + [("candidate", "=", "hgb_conservative")]).to_pandas()
    test = pq.read_table(ARRIVALS_TEST_FILE, columns=cols, filters=f).to_pandas()
    df = pd.concat([val, test], ignore_index=True).sort_values(["period", "row"]).reset_index(drop=True)
    _check(set(df["period"]) <= ARRIVAL_PERIODS, f"arrivals rows outside validation/test: {set(df['period'])}")
    return df.rename(columns={"y": "observed"})


# ---------------------------------------------------------------- production context (Phase 10, D-46 - D-48)
def production_design() -> pd.DataFrame:
    """Design-window rows only (source years <= 2018-19). Later rows are dropped as the file is read."""
    parts = [c[c["source_apy_year"] <= DESIGN_END] for c in pd.read_csv(PC / "production_context_v1.csv", chunksize=5000)]
    df = pd.concat(parts, ignore_index=True)
    _check(df["source_apy_year"].max() <= DESIGN_END, "a production row after 2018-19 was returned")
    return df


def production_reserved_counts() -> pd.DataFrame:
    """Counts per crop x reserved source year x pq_class, from the Phase 10 output manifest (no values)."""
    man = pd.read_csv(PC / "output_manifest.csv", dtype=str)
    c = man[man["item"] == "counts"]
    parts = c["name"].str.split("|", expand=True)
    out = pd.DataFrame({"crop": parts[0], "source_apy_year": parts[1], "pq_class": parts[2], "rows": c["value"].astype(int)})
    out = out[out["source_apy_year"].isin(RESERVED)]
    return out.pivot_table(index=["crop", "source_apy_year"], columns="pq_class", values="rows", aggfunc="sum",
                           fill_value=0).reset_index()


def production_summary(df: pd.DataFrame, level: str = "state") -> pd.DataFrame:
    """Totals per crop x source year x (state | district) within ONE comparability class at a time (never merged)."""
    keys = ["crop", "source_apy_year", "annual_comparability"] + (["apy_state"] if level == "state" else ["apy_state", "apy_district"])
    usable = df[df["pq_class"] != "unusable"]
    return usable.groupby(keys, as_index=False).agg(districts=("apy_district", "nunique"),
                                                    production_tonnes=("production_tonnes", "sum"),
                                                    area_ha=("area_ha", "sum"))


# ---------------------------------------------------------------- Big Data component
def bigdata() -> dict[str, pd.DataFrame]:
    names = ["run_manifest", "run_log", "quality_checks", "parity_report", "district_year_spark", "weekly_state_spark",
             "top_districts_spark", "mapreduce_counts", "word_count"]
    return {n: pd.read_csv(BD / f"{n}.csv") for n in names if (BD / f"{n}.csv").exists()}
