"""
D-52 post-run invariant (D-53 item 10): a run lock is always accompanied by a completion record that matches the run
manifest, which matches the freeze, and every output matches its recorded hash. Replaces the pre-run-only "no lock"
assertion in the frozen test_persistence_test_candidate.py, which is left unchanged. The real evidence is only hashed
and read as JSON; run() is only ever called on a synthetic root, so the real evaluation is never rerun.
"""

import json, shutil

import pandas as pd
import pytest

from Code.candidates import baselines_candidate as bc, persistence_test_candidate as pt

OUTPUTS = {f"{k}.csv" for k in ("coverage", "by_crop", "by_crop_month", "by_crop_state", "leave_one_state_out", "exclusions")}


def check_completed_run(root):
    """Assert the post-run invariant under root; returns the run manifest."""
    lock, done, man = root / pt.LOCK, root / pt.DONE, root / pt.RUN_DIR / "run_manifest.json"
    assert lock.exists(), "no run lock"
    assert done.exists(), "lock without completion record"
    assert json.loads(done.read_text())["run_manifest_sha256"] == pt.sha(man), "completion record does not match the run manifest"
    m = json.loads(man.read_text())
    assert m["freeze_manifest_sha256"] == pt.sha(root / pt.FREEZE) == json.loads(lock.read_text())["freeze_manifest_sha256"], \
        "run manifest or lock does not match the freeze"
    assert set(m["outputs_sha256"]) == OUTPUTS, "unexpected output set"
    bad = [f for f, h in m["outputs_sha256"].items() if pt.sha(root / pt.RUN_DIR / f) != h]
    assert not bad, f"outputs changed: {bad}"
    return m


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    (tmp_path / bc.DATASET).mkdir(parents=True)
    o = pd.to_datetime(["2026-06-22", "2026-06-29"])
    mt = pd.DataFrame({"Commodity": "Onion", "canonical_id": ["A|D|M", "B|D|M"], "Variety": "V", "origin_week_start": o,
                       "origin_date": o + pd.Timedelta(days=6), "target_week_start": o + pd.Timedelta(weeks=1), "horizon_weeks": 1,
                       "y_origin": 100.0, "y_target": [110.0, 95.0], "eligible_d41": True})
    for d in ("faq_only", "faq_local", "pooled"):
        mt.assign(design=d).to_parquet(tmp_path / bc.DATASET / f"model_table_{d}.parquet")
    (tmp_path / pt.D52_DIR).mkdir(parents=True); (tmp_path / pt.FREEZE).write_text("{}")
    rec = {"code": {}, "designs": ["faq_only", "faq_local", "pooled"], "horizons": [1, 2, 4]}
    monkeypatch.setattr(pt, "verify", lambda root: (rec, {"synthetic": True}))
    monkeypatch.setattr(pt, "loaded_code", lambda root: [])
    pt.run(tmp_path, "D-52")
    return tmp_path


def test_invariant_holds_after_a_synthetic_completed_run(synthetic_run):
    assert check_completed_run(synthetic_run)["decision"] == "D-52"


@pytest.mark.parametrize("target, match", [(pt.RUN_DIR / "by_crop.csv", "outputs changed"),
                                           (pt.RUN_DIR / "run_manifest.json", "does not match the run manifest"),
                                           (pt.FREEZE, "does not match the freeze")])
def test_invariant_detects_tampered_evidence(synthetic_run, target, match):
    p = synthetic_run / target
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(AssertionError, match=match):
        check_completed_run(synthetic_run)


def test_invariant_detects_a_lock_without_completion(synthetic_run, tmp_path_factory):
    copy = tmp_path_factory.mktemp("interrupted")
    shutil.copytree(synthetic_run / pt.D52_DIR, copy / pt.D52_DIR)
    (copy / pt.DONE).unlink()                              # a copy: the synthetic original is untouched
    with pytest.raises(AssertionError, match="lock without completion"):
        check_completed_run(copy)
    with pytest.raises(bc.GuardError, match="did not complete"):   # and the guard still refuses a rerun
        pt.take_lock(copy, "f")


def test_real_d52_evidence_is_complete_and_still_matches_the_freeze():
    """Read-only: hashes and JSON of the real run evidence; verify() hashes inputs only. Nothing is rerun."""
    if not pt.LOCK.exists():
        pytest.skip("D-52 run evidence not present (fresh clone)")
    m = check_completed_run(pt.Path("."))
    assert m["designs"] == ["faq_only", "faq_local", "pooled"] and m["horizons"] == [1, 2, 4]
    assert m["seed"] == 20261022 and m["reps"] == 10_000 and "persistence only" in m["note"]
    rec, _ = pt.verify()
    assert set(m["loaded_code"]) <= set(rec["code"])
    with pytest.raises(bc.GuardError, match="already completed"):   # the guard refuses before anything is read
        pt.take_lock(pt.Path("."), "f")
