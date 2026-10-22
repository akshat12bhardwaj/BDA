"""
Phase 9 learned-arrivals experiment framework (protocol phase9-arrivals-protocol-v1; Documentation/Phase_09_Model_Protocol.md).

STATUS: APPROVED 2026-10-22 (D-44). require_approved() needs BOTH PROTOCOL_STATUS == "APPROVED" and the D-44
heading in Documentation/Decision_Log.md reading ACCEPTED; fitting is authorised under this exact protocol only
(no added candidates, no tuning, no change to the selection rule).

  target      = D-43: weekly median usable arrivals per reported day in week W+h; models predict
                log1p(target) - log1p(origin-week median), converted back and clipped at 0
  features    = origin-time only (weeks <= W; see FEATURES); computed on the Phase 5 usable view - AQ-1 flags are
                never knowable for the origin week and are not used in features
  population  = primary: AQ-1 v1 'aq1_likely' targets (retrospective cleaning; training targets cleaned only when
                aq1_available_from <= refit date); sensitivity: the original population
  evaluation  = 2019 and 2020 separately, identical rows vs persistence, paired series/market bootstrap
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from Code.features.pipeline import MODAL, SERIES
from Code.modelling import arrivals as ar
from Code.modelling import dataset as d
from Code.modelling.baselines import VALIDATION

PROTOCOL_VERSION = "phase9-arrivals-protocol-v1"
PROTOCOL_STATUS = "APPROVED"          # D-44 accepted 2026-10-22 by the project owner
DECISION_LOG = Path("Documentation/Decision_Log.md")
OUT_DIR = ar.OUT_DIR.parent / "phase09_models"
SEED = 20261022
K = SERIES + ["week_start"]
LAGS = (1, 2, 4, 52)
# Same learners and settings as Phase 8 (no tuning); the conservative HGB is the Phase 8 §L.1 configuration.
CANDIDATES = {
    "ridge": lambda: make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), Ridge(alpha=1.0)),
    "hgb_conservative": lambda: HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                                              min_samples_leaf=1000, l2_regularization=10.0,
                                                              early_stopping=False, random_state=0),
}
BASELINE = "persistence"
EXPLORATORY = ["calendar_adjusted_persistence"]          # reported, never selectable (D-43)
FEATURES = (["f_log_origin", "f_origin_reported_days", "f_log_n_dates"]
            + [f"f_lag{k}_logratio" for k in LAGS]
            + ["f_med4_logratio", "f_med13_logratio", "f_weeks_reported_13", "f_has_price", "f_price_logchange_4w",
               "tw_month_sin", "tw_month_cos", "tw_week_of_year"])
PRIMARY_POPULATION, SENSITIVITY_POPULATION = "aq1_likely", "original"
MP_SENSITIVITY_POPULATION = "aq1_likely_excl_mp_pending"   # U3: reported only, not part of the selection rule
MIN_REL = 2.0
REPRO_TOL = 1e-12
FAMILY = len(CANDIDATES) * 3 * len(d.HORIZONS) * 2        # candidates x crops x horizons x validation years
Z_BONFERRONI = NormalDist().inv_cdf(1 - 0.05 / (2 * FAMILY))


def approval_recorded(path: Path | None = None) -> bool:
    """True when the decision log records D-44 as ACCEPTED (the audit trail behind PROTOCOL_STATUS)."""
    p = Path(path) if path is not None else DECISION_LOG
    return p.exists() and re.search(r"^### D-44 — \[ACCEPTED", p.read_text(encoding="utf-8"), re.M) is not None


def require_approved() -> None:
    if PROTOCOL_STATUS != "APPROVED":
        raise d.ModellingError(f"{PROTOCOL_VERSION} is {PROTOCOL_STATUS}: no learned arrivals model may be fitted "
                               "until the project owner approves the protocol")
    if not approval_recorded():
        raise d.ModellingError("PROTOCOL_STATUS is APPROVED but Decision_Log.md does not record D-44 as ACCEPTED")


def population_weeks(flags: pd.DataFrame, population: str) -> pd.DataFrame | None:
    """Target-week table for a population (None = original). U3 adds every provider_query_pending row."""
    from Code.modelling import arrivals_aq1 as a1
    if population == SENSITIVITY_POPULATION:
        return None
    if population == PRIMARY_POPULATION:
        return a1.clean_weeks(flags, a1.excluded(flags, "aq1_likely"))
    if population == MP_SENSITIVITY_POPULATION:
        return a1.clean_weeks(flags, a1.excluded(flags, "aq1_likely") | flags["provider_query_pending"])
    raise d.ModellingError(f"unknown population {population!r}")


def protocol() -> dict:
    return {"protocol_version": PROTOCOL_VERSION, "status": PROTOCOL_STATUS, "seed": SEED, "cutoff": ar.CUTOFF.date().isoformat(),
            "candidates": {k: str(v().get_params() if not hasattr(v(), "steps") else v().steps) for k, v in CANDIDATES.items()},
            "baseline": BASELINE, "exploratory": EXPLORATORY, "features": FEATURES, "primary_population": PRIMARY_POPULATION,
            "sensitivity_population": SENSITIVITY_POPULATION, "mp_sensitivity_population": MP_SENSITIVITY_POPULATION,
            "decision": "D-44 accepted 2026-10-22; U2-U6 per Decision_Log.md", "metric": "log MAE (log1p)", "min_rel_improvement_pct": MIN_REL,
            "bonferroni_family": FAMILY, "z_bonferroni": round(Z_BONFERRONI, 3), "validation_years": VALIDATION}


# ---------------------------------------------------------------- features (weeks <= origin only)
def origin_features(origins: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """One row per series-week (= origin week W). Every value uses arrivals/price weeks dated <= W only."""
    o = origins[K + ["origin_week_median_arrivals", "origin_week_reported_days", "n_usable_arrival_dates_to_origin",
                     "has_usable_price_in_origin_week"]].sort_values(K, ignore_index=True)
    lo = np.log1p(o["origin_week_median_arrivals"])
    f = o[K].copy()
    f["f_log_origin"] = lo
    f["f_origin_reported_days"] = o["origin_week_reported_days"].astype(float)
    f["f_log_n_dates"] = np.log1p(o["n_usable_arrival_dates_to_origin"])
    wk = o[K].assign(_v=lo)
    for k in LAGS:                                    # exact calendar-week lags: a week not reported stays NaN
        lag = wk.assign(week_start=wk["week_start"] + pd.Timedelta(weeks=k)).rename(columns={"_v": "_lag"})
        f[f"f_lag{k}_logratio"] = o[K].merge(lag, on=K, how="left", validate="1:1")["_lag"].to_numpy() - lo
    g = wk.groupby(SERIES, observed=True)["_v"]
    for w, name in [(4, "f_med4_logratio"), (13, "f_med13_logratio")]:   # previous reported weeks, own week excluded
        f[name] = g.transform(lambda s, w=w: s.shift(1).rolling(w, min_periods=1).median()) - lo
    wnum = ((o["week_start"] - pd.Timestamp("2000-01-03")).dt.days // 7).to_numpy()
    sid = o.groupby(SERIES, observed=True).ngroup().to_numpy()
    key = sid * 10_000 + wnum                          # sorted within series, so searchsorted counts weeks in (W-13, W]
    f["f_weeks_reported_13"] = (np.arange(len(key)) - np.searchsorted(key, key - 13, side="right") + 1).astype(float)
    f["f_has_price"] = o["has_usable_price_in_origin_week"].astype(float)
    pw = (df[df["usable_modal_price"] & (df["reported_date"] <= ar.CUTOFF)]
          .assign(week_start=lambda x: d.week_start(x["reported_date"])).groupby(K, observed=True)[MODAL].median()
          .rename("_p").reset_index())
    now = o[K].merge(pw, on=K, how="left", validate="1:1")["_p"].to_numpy()
    before = o[K].merge(pw.assign(week_start=pw["week_start"] + pd.Timedelta(weeks=4)), on=K, how="left", validate="1:1")["_p"].to_numpy()
    f["f_price_logchange_4w"] = np.log(now) - np.log(before)
    return f


def design(ex: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    x = ex[K].merge(feats, on=K, how="left", validate="m:1")
    x.index = ex.index
    m = (ex["target_week_start"] + pd.Timedelta(days=3))
    x["tw_month_sin"] = np.sin(2 * np.pi * (m.dt.month - 1) / 12)
    x["tw_month_cos"] = np.cos(2 * np.pi * (m.dt.month - 1) / 12)
    x["tw_week_of_year"] = m.dt.isocalendar().week.astype(float).to_numpy()
    return x[FEATURES].astype(float)


def to_target(y, origin):
    return np.log1p(y) - np.log1p(origin)


def from_target(pred, origin):
    return np.clip(np.expm1(np.log1p(origin) + pred), 0, None)


# ---------------------------------------------------------------- leakage probe and baseline reproduction
def leakage_probe(df: pd.DataFrame, origin_date, n_series: int = 20) -> pd.DataFrame:
    """Recompute features with every row after origin_date replaced by an absurd value; origins <= it must match."""
    origin = pd.Timestamp(origin_date)
    keys = df[SERIES].drop_duplicates().head(n_series)
    sub = df.merge(keys, on=SERIES)
    late = sub["reported_date"] > origin
    poisoned = sub.assign(arrivals_tonnes=sub["arrivals_tonnes"].where(~late, 1e9),
                          **{MODAL: sub[MODAL].where(~late, 1e9)})
    a = origin_features(ar.build_arrivals_examples(sub)[1], sub)
    b = origin_features(ar.build_arrivals_examples(poisoned)[1], poisoned)
    a, b = (x[x["week_start"] + pd.Timedelta(days=6) <= origin].reset_index(drop=True) for x in (a, b))
    diff = (a[FEATURES[:-3]].fillna(-999) != b[FEATURES[:-3]].fillna(-999)).sum()
    return pd.DataFrame({"feature": diff.index, "rows_compared": len(a), "rows_changed": diff.to_numpy()})


def reproduce_persistence(preds: pd.DataFrame, saved_metrics: pd.DataFrame) -> pd.DataFrame:
    """Recomputed persistence scores vs the saved Phase 9 baseline (all segment, every crop/h/period)."""
    s = ar.score(preds)
    s = s[(s["segment"] == "all") & (s["baseline"] == "persistence")]
    ref = saved_metrics[(saved_metrics["segment"] == "all") & (saved_metrics["baseline"] == "persistence")]
    j = s.merge(ref, on=["crop", "horizon_weeks", "period"], suffixes=("", "_saved"))
    j = j.assign(abs_diff_log_mae=(j["log_mae"] - j["log_mae_saved"]).abs(), n_equal=j["n"] == j["n_saved"])
    # saved values went through a CSV text round-trip, which can change the last float bit (~1e-17)
    j["reproduced"] = j["n_equal"] & (j["abs_diff_log_mae"] <= REPRO_TOL)
    return j[["crop", "horizon_weeks", "period", "n", "n_saved", "n_equal", "log_mae", "log_mae_saved",
              "abs_diff_log_mae", "reproduced"]]


# ---------------------------------------------------------------- gated fitting
def fit_predict(ex: pd.DataFrame, origins: pd.DataFrame, feats: pd.DataFrame, weeks: pd.DataFrame | None,
                candidate: str, crop: str, h: int) -> pd.DataFrame:
    """
    Quarterly-refit predictions of one candidate on origin-eligible validation rows. `weeks` (from
    arrivals_aq1.clean_weeks) defines the population: evaluation targets are cleaned, and a training target is
    cleaned only if its flags were knowable by the refit date. weeks=None -> original population.
    """
    require_approved()
    if candidate not in CANDIDATES:
        raise d.ModellingError(f"unknown candidate {candidate!r}")
    if weeks is not None:
        ex = ex.merge(weeks.rename(columns={"week_start": "target_week_start"}), on=SERIES + ["target_week_start"],
                      how="left", validate="1:1").set_axis(ex.index)      # keep row ids identical across populations
    else:
        ex = ex.assign(clean_median=ex[ar.TARGET], flag_available=pd.NaT)
    X = design(ex, feats)
    ev = ex[ex["period"].isin(VALIDATION) & ex["eligible_at_origin"] & ex["clean_median"].notna()]
    refit = d.refit_date_for(ev["origin_date"], d.refit_schedule())
    yhat = pd.Series(np.nan, index=ev.index)
    for r in sorted(refit.unique()):
        tr = d.training_examples(ex, r)
        knowable = tr["flag_available"].notna() & (tr["flag_available"] <= r)
        y_tr = tr[ar.TARGET].where(~knowable, tr["clean_median"]).dropna()
        if y_tr.empty or tr.loc[y_tr.index, "target_sunday"].max() > r:
            raise d.ModellingError(f"invalid training set at refit {r.date()}")
        model = CANDIDATES[candidate]()
        model.fit(X.loc[y_tr.index], to_target(y_tr, tr.loc[y_tr.index, "origin_week_median_arrivals"]))
        idx = refit.index[refit == r]
        yhat[idx] = from_target(model.predict(X.loc[idx]), ev.loc[idx, "origin_week_median_arrivals"])
    return pd.DataFrame({"crop": crop, "horizon_weeks": h, "period": ev["period"], "row": ev.index,
                         **{c: ev[c].astype(str) for c in SERIES if c != "crop"},
                         "y": ev["clean_median"], "persistence": ev["origin_week_median_arrivals"], candidate: yhat})


# ---------------------------------------------------------------- selection rule
def select(primary_boot: pd.DataFrame, sensitivity_boot: pd.DataFrame) -> pd.DataFrame:
    """
    Per crop x horizon x candidate (all must hold): (1) 95% CI of the log-MAE improvement over persistence > 0
    in 2019 AND 2020 with series AND market clusters (primary population); (2) estimate/SE > Z_BONFERRONI in both
    years; (3) relative improvement >= MIN_REL % in both years; (4) on the original population the improvement
    is also > 0 (CI) in both years. Persistence is kept where no candidate passes.
    """
    rows = []
    for (crop, h, cand), g in primary_boot[primary_boot["period"].isin(VALIDATION)].groupby(["crop", "horizon_weeks", "candidate"]):
        s, m = g[g["cluster"] == "series"].set_index("period"), g[g["cluster"] == "market"].set_index("period")
        sb = sensitivity_boot[(sensitivity_boot["crop"] == crop) & (sensitivity_boot["horizon_weeks"] == h)
                              & (sensitivity_boot["candidate"] == cand) & (sensitivity_boot["cluster"] == "series")
                              & sensitivity_boot["period"].isin(VALIDATION)]
        z = s["log_mae_improvement"] / s["se"]
        r = {"crop": crop, "horizon_weeks": h, "candidate": cand,
             "rel_2019_pct": s.loc["val_2019", "rel_log_mae_improvement_pct"], "rel_2020_pct": s.loc["val_2020", "rel_log_mae_improvement_pct"],
             "c1_ci_both_years_both_clusterings": bool((s.reindex(VALIDATION)["verdict"] == "better").all()
                                                       and (m.reindex(VALIDATION)["verdict"] == "better").all()),
             "c2_bonferroni": bool((z.reindex(VALIDATION) > Z_BONFERRONI).all()),
             "c3_practical": bool((s.reindex(VALIDATION)["rel_log_mae_improvement_pct"] >= MIN_REL).all()),
             "c4_original_population": bool(len(sb) == 2 and (sb["verdict"] == "better").all())}
        r["passes"] = r["c1_ci_both_years_both_clusterings"] and r["c2_bonferroni"] and r["c3_practical"] and r["c4_original_population"]
        rows.append(r)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    best = (out[out["passes"]].assign(worst=lambda x: x[["rel_2019_pct", "rel_2020_pct"]].min(axis=1))
            .sort_values("worst", ascending=False).groupby(["crop", "horizon_weeks"]).head(1))
    return out.merge(best[["crop", "horizon_weeks", "candidate"]].assign(proposed=True),
                     on=["crop", "horizon_weeks", "candidate"], how="left").assign(proposed=lambda x: x["proposed"].eq(True))


def environment() -> dict:
    import platform
    import sklearn
    return {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
            "scikit_learn": sklearn.__version__}


def write_config(out_dir=OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = protocol() | {"environment": environment()}
    (out_dir / "experiment_config.json").write_text(json.dumps(cfg, indent=2, default=str), encoding="utf-8")
