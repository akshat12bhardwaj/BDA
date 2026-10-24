"""
Candidate price-anomaly policy: flags match Phase 5 R03/R04/R07/R08, values are never altered or dropped, and only
unflagged records are usable. Synthetic records only.
"""

import pandas as pd

from Code.candidates import price_policy as pp


def rec(market, mn="1000", mx="2000", md="1500", variety="Other", d="15/05/2024"):
    return {"State": "S", "District": "D", "Market": market, "Commodity": "Wheat", "Commodity_Code": "1", "Variety": variety,
            "Grade": "FAQ", "Arrival_Date": d, "Min_Price": mn, "Max_Price": mx, "Modal_Price": md}


def frame(*recs):
    return pd.DataFrame(list(recs), dtype=str)


def test_flags_and_reasons():
    df = pp.apply_policy(frame(rec("ok"), rec("low", md="900"), rec("high", md="2100"), rec("swap", mn="2000", mx="1000"),
                               rec("zero", md="0"), rec("c", md="1500"), rec("c", md="1600")))
    got = dict(zip(df.Market + df.Modal_Price, df.price_anomaly.astype(str)))
    assert got == {"ok1500": "none", "low900": "modal_outside_range", "high2100": "modal_outside_range",
                   "swap1500": "min_gt_max", "zero0": "modal_missing", "c1500": "key_conflict", "c1600": "key_conflict"}
    assert df.usable_modal_price.tolist() == [True, False, False, False, False, False, False]


def test_source_values_are_never_changed_or_dropped():
    src = frame(rec("a"), rec("b", md="900"), rec("z", md="0"))
    df = pp.apply_policy(src)
    assert len(df) == len(src)
    assert df[src.columns].equals(src)  # original strings preserved exactly
    assert df.loc[df.Market == "b", "modal_price_rs_per_quintal"].item() == 900.0  # flagged, not corrected
    assert pd.isna(df.loc[df.Market == "z", "modal_price_rs_per_quintal"].item())  # R04: zero is missing in the parsed copy
    assert df.loc[df.Market == "z", "modal_price_status"].item() == "zero_set_missing"


def test_policy_effect_counts_records_and_weekly_cells():
    df = pp.apply_policy(frame(rec("a"), rec("a", d="16/05/2024"), rec("b", md="900"), rec("c", md="0")))
    e = pp.policy_effect(df).iloc[0]
    assert (e.records, e.usable_before, e.usable_after, e.excluded_by_policy) == (4, 3, 2, 1)
    assert (e.markets_before, e.markets_after, e.weekly_cells_before, e.weekly_cells_after) == (2, 1, 2, 1)


def test_type_variant_copies_are_deduplicated_only_in_v11_keeping_the_string_copy():
    a, b = rec("t"), rec("t")  # identical as text: the feed's string- and number-typed copies
    df = frame(a, b, rec("u", md="1600"), rec("u", md="1700")).assign(raw_index=[0, 5, 1, 2], raw_value_types=["num", "str", "str", "str"])
    v1 = pp.apply_policy(df)
    assert v1.price_anomaly.astype(str).tolist() == ["key_conflict"] * 4  # v1 behaviour unchanged
    v11 = pp.apply_policy(df, dedup_type_variants=True)
    assert v11.price_anomaly.astype(str).tolist() == ["type_variant_duplicate", "none", "key_conflict", "key_conflict"]
    assert v11.usable_modal_price.tolist() == [False, True, False, False]  # string copy kept; real conflict stays excluded
    assert v11.loc[1, "raw_value_types"] == "str" and len(v11) == 4 and v11.policy_version.iloc[0].endswith(".1")


def test_anomaly_rates_by_month():
    df = pp.apply_policy(frame(rec("a"), rec("b", md="900"), rec("c", d="15/06/2024")))
    r = pp.anomaly_rates(df).set_index("month")
    assert r.loc["2024-05", "modal_outside_range_pct"] == 50.0 and r.loc["2024-06", "modal_outside_range"] == 0
