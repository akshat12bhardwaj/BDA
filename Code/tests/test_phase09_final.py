"""
Phase 9 freeze and run-once guard tests. Synthetic data and temporary paths only: nothing here reads the real
reserved 2021-2022 rows or the 2023+ holdout.
"""

import numpy as np
import pandas as pd
import pytest

from Code.integration.pipeline import file_sha256
from Code.modelling import arrivals_final as af
from Code.modelling import arrivals_models as am
from Code.modelling import dataset as m
from Code.tests.test_phase09_arrivals import daily_arr

ACCEPTED = "### D-44 — [ACCEPTED 2026-10-22] protocol\nbody\n### D-45 — [ACCEPTED 2026-10-23 by the project owner] selection\nbody\n"
PROPOSED = ACCEPTED.replace("D-45 — [ACCEPTED 2026-10-23 by the project owner]", "D-45 — [PROPOSED — awaiting]")


def synthetic(tmp_path, decision=ACCEPTED, years=2600):
    """Synthetic features (2016 .. 2023, i.e. including 'holdout' dates), a decision log and a frozen file."""
    df = pd.concat([daily_arr("2016-01-04", years), daily_arr("2016-01-04", years, market="N", base=100.0)
                    .assign(source_row=lambda x: x["source_row"] + 50_000)], ignore_index=True)
    (tmp_path / "f").mkdir()
    path = tmp_path / "f" / "features_onion.parquet"
    df.to_parquet(path, index=False)
    log = tmp_path / "Decision_Log.md"
    log.write_text(decision, encoding="utf-8")
    code = tmp_path / "code.py"
    code.write_text("x = 1\n", encoding="utf-8")
    spec = {"files": [code], "decision_log": log, "inputs": {str(path): file_sha256(path)}}
    return df, path, spec


def test_decision_sections_and_acceptance(tmp_path):
    assert af.decision_section(ACCEPTED, "D-45").startswith("### D-45") and "D-44" not in af.decision_section(ACCEPTED, "D-45")
    log = tmp_path / "log.md"
    log.write_text(PROPOSED, encoding="utf-8")
    assert not af.selection_accepted(log)
    log.write_text(ACCEPTED, encoding="utf-8")
    assert af.selection_accepted(log)
    assert af._sha_text("a\r\nb") == af._sha_text("a\nb")                       # line-ending independent


def test_freeze_written_once_and_detects_changes(tmp_path):
    _, path, spec = synthetic(tmp_path)
    fz = tmp_path / "out" / "freeze.csv"
    man = af.freeze(spec, fz)
    assert set(man["item"]) >= {"file", "decision", "input", "selection", "config", "window"}
    assert len(man[man["item"] == "selection"]) == 9 and man.loc[man["item"] == "selection", "value"].str.startswith("hgb_conservative|").all()
    af.verify_freeze(spec, fz)
    with pytest.raises(m.ModellingError, match="written once"):
        af.freeze(spec, fz)
    spec["files"][0].write_text("x = 2\n", encoding="utf-8")                     # a frozen file changes
    with pytest.raises(m.ModellingError, match="mismatch"):
        af.verify_freeze(spec, fz)


def test_freeze_detects_an_edited_decision(tmp_path):
    _, path, spec = synthetic(tmp_path)
    fz = tmp_path / "out" / "freeze.csv"
    af.freeze(spec, fz)
    spec["decision_log"].write_text(ACCEPTED.replace("selection\nbody", "selection\nedited"), encoding="utf-8")
    with pytest.raises(m.ModellingError, match="mismatch"):
        af.verify_freeze(spec, fz)


def test_bad_input_hash_is_rejected(tmp_path):
    _, path, spec = synthetic(tmp_path)
    spec["inputs"] = {str(path): "0" * 64}
    with pytest.raises(m.ModellingError, match="differs from its recorded hash"):
        af.build_manifest(spec)


def test_preflight_rejects_unaccepted_decision_bad_hash_and_wrong_window(tmp_path):
    _, path, spec = synthetic(tmp_path)
    out = tmp_path / "out"
    fz = out / "freeze.csv"
    af.freeze(spec, fz)
    af.preflight(spec, fz, out)                                                     # all good
    with pytest.raises(m.ModellingError, match="window"):
        af.preflight(spec, fz, out, window=("2021-01-03", "2023-01-08"))           # reaches the holdout
    with pytest.raises(m.ModellingError, match="window"):
        af.preflight(spec, fz, out, window=("2020-01-05", "2022-12-25"))
    spec["decision_log"].write_text(PROPOSED, encoding="utf-8")
    with pytest.raises(m.ModellingError, match="not recorded as ACCEPTED"):
        af.preflight(spec, fz, out)


def test_one_time_run_scores_test_years_only_never_reads_holdout_and_blocks_reruns(tmp_path):
    df, path, spec = synthetic(tmp_path)
    assert df["reported_date"].max() > pd.Timestamp("2023-01-01")                 # holdout-period rows exist on disk
    out = tmp_path / "out"
    fz = out / "freeze.csv"
    af.freeze(spec, fz)
    r = af.run_test(tmp_path / "f", out, ["Onion"], spec, fz, b=50)
    audit = r["audit"]
    assert (audit["rows_after_2022_12_25_read"] == 0).all()
    assert (pd.to_datetime(audit["max_reported_date_read"]) <= af.DATA_END).all()
    assert (pd.to_datetime(audit["last_scored_target_sunday"]) <= af.TEST_LAST).all()
    assert (pd.to_datetime(audit["first_scored_target_sunday"]) >= af.TEST_FIRST).all()
    met = r["metrics"]
    assert set(met["period"]) == {"test_2021", "test_2022", "test_combined"}
    assert set(met["population"]) == {"primary", "original", "mp_excluded"} and set(met["horizon_weeks"]) == {1, 2, 4}
    p = r["predictions"]
    assert p["hgb_conservative"].notna().all() and np.isfinite(p["persistence"]).all()   # identical rows for both
    log = pd.read_csv(out / "run_log.csv")
    assert log["status"].tolist() == ["started", "completed"]
    with pytest.raises(m.ModellingError, match="already attempted"):
        af.run_test(tmp_path / "f", out, ["Onion"], spec, fz, b=50)
    assert pd.read_csv(out / "run_log.csv")["status"].tolist() == ["started", "completed"]   # refusal is not a run


def test_a_failed_run_is_logged_as_failed_and_blocks_a_silent_retry(tmp_path, monkeypatch):
    _, path, spec = synthetic(tmp_path)
    out = tmp_path / "out"
    fz = out / "freeze.csv"
    af.freeze(spec, fz)

    def boom(*a, **k):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(am, "fit_predict", boom)
    with pytest.raises(RuntimeError, match="simulated"):
        af.run_test(tmp_path / "f", out, ["Onion"], spec, fz, b=50)
    log = pd.read_csv(out / "run_log.csv")
    assert log["status"].tolist() == ["started", "failed"] and "simulated" in log["detail"].iloc[-1]
    assert not (out / af.RESULTS).exists()
    monkeypatch.undo()
    with pytest.raises(m.ModellingError, match="review required"):
        af.run_test(tmp_path / "f", out, ["Onion"], spec, fz, b=50)


def test_test_year_labels_reject_dates_outside_the_window():
    ok = af.test_year(pd.Series(pd.to_datetime(["2021-01-03", "2022-12-25"])))
    assert ok.tolist() == ["test_2021", "test_2022"]
    with pytest.raises(m.ModellingError, match="outside the test years"):
        af.test_year(pd.Series(pd.to_datetime(["2023-01-01"])))
