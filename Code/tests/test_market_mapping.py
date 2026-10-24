"""
Proposed market mapping: candidates come from names, but confidence needs independent evidence; ambiguous and
many-to-one cases are never mapped. Synthetic records only.
"""

import pandas as pd

from Code.candidates import market_mapping as mm


def rows(state, district, market, dates, modal=1500, variety="Onion", grade="FAQ", crop="Onion"):
    return [{"State": state, "District": district, "Market": market, "Commodity": crop, "Variety": variety, "Grade": grade,
             "reported_date": pd.Timestamp(d), "Min_Price": "1000", "Max_Price": "2000", "Modal_Price": str(modal),
             "modal_price_rs_per_quintal": float(modal), "usable_modal_price": True} for d in dates]


PRE = ["2025-10-20", "2025-10-28", "2025-11-01", "2025-11-02", "2025-11-03", "2025-11-04", "2025-11-05"]
CUT = ["2025-11-01", "2025-11-02", "2025-11-03", "2025-11-04", "2025-11-05", "2025-11-20"]


def run(*recs):
    df = pd.DataFrame([r for rs in recs for r in rs])
    inv = mm.inventory(df)
    pairs = mm.candidates(inv)
    scored = mm.score(pairs, mm.co_reporting(df, pairs))
    return df, inv, scored, mm.mapping_table(inv, scored)


def test_successor_with_co_reporting_is_high_confidence_but_only_proposed():
    _, _, scored, t = run(rows("S", "D", "Mapusa", PRE), rows("S", "D", "Mapusa APMC", CUT))
    r = scored.iloc[0]
    assert (r.confidence, r.review_status, r.co_reported, r.identical_share) == ("high", "proposed", 5, 1.0)
    new = t[t.Market == "Mapusa APMC"].iloc[0]
    assert new.canonical_market_id == "S|D|Mapusa" and new.mapping_type == "renamed_successor"
    assert (t.review_status != "approved").all()


def test_suffix_alone_without_co_reporting_is_at_most_medium():
    _, _, scored, _ = run(rows("S", "D", "Kota", ["2025-10-20", "2025-10-28"]), rows("S", "D", "Kota APMC", ["2025-11-10"]))
    assert scored.iloc[0].confidence == "medium"


def test_different_district_or_continuing_old_market_is_not_mapped():
    _, _, s1, t1 = run(rows("S", "D1", "Bassi", PRE), rows("S", "D2", "Bassi APMC", CUT))
    assert s1.iloc[0].confidence == "low" and t1[t1.Market == "Bassi APMC"].iloc[0].canonical_market_id == "S|D2|Bassi APMC"
    _, _, s2, _ = run(rows("S", "D", "Una", PRE + ["2026-03-01"]), rows("S", "D", "Una APMC", CUT))
    assert s2.iloc[0].confidence == "low"  # old name still reporting months later: not a succession


def test_many_to_one_is_never_mapped():
    _, _, scored, t = run(rows("S", "D", "Sheohar", PRE), rows("S", "D", "SHEOHAR", PRE), rows("S", "D", "Sheohar APMC", CUT))
    assert set(scored.confidence) == {"low"} and not scored.one_to_one.any()
    assert t[t.Market == "Sheohar APMC"].iloc[0].mapping_type == "ambiguous_candidate"


def test_identical_prices_without_name_candidate_never_pair():
    _, _, scored, _ = run(rows("S", "D", "Alpha", PRE), rows("S", "D", "Beta APMC", CUT))
    assert scored.empty


def test_weekly_effect_counts_fragmentation_and_cross_name_duplicates():
    df, _, _, t = run(rows("S", "D", "Mapusa", PRE), rows("S", "D", "Mapusa APMC", CUT))
    e = mm.weekly_effect(df, t)
    assert e["source_names"]["series"] == 2 and e["proposed_mapping"]["series"] == 1
    assert e["cross_name_identical_records_after_mapping"] == 5  # 2025-11-01 .. 11-05 reported under both names
