"""
Identity review: mapping constraints, deterministic de-duplication, conflict handling, grade preservation and weekly
series identity. Synthetic records only.
"""

import pandas as pd

from Code.candidates import identity_review as ir


def rec(market, d, modal="1500", grade="FAQ", variety="Onion", crop="Onion", mn="1000", mx="2000", district="D"):
    ts = pd.Timestamp(d)
    return {"State": "S", "District": district, "Market": market, "Commodity": crop, "Commodity_Code": "23", "Variety": variety,
            "Grade": grade, "Arrival_Date": ts.strftime("%d/%m/%Y"), "Min_Price": mn, "Max_Price": mx, "Modal_Price": modal,
            "reported_date": ts, "modal_price_rs_per_quintal": float(modal), "usable_modal_price": True}


def frame(*rs):
    return pd.DataFrame(list(rs))


ACCEPTED = pd.DataFrame({"old_id": ["S|D|Mapusa"], "new_id": ["S|D|Mapusa APMC"]})


def test_exact_cross_name_duplicate_keeps_canonical_name_record_and_logs_it():
    df = frame(rec("Mapusa APMC", "2025-11-03"), rec("Mapusa", "2025-11-03"), rec("Mapusa", "2025-11-04"))
    d, log = ir.dedupe(df, ACCEPTED)
    assert d.dedup_status.tolist() == ["exact_duplicate_removed", "exact_duplicate_retained", "unique"]
    assert d.loc[1, "source_id"] == d.loc[1, "canonical_id"] == "S|D|Mapusa"  # tie-break: canonical-name record kept
    assert len(log) == 1 and log.removed_from_view.item() == 1 and log.retained_ref.item() == d.loc[1, "record_ref"]
    assert d.usable_for_target.tolist() == [False, True, True]
    assert len(d) == len(df)  # nothing deleted: removal is a flag in the analytical view


def test_dedup_keeps_earlier_exclusions():
    df = frame(rec("Mapusa", "2025-11-04"), rec("Mapusa", "2025-11-05")).assign(usable_for_target=[False, True])  # e.g. R09 excluded
    d, _ = ir.dedupe(df, ACCEPTED)
    assert d.usable_for_target.tolist() == [False, True]


def test_dedup_is_deterministic_under_row_order():
    rs = [rec("Mapusa APMC", "2025-11-03"), rec("Mapusa", "2025-11-03")]
    a, _ = ir.dedupe(frame(*rs), ACCEPTED)
    b, _ = ir.dedupe(frame(*reversed(rs)), ACCEPTED)
    keep = lambda d: d.loc[d.dedup_status == "exact_duplicate_retained", "record_ref"].item()
    assert keep(a) == keep(b)


def test_differing_values_become_conflict_never_averaged():
    df = frame(rec("Mapusa APMC", "2025-11-03", modal="1500"), rec("Mapusa", "2025-11-03", modal="1600"))
    d, log = ir.dedupe(df, ACCEPTED)
    assert set(d.dedup_status) == {"identity_conflict"} and not d.usable_for_target.any()
    assert d.modal_price_rs_per_quintal.tolist() == [1500.0, 1600.0] and log.removed_from_view.item() == 0


def test_unaccepted_identities_and_different_grades_are_never_deduplicated():
    df = frame(rec("Sheohar APMC", "2025-11-03"), rec("Sheohar", "2025-11-03"),          # identity not accepted
               rec("Mapusa APMC", "2025-11-03", grade="Local"), rec("Mapusa", "2025-11-03"))  # different grade
    d, log = ir.dedupe(df, ACCEPTED)
    assert set(d.dedup_status) == {"unique"} and log.empty
    assert sorted(d.Grade) == ["FAQ", "FAQ", "FAQ", "Local"]  # grades preserved


def test_series_identity_uses_canonical_market_and_optional_grade():
    assert ir.series_key(False) == ["Commodity", "canonical_id", "Variety"]
    assert ir.series_key(True) == ["Commodity", "canonical_id", "Variety", "Grade"]
    df = frame(rec("Mapusa", "2025-10-20"), rec("Mapusa APMC", "2025-11-20"), rec("Mapusa APMC", "2025-11-21", grade="Local"))
    d, _ = ir.dedupe(df, ACCEPTED)
    assert ir.series_stats(d, ir.series_key(False))["series"] == 1  # one history across the rename
    assert ir.series_stats(d, ir.series_key(True))["series"] == 2   # grade-aware splits FAQ and Local


def _pair(**kw):
    base = dict(State="S", District_old="D", Market_old="Mapusa", District_new="D", Market_new="Mapusa APMC", same_district=True)
    return pd.Series({**base, **kw})


def test_pair_checks_accept_reject_and_unresolved():
    pre = [rec("Mapusa", d) for d in ["2025-10-10", "2025-10-20", "2025-11-01", "2025-11-02", "2025-11-03", "2025-11-04", "2025-11-05"]]
    post = [rec("Mapusa APMC", d) for d in ["2025-11-01", "2025-11-02", "2025-11-03", "2025-11-04", "2025-11-05", "2025-11-10"]]
    df = frame(*pre, *post)
    off_new = {("s", "mapusaapmc"): {"id": 7, "district": "D"}}
    ok = ir.pair_checks(_pair(), df, off_new, {}, {})
    assert ok["validation_status"] == "accepted_rule_v1" and ok["same_day_records"] == 5
    collide = ir.pair_checks(_pair(), df, off_new, {}, {"S|D|Mapusa": 2})
    assert collide["validation_status"] == "rejected" and "many_to_one_collision" in collide["hard_fail"]
    late = ir.pair_checks(_pair(), frame(*pre, *post, rec("Mapusa", "2026-03-01")), off_new, {}, {})
    assert "old_name_active_after_cutover" in late["hard_fail"]
    unlisted = ir.pair_checks(_pair(), df, {}, {}, {})
    assert unlisted["validation_status"] == "unresolved" and "new_name_not_in_agmarknet2_market_list" in unlisted["unmet"]


def test_proposal_targets_counts_many_to_one_across_high_and_medium_only():
    scored = pd.DataFrame([{"State": "S", "District_old": "D", "Market_old": "Una", "confidence": c} for c in ["high", "medium", "low"]]
                          + [{"State": "S", "District_old": "D", "Market_old": "Kota", "confidence": "high"}])
    assert ir.proposal_targets(scored) == {"S|D|Una": 2, "S|D|Kota": 1}


def test_medium_sample_is_reproducible_and_stratified():
    med = pd.DataFrame([{"State": s, "District_new": "D", "Market_new": f"M{i}", "District_old": "D", "Market_old": f"O{i}",
                         "co_reported": i % 5, "crops_new": "Onion" if i % 2 else "Onion,Wheat", "same_district": True}
                        for i, s in enumerate(["A"] * 60 + ["B"] * 15)])
    a, b = ir.medium_sample(med, None), ir.medium_sample(med, None)
    assert a.Market_new.tolist() == b.Market_new.tolist()
    per = a.groupby("stratum").size()
    assert (per >= 1).all() and len(a) < len(med)
    assert set(ir.medium_strata(med, None).stratum) == set(a.stratum)  # every stratum represented
