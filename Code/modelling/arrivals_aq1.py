"""
Phase 9 — AQ-1 v1 derived flag table and arrivals baseline reruns under AQ-1 population variants.
Validation 2019-2020 only; input truncated at arrivals.CUTOFF (2020-12-27). No learned model is trained.

Leakage rules (Phase_09_Arrivals_Plan.md §12):
  - AQ-1 flags never touch Phase 4-7 outputs; they live in a separate versioned table (aq1/).
  - Targets (ground truth) are cleaned retrospectively: excluded rows are dropped from the target week's median;
    a target week whose rows are all excluded yields no example.
  - Calendar-factor training at refit r uses a cleaned training target only if every excluded row of that week
    has aq1_available_from <= r; otherwise the original value is used (the flag was not yet knowable).
  - Origin inputs (origin-week median = the persistence forecast) and eligibility stay on the Phase 5 view: an
    origin-week row's AQ-1 class needs >= 2 later reported weeks, so it is never available at the origin.
Variants: original | aq1_likely (policy core) | aq1_likely_and_spikes (sensitivity) |
          Wheat only: aq1_wheat_marmay_review_except_unitsig, aq1_wheat_marmay_review_all.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from Code.features.pipeline import ARR, FEATURE_DIR, MODAL, SERIES
from Code.integration.pipeline import file_sha256, frame_fingerprint
from Code.modelling import arrivals as ar
from Code.modelling import arrivals_quality as aq
from Code.modelling import dataset as d
from Code.modelling.baselines import VALIDATION

AQ1_VERSION = "AQ-1 v1"
AQ_DIR = ar.OUT_DIR / "aq1"
VARIANTS = ["original", "aq1_likely", "aq1_likely_and_spikes",
            "aq1_wheat_marmay_review_except_unitsig", "aq1_wheat_marmay_review_all"]
WHEAT_ONLY = {"aq1_wheat_marmay_review_except_unitsig", "aq1_wheat_marmay_review_all"}
K = SERIES + ["week_start"]
FLAG_COLS = ["source_row"] + SERIES + ["reported_date", "week_start", ARR, "arrivals_extreme_level", "prev_ref",
                                        "next_ref", "r_prev", "r_next", "aq1_class", "aq1_available_from",
                                        "unit_factor_signature", "tiny_value", "high_side", "march_to_may",
                                        "week_reported_days", "usable_modal_price", MODAL]


def flag_table(df: pd.DataFrame, cutoff=ar.CUTOFF) -> pd.DataFrame:
    """AQ-1 v1 flags for every usable arrivals row dated <= cutoff; the input frame is never modified."""
    s = aq.screen(df, cutoff=cutoff)
    ctx = df.loc[:, ["source_row", "usable_modal_price", MODAL]]
    out = s.merge(ctx, on="source_row", how="left", validate="1:1")[FLAG_COLS]
    # Madhya Pradesh 2019-2020 values <= 0.1 t stay marked until the data provider answers (no exclusion implied)
    pending = (out["tiny_value"] & (out["state"].astype(str) == "Madhya Pradesh")
               & out["reported_date"].dt.year.isin([2019, 2020]))
    return out.assign(provider_query_pending=pending, aq1_version=AQ1_VERSION).sort_values(["source_row"], ignore_index=True)


def excluded(flags: pd.DataFrame, variant: str) -> pd.Series:
    if variant not in VARIANTS:
        raise d.ModellingError(f"unknown AQ-1 variant {variant!r}")
    if variant == "original":
        return pd.Series(False, index=flags.index)
    out = flags["aq1_class"].isin(aq.LIKELY_ERRORS)
    if variant == "aq1_likely_and_spikes":
        out |= flags["aq1_class"] == "isolated_spike"
    if variant in WHEAT_ONLY:
        keep = flags["high_side"] & flags["march_to_may"] & (flags["crop"].astype(str) == "Wheat")
        if variant == "aq1_wheat_marmay_review_except_unitsig":
            keep &= ~flags["unit_factor_signature"]
        out &= ~keep
    return out


def clean_weeks(flags: pd.DataFrame, excl: pd.Series) -> pd.DataFrame:
    """Per series-week: median of non-excluded rows (NaN if all excluded) and when the exclusions became knowable."""
    weeks = flags[K].drop_duplicates()
    med = flags[~excl].groupby(K, observed=True)[ARR].median().rename("clean_median").reset_index()
    avail = flags[excl].groupby(K, observed=True)["aq1_available_from"].max().rename("flag_available").reset_index()
    return (weeks.merge(med, on=K, how="left", validate="1:1").merge(avail, on=K, how="left", validate="1:1"))


def variant_predictions(ex: pd.DataFrame, origins: pd.DataFrame, weeks: pd.DataFrame, crop: str, h: int) -> pd.DataFrame:
    tw = weeks.rename(columns={"week_start": "target_week_start"})
    ex = ex.merge(tw, on=SERIES + ["target_week_start"], how="left", validate="1:1")
    ev = ex[ex["period"].isin(VALIDATION) & ex["eligible_at_origin"] & ex["clean_median"].notna()]
    if ev.empty:
        raise d.ModellingError("no validation examples")
    refit = d.refit_date_for(ev["origin_date"], d.refit_schedule())
    cal = pd.Series(np.nan, index=ev.index)
    for r in sorted(refit.unique()):
        tr = d.training_examples(ex, r)
        knowable = tr["flag_available"].notna() & (tr["flag_available"] <= r)
        tr = tr.assign(**{ar.TARGET: tr[ar.TARGET].where(~knowable, tr["clean_median"])}).dropna(subset=[ar.TARGET])
        if tr.empty or tr["target_sunday"].max() > r:
            raise d.ModellingError(f"invalid training set at refit {r.date()}")
        idx = refit.index[refit == r]
        cal[idx] = ar.CalendarAdjustedPersistence().fit(tr).predict(ev.loc[idx])
    return pd.DataFrame({"crop": crop, "horizon_weeks": h, "period": ev["period"], "row": ev.index,
                         **{c: ev[c].astype(str) for c in SERIES if c != "crop"},
                         "y": ev["clean_median"], "y_original": ev[ar.TARGET],
                         "persistence": ev["origin_week_median_arrivals"], "calendar_adjusted_persistence": cal})


def compare(preds: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Metrics per variant on identical rows within the variant, and population changes against the original."""
    met, pop = [], []
    keys = ["crop", "horizon_weeks"]
    for (variant, crop, h), g in preds.groupby(["variant"] + keys, sort=True):
        orig = preds[(preds["variant"] == "original") & (preds["crop"] == crop) & (preds["horizon_weeks"] == h)]
        for period in VALIDATION + ["val_combined"]:
            part = g if period == "val_combined" else g[g["period"] == period]
            op = orig if period == "val_combined" else orig[orig["period"] == period]
            for baseline in ["persistence", "calendar_adjusted_persistence"]:
                m, pm = ar.metrics(part["y"], part[baseline]), ar.metrics(part["y"], part["persistence"])
                met.append({"variant": variant, "crop": crop, "horizon_weeks": h, "period": period, "baseline": baseline,
                            "n_series": part[["state", "district", "market", "variety"]].drop_duplicates().shape[0]} | m
                           | {"skill_log_mae_vs_persistence": 1 - m["log_mae"] / pm["log_mae"] if pm["log_mae"] else np.nan})
            common = part[part["row"].isin(op["row"])]
            pop.append({"variant": variant, "crop": crop, "horizon_weeks": h, "period": period,
                        "examples_original": len(op), "examples_variant": len(part),
                        "examples_dropped": len(op) - len(part), "examples_target_changed": int((common["y"] != common["y_original"]).sum()),
                        "series_original": op[["state", "district", "market", "variety"]].drop_duplicates().shape[0],
                        "series_variant": part[["state", "district", "market", "variety"]].drop_duplicates().shape[0],
                        "persistence_log_mae_original": ar.metrics(op["y"], op["persistence"])["log_mae"],
                        "persistence_log_mae_variant": ar.metrics(part["y"], part["persistence"])["log_mae"],
                        "persistence_log_mae_common_rows_original_target": ar.metrics(common["y_original"], common["persistence"])["log_mae"],
                        "persistence_log_mae_common_rows_cleaned_target": ar.metrics(common["y"], common["persistence"])["log_mae"]})
    return pd.DataFrame(met), pd.DataFrame(pop)


def practical_check(boot: pd.DataFrame, min_rel: float = 2.0) -> pd.DataFrame:
    """Phase 8 §L.2-style reading for the calendar adjustment: CI > 0 in both years (both clusterings) and >= 2%."""
    b = boot[boot["period"].isin(VALIDATION)]
    rows = []
    for (variant, crop, h), g in b.groupby(["variant", "crop", "horizon_weeks"]):
        s = g[g["cluster"] == "series"].set_index("period")
        mk = g[g["cluster"] == "market"].set_index("period")
        rows.append({"variant": variant, "crop": crop, "horizon_weeks": h,
                     "rel_2019_pct": s.loc["val_2019", "rel_log_mae_improvement_pct"],
                     "rel_2020_pct": s.loc["val_2020", "rel_log_mae_improvement_pct"],
                     "ci_above_zero_both_years_both_clusterings": bool((s["verdict"] == "better").all() and (mk["verdict"] == "better").all()),
                     "practical_2pct_both_years": bool((s["rel_log_mae_improvement_pct"] >= min_rel).all())})
    return pd.DataFrame(rows).assign(meets_both=lambda x: x["ci_above_zero_both_years_both_clusterings"] & x["practical_2pct_both_years"])


def mp_placeholder_report(flags: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Wheat Madhya Pradesh tiny values (<= 0.1 t): descriptive tables; nothing is changed or asserted."""
    f = flags.assign(year=flags["reported_date"].dt.year, state=flags["state"].astype(str))
    tiny = f[f["tiny_value"]]
    by_year_state = (tiny.assign(mp=tiny["state"].eq("Madhya Pradesh")).groupby(["year", "mp"]).size()
                     .unstack(fill_value=0).rename(columns={True: "madhya_pradesh", False: "other_states"}).reset_index())
    mp = tiny[(tiny["state"] == "Madhya Pradesh") & tiny["year"].isin([2019, 2020])]
    allmp = f[(f["state"] == "Madhya Pradesh") & f["year"].isin([2019, 2020])]
    per_series = (allmp.groupby(SERIES[1:], observed=True).agg(rows=(ARR, "size"), tiny_rows=("tiny_value", "sum"),
                                                              median_arrivals=(ARR, "median"))
                  .query("tiny_rows > 0").reset_index().sort_values("tiny_rows", ascending=False))
    summary = pd.DataFrame([{
        "rows_tiny_mp_2019_2020": len(mp), "markets": mp["market"].nunique(), "series": mp[SERIES[1:]].drop_duplicates().shape[0],
        "districts": mp["district"].nunique(), "share_of_mp_2019_2020_rows_pct": round(100 * len(mp) / max(len(allmp), 1), 3),
        "value_counts": "; ".join(f"{k:g} t: {v}" for k, v in mp[ARR].value_counts().head(6).items()),
        "aq1_class_counts": "; ".join(f"{k}: {v}" for k, v in mp["aq1_class"].value_counts().items()),
        "with_usable_price_same_row_pct": round(100 * mp["usable_modal_price"].mean(), 1),
        "series_median_level_of_affected_series_t": round(per_series["median_arrivals"].median(), 2),
        "first_date": mp["reported_date"].min().date().isoformat(), "last_date": mp["reported_date"].max().date().isoformat()}])
    by_month = mp.groupby(mp["reported_date"].dt.to_period("M").astype(str)).size().rename("rows").reset_index()
    by_weekday = mp.groupby(mp["reported_date"].dt.day_name()).size().rename("rows").reset_index()
    examples = (mp.sort_values(["market", "reported_date"])
                .groupby("market", observed=True).head(1).head(10)[["district", "market", "variety", "reported_date", ARR,
                                                                     "prev_ref", "next_ref", "aq1_class", MODAL]])
    return {"summary": summary, "by_year_state": by_year_state, "by_month": by_month, "by_weekday": by_weekday,
            "series": per_series.head(25), "examples": examples}


def run_aq1(feature_dir: Path = FEATURE_DIR, out_dir: Path = ar.OUT_DIR, crops: list[str] | None = None,
            expected: dict[str, str] | None = None, registry_path: Path = d.REGISTRY_PATH, b: int | None = None) -> dict:
    t0 = time.time()
    out_dir = Path(out_dir)
    aq_dir = out_dir / "aq1"
    for p in d.PROTECTED_DIRS:
        if out_dir.resolve().is_relative_to(p.resolve()):
            raise d.ModellingError(f"output directory {out_dir} is inside protected {p}")
    crops = crops or d.load_selected_crops()
    inputs = [Path(feature_dir) / f"features_{c.lower()}.parquet" for c in crops] + [Path(registry_path)]
    expected = d.phase7_expected_hashes() if expected is None else expected
    before = d.check_inputs(inputs, expected)
    reg = d.registry_columns(pd.read_csv(registry_path))
    aq_dir.mkdir(parents=True, exist_ok=True)
    preds, manifest, mp = [], [], {}
    for crop, path in zip(crops, inputs):
        df = pd.read_parquet(path)
        d.validate_schema(df, reg, crop)
        df = df[df["reported_date"] <= ar.CUTOFF]
        flags = flag_table(df)
        fpath = aq_dir / f"aq1_flags_v1_{crop.lower()}.parquet"
        flags.to_parquet(fpath, index=False)
        manifest.append({"crop": crop, "file": fpath.name, "rows": len(flags), "max_reported_date": flags["reported_date"].max().date().isoformat(),
                         "content_sha256": frame_fingerprint(flags), "file_sha256": file_sha256(fpath),
                         "provider_query_pending": int(flags["provider_query_pending"].sum()),
                         **{f"class_{c}": int((flags["aq1_class"] == c).sum()) for c in aq.CLASSES}})
        by_h, origins = ar.build_arrivals_examples(df)
        for variant in VARIANTS:
            if variant in WHEAT_ONLY and crop != "Wheat":
                continue
            weeks = clean_weeks(flags, excluded(flags, variant))
            for h, ex in by_h.items():
                ar.validate_arrivals_examples(ex)
                preds.append(variant_predictions(ex, origins, weeks, crop, h).assign(variant=variant))
        if crop == "Wheat":
            mp = mp_placeholder_report(flags)
        del df, flags
    if d.check_inputs(inputs) != before:
        raise d.ModellingError("protected inputs changed during the AQ-1 run")
    p = pd.concat(preds, ignore_index=True)
    metrics, pop = compare(p)
    boot = pd.concat([ar.bootstrap_log_mae(g, b=b).assign(variant=v) for v, g in p.groupby("variant", sort=True)], ignore_index=True)
    prov = pd.DataFrame([{"key": k, "value": v} for k, v in {
        "aq1_version": AQ1_VERSION, "input_cutoff": ar.CUTOFF.date().isoformat(), "test_period_scored": False,
        "holdout_accessed": False, "thresholds": f"review {aq.REVIEW}x, error {aq.ERROR}x (unit factors, D-29/D-30)",
        "references": f"prev {aq.PREV_WEEKS} reported weeks (min {aq.PREV_MIN}); next {aq.NEXT_WEEKS} (min {aq.NEXT_MIN})",
        "variants": ", ".join(VARIANTS), "phase5_outputs_modified": False, "models_fitted": "calendar month factors only",
        **{f"input_sha256 {Path(k).name}": v for k, v in before.items()}, "seconds": round(time.time() - t0, 1)}.items()])
    tables = {"arrivals_aq1_baseline_metrics": metrics, "arrivals_aq1_population_changes": pop,
              "arrivals_aq1_bootstrap": boot, "arrivals_aq1_practical_check": practical_check(boot),
              "arrivals_aq1_provenance": prov}
    for name, frame in tables.items():
        frame.to_csv(out_dir / f"{name}.csv", index=False)
    pd.DataFrame(manifest).to_csv(aq_dir / "aq1_flags_v1_manifest.csv", index=False)
    for name, frame in mp.items():
        frame.to_csv(out_dir / f"arrivals_mp_placeholder_{name}.csv", index=False)
    return tables | {"predictions": p, "flags_manifest": pd.DataFrame(manifest), "mp": mp}
