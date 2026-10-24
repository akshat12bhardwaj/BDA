"""
Pre-registered exploratory learned model: features use only origin-time columns, the estimator is the frozen Phase 8
one unchanged, training never sees a target after the refit, and the selection rule is applied exactly as registered.
Synthetic data only; the real experiment is not run here.
"""

import numpy as np
import pandas as pd
import pytest

from Code.candidates import learned_candidate as lc

S = {"Commodity": "Onion", "canonical_id": "S|D|M", "Variety": "V"}


def table(weeks, eligible_from=10):
    o = pd.date_range("2025-02-03", periods=weeks, freq="7D")
    rng = np.random.RandomState(1)
    y = 1000 + rng.rand(weeks + 1).cumsum() * 10
    return pd.DataFrame({**S, "origin_week_start": o, "target_week_start": o + pd.Timedelta(weeks=1), "horizon_weeks": 1,
                         "y_origin": y[:-1], "y_target": y[1:], "eligible_d41": np.arange(weeks) >= eligible_from,
                         "lag1": np.r_[np.nan, y[:-2]], "lag2": np.r_[[np.nan] * 2, y[:-3]], "lag4": np.r_[[np.nan] * 4, y[:-5]],
                         "lag52": np.nan, "weeks_since_prev_obs": np.r_[np.nan, np.ones(weeks - 1)], "n_weeks_history": np.arange(1, weeks + 1)})


def test_features_are_the_registered_set_and_keep_missing_values():
    X = lc.features(table(12))
    assert list(X.columns) == list(lc.FEATURES) and len(lc.FEATURES) == 9
    assert X.r_lag52.isna().all() and np.isnan(X.r_lag1.iloc[0])  # no imputation: HGB handles NaN natively
    assert X.month_sin.between(-1, 1).all()


def test_estimator_is_the_frozen_phase8_hgb_conservative_unchanged():
    assert lc.estimator_params() == {"max_iter": 200, "learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 1000,
                                     "l2_regularization": 10.0, "early_stopping": False, "random_state": 0}


def test_training_never_uses_targets_after_the_refit_and_respects_d41_by_refit():
    mt = table(60)
    pool = lc.training_pool(mt)
    r = pd.Timestamp("2025-10-05")
    tr = pool[(pool.t_sun <= r) & (pool.eligible_from <= r)]
    assert tr.t_sun.max() <= r and (~tr.eligible_d41).any()  # earlier, not-yet-eligible weeks are included (Phase 8 rule)
    late = table(60, eligible_from=59)
    p2 = lc.training_pool(late)
    assert p2[(p2.t_sun <= r) & (p2.eligible_from <= r)].empty  # a series not eligible by the refit contributes nothing


def test_selection_rule_requires_both_quarters_and_ci_above_zero():
    q = pd.DataFrame([{"Commodity": "Onion", "quarter": qt, "model": m, "mae": mae, "skill_vs_persistence": sk}
                      for qt, lm in (("2026Q1", 90.0), ("2026Q2", 95.0)) for m, mae, sk in (("learned", lm, 1 - lm / 100), ("persistence", 100.0, 0.0))])
    ok = pd.DataFrame([{"crop": "Onion", "period": "2026Q1", "skill_ci95": [0.02, 0.15]}, {"crop": "Onion", "period": "2026Q2", "skill_ci95": [0.01, 0.09]}])
    assert lc.selection(ok, q).passes_preregistered_rule.item()
    weak = ok.copy(); weak.at[1, "skill_ci95"] = [-0.01, 0.09]  # Q2 interval touches 0
    assert not lc.selection(weak, q).passes_preregistered_rule.item()


def test_run_refuses_a_changed_registration(tmp_path, monkeypatch):
    monkeypatch.setattr(lc, "PREREG", tmp_path / "prereg.json")  # absolute, so root / PREREG is this file
    (tmp_path / "prereg.json").write_bytes(b"{}")
    with pytest.raises(lc.bc.GuardError, match="does not match"):
        lc.verify_registration(tmp_path, "0" * 64)
