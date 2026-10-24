"""
data.gov.in extraction pilot: date selection, response classification and crop-day verdicts. No network call, no key.
"""

import json

from Code.candidates import datagov_pilot as p


def rec(market, modal=1500, d="18/06/2025", crop="Onion"):
    return {"Arrival_Date": d, "Commodity": crop, "Commodity_Code": 23, "District": "D", "Grade": "FAQ", "Market": market,
            "Max_Price": 2000, "Min_Price": 1000, "Modal_Price": modal, "State": "S", "Variety": "Onion"}


def test_selection_is_30_distinct_crop_days_inside_the_window():
    sel = p.select_dates()
    assert len(sel) == 30 and len({(c, d) for c, d, _ in sel}) == 30
    assert all(sum(c == crop for c, _, _ in sel) == 10 for crop in p.CROPS)
    assert all(p.START.isoformat() <= d <= p.END.isoformat() for _, d, _ in sel)
    assert len({d for _, d, w in sel if w == "spread"}) == 24  # crops never share a spread date
    assert all((c, d) in {(c2, d2) for c2, d2, _ in sel} for c, d in p.PARTITION.items())


def test_classify_retries_transient_and_stops_on_access_or_rate_limit():
    ok = json.dumps({"total": 1, "records": [rec("a")]}).encode()
    assert p.classify("200", ok) == "ok"
    assert p.classify("502", b"<html>bad gateway</html>") == "retry"
    assert p.classify("none", b"") == "retry"
    assert p.classify("429", ok) == "stop"
    assert p.classify("403", b"") == "stop"
    assert p.classify("200", json.dumps({"message": "Rate limit exceeded"}).encode()) == "stop"
    assert p.classify("200", json.dumps({"message": "Invalid key", "records": []}).encode()) == "stop"


def test_crop_day_passes_only_with_two_identical_complete_fetches():
    a, b = rec("a"), rec("b", modal=114)  # b is a source flag (modal below min), not a failure
    good = {"total": 2, "records": [a, b]}
    r = p.crop_day_result("Onion", "2025-06-18", [good, {"total": 2, "records": [b, a]}])  # order differs: still identical
    assert r["pass"] and r["repeat_sets_identical"] and r["source_flags"] == {"modal outside [min, max]": 1}
    changed = p.crop_day_result("Onion", "2025-06-18", [good, {"total": 2, "records": [a, rec("c")]}])
    assert not changed["pass"] and not changed["repeat_sets_identical"]
    short = p.crop_day_result("Onion", "2025-06-18", [{"total": 3, "records": [a, b]}, good])
    assert not short["pass"]
    wrong_day = p.crop_day_result("Onion", "2025-06-18", [{"total": 1, "records": [rec("a", d="19/06/2025")]}] * 2)
    assert not wrong_day["pass"] and wrong_day["malformed"]
