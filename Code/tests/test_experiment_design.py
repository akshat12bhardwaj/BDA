"""
Proposed experiment design: the calendar split is ordered and inside the candidate weeks, examples are assigned by
target-week Sunday (Phase 8 B.7), and the sensitivity helpers never change the inputs. Synthetic data only.
"""

import pandas as pd

from Code.candidates import experiment_design as ed


def mt(origins, h):
    o = pd.to_datetime(origins)
    return pd.DataFrame({"origin_week_start": o, "horizon_weeks": h, "target_week_start": o + pd.Timedelta(weeks=h)})


def test_split_is_ordered_disjoint_and_inside_candidate_weeks():
    assert ed.check_split()
    assert ed.PROPOSED_SPLIT["test"][1] == "2026-10-18"  # Sunday of the last complete candidate week


def test_examples_are_assigned_by_target_sunday_so_training_targets_precede_evaluated_targets():
    # origin week 2025-12-22: h=1 target Sunday 2026-01-04 -> validation; h=4 origin 2025-11-24 -> target Sunday 2025-12-28 -> train
    a = ed.assign_period(mt(["2025-12-22"], 1))
    b = ed.assign_period(mt(["2025-11-24"], 4))
    c = ed.assign_period(mt(["2026-06-22"], 1))  # target Sunday 2026-07-05 -> test
    assert (a.item(), b.item(), c.item()) == ("validation", "train", "test")


def test_no_example_falls_in_two_periods():
    x = mt(pd.date_range("2025-02-03", "2026-10-05", freq="7D"), 1)
    p = ed.assign_period(x)
    assert p.isin(["train", "validation", "test"]).all()
    t = x.target_week_start + pd.Timedelta(days=6)
    assert t[p == "train"].max() < t[p == "validation"].min() and t[p == "validation"].max() < t[p == "test"].min()


def test_protocol_matches_the_documented_proposal_and_phase8_seed():
    p = ed.PROTOCOL
    assert p["split_by_target_sunday"] == {"train": (None, "2025-12-28"), "validation": ("2026-01-04", "2026-06-28"),
                                           "test": ("2026-07-05", "2026-10-18")}
    assert ed.REFITS == ["2026-01-04", "2026-04-05", "2026-07-05", "2026-10-04"]
    assert p["horizons"] == {"primary": 1, "secondary": [2, 4]} and p["designs"]["primary"] == "faq_only"
    assert set(p["baselines"]) == {"persistence", "seasonal_naive", "calendar_climatology"} and "NOT executed" in p["status"]
    assert str(ed.PHASE8_SEED) in p["uncertainty"]["paired_bootstrap"] and ed.PHASE8_SEED == 20261022


def test_learned_model_plan_reads_frozen_phase8_settings_and_lists_approvals():
    plan = ed.learned_model_plan()
    s = plan["reusable_unchanged"]["estimator_settings (Code/modelling/models.py LEARNERS)"]
    assert s == {"max_iter": 200, "learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 1000,
                 "l2_regularization": 10.0, "early_stopping": False, "random_state": 0}
    assert {"feature_set", "selection_rule", "scope"} <= set(plan["requires_approval"])


def test_sensitivity_helpers_leave_records_unchanged():
    rec = pd.DataFrame({"Commodity": "Wheat", "canonical_id": "S|D|M", "Variety": "V", "week_start": pd.to_datetime("2025-03-03"),
                        "modal_price_rs_per_quintal": [2000.0, 20.0, 2100.0], "usable_for_target": True, "in_faq_only": True,
                        "in_faq_local": True, "in_pooled": True, "in_complete_week": True, "unit_scale_suspected": [False, True, False],
                        "price_anomaly": ["none", "none", "key_conflict"], "State": "Madhya Pradesh", "Grade": "FAQ"})
    before = rec.copy()
    s = ed.sensitivity_r09u(rec)
    assert s["cells_changed"] == {"Wheat": 1} and rec.equals(before)
    w = ed.sensitivity_wheat_conflicts(rec)
    assert w["conflict_records"] == 1 and w["faq_only"]["cells_lost_entirely"] == 0 and rec.equals(before)
