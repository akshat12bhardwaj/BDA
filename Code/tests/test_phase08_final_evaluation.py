"""
Phase 8 final (test-period) evaluation tests on synthetic data: freeze manifest, run-once guard, test-row
selection, refit cutoffs, holdout exclusion and persistence identity. Real outputs are only read, never written.
"""

import pandas as pd
import pytest

from Code.integration.pipeline import file_sha256
from Code.modelling import dataset as m
from Code.modelling import final_evaluation as fe
from Code.tests.test_phase08_models import seasonal

needs_outputs = pytest.mark.skipif(not (m.MODEL_DATA_DIR / fe.RESULTS_NAME).exists(),
                                   reason="the frozen test evaluation has not been run")


def test_freeze_is_written_once_and_detects_changed_files(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("x = 1\n")
    path = tmp_path / "freeze.csv"
    fe.freeze(path, files=[f])
    fe.verify_freeze(path)
    with pytest.raises(m.ModellingError, match="written once"):
        fe.freeze(path, files=[f])
    f.write_text("x = 2\n")
    with pytest.raises(m.ModellingError, match="changed since the freeze"):
        fe.verify_freeze(path)
    with pytest.raises(m.ModellingError, match="no freeze manifest"):
        fe.verify_freeze(tmp_path / "missing.csv")


def test_freeze_records_the_d42_selection_and_settings(tmp_path):
    fz = fe.freeze(tmp_path / "f.csv")
    sel = fz[fz["item"] == "selection"].set_index("name")["value"]
    assert sel["Onion h=1"] == "hgb_conservative (weather)" and sel["all other crop x horizon"] == "persistence"
    s = fz.loc[fz["item"] == "settings", "value"].iloc[0]
    for kv in ["learning_rate=0.05", "max_leaf_nodes=15", "min_samples_leaf=1000", "l2_regularization=10.0",
               "early_stopping=False", "random_state=0", "max_iter=200"]:
        assert kv in s
    assert set(fz.loc[fz["item"] == "file", "name"]) == {str(p) for p in fe.FROZEN_FILES}


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("final")
    df = pd.concat([seasonal(days=2650), seasonal(level=2000.0, market="N", days=2650, review_every=50)], ignore_index=True)
    df["source_row"] = range(len(df))                 # 2016-01-04 .. 2023-04: includes 2023 holdout data
    (tmp / "f").mkdir()
    path = tmp / "f" / "features_onion.parquet"
    df.to_parquet(path, index=False)
    fe.freeze(tmp / "freeze.csv")
    out = fe.run_test_evaluation(tmp / "f", tmp / "out", ["Onion"], {str(path): file_sha256(path)},
                                 freeze_path=tmp / "freeze.csv", b_reps=200)
    return tmp, path, out


def test_only_eligible_test_rows_are_scored(run):
    _, _, out = run
    p = out["predictions"]
    assert set(p["period"]) == {"test_2021", "test_2022"}
    assert set(out["test_results"]["period"]) == {"test_2021", "test_2022", "test_combined"}
    r = out["test_results"].set_index(["horizon_weeks", "period"])
    assert (r.xs("test_combined", level="period")["n_obs"] ==
            r.xs("test_2021", level="period")["n_obs"] + r.xs("test_2022", level="period")["n_obs"]).all()


def test_persistence_cells_have_zero_improvement_and_learned_cell_is_compared_on_identical_rows(run):
    _, _, out = run
    r = out["test_results"]
    pers = r[r["approach"] == "persistence"]
    assert set(pers["horizon_weeks"]) == {2, 4} and (pers["mae_improvement"] == 0).all() and (pers["mae"] == pers["persistence_mae"]).all()
    learned = r[r["approach"] == "hgb_conservative"]
    assert set(learned["horizon_weeks"]) == {1}
    bs = out["test_bootstrap"]
    s = bs[(bs["cluster"] == "series")].set_index("period")
    l1 = learned.set_index("period")
    assert (s.loc[l1.index, "n_obs"] == l1["n_obs"]).all()
    assert s.loc["test_2021", "mae_improvement"] == pytest.approx(l1.loc["test_2021", "mae_improvement"])


def test_refits_never_see_targets_after_the_refit_or_from_the_holdout(run):
    _, _, out = run
    lg = out["test_refit_log"]
    assert (pd.to_datetime(lg["train_last_target_sunday"]) <= pd.to_datetime(lg["refit_date"])).all()
    assert pd.to_datetime(lg["refit_date"]).max() <= pd.Timestamp("2022-10-02")
    assert pd.to_datetime(lg["train_last_target_sunday"]).max() < pd.Timestamp("2023-01-01")


def test_second_run_is_refused(run):
    tmp, path, _ = run
    with pytest.raises(m.ModellingError, match="already been run"):
        fe.run_test_evaluation(tmp / "f", tmp / "out", ["Onion"], {str(path): file_sha256(path)},
                               freeze_path=tmp / "freeze.csv", b_reps=10)


def test_eval_rows_rejects_rows_outside_the_test_years():
    ex = pd.DataFrame({"period": ["test"], "eligible_at_origin": [True], "target_sunday": [pd.Timestamp("2023-01-01")]})
    with pytest.raises(m.ModellingError, match="outside the test years"):
        fe.eval_rows(ex)


@needs_outputs
def test_real_test_results_are_consistent():
    r = pd.read_csv(m.MODEL_DATA_DIR / fe.RESULTS_NAME)
    assert set(r["period"]) == {"test_2021", "test_2022", "test_combined"}
    learned = r[r["approach"] != "persistence"]
    assert set(zip(learned["crop"], learned["horizon_weeks"])) == set(fe.SELECTED)
    assert (r.loc[r["approach"] == "persistence", "mae_improvement"] == 0).all()
    lg = pd.read_csv(m.MODEL_DATA_DIR / "test_refit_log.csv")
    assert pd.to_datetime(lg["train_last_target_sunday"]).max() < pd.Timestamp("2023-01-01")
