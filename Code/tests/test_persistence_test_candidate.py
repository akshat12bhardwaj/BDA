"""
D-52 persistence-only test runner: authorised window, holdout refusal, availability checks, persistence metrics, the
one-time guard and the freeze checks. Synthetic data in tmp_path only; no real test-window or holdout record is read,
and run() is only ever called on a synthetic root.
"""

import inspect, json

import numpy as np
import pandas as pd
import pytest

from Code.candidates import baselines_candidate as bc, persistence_test_candidate as pt

S = {"Commodity": "Onion", "Variety": "V"}


def rows(origins, h=1, **kw):
    o = pd.to_datetime(origins)
    d = {**S, "canonical_id": "A|D|M", "origin_week_start": o, "origin_date": o + pd.Timedelta(days=6),
         "target_week_start": o + pd.Timedelta(weeks=h), "horizon_weeks": h, "y_origin": 100.0, "y_target": 110.0, "eligible_d41": True}
    return pd.DataFrame({**d, **kw})


def test_authorised_window_is_the_frozen_protocol_test_split():
    assert pt.AUTHORISED_TEST == bc.ed.PROPOSED_SPLIT["test"] == ("2026-07-05", "2026-10-18")
    assert (pt.FIRST_WEEK, pt.LAST_WEEK) == (pd.Timestamp("2026-06-29"), pd.Timestamp("2026-10-12"))
    assert pt.LAST_WEEK == pd.Timestamp(bc.ed.b.LAST_WEEK)            # the last complete week of the dataset
    p = bc.PROTOCOL_FILE
    if p.exists():  # protocol only (no data rows)
        assert tuple(json.loads(p.read_text())["split_by_target_sunday"]["test"]) == pt.AUTHORISED_TEST
        assert bc.protocol_hash(p) == pt.PROTOCOL_LF_SHA256


def test_existing_guards_are_unchanged():
    assert bc.LAST_ALLOWED_TARGET_WEEK == pd.Timestamp("2026-06-22") and bc.cd.CANDIDATE_START == "2024-02-03"
    assert bc.APPROVED_PROTOCOL == "a6b1240c" and bc.cd.R09U_APPROVED is False


def test_read_test_rows_loads_only_the_authorised_window(tmp_path):
    # targets 2026-06-22 (validation), 06-29 and 10-12 (test), 10-19 (after the window)
    rows(["2026-06-15", "2026-06-22", "2026-10-05", "2026-10-12"]).to_parquet(tmp_path / "m.parquet")
    df = pt.read_test_rows(tmp_path / "m.parquet")
    assert sorted(df.target_week_start.dt.strftime("%Y-%m-%d")) == ["2026-06-29", "2026-10-12"]


def test_holdout_period_origins_are_refused():
    df = rows(["2026-06-22"])
    df.loc[0, ["origin_week_start", "origin_date"]] = [pd.Timestamp("2023-06-05"), pd.Timestamp("2023-06-11")]
    with pytest.raises(bc.GuardError, match="2024-02-03"):
        pt.check_availability(df)


@pytest.mark.parametrize("col, value", [("target_week_start", "2026-07-13"), ("origin_date", "2026-06-30"), ("horizon_weeks", 2)])
def test_inconsistent_origin_horizon_or_target_is_refused(col, value):
    df = rows(["2026-06-22"])
    df[col] = pd.Timestamp(value) if isinstance(value, str) else value
    with pytest.raises(bc.GuardError, match="availability"):
        pt.check_availability(df)


def test_persistence_is_y_origin_and_exclusions_keep_their_reason():
    mt = pd.concat([rows(["2026-06-22"]), rows(["2026-06-29"], eligible_d41=False), rows(["2026-07-06"], y_target=0.0),
                    rows(["2026-07-13"], h=2)], ignore_index=True)
    x, ev = pt.evaluate(mt, 1)
    assert len(x) == 3 and ev.pred.tolist() == [100.0] and ev.month.tolist() == ["2026-07"]
    assert sorted(x.exclusion[x.exclusion != ""]) == ["missing_or_non_positive_target", "not_eligible_d41_at_origin"]
    t = pt.cell_tables(mt, 1)
    assert t["by_crop"].mae.tolist() == [10.0] and t["coverage"].loc[0, ["test_rows", "excluded_rows", "evaluated_rows"]].tolist() == [3, 2, 1]
    assert t["exclusions"].rows.sum() == 2


def test_month_is_named_by_the_thursday_of_the_target_week():
    _, ev = pt.evaluate(rows(["2026-07-20"]), 1)              # target week Mon 2026-07-27 .. Sun 08-02 -> July
    assert ev.month.tolist() == ["2026-07"]


def test_mae_ci_is_seeded_and_brackets_the_mae():
    rng = np.random.RandomState(0)
    df = pd.DataFrame({"canonical_id": np.repeat(list("abcdefgh"), 5), "y_target": 100.0, "pred": 100 + rng.normal(0, 10, 40)})
    n, lo, hi = pt.mae_ci(df, "canonical_id", reps=2000)
    assert n == 8 and lo <= (df.pred - df.y_target).abs().mean() <= hi and (lo, hi) == pt.mae_ci(df, "canonical_id", reps=2000)[1:]
    assert np.isnan(pt.mae_ci(df[df.canonical_id == "a"], "canonical_id")[1])   # one cluster: no interval


def test_leave_one_state_out_and_state_rows():
    mt = pd.concat([rows(["2026-06-22"]), rows(["2026-06-22"], canonical_id="B|D|M", y_target=130.0)], ignore_index=True)
    t = pt.cell_tables(mt, 1)
    assert sorted(t["leave_one_state_out"].mae) == [10.0, 30.0] and t["by_crop_state"].state.tolist() == ["A", "B"]
    assert t["by_crop"].loc[0, ["markets", "states", "market_clusters"]].tolist() == [2, 2, 2]


def test_one_time_guard_refuses_after_start_completion_or_stray_outputs(tmp_path):
    pt.take_lock(tmp_path, "f")
    with pytest.raises(bc.GuardError, match="did not complete"):          # interrupted run: no bypass
        pt.take_lock(tmp_path, "f")
    (tmp_path / pt.DONE).write_text("{}")
    with pytest.raises(bc.GuardError, match="already completed"):
        pt.take_lock(tmp_path, "f")
    other = tmp_path / "o"; (other / pt.RUN_DIR).mkdir(parents=True)
    with pytest.raises(bc.GuardError, match="without a lock"):
        pt.take_lock(other, "f")


def test_run_needs_the_explicit_confirmation_before_any_check(tmp_path):
    for c in (None, "yes", "D-51"):
        with pytest.raises(bc.GuardError, match="final execution gate"):
            pt.run(tmp_path, c)
    assert not (tmp_path / pt.LOCK).exists()


def _signed_root(tmp_path, entry="### D-52 — [ACCEPTED x] y\nbody\n"):
    (tmp_path / "Documentation").mkdir(); (tmp_path / pt.DECISION_LOG).write_text("### D-51 — a\n" + entry, encoding="utf-8")
    (tmp_path / "a.txt").write_text("frozen")
    rec = {"decision_section_lf_sha256": pt.decision_sha(entry), "files": {"a.txt": pt.sha(tmp_path / "a.txt")}, "code": {}}
    (tmp_path / pt.D52_DIR).mkdir(parents=True); (tmp_path / pt.FREEZE).write_text(json.dumps(rec))
    return rec


def test_verify_refuses_without_freeze_unrecorded_or_edited_decision_and_changed_files(tmp_path):
    with pytest.raises(bc.GuardError, match="no D-52 freeze"):
        pt.verify(tmp_path)
    _signed_root(tmp_path)
    (tmp_path / "a.txt").write_text("changed")
    with pytest.raises(bc.GuardError, match="missing or changed"):
        pt.verify(tmp_path)
    (tmp_path / pt.DECISION_LOG).write_text("### D-52 — [ACCEPTED x] y\nedited\n", encoding="utf-8")
    with pytest.raises(bc.GuardError, match="changed after the freeze"):
        pt.verify(tmp_path)
    (tmp_path / pt.DECISION_LOG).write_text("### D-51 — a\n", encoding="utf-8")
    with pytest.raises(bc.GuardError, match="not recorded"):
        pt.verify(tmp_path)
    assert pt.decision_sha("### D-52 — [ACCEPTED x] y\r\nbody\r\n") == pt.decision_sha("### D-52 — [ACCEPTED x] y\nbody\n")


def test_freeze_is_written_once(tmp_path):
    (tmp_path / pt.D52_DIR).mkdir(parents=True); (tmp_path / pt.FREEZE).write_text("{}")
    with pytest.raises(bc.GuardError, match="written once"):
        pt.freeze(tmp_path)


def test_run_end_to_end_on_a_synthetic_root_and_refuses_a_second_run(tmp_path, monkeypatch):
    (tmp_path / bc.DATASET).mkdir(parents=True)
    mt = pd.concat([rows(["2026-06-22", "2026-06-29"]), rows(["2026-06-22"], canonical_id="B|D|M", y_target=90.0),
                    rows(["2026-06-01"], h=4)], ignore_index=True)
    for d in ("faq_only", "faq_local", "pooled"):
        mt.assign(design=d).to_parquet(tmp_path / bc.DATASET / f"model_table_{d}.parquet")
    _signed_root(tmp_path)
    rec = {"code": {}, "designs": ["faq_only", "faq_local", "pooled"], "horizons": [1, 2, 4]}
    monkeypatch.setattr(pt, "verify", lambda root: (rec, {"synthetic": True}))
    monkeypatch.setattr(pt, "loaded_code", lambda root: [])
    man = pt.run(tmp_path, "D-52")
    out = pd.read_csv(tmp_path / pt.RUN_DIR / "by_crop.csv")
    assert set(zip(out.design, out.horizon)) == {(d, h) for d in rec["designs"] for h in (1, 4)}   # no h = 2 rows exist
    assert out[(out.design == "faq_only") & (out.horizon == 1)].mae.tolist() == [10.0]
    assert set(man["outputs_sha256"]) == {f"{k}.csv" for k in ("coverage", "by_crop", "by_crop_month", "by_crop_state",
                                                                "leave_one_state_out", "exclusions")}
    assert (tmp_path / pt.LOCK).exists() and (tmp_path / pt.DONE).exists()
    with pytest.raises(bc.GuardError, match="already completed"):
        pt.run(tmp_path, "D-52")


def test_runner_source_reads_no_protected_or_holdout_path_and_fits_nothing():
    src = inspect.getsource(pt)
    for p in ("Processed_Data/cleaned", "Processed_Data/features", "Processed_Data/modelling", "Processed_Data/integration", "Dataset/",
              "Dataset_Candidates", "records_", "weekly_", "dataset_v1'", "'2023-", '"2023-'):
        assert p not in src, p
    for f in (".fit(", "LEARNERS", "refit_date_for", "seasonal_naive(", "climatology("):
        assert f not in src, f


def test_decision_log_records_d52():
    from pathlib import Path
    log = Path("Documentation/Decision_Log.md").read_text(encoding="utf-8")
    pt.decision_sha(log)
    sec = log[log.index("### D-52"):]
    for s in ("Project owner".lower(), "exactly **one** persistence-only", "2026-07-05 → 2026-10-18", "2023 holdout", "fresh evaluation period",
              pt.PROTOCOL_LF_SHA256, "must not be used to tune"):
        assert s in sec or s in sec.lower(), s


def test_real_freeze_verifies_without_reading_records():
    """Hashes and the existing preflight only; no row is decoded and no lock is taken."""
    if not pt.FREEZE.exists():
        pytest.skip("D-52 freeze manifest not present (fresh clone)")
    rec, pre = pt.verify()
    assert rec["decision"] == "D-52" and pre["dataset_version"] == "candidate-prices-v1.1" and not pt.LOCK.exists()
