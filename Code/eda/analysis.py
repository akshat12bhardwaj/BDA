"""
Phase 7 — EDA summary computations (no models, no forecasting).

Reads Processed_Data/features/features_<crop>.parquet (Phase 6, immutable) plus Phase 4/5
audit tables, and writes machine-readable summaries to Processed_Data/eda/. Every table states
its analysis sample in a `sample` column (see SAMPLES). Prices are nominal Rs/quintal; no
inflation adjustment is made anywhere.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from Code.features.pipeline import (ARR, FEATURE_DIR, MODAL, SERIES,
                                    FeatureError, feature_registry)
from Code.integration.pipeline import OUT_DIR as INTEGRATION_DIR, file_sha256, load_selected_crops

log = logging.getLogger("phase7_eda")
EDA_DIR = Path("Processed_Data/eda")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

SAMPLES = {
    "all_rows": "every Phase 6 row (incl. conflicts and flagged rows)",
    "price_present": "rows with a non-missing modal price (any flag)",
    "usable_price": "usable_modal_price = True (Phase 5 view)",
    "usable_price_excl_review": "usable_modal_price and price_extreme_level != review",
    "usable_arrivals": "usable_arrivals = True (Phase 5 view)",
    "usable_arrivals_excl_review": "usable_arrivals and arrivals_extreme_level != review",
}


class EDAError(FeatureError):
    """Raised when an EDA reconciliation check fails."""


def masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "all_rows": pd.Series(True, index=df.index),
        "price_present": df[MODAL].notna(),
        "usable_price": df["usable_modal_price"],
        "usable_price_excl_review": df["usable_modal_price"] & (df["price_extreme_level"] != "review"),
        "usable_arrivals": df["usable_arrivals"],
        "usable_arrivals_excl_review": df["usable_arrivals"] & (df["arrivals_extreme_level"] != "review"),
    }


QUANTS = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]


def distribution(df: pd.DataFrame, col: str, ms: dict, samples: list[str], crop: str) -> list[dict]:
    rows = []
    for s in samples:
        v = df.loc[ms[s], col]
        q = v.quantile(QUANTS)
        rows.append({"crop": crop, "variable": col, "sample": s, "rows_in_sample": int(len(v)),
                     "non_missing": int(v.notna().sum()), "min": v.min(), "mean": v.mean(), "std": v.std(),
                     **{f"p{int(k * 100):02d}": q[k] for k in QUANTS}, "max": v.max(),
                     "cv": v.std() / v.mean() if v.mean() else np.nan})
    return rows


def yearly(df: pd.DataFrame, mask: pd.Series, col: str, crop: str, sample: str) -> pd.DataFrame:
    d = df.loc[mask]
    g = d.groupby(d["reported_date"].dt.year)
    out = pd.DataFrame({"rows": g.size(), "series_active": g.apply(lambda x: x[SERIES].drop_duplicates().shape[0]),
                        "markets_active": g.apply(lambda x: x[["state", "district", "market"]].drop_duplicates().shape[0]),
                        "median": g[col].median(), "p25": g[col].quantile(0.25), "p75": g[col].quantile(0.75),
                        "sum": g[col].sum()})
    out.index.name = "year"
    return out.reset_index().assign(crop=crop, variable=col, sample=sample)


def seasonal_index(df: pd.DataFrame, mask: pd.Series, col: str, crop: str, sample: str,
                   min_obs: int = 20) -> pd.DataFrame:
    """
    value / median of the same series in the same calendar year (series-years with >= min_obs
    observations), summarised by calendar month. Dividing by the series-year median removes market
    level, variety level and the year's (nominal) price level, so months are comparable across
    decades without an inflation index.
    """
    d = df.loc[mask & df[col].notna(), SERIES + ["reported_date", col]].copy()
    d["year"] = d["reported_date"].dt.year
    g = d.groupby(SERIES + ["year"], observed=True)[col]
    d["_n"], d["_med"], d["_mean"] = g.transform("size"), g.transform("median"), g.transform("mean")
    d = d[(d["_n"] >= min_obs) & (d["_med"] > 0)].copy()
    d["rel"] = d[col] / d["_med"]
    d["rel_mean"] = d[col] / d["_mean"]   # mean-based version: informative for skewed arrivals
    d["month"] = d["reported_date"].dt.month
    m = d.groupby("month")
    out = pd.DataFrame({"rows": m.size(), "median_rel": m["rel"].median(), "p25_rel": m["rel"].quantile(0.25),
                        "p75_rel": m["rel"].quantile(0.75), "mean_rel_to_series_year_mean": m["rel_mean"].mean()
                        }).reindex(range(1, 13))
    out.index.name = "month"
    return out.reset_index().assign(crop=crop, variable=col, sample=sample,
                                    series_years=d.groupby(SERIES + ["year"], observed=True).ngroups)


def series_table(df: pd.DataFrame, crop: str) -> pd.DataFrame:
    """One row per series: coverage, reporting density and price/arrivals level and variability."""
    u = df[df["usable_modal_price"]]
    g_all = df.groupby(SERIES, observed=True)
    g_u = u.groupby(SERIES, observed=True)
    out = pd.DataFrame({
        "rows": g_all.size(),
        "conflict_rows": g_all["dup_status"].apply(lambda s: int((s == "conflict_unresolved").sum())),
        "usable_price_rows": g_u.size(),
        "first_date": g_u["reported_date"].min(), "last_date": g_u["reported_date"].max(),
        "distinct_usable_dates": g_u["reported_date"].nunique(),
        "median_modal": g_u[MODAL].median(), "cv_modal": g_u[MODAL].std() / g_u[MODAL].mean(),
        "median_abs_pct_change": u["modal_pct_change_prev_obs"].abs().groupby([u[k] for k in SERIES], observed=True).median(),
        "median_arrivals": df[df["usable_arrivals"]].groupby(SERIES, observed=True)[ARR].median(),
    })
    out["usable_price_rows"] = out["usable_price_rows"].fillna(0).astype(int)
    out["span_days"] = (out["last_date"] - out["first_date"]).dt.days + 1
    out["reporting_density"] = out["distinct_usable_dates"] / out["span_days"]
    return out.reset_index().assign(crop=crop)


def variety_table(df: pd.DataFrame, crop: str) -> pd.DataFrame:
    u = df[df["usable_modal_price"]]
    g = u.groupby("variety", observed=True)
    out = pd.DataFrame({"usable_price_rows": g.size(),
                        "series": g[SERIES].apply(lambda x: x.drop_duplicates().shape[0]),
                        "median_modal": g[MODAL].median(), "p25_modal": g[MODAL].quantile(0.25),
                        "p75_modal": g[MODAL].quantile(0.75)})
    out["share_of_usable_rows"] = out["usable_price_rows"] / len(u)
    return out.sort_values("usable_price_rows", ascending=False).reset_index().assign(crop=crop)


def within_series_spearman(df: pd.DataFrame, mask: pd.Series, a: str, b: str, min_obs: int = 60) -> pd.Series:
    """Spearman correlation of a and b within each series (series with >= min_obs paired rows)."""
    d = df.loc[mask & df[a].notna() & df[b].notna(), SERIES + [a, b]]
    d = d[d.groupby(SERIES, observed=True)[a].transform("size") >= min_obs]
    d = d.assign(ra=d.groupby(SERIES, observed=True)[a].rank(), rb=d.groupby(SERIES, observed=True)[b].rank())
    with np.errstate(invalid="ignore", divide="ignore"):
        r = d.groupby(SERIES, observed=True)[["ra", "rb"]].apply(lambda x: x["ra"].corr(x["rb"]))
    return r.dropna()   # constant series (no variation) have no defined correlation


def corr_summary(r: pd.Series, crop: str, label: str, sample: str) -> dict:
    return {"crop": crop, "relationship": label, "sample": sample, "series": int(len(r)),
            "median_spearman": r.median(), "p25": r.quantile(0.25), "p75": r.quantile(0.75),
            "share_negative": float((r < 0).mean()) if len(r) else np.nan}


def horizon_feasibility(df: pd.DataFrame, crop: str, horizons=(1, 7, 14, 30), tol: int = 3) -> pd.DataFrame:
    """
    From every usable price observation (origin date o), how often does the same series have a
    usable price exactly on o+h, within +-tol days of o+h, and what is the next observation's gap?
    """
    u = df.loc[df["usable_modal_price"], SERIES + ["reported_date"]].copy()
    u["_g"] = u.groupby(SERIES, observed=True, sort=False).ngroup()
    obs = u[["_g", "reported_date"]].drop_duplicates()
    rows = []
    for h in horizons:
        tgt = obs.assign(reported_date=obs["reported_date"] + pd.Timedelta(days=h))
        exact = tgt.merge(obs.assign(_hit=True), on=["_g", "reported_date"], how="left")["_hit"].notna()
        near = pd.merge_asof(tgt.sort_values("reported_date").reset_index(),
                             obs.rename(columns={"reported_date": "obs_date"}).sort_values("obs_date"),
                             left_on="reported_date", right_on="obs_date", by="_g", direction="nearest",
                             tolerance=pd.Timedelta(days=tol))
        rows.append({"crop": crop, "horizon_days": h, "origins": len(obs),
                     "share_exact_day_observed": float(exact.mean()),
                     f"share_observed_within_pm{tol}d": float(near["obs_date"].notna().mean())})
    gaps = obs.sort_values(["_g", "reported_date"]).groupby("_g")["reported_date"].diff().dt.days.dropna()
    for r in rows:
        r["next_obs_gap_median_days"] = gaps.median()
        r["next_obs_gap_p90_days"] = gaps.quantile(0.9)
    return pd.DataFrame(rows)


def weekly_feasibility(df: pd.DataFrame, crop: str, horizons=(1, 2, 4)) -> pd.DataFrame:
    """Share of series-weeks with a usable price whose week h weeks later also has >= 1 usable price
    (weeks = Monday-start calendar weeks, counted by date difference, so year boundaries are handled)."""
    u = df.loc[df["usable_modal_price"], SERIES + ["reported_date"]].copy()
    u["_g"] = u.groupby(SERIES, observed=True, sort=False).ngroup()
    u["week"] = (u["reported_date"] - pd.to_timedelta(u["reported_date"].dt.dayofweek, unit="D")).dt.normalize()
    wk = u[["_g", "week"]].drop_duplicates()
    rows = []
    for h in horizons:
        tgt = wk.assign(week=wk["week"] + pd.Timedelta(weeks=h))
        hit = tgt.merge(wk.assign(_hit=True), on=["_g", "week"], how="left")["_hit"].notna()
        rows.append({"crop": crop, "horizon_weeks": h, "origin_series_weeks": len(wk),
                     "share_target_week_observed": float(hit.mean())})
    return pd.DataFrame(rows)


def split_evidence(df: pd.DataFrame, crop: str) -> pd.DataFrame:
    """Per year: usable price rows, active series, weather coverage, and how many of that year's
    series already had usable history in earlier years (needed for out-of-time evaluation)."""
    u = df[df["usable_modal_price"]].copy()
    u["year"] = u["reported_date"].dt.year
    u["_g"] = u.groupby(SERIES, observed=True).ngroup()
    first_year = u.groupby("_g")["year"].transform("min")
    g = u.groupby("year")
    return pd.DataFrame({
        "usable_price_rows": g.size(), "series_active": g["_g"].nunique(),
        "series_with_earlier_history": u[first_year < u["year"]].groupby("year")["_g"].nunique(),
        "share_rows_with_weather_features": g["wx_rain_sum_30d"].apply(lambda s: s.notna().mean()),
        "share_rows_with_apy_lag2": g["apy_production_tonnes_lag2"].apply(lambda s: s.notna().mean()),
    }).fillna({"series_with_earlier_history": 0}).reset_index().assign(crop=crop)


def review_effect(df: pd.DataFrame, crop: str) -> list[dict]:
    """How much the review-flagged rows change headline statistics (usable views)."""
    ms = masks(df)
    out = []
    for col, base, excl in [(MODAL, "usable_price", "usable_price_excl_review"),
                            (ARR, "usable_arrivals", "usable_arrivals_excl_review")]:
        a, b = df.loc[ms[base], col], df.loc[ms[excl], col]
        out.append({"crop": crop, "variable": col, "rows_with": len(a), "rows_without": len(b),
                    "review_rows": len(a) - len(b), "review_share": (len(a) - len(b)) / len(a),
                    "median_with": a.median(), "median_without": b.median(),
                    "mean_with": a.mean(), "mean_without": b.mean(),
                    "std_with": a.std(), "std_without": b.std(),
                    "p99_with": a.quantile(0.99), "p99_without": b.quantile(0.99)})
    return out


def quality_table(df: pd.DataFrame, crop: str, series: pd.DataFrame, registry: pd.DataFrame) -> list[dict]:
    n = len(df)
    pred = [c for c in registry.loc[registry["role"] == "predictor", "feature"].str.split(" / ").explode()
            if c in df.columns]
    r = [("rows", n), ("series (crop x market x variety)", len(series)),
         ("markets", df[["state", "district", "market"]].drop_duplicates().shape[0]),
         ("first_date", str(df["reported_date"].min().date())), ("last_date", str(df["reported_date"].max().date())),
         ("conflict_unresolved rows", int((df["dup_status"] == "conflict_unresolved").sum())),
         ("price scale_error_suspected rows", int((df["price_extreme_level"] == "scale_error_suspected").sum())),
         ("price review rows", int((df["price_extreme_level"] == "review").sum())),
         ("arrivals entry_error_suspected rows", int((df["arrivals_extreme_level"] == "entry_error_suspected").sum())),
         ("arrivals review rows", int((df["arrivals_extreme_level"] == "review").sum())),
         ("modal target missing (of all rows)", int(df[MODAL].isna().sum())),
         ("rows not usable_modal_price", int((~df["usable_modal_price"]).sum())),
         ("rows not usable_arrivals", int((~df["usable_arrivals"]).sum())),
         ("series with 0 usable price rows", int((series["usable_price_rows"] == 0).sum())),
         ("series with < 30 usable price rows", int((series["usable_price_rows"] < 30).sum())),
         ("series with >= 365 usable price rows", int((series["usable_price_rows"] >= 365).sum())),
         ("usable price rows in series with >= 365 usable rows",
          int(series.loc[series["usable_price_rows"] >= 365, "usable_price_rows"].sum()))]
    out = [{"crop": crop, "metric": k, "value": v, "denominator": "all rows" if "rows" in k else "-"} for k, v in r]
    for c in pred:
        out.append({"crop": crop, "metric": f"missing % (predictor) {c}", "value": round(df[c].isna().mean() * 100, 3),
                    "denominator": f"all {n} rows"})
    return out


def conflict_table(df: pd.DataFrame, crop: str) -> pd.DataFrame:
    """Where the Phase 5 unresolved conflicts sit (kept visible; never dropped from EDA)."""
    c = df[df["dup_status"] == "conflict_unresolved"]
    return (c.groupby([c["state"].astype(str), c["reported_date"].dt.year.rename("year")]).size()
            .rename("conflict_rows").reset_index().assign(crop=crop))


def apy_link_assoc(crops) -> pd.DataFrame:
    """District-year association between APY production and mandi arrivals (Phase 4 link table,
    both sides present), per crop and agricultural year: Spearman across districts."""
    m = pd.read_csv(INTEGRATION_DIR / "mandi_apy_district_year.csv")
    m = m[(m["link_status"] == "mandi_and_apy") & m["production_tonnes"].notna() & ~m["mandi_partial_year"].astype(bool)]
    rows = []
    for crop in crops:
        for yr, d in m[m["crop"] == crop].groupby("apy_year"):
            if len(d) >= 20:
                rows.append({"crop": crop, "apy_year": yr, "districts": len(d),
                             "spearman_production_vs_mandi_arrivals": d["production_tonnes"].corr(
                                 d["mandi_arrivals_tonnes_sum"], method="spearman"),
                             "spearman_production_vs_median_modal": d["production_tonnes"].corr(
                                 d["mandi_modal_price_median"], method="spearman")})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- orchestration
def run_eda(feature_dir: Path = FEATURE_DIR, eda_dir: Path = EDA_DIR, crops: list[str] | None = None) -> dict:
    t0 = time.time()
    crops = crops or load_selected_crops()
    eda_dir = Path(eda_dir)
    eda_dir.mkdir(parents=True, exist_ok=True)
    inputs = [Path(feature_dir) / f"features_{c.lower()}.parquet" for c in crops]
    before = {str(p): file_sha256(p) for p in inputs}
    registry = feature_registry()
    T = {k: [] for k in ["distribution", "yearly", "seasonal", "series", "variety", "correlations", "horizon",
                         "split", "review_effect", "quality", "sample_counts", "conflicts", "weekly"]}

    for crop, path in zip(crops, inputs):
        df = pd.read_parquet(path)
        if set(df["crop"].astype(str)) != {crop}:
            raise EDAError(f"{crop}: unexpected crops in {path.name}")
        ms = masks(df)
        T["sample_counts"] += [{"crop": crop, "sample": s, "definition": SAMPLES[s], "rows": int(m.sum()),
                                "share_of_all_rows": float(m.mean())} for s, m in ms.items()]
        T["distribution"] += distribution(df, MODAL, ms, ["price_present", "usable_price", "usable_price_excl_review"], crop)
        T["distribution"] += distribution(df, ARR, ms, ["all_rows", "usable_arrivals", "usable_arrivals_excl_review"], crop)
        T["yearly"] += [yearly(df, ms["usable_price"], MODAL, crop, "usable_price"),
                        yearly(df, ms["usable_arrivals"], ARR, crop, "usable_arrivals")]
        for col, s in [(MODAL, "usable_price"), (MODAL, "usable_price_excl_review"), (ARR, "usable_arrivals")]:
            T["seasonal"].append(seasonal_index(df, ms[s], col, crop, s))
        st = series_table(df, crop)
        T["series"].append(st)
        T["variety"].append(variety_table(df, crop))
        both = ms["usable_price"] & ms["usable_arrivals"]
        pos = both & (df[ARR] > 0)
        T["correlations"].append(corr_summary(within_series_spearman(df, pos, MODAL, ARR), crop,
                                              "same-day modal price vs arrivals (within series)",
                                              "usable_price & usable_arrivals"))
        T["correlations"].append(corr_summary(within_series_spearman(df, ms["usable_price"], MODAL, "modal_prev_obs"),
                                              crop, "modal price vs previous observation (within series)",
                                              "usable_price"))
        wx = ms["usable_price"] & df["wx_rain_sum_30d"].notna() & df["modal_roll90d_mean"].notna()
        rel = df[MODAL] / df["modal_roll90d_mean"]
        dd = df.assign(price_rel_90d=rel)
        for w in ["wx_rain_sum_30d", "wx_temp_mean_mean_30d"]:
            T["correlations"].append(corr_summary(within_series_spearman(dd, wx, "price_rel_90d", w), crop,
                                                  f"price / trailing-90d mean vs {w} (within series)",
                                                  "usable_price with weather features"))
        T["horizon"].append(horizon_feasibility(df, crop))
        T["weekly"].append(weekly_feasibility(df, crop))
        T["split"].append(split_evidence(df, crop))
        T["review_effect"] += review_effect(df, crop)
        T["quality"] += quality_table(df, crop, st, registry)
        T["conflicts"].append(conflict_table(df, crop))
        log.info("%s done", crop)
        del df, dd

    tables = {
        "sample_definitions.csv": pd.DataFrame(T["sample_counts"]),
        "distribution_summary.csv": pd.DataFrame(T["distribution"]),
        "yearly_profile.csv": pd.concat(T["yearly"], ignore_index=True),
        "seasonal_index.csv": pd.concat(T["seasonal"], ignore_index=True),
        "series_summary.csv": pd.concat(T["series"], ignore_index=True),
        "variety_summary.csv": pd.concat(T["variety"], ignore_index=True),
        "relationship_summary.csv": pd.DataFrame(T["correlations"]),
        "horizon_feasibility.csv": pd.concat(T["horizon"], ignore_index=True),
        "weekly_horizon_feasibility.csv": pd.concat(T["weekly"], ignore_index=True),
        "split_evidence.csv": pd.concat(T["split"], ignore_index=True),
        "review_flag_effect.csv": pd.DataFrame(T["review_effect"]),
        "quality_readiness.csv": pd.DataFrame(T["quality"]),
        "conflict_distribution.csv": pd.concat(T["conflicts"], ignore_index=True),
        "apy_district_year_association.csv": apy_link_assoc(crops),
    }
    for name, frame in tables.items():
        frame.to_csv(eda_dir / name, index=False)
    after = {p: file_sha256(Path(p)) for p in before}
    fp = pd.DataFrame([{"path": p, "sha256_before": before[p], "sha256_after": after[p],
                        "unchanged": before[p] == after[p]} for p in before])
    fp.to_csv(eda_dir / "input_fingerprints.csv", index=False)
    if not fp["unchanged"].all():
        raise EDAError("Phase 6 feature files changed during EDA")
    log.info("Phase 7 EDA tables written in %.1fs", time.time() - t0)
    return {k.removesuffix(".csv"): v for k, v in tables.items()} | {"input_fingerprints": fp,
                                                                     "seconds": round(time.time() - t0, 1)}
