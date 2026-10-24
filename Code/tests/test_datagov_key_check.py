"""
data.gov.in key-check harness: pagination and record validation on synthetic pages, key loading and the no-key exit.
No test makes a network call or needs a real key.
"""

import sys

from Code.candidates import datagov_key_check as dk

DATE = "17/01/2024"


def rec(market, modal=1500, date=DATE, commodity="Onion", variety="Other"):
    return {"Arrival_Date": date, "Commodity": commodity, "Commodity_Code": "23", "District": "D", "Grade": "FAQ",
            "Market": market, "Max_Price": "2000", "Min_Price": "1000", "Modal_Price": str(modal), "State": "S", "Variety": variety}


def test_clean_pagination_passes():
    pages = [[rec("a"), rec("b")], [rec("c"), rec("d")], [rec("e")]]
    r = dk.check_pages(pages, total=5, page_size=2, commodity="Onion", date=DATE)
    assert r["complete_and_unique"] and r["duplicate_rows"] == 0 and r["gap_records"] == 0


def test_duplicates_across_pages_and_gaps_are_detected():
    # page 2 repeats a record from page 1, so one real record is never returned
    pages = [[rec("a"), rec("b")], [rec("b"), rec("c")], [rec("d")]]
    r = dk.check_pages(pages, total=6, page_size=2, commodity="Onion", date=DATE)
    assert r["duplicate_rows"] == 1 and r["gap_records"] == 2 and not r["complete_and_unique"]


def test_short_page_and_key_conflict_are_detected():
    pages = [[rec("a")], [rec("a", modal=1600), rec("b")]]
    r = dk.check_pages(pages, total=3, page_size=2, commodity="Onion", date=DATE)
    assert r["short_non_final_pages"] == [0] and r["key_conflicts"] == 1


def test_malformed_records_are_reported():
    bad = [rec("a", date="18/01/2024"), rec("b", commodity="Potato"), rec("c", modal="x"), rec("d", modal=5000), {"Market": "e"}]
    r = dk.check_pages([bad], total=5, page_size=5, commodity="Onion", date=DATE)
    probs = r["malformed"]
    assert {"date 18/01/2024 != 17/01/2024", "commodity Potato", "non-numeric price"} <= set(probs)
    assert any(p.startswith("missing") for p in probs)
    # range violations are source flags (published as-is), not malformed responses
    assert r["source_flags"] == {"modal outside [min, max]": 1} and "modal outside [min, max]" not in probs


def test_source_flags_alone_do_not_fail_a_complete_retrieval():
    r = dk.check_pages([[rec("a"), rec("b", modal=114)]], total=2, page_size=2, commodity="Onion", date=DATE)
    assert r["complete_and_unique"] and r["source_flags"] == {"modal outside [min, max]": 1}


def test_key_from_env_then_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DATAGOV_API_KEY", raising=False)
    assert dk.load_key(tmp_path) is None
    (tmp_path / ".secrets").mkdir(); (tmp_path / ".secrets" / "datagov_api_key").write_text("file-key\n")
    assert dk.load_key(tmp_path) == "file-key"
    monkeypatch.setenv("DATAGOV_API_KEY", "env-key")
    assert dk.load_key(tmp_path) == "env-key"


def test_no_key_stops_before_any_request(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DATAGOV_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["datagov_key_check.py"])
    monkeypatch.setattr(dk.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network call")))
    assert dk.main() == 2
    assert "Live test not run" in capsys.readouterr().out
