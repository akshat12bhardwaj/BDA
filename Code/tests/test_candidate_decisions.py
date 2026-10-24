"""
Recorded candidate decisions: only rule-accepted pairs are approved (candidate scope), the worksheet leaves decisions
blank, R09 is unchanged and R09u flags only x100 unit errors, grade designs keep grades visible, and the U3 guard
refuses holdout-period inputs. Synthetic data only.
"""

import pandas as pd
import pytest

from Code.candidates import candidate_decisions as cd


def scored_row(new, old, conf):
    return {"State": "S", "District_old": "D", "Market_old": old, "District_new": "D", "Market_new": new, "confidence": conf}


def test_only_rule_accepted_pairs_are_approved_and_only_for_the_candidate_experiment():
    scored = pd.DataFrame([scored_row("A APMC", "A", "high"), scored_row("B APMC", "B", "high"), scored_row("C APMC", "C", "high"),
                           scored_row("E APMC", "E", "medium"), scored_row("F APMC", "F", "low")])
    hv = pd.DataFrame({"old_id": ["S|D|A", "S|D|B", "S|D|C"], "new_id": ["S|D|A APMC", "S|D|B APMC", "S|D|C APMC"],
                       "validation_status": ["accepted_rule_v1", "rejected", "unresolved"], "hard_fail": ["", "x", ""],
                       "unmet": ["", "", "y"], "same_day_records": [8, 6, 5], "equal_Modal_Price": [1.0, 1.0, 1.0],
                       "agmarknet2_market_id": [1, 2, None], "legacy_market_code": [9, 8, 7]})
    dec = cd.mapping_decisions(scored, hv)
    assert dec.decision.tolist() == ["approved_candidate_experiment", "separate_rejected", "separate_unresolved",
                                     "separate_pending_review", "separate_not_mapped"]
    assert dec.loc[0, "decision_scope"] == "candidate-prices-v1 only; not production"
    assert cd.approved_pairs(dec).values.tolist() == [["S|D|A", "S|D|A APMC"]]
    assert not (dec.decision == "approved").any()


def test_worksheet_leaves_every_decision_blank():
    cols = ["State", "District_old", "Market_old", "District_new", "Market_new", "first_seen_old", "last_seen_old", "first_seen_new",
            "last_seen_new", "n_records_old", "n_records_new", "crops_new", "co_reported", "identical_share", "evidence_type",
            "overlap_bucket", "stratum", "varieties_old", "varieties_new", "grades_old", "grades_new", "price_evidence"]
    w = cd.review_worksheet(pd.DataFrame([{c: "x" for c in cols}] * 3))
    assert w.review_id.tolist() == ["MR001", "MR002", "MR003"]
    assert (w[["decision", "reason_code", "reviewer", "review_date"]] == "").all().all()


def _prices(modals, days=None):
    days = days or [f"2024-02-{i + 3:02d}" for i in range(len(modals))]
    return pd.DataFrame({"reported_date": pd.to_datetime(days), "min_price_rs_per_quintal": [m * 0.9 for m in modals],
                         "max_price_rs_per_quintal": [m * 1.1 for m in modals], "modal_price_rs_per_quintal": modals,
                         "usable_modal_price": True})


def test_r09u_is_not_active_until_approved():
    assert cd.R09U_APPROVED is False
    d = cd.scale_flags(_prices([1600.0] * 20 + [40.0]))  # ratio ~44 < 50: R09 alone keeps it usable
    assert d.iloc[20].price_extreme_level == "review"
    assert d.iloc[20].unit_scale_suspected and d.iloc[20].usable_for_target  # flagged for evidence, not excluded
    assert not cd.scale_flags(_prices([1600.0] * 20 + [40.0]), r09u_active=True).iloc[20].usable_for_target


def test_scale_rule_flags_kg_entries_but_keeps_values_and_r09_review_rows():
    d = cd.scale_flags(_prices([1600.0] * 20 + [16.0, 120.0, 17000.0]), r09u_active=True)
    kg, low, high = d.iloc[20], d.iloc[21], d.iloc[22]
    assert kg.unit_scale_suspected and not kg.usable_for_target and kg.modal_price_rs_per_quintal == 16.0
    assert not low.unit_scale_suspected  # 100 x 120 = 12,000 is outside [ref/3, 3 ref]: not a unit error
    assert high.price_extreme_level == "review" and high.usable_for_target  # Phase 5 R09: review rows stay usable
    assert d.iloc[:20].usable_for_target.all() and len(d) == 23


def test_r09_thresholds_are_phase5_values():
    assert (cd.PRICE_REVIEW_RATIO, cd.PRICE_SCALE_RATIO) == (10.0, 50.0) and cd.UNIT_BAND == (1 / 3, 3.0)


def test_grade_designs_keep_grade_visible_and_never_merge_labels():
    d = pd.DataFrame({"Grade": ["FAQ", "Local", "Non-FAQ"], "x": [1, 2, 3]})
    assert cd.grade_subset(d, "faq_only").Grade.tolist() == ["FAQ"]
    assert cd.grade_subset(d, "faq_local").Grade.tolist() == ["FAQ", "Local"]  # labels unchanged, not relabelled
    assert cd.grade_subset(d, "pooled").Grade.tolist() == ["FAQ", "Local", "Non-FAQ"]


def test_contract_records_d50_decisions_with_r09u_disabled_and_the_date_guard():
    a = cd.CONTRACT["approvals"]
    assert cd.CONTRACT["decision"].startswith("D-50") and "authorised" in cd.CONTRACT["status"]
    assert all(v.startswith("recorded D-50") for v in a.values())
    assert "NOT approved" in a["r09u_unit_scale"] and cd.R09U_APPROVED is False
    assert "0 of 160" in a["medium_review"] and "1,053" in a["medium_review"]
    assert cd.CONTRACT["primary_design"].startswith("faq_only") and cd.CANDIDATE_START == "2024-02-03"


def test_new_decision_entries_keep_the_phase8_to_10_freezes_valid():
    """Freezes hash each decision up to the next '### ' heading, so an appended entry must not alter earlier sections."""
    from pathlib import Path
    from Code.production import pipeline as pq
    from Code.modelling import final_evaluation as fe, arrivals_final as af
    spec = pq.default_spec()
    if not (Path(spec["out_dir"]) / "pq1_freeze_manifest.csv").exists() or not fe.FREEZE.exists():
        pytest.skip("frozen artefacts not present (fresh clone)")
    fe.verify_freeze(); af.verify_freeze(); pq.verify_freeze(spec)


def test_decision_log_contains_d50():
    from pathlib import Path
    log = Path("Documentation/Decision_Log.md").read_text(encoding="utf-8")
    assert "### D-50" in log and "2024-02-03" in log and "R09u" in log and "not approved and disabled" in log.replace("**", "")


def test_u3_guard_refuses_holdout_period_inputs():
    cd.assert_no_holdout_inputs(pd.DataFrame({"reported_date": pd.to_datetime(["2024-02-03"])}))
    with pytest.raises(ValueError, match="U3"):
        cd.assert_no_holdout_inputs(pd.DataFrame({"reported_date": pd.to_datetime(["2024-01-28", "2024-02-03"])}))
