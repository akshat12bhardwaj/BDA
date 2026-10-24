"""
Staged data.gov.in extraction runner: stage dates, content hashing, atomic writes, resume rules and stage acceptance.
No network call, no key.
"""

import json

from Code.candidates import datagov_extract as ex


def rec(market, modal=1500):
    return {"Arrival_Date": "03/02/2024", "Commodity": "Onion", "Commodity_Code": "23", "District": "D", "Grade": "FAQ",
            "Market": market, "Max_Price": "2000", "Min_Price": "1000", "Modal_Price": str(modal), "State": "S", "Variety": "Other"}


def test_s1_covers_2024_02_03_to_2024_04_30_inclusive():
    days = ex.stage_days(ex.STAGES["S1"]["start"], ex.STAGES["S1"]["end"])
    assert days[0] == "2024-02-03" and days[-1] == "2024-04-30" and len(days) == 88 == len(set(days))
    assert ex.api_date("2024-02-03") == "03/02/2024"


def test_approved_stages_are_consistent_contiguous_and_end_at_2026_10_20():
    assert set(ex.STAGES) == {"S1", "S2", "S3"}
    s2, s3 = ex.STAGES["S2"], ex.STAGES["S3"]
    days = ex.stage_days(s2["start"], s2["end"])
    assert days[0] == "2024-05-01" and days[-1] == "2025-11-06" and len(days) * 3 == s2["crop_days"] == 1665
    days3 = ex.stage_days(s3["start"], s3["end"])
    assert days3[0] == "2025-11-07" and days3[-1] == "2026-10-20" and len(days3) * 3 == s3["crop_days"] == 1044
    assert all(s["crop_days"] == len(ex.stage_days(s["start"], s["end"])) * 3 for s in ex.STAGES.values())
    assert all(s["start"] <= d <= s["end"] for s in ex.STAGES.values() for _, d in s["partitions"])
    assert len({(c, d) for _, s in ex.STAGES.items() for c, d in s["partitions"]}) == 13
    # stages are contiguous and never overlap: every date in the window belongs to exactly one stage
    all_days = [d for s in ex.STAGES.values() for d in ex.stage_days(s["start"], s["end"])]
    assert len(all_days) == len(set(all_days)) == len(ex.stage_days("2024-02-03", "2026-10-20"))


def test_content_hash_ignores_order_but_not_content():
    a, b = rec("a"), rec("b")
    assert ex.content_hash([a, b]) == ex.content_hash([b, a])
    assert ex.content_hash([a, b]) != ex.content_hash([a, rec("b", modal=1501)])


def test_atomic_write_leaves_no_temp_file(tmp_path):
    p = tmp_path / "x" / "f.json"
    ex.atomic_write(p, b"{}")
    assert p.read_bytes() == b"{}" and not list(p.parent.glob("*.tmp"))


def _passed(tmp_path, records, crop="Onion", d="2024-02-03"):
    body = json.dumps({"total": len(records), "records": records}).encode()
    for p in ex.raw_paths(tmp_path, crop, d):
        ex.atomic_write(p, body)
    return {"status": "pass", "filters": ex.params(crop, d), "limit": str(ex.LIMIT), "content_sha256": ex.content_hash(records)}


def test_resume_only_when_params_and_raw_hashes_match(tmp_path):
    row = _passed(tmp_path, [rec("a"), rec("b")])
    assert ex.can_resume(row, "Onion", "2024-02-03", tmp_path)
    assert not ex.can_resume(row, "Onion", "2024-02-04", tmp_path)                 # different parameters
    assert not ex.can_resume({**row, "status": "fail"}, "Onion", "2024-02-03", tmp_path)
    assert not ex.can_resume({**row, "limit": "100"}, "Onion", "2024-02-03", tmp_path)
    ex.raw_paths(tmp_path, "Onion", "2024-02-03")[1].write_bytes(json.dumps({"records": [rec("a")]}).encode())  # tampered
    assert not ex.can_resume(row, "Onion", "2024-02-03", tmp_path)
    assert not ex.can_resume(None, "Onion", "2024-02-03", tmp_path)


def test_manifest_round_trip(tmp_path):
    m = {("Onion", "2024-02-03"): {"commodity": "Onion", "date": "2024-02-03", "status": "pass", "api_total": 2}}
    ex.write_manifest(tmp_path / "m.csv", m)
    back = ex.read_manifest(tmp_path / "m.csv")
    assert back[("Onion", "2024-02-03")]["status"] == "pass" and not list(tmp_path.glob("*.tmp"))


def _row(crop, d, status="pass", total=5, flags="{}"):
    return {"commodity": crop, "date": d, "status": status, "api_total": str(total), "source_flags": flags}


def test_stage_summary_requires_every_crop_day():
    days = ["2024-02-03", "2024-02-04"]
    man = {(c, d): _row(c, d) for d in days for c in ex.CROPS}
    s = ex.stage_summary(man, days, "S1", 6)
    assert s["accepted"] and s["manifest_covers_period_exactly"] and s["records_by_crop"]["Onion"] == 10
    man.pop(("Wheat", "2024-02-04"))
    s = ex.stage_summary(man, days, "S1", 6)
    assert not s["accepted"] and s["status_counts"]["missing"] == 1 and not s["manifest_covers_period_exactly"]


def test_stage_summary_lists_zero_days_and_flags():
    days = ["2024-02-03"]
    man = {(c, "2024-02-03"): _row(c, "2024-02-03") for c in ex.CROPS}
    man[("Wheat", "2024-02-03")] = _row("Wheat", "2024-02-03", "zero_review", 0)
    man[("Onion", "2024-02-03")] = _row("Onion", "2024-02-03", flags='{"modal outside [min, max]": 3}')
    s = ex.stage_summary(man, days, "S1", 6)
    assert s["zero_record_crop_days"] == [("Wheat", "2024-02-03")]
    assert s["source_flags"] == {"Onion: modal outside [min, max]": 3}
