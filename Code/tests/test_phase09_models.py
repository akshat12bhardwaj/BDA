"""
Phase 9 learned-arrivals framework tests (protocol PROPOSED; synthetic data only): origin-time feature cutoffs,
missing-week semantics, determinism, the approval gate, population handling, identical comparison rows,
persistence reproduction, the selection rule, and the notebook's data contract.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from Code.modelling import arrivals as ar
from Code.modelling import arrivals_aq1 as a1
from Code.modelling import arrivals_models as am
from Code.modelling import dataset as m
from Code.tests.test_phase09_arrivals import daily_arr
from Code.tests.test_phase09_arrivals_quality import series

NOTEBOOK = Path("Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb")


def two_series(n=1820):
    a = daily_arr("2016-01-04", n)
    b = daily_arr("2016-01-04", n, market="N", base=100.0).assign(source_row=lambda x: x["source_row"] + 50_000)
    return pd.concat([a, b], ignore_index=True)


@pytest.fixture(scope="module")
def built():
    df = two_series()
    by_h, o = ar.build_arrivals_examples(df)
    return df, by_h, o, am.origin_features(o, df)


# ---------------------------------------------------------------- features
def test_features_use_only_weeks_up_to_the_origin():
    df = two_series()
    probe = am.leakage_probe(df, "2018-06-03", n_series=2)
    assert probe["rows_compared"].iloc[0] > 100 and (probe["rows_changed"] == 0).all()


def test_lags_are_exact_calendar_weeks_and_unreported_weeks_stay_missing():
    df = series([10, 20, 40, 80, 160, 320], start="2019-01-07", every=7)
    df = df[df["reported_date"] != pd.Timestamp("2019-01-21")]           # week 3 not reported
    o = ar.build_arrivals_examples(df)[1]
    f = am.origin_features(o, df).set_index("week_start")
    w4 = pd.Timestamp("2019-01-28")
    assert np.isnan(f.loc[w4, "f_lag1_logratio"])                         # the gap is not zero and not carried forward
    assert f.loc[w4, "f_lag2_logratio"] == pytest.approx(np.log1p(20) - np.log1p(80))
    assert f.loc[w4, "f_weeks_reported_13"] == 3                            # weeks 1, 2 and 4 of the last 13
    assert f.loc[pd.Timestamp("2019-01-07"), "f_med4_logratio"] != f.loc[pd.Timestamp("2019-01-07"), "f_med4_logratio"]  # NaN: no history


def test_features_and_design_are_deterministic(built):
    df, by_h, o, f = built
    f2 = am.origin_features(o, df)
    pd.testing.assert_frame_equal(f, f2)
    x = am.design(by_h[2], f)
    assert list(x.columns) == am.FEATURES and x.index.equals(by_h[2].index)


def test_target_transform_round_trips_and_never_goes_negative():
    y, o = np.array([0.0, 5.0, 120.0]), np.array([3.0, 5.0, 100.0])
    assert np.allclose(am.from_target(am.to_target(y, o), o), y)
    assert (am.from_target(np.array([-50.0]), np.array([1.0])) >= 0).all()


# ---------------------------------------------------------------- approval gate and fitting
def test_fitting_is_refused_unless_status_and_decision_log_both_record_approval(built, monkeypatch, tmp_path):
    df, by_h, o, f = built
    assert am.PROTOCOL_STATUS == "APPROVED" and am.approval_recorded()        # the real repository state (D-44)
    monkeypatch.setattr(am, "PROTOCOL_STATUS", "PROPOSED")
    with pytest.raises(m.ModellingError, match="PROPOSED"):
        am.fit_predict(by_h[1], o, f, None, "ridge", "Onion", 1)
    monkeypatch.setattr(am, "PROTOCOL_STATUS", "APPROVED")
    log = tmp_path / "Decision_Log.md"
    log.write_text("### D-44 — [PROPOSED, for review; NOT accepted] protocol\n", encoding="utf-8")
    monkeypatch.setattr(am, "DECISION_LOG", log)
    assert not am.approval_recorded()
    with pytest.raises(m.ModellingError, match="does not record D-44"):
        am.fit_predict(by_h[1], o, f, None, "ridge", "Onion", 1)
    log.write_text("### D-44 — [ACCEPTED 2026-10-22 by the project owner] protocol\n", encoding="utf-8")
    assert am.approval_recorded()


def test_population_weeks_and_the_mp_sensitivity_exclusion():
    df = series([100] * 8 + [0.01] + [100] * 6 + [0.05] + [100] * 6, start="2019-01-07").assign(state="Madhya Pradesh")
    flags = a1.flag_table(df)
    assert am.population_weeks(flags, "original") is None
    prim = am.population_weeks(flags, "aq1_likely").set_index("week_start")["clean_median"]
    mp = am.population_weeks(flags, "aq1_likely_excl_mp_pending").set_index("week_start")["clean_median"]
    pending_weeks = flags.loc[flags["provider_query_pending"], "week_start"]
    assert len(pending_weeks) == 2 and mp.loc[pending_weeks].isna().all()   # all flagged MP rows excluded in U3 run
    assert prim.notna().sum() >= mp.notna().sum()
    with pytest.raises(m.ModellingError, match="unknown population"):
        am.population_weeks(flags, "everything")


def test_approved_fit_uses_identical_rows_and_past_targets_only(built, monkeypatch):
    df, by_h, o, f = built
    monkeypatch.setattr(am, "PROTOCOL_STATUS", "APPROVED")
    ex = by_h[1]
    p = am.fit_predict(ex, o, f, None, "ridge", "Onion", 1)
    base, _ = ar.validation_predictions(ex, o, "Onion", 1)
    assert set(p["row"]) == set(base.index) and p["ridge"].notna().all()     # identical evaluation rows
    assert np.allclose(p.set_index("row").loc[base.index, "persistence"], base["persistence"])
    assert set(p["period"]) == {"val_2019", "val_2020"}
    # changing targets after mid-2019 must not move predictions from refits trained before then
    late = ex["target_first_date"] > pd.Timestamp("2019-06-30")
    p2 = am.fit_predict(ex.assign(**{ar.TARGET: ex[ar.TARGET].where(~late, ex[ar.TARGET] * 30)}), o, f, None, "ridge", "Onion", 1)
    early = ex.loc[p["row"], "origin_date"].to_numpy() < np.datetime64("2019-07-07")
    assert np.allclose(p.loc[early, "ridge"].to_numpy(), p2.loc[early, "ridge"].to_numpy())
    with pytest.raises(m.ModellingError, match="unknown candidate"):
        am.fit_predict(ex, o, f, None, "xgboost", "Onion", 1)


def test_aq1_population_cleans_targets_without_changing_origin_inputs(monkeypatch):
    monkeypatch.setattr(am, "PROTOCOL_STATUS", "APPROVED")
    df = two_series()
    df.loc[df["reported_date"] == pd.Timestamp("2019-03-27"), "arrivals_tonnes"] = 1e5
    by_h, o = ar.build_arrivals_examples(df)
    f = am.origin_features(o, df)
    flags = a1.flag_table(df)
    weeks = a1.clean_weeks(flags, a1.excluded(flags, "aq1_likely"))
    orig = am.fit_predict(by_h[1], o, f, None, "ridge", "Onion", 1).set_index("row")
    cln = am.fit_predict(by_h[1], o, f, weeks, "ridge", "Onion", 1).set_index("row")
    common = cln.index.intersection(orig.index)
    assert np.allclose(cln.loc[common, "persistence"], orig.loc[common, "persistence"])
    assert (cln.loc[common, "y"] != orig.loc[common, "y"]).sum() >= 1


def test_persistence_reproduction_matches_saved_metrics(built):
    df, by_h, o, f = built
    p, _ = ar.validation_predictions(by_h[1], o, "Onion", 1)
    saved = ar.score(p)
    r = am.reproduce_persistence(p, saved)
    assert (r["abs_diff_log_mae"] == 0).all() and r["reproduced"].all()
    bad = am.reproduce_persistence(p, saved.assign(log_mae=saved["log_mae"] + 1e-6))      # a real difference fails
    assert not bad["reproduced"].any()
    off = am.reproduce_persistence(p, saved.assign(n=saved["n"] + 1))
    assert not off["reproduced"].any()


# ---------------------------------------------------------------- selection rule
def _boot(rel19, rel20, lo=0.01, verdict="better", cand="ridge", se=0.001):
    rows = []
    for period, rel in [("val_2019", rel19), ("val_2020", rel20)]:
        for cluster in ["series", "market"]:
            rows.append({"crop": "Wheat", "horizon_weeks": 4, "candidate": cand, "period": period, "cluster": cluster,
                         "rel_log_mae_improvement_pct": rel, "log_mae_improvement": rel / 100 * 0.6, "se": se,
                         "ci_low": lo, "verdict": verdict})
    return pd.DataFrame(rows)


def test_selection_requires_all_four_criteria():
    ok = am.select(_boot(3.0, 2.5), _boot(3.0, 2.5))
    assert ok["passes"].iloc[0] and ok["proposed"].iloc[0]
    small = am.select(_boot(3.0, 1.5), _boot(3.0, 1.5))
    assert not small["c3_practical"].iloc[0] and not small["proposed"].iloc[0]
    noisy = am.select(_boot(3.0, 2.5, se=0.01), _boot(3.0, 2.5))
    assert not noisy["c2_bonferroni"].iloc[0]
    fragile = am.select(_boot(3.0, 2.5), _boot(3.0, 2.5, verdict="inconclusive"))
    assert not fragile["c4_original_population"].iloc[0] and not fragile["passes"].iloc[0]
    assert am.Z_BONFERRONI == pytest.approx(3.197, abs=0.01)                 # 36 tests, two-sided 5%


def test_exploratory_baseline_is_never_a_candidate():
    assert not set(am.EXPLORATORY) & set(am.CANDIDATES) and am.BASELINE not in am.CANDIDATES


# ---------------------------------------------------------------- notebook contract
def test_notebook_contract():
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    src = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    assert nb["metadata"]["kernelspec"]["name"] == "python3"
    assert "from Code.modelling import arrivals_models as am" in src and "PROJECT_ROOT" in src
    assert "am.PROTOCOL_STATUS" in src and "require_approved" not in src.replace("am.require_approved", "")
    assert "C:\\\\" not in src and "C:/" not in src                                  # no absolute paths
    assert "2021" not in src and "holdout" not in src.lower().replace("holdout_accessed", "")  # no reserved periods
    assert "reproduce_persistence" in src and "leakage_probe" in src and "select(" in src
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert not any(o.get("output_type") == "error" for o in cell.get("outputs", []))
