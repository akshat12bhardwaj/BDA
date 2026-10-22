"""
Phase 9 arrivals quality audit and PROPOSED flagging policy AQ-1 (Documentation/Phase_09_Arrivals_Plan.md §11).

Read-only: Phase 5 flags (R12) and all Phase 4-7 outputs are unchanged; nothing is deleted or overwritten.
The audit reads rows dated <= the Phase 9 cutoff (2020-12-27) only.

AQ-1 compares each usable daily arrivals value of a series with ROBUST references from the same series:
  prev_ref = median of the series' previous 13 reported weekly medians (>= 4 weeks), the row's week excluded
  next_ref = median of the series' next 4 reported weekly medians (>= 2 weeks), the row's week excluded
Ratios r_prev = value / prev_ref and r_next = value / next_ref, with thresholds 10 / 100 inherited from the
unit-factor reasoning of D-29/D-30 (tonnes vs quintal vs kg), not from any physical capacity bound:
  likely_unit_error      r_prev >= 100 and (r_next >= 100 or no next_ref)      (spike that does not persist)
  likely_unit_error_low  0 < r_prev <= 1/100 and (r_next <= 1/100 or no next_ref)
  isolated_spike         10 <= r_prev < 100 and (r_next >= 10 or no next_ref)  (review)
  sustained_shift        r_prev >= 10 and r_next < 10                         (level persists: possibly genuine)
  likely_unit_error_forward_only  no prev_ref, and r_next >= 100 or 0 < r_next <= 1/100 (start-of-series errors)
  unscreenable           no prev_ref (fewer than 4 earlier reported weeks) or prev_ref == 0, and no forward signal
Descriptive context (not a class): unit_factor_signature (ratio within 0.15 log10 of a power of ten) and
tiny_value (<= 0.1 t, the placeholder-like values seen in 2019-2020).
  ok                     otherwise
next_ref uses up to 4 reported weeks AFTER the row: AQ-1 is a retrospective data-quality label. Each row carries
aq1_available_from (Sunday of the 4th following reported week, or the cutoff if fewer exist); a modelling
pipeline may use the class only at times >= aq1_available_from (enforced in arrivals_aq1.py).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from Code.features.pipeline import ARR, FEATURE_DIR, SERIES
from Code.modelling import arrivals as ar
from Code.modelling import dataset as d

PREV_WEEKS, PREV_MIN, NEXT_WEEKS, NEXT_MIN = 13, 4, 4, 2
REVIEW, ERROR = 10.0, 100.0
CLASSES = ["ok", "isolated_spike", "sustained_shift", "likely_unit_error", "likely_unit_error_low",
           "likely_unit_error_forward_only", "unscreenable"]
LIKELY_ERRORS = ["likely_unit_error", "likely_unit_error_low", "likely_unit_error_forward_only"]


def screen(df: pd.DataFrame, cutoff=ar.CUTOFF) -> pd.DataFrame:
    """Return one row per usable arrivals record (<= cutoff) with references, ratios and the AQ-1 class."""
    u = df.loc[df["usable_arrivals"] & (df["reported_date"] <= cutoff),
               SERIES + ["source_row", "reported_date", ARR, "arrivals_extreme_level"]].copy()
    u["week_start"] = d.week_start(u["reported_date"])
    k = SERIES + ["week_start"]
    wk = u.groupby(k, observed=True)[ARR].agg(["median", "size"]).reset_index().sort_values(k, ignore_index=True)
    g = wk.groupby(SERIES, observed=True)["median"]
    wk["prev_ref"] = g.transform(lambda s: s.shift(1).rolling(PREV_WEEKS, min_periods=PREV_MIN).median())
    wk["next_ref"] = g.transform(lambda s: s[::-1].shift(1).rolling(NEXT_WEEKS, min_periods=NEXT_MIN).median()[::-1])
    # When the row's full class becomes knowable: the Sunday of the 4th following reported week; if fewer than 4
    # following weeks exist before the cutoff, the class depends on data being absent up to the cutoff -> cutoff.
    fourth = wk.groupby(SERIES, observed=True)["week_start"].shift(-NEXT_WEEKS)
    wk["aq1_available_from"] = (fourth + pd.Timedelta(days=6)).fillna(pd.Timestamp(cutoff))
    wk = wk.rename(columns={"size": "week_reported_days"})
    out = u.merge(wk[k + ["prev_ref", "next_ref", "week_reported_days", "aq1_available_from"]], on=k, how="left", validate="m:1")
    with np.errstate(divide="ignore", invalid="ignore"):
        rp = out[ARR] / out["prev_ref"].where(out["prev_ref"] > 0)
        rn = out[ARR] / out["next_ref"].where(out["next_ref"] > 0)
    out["r_prev"], out["r_next"] = rp, rn
    no_next = rn.isna()
    out["aq1_class"] = np.select(
        [rp.isna() & ((rn >= ERROR) | ((rn > 0) & (rn <= 1 / ERROR))),
         rp.isna(),
         (rp >= ERROR) & (no_next | (rn >= ERROR)),
         (rp > 0) & (rp <= 1 / ERROR) & (no_next | (rn <= 1 / ERROR)),
         (rp >= REVIEW) & ~no_next & (rn < REVIEW),
         (rp >= REVIEW) & (no_next | (rn >= REVIEW))],
        ["likely_unit_error_forward_only", "unscreenable", "likely_unit_error", "likely_unit_error_low",
         "sustained_shift", "isolated_spike"], "ok")
    lr = np.log10(rp.where(rp > 0)).abs()
    out["unit_factor_signature"] = (lr.round() >= 1) & ((lr - lr.round()).abs() <= 0.15)
    out["tiny_value"] = out[ARR] <= 0.1
    out["high_side"] = (out["aq1_class"] == "likely_unit_error") | (
        (out["aq1_class"] == "likely_unit_error_forward_only") & (rn >= ERROR))
    out["march_to_may"] = out["reported_date"].dt.month.isin([3, 4, 5])
    return out


def summarise(s: pd.DataFrame, crop: str) -> dict[str, pd.DataFrame]:
    s = s.assign(crop=crop, year=s["reported_date"].dt.year,
                 reporting=pd.cut(s["week_reported_days"], ar.REPORT_BINS, labels=ar.REPORT_LABELS).astype(str))
    flagged = s[s["aq1_class"].isin(LIKELY_ERRORS + ["isolated_spike", "sustained_shift"])]
    return {
        "by_class_vs_phase5": s.groupby(["crop", "aq1_class", "arrivals_extreme_level"], observed=True).size()
                              .rename("rows").reset_index(),
        "by_year": flagged.groupby(["crop", "year", "aq1_class"]).size().rename("rows").reset_index(),
        "by_month": flagged.assign(month=s["reported_date"].dt.month).groupby(["crop", "month", "aq1_class"]).size()
                    .rename("rows").reset_index(),
        "context": s[s["aq1_class"].isin(LIKELY_ERRORS)].groupby(["crop", "aq1_class"])
                   .agg(rows=("aq1_class", "size"), unit_factor_signature=("unit_factor_signature", "sum"),
                        tiny_value=("tiny_value", "sum")).reset_index(),
        "by_state": flagged.groupby(["crop", "state", "aq1_class"], observed=True).size().rename("rows").reset_index()
                    .sort_values("rows", ascending=False),
        "by_reporting": s.groupby(["crop", "reporting", "aq1_class"]).size().rename("rows").reset_index(),
        "examples": s[s["aq1_class"] == "likely_unit_error"].nlargest(10, ARR)[
            ["crop", "state", "district", "market", "variety", "reported_date", ARR, "prev_ref", "next_ref",
             "r_prev", "r_next", "unit_factor_signature", "arrivals_extreme_level"]],
    }


def validation_exposure(s: pd.DataFrame, df: pd.DataFrame, crop: str) -> pd.DataFrame:
    """Share of Phase 9 validation examples whose origin or target week contains an AQ-1 likely error."""
    bad = s.loc[s["aq1_class"].isin(LIKELY_ERRORS), SERIES + ["week_start"]].drop_duplicates()
    by_h, _ = ar.build_arrivals_examples(df)
    rows = []
    for h, ex in by_h.items():
        ev = ex[ex["period"].isin(["val_2019", "val_2020"]) & ex["eligible_at_origin"]]
        o = ev.merge(bad.assign(_o=True), on=SERIES + ["week_start"], how="left")["_o"].notna().to_numpy()
        t = ev.merge(bad.rename(columns={"week_start": "target_week_start"}).assign(_t=True),
                     on=SERIES + ["target_week_start"], how="left")["_t"].notna().to_numpy()
        rows.append({"crop": crop, "horizon_weeks": h, "validation_examples": len(ev),
                     "origin_week_flagged": int(o.sum()), "target_week_flagged": int(t.sum()),
                     "either_flagged_pct": round(100 * float((o | t).mean()), 3)})
    return pd.DataFrame(rows)


def run_audit(feature_dir: Path = FEATURE_DIR, out_dir: Path = ar.OUT_DIR, crops: list[str] | None = None,
              expected: dict[str, str] | None = None, registry_path: Path = d.REGISTRY_PATH) -> dict:
    crops = crops or d.load_selected_crops()
    inputs = [Path(feature_dir) / f"features_{c.lower()}.parquet" for c in crops] + [Path(registry_path)]
    expected = d.phase7_expected_hashes() if expected is None else expected
    before = d.check_inputs(inputs, expected)
    reg = d.registry_columns(pd.read_csv(registry_path))
    parts: dict[str, list] = {}
    for crop, path in zip(crops, inputs):
        df = pd.read_parquet(path)
        d.validate_schema(df, reg, crop)
        df = df[df["reported_date"] <= ar.CUTOFF]
        s = screen(df)
        for name, frame in summarise(s, crop).items():
            parts.setdefault(name, []).append(frame)
        parts.setdefault("validation_exposure", []).append(validation_exposure(s, df, crop))
        del df, s
    if d.check_inputs(inputs) != before:
        raise d.ModellingError("protected inputs changed during the arrivals quality audit")
    tables = {f"arrivals_quality_{k}": pd.concat(v, ignore_index=True) for k, v in parts.items()}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(Path(out_dir) / f"{name}.csv", index=False)
    return tables
