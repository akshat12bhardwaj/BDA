"""
data.gov.in single-call partition checks on synthetic responses. No network call, no key.
"""

import sys

from Code.candidates import datagov_partition_check as pc


def r(market, state="S", variety="Other", modal=1500):
    return {"State": state, "Market": market, "Variety": variety, "Modal_Price": str(modal), "Arrival_Date": "17/01/2024"}


def test_single_call_accepts_only_complete_distinct_untruncated():
    assert pc.single_call_ok({"total": 2, "records": [r("a"), r("b")]})["ok"]
    assert not pc.single_call_ok({"total": 3, "records": [r("a"), r("b")]})["ok"]          # short
    assert not pc.single_call_ok({"total": 2, "records": [r("a"), r("a")]})["ok"]          # duplicate
    assert not pc.single_call_ok({"total": 2, "records": [r("a"), r("b")]}, limit=2)["ok"]  # may be truncated


def test_partitions_that_reassemble_the_coarse_set():
    coarse = [r("a", "X"), r("b", "X"), r("c", "Y")]
    res = pc.compare_partitions(coarse, {"X": (2, coarse[:2]), "Y": (1, coarse[2:])})
    assert res["equal"] and res["missing_from_parts"] == res["extra_in_parts"] == res["overlap_between_parts"] == 0


def test_missing_extra_and_overlapping_partitions_fail():
    coarse = [r("a", "X"), r("b", "X"), r("c", "Y")]
    missing = pc.compare_partitions(coarse, {"X": (2, coarse[:2])})
    assert missing["missing_from_parts"] == 1 and not missing["equal"]
    extra = pc.compare_partitions(coarse, {"X": (2, coarse[:2]), "Y": (2, [coarse[2], r("z", "Y")])})
    assert extra["extra_in_parts"] == 1 and not extra["equal"]
    overlap = pc.compare_partitions(coarse, {"X": (2, coarse[:2]), "Y": (2, coarse[1:])})
    assert overlap["overlap_between_parts"] == 1 and not overlap["equal"]


def test_totals_must_sum_even_when_sets_match():
    coarse = [r("a"), r("b")]
    assert not pc.compare_partitions(coarse, {"S": (3, coarse)})["equal"]


def test_no_key_stops_before_any_request(tmp_path, monkeypatch):
    monkeypatch.delenv("DATAGOV_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["datagov_partition_check.py"])
    monkeypatch.setattr(pc.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network call")))
    assert pc.main() == 2
