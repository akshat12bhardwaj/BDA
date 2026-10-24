"""
candidate-prices-v1 build: identity status, grade separation, weekly medians with traceable cells, leakage-safe price-only
model tables, the D-50 date guard and R09u staying disabled. Synthetic data only; no network, no real files written.
"""

import pandas as pd
import pytest

from Code.candidates import build_candidate_prices as b, candidate_decisions as cd


def recs(rows):
    d = pd.DataFrame(rows)
    d["reported_date"] = pd.to_datetime(d.date)
    d["week_start"] = d.reported_date - pd.to_timedelta(d.reported_date.dt.dayofweek, unit="D")
    d["in_complete_week"] = True
    d["record_ref"] = [f"r{i:03d}" for i in range(len(d))]
    for k in ("usable_for_target",):
        d[k] = d.get(k, True)
    return b.grade_membership(d)


def row(date, modal, grade="FAQ", market="S|D|M", variety="Onion", usable=True):
    return {"date": date, "modal_price_rs_per_quintal": float(modal), "Grade": grade, "canonical_id": market,
            "Commodity": "Onion", "Variety": variety, "usable_for_target": usable}


def test_weekly_median_per_grade_design_never_mixes_excluded_or_other_grades():
    d = recs([row("2024-02-05", 1000), row("2024-02-06", 1200), row("2024-02-07", 5000, grade="Non-FAQ"),
              row("2024-02-08", 9999, usable=False), row("2024-02-09", 1100, grade="Local")])
    faq = b.weekly(d, "faq_only").iloc[0]
    assert (faq.target_median, faq.n_records, faq.grades) == (1100.0, 2, "FAQ")
    fl = b.weekly(d, "faq_local").iloc[0]
    assert (fl.target_median, fl.n_records, fl.grades) == (1100.0, 3, "FAQ,Local")
    pooled = b.weekly(d, "pooled").iloc[0]
    assert pooled.n_records == 4 and pooled.grades == "FAQ,Local,Non-FAQ"  # the excluded 9999 never enters
    assert d.Grade.tolist() == ["FAQ", "FAQ", "Non-FAQ", "FAQ", "Local"]  # source labels unchanged


def test_weekly_cells_are_traceable_and_deterministic():
    d = recs([row("2024-02-05", 1000), row("2024-02-06", 1200)])
    a, c = b.weekly(d, "pooled"), b.weekly(d.iloc[::-1].copy(), "pooled")
    assert a.cell_refs_sha.item() == c.cell_refs_sha.item()
    assert a.equals(c)


def test_separate_identities_stay_separate_series():
    d = recs([row("2024-02-05", 1000, market="S|D|Sheohar"), row("2024-02-05", 1000, market="S|D|Sheohar APMC")])
    w = b.weekly(d, "pooled")
    assert len(w) == 2  # identical prices never merge unapproved identities


def _weekly(weeks, values, market="S|D|M"):
    return pd.DataFrame({"design": "faq_only", "Commodity": "Onion", "canonical_id": market, "Variety": "Onion",
                         "week_start": pd.to_datetime(weeks), "target_median": values, "n_days": 6})


def test_model_table_features_only_from_the_past_and_targets_exact_horizon():
    weeks = pd.date_range("2024-02-05", periods=60, freq="7D")
    mt = b.model_table(_weekly(weeks, [float(i) for i in range(60)]))
    r = mt[(mt.horizon_weeks == 4) & (mt.origin_week_start == weeks[55])].iloc[0]
    assert (r.y_origin, r.lag1, r.lag4, r.lag52, r.y_target) == (55.0, 54.0, 51.0, 3.0, 59.0)
    assert (mt.target_week_start - mt.origin_week_start).dt.days.isin([7, 14, 28]).all()
    assert mt[mt.origin_week_start == weeks[10]].lag52.isna().all()  # no history before the series start
    # cumulative usable dates to the origin: the last origin with a target is week index 58 -> 59 weeks x 6 days
    assert not mt.eligible_d41.iloc[0] and mt.n_usable_dates_to_origin.max() == 6 * 59


def test_v11_d41_count_includes_dates_before_the_first_complete_week():
    weeks = pd.date_range("2024-02-05", periods=61, freq="7D")  # 61 weeks x 6 days = 366 by the last origin
    w = _weekly(weeks, [1.0] * 61)
    w.loc[:, "n_days"] = 6
    v1 = b.model_table(w)
    key = ("Onion", "S|D|M", "Onion")
    v11 = b.model_table(w, pd.Series({key: 2}))
    o = weeks[59]  # 60 weeks x 6 = 360 complete-week dates: v1 not eligible, +2 partial-week dates still 362
    r1 = v1[(v1.origin_week_start == o) & (v1.horizon_weeks == 1)].iloc[0]
    r11 = v11[(v11.origin_week_start == o) & (v11.horizon_weeks == 1)].iloc[0]
    assert r11.n_usable_dates_to_origin == r1.n_usable_dates_to_origin + 2
    assert v11.drop(columns=["n_usable_dates_to_origin", "eligible_d41"]).equals(v1.drop(columns=["n_usable_dates_to_origin", "eligible_d41"]))
    assert b.D41_MIN_DATES == 365  # threshold unchanged


def test_v1_is_the_frozen_reference_and_v11_records_its_changes():
    assert b.VERSIONS["v1"]["changes"] == [] and not b.VERSIONS["v1"]["d41_full_count"] and not b.VERSIONS["v1"]["dedup_type_variants"]
    assert b.VERSIONS["v1.1"]["d41_full_count"] and b.VERSIONS["v1.1"]["dedup_type_variants"] and len(b.VERSIONS["v1.1"]["changes"]) == 2
    assert b.VERSIONS["v1"]["dest"] != b.VERSIONS["v1.1"]["dest"]


def test_model_table_gap_gives_missing_lag_not_a_shifted_one():
    mt = b.model_table(_weekly(pd.to_datetime(["2024-02-05", "2024-02-19", "2024-02-26"]), [1.0, 3.0, 4.0]))
    r = mt[(mt.origin_week_start == "2024-02-19") & (mt.horizon_weeks == 1)].iloc[0]
    assert pd.isna(r.lag1) and r.lag2 == 1.0 and r.weeks_since_prev_obs == 2


def test_leakage_check_enforces_d50_start_and_price_only():
    weeks = pd.date_range("2024-02-05", periods=10, freq="7D")
    mt = b.model_table(_weekly(weeks, [1.0] * 10))
    ok_records = pd.DataFrame({"reported_date": pd.to_datetime(["2024-02-03"])})
    b.check_leakage(mt, ok_records)
    with pytest.raises(ValueError, match="U3"):
        b.check_leakage(mt, pd.DataFrame({"reported_date": pd.to_datetime(["2023-12-31"])}))
    with pytest.raises(AssertionError):
        b.check_leakage(mt.assign(arrivals_tonnes=1.0), ok_records)


def test_identity_status_labels():
    dec = pd.DataFrame({"old_id": ["A", "C", "E"], "new_id": ["B", "D", "F"],
                        "decision": ["approved_candidate_experiment", "separate_pending_review", "separate_not_mapped"]})
    d = pd.DataFrame({"source_id": ["A", "B", "C", "D", "F", "Z"]})
    assert b.identity_status(d, dec).tolist() == ["approved_mapping", "approved_mapping", "separate_pending_review",
                                                  "separate_pending_review", "separate_not_mapped", "own"]


def test_complete_week_window_and_r09u_disabled():
    assert pd.Timestamp(b.FIRST_WEEK).dayofweek == 0 and pd.Timestamp(b.LAST_WEEK).dayofweek == 0
    assert pd.Timestamp(b.FIRST_WEEK) >= pd.Timestamp(cd.CANDIDATE_START)
    assert pd.Timestamp(b.LAST_WEEK) + pd.Timedelta(days=6) <= pd.Timestamp("2026-10-20")
    assert cd.R09U_APPROVED is False
