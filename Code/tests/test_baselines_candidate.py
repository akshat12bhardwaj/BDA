"""
exp-candidate-v1 baselines: test-window guard, refit-rule guard, protocol hash, and the Phase 8 baseline definitions.
Synthetic data only (temporary parquet files); no real candidate data is scored.
"""

import numpy as np
import pandas as pd
import pytest

from Code.candidates import baselines_candidate as bc

S = {"Commodity": "Onion", "canonical_id": "S|D|M", "Variety": "V"}


def test_guarded_read_never_loads_the_test_window(tmp_path):
    weeks = pd.date_range("2026-06-15", "2026-07-20", freq="7D")  # spans validation end (week of 2026-06-22) into test
    pd.DataFrame({**S, "week_start": weeks, "target_median": 1.0}).to_parquet(tmp_path / "w.parquet")
    df = bc.guarded_read(tmp_path / "w.parquet", "week_start")
    assert df.week_start.max() == pd.Timestamp("2026-06-22") and len(df) == 2
    assert bc.LAST_ALLOWED_TARGET_WEEK == pd.Timestamp("2026-06-22")


def test_refit_guard_refuses_origins_before_the_first_approved_refit_and_phase8_rule_covers_them():
    o = pd.Series(pd.to_datetime(["2025-12-28", "2026-01-04"]))
    with pytest.raises(bc.GuardError, match="precedes"):
        bc.refits_for(o, "approved_list")
    r = bc.refits_for(o, "phase8_quarterly")
    assert [str(x.date()) for x in r] == ["2025-10-05", "2026-01-04"]
    assert set(pd.to_datetime(bc.ed.REFITS)) <= set(bc.REFIT_RULES["phase8_quarterly"]())  # approved list is a subset


def test_protocol_hash_ignores_line_endings(tmp_path):
    (tmp_path / "a.json").write_bytes(b'{\n "x": 1\n}'); (tmp_path / "b.json").write_bytes(b'{\r\n "x": 1\r\n}')
    assert bc.protocol_hash(tmp_path / "a.json") == bc.protocol_hash(tmp_path / "b.json")


def test_seasonal_naive_uses_52_weeks_before_the_target_week_not_the_origin():
    weekly = pd.DataFrame({**S, "week_start": pd.to_datetime(["2025-01-06", "2025-01-13"]), "target_median": [10.0, 20.0]})
    rows = pd.DataFrame({**S, "origin_week_start": pd.to_datetime(["2025-12-29"]), "target_week_start": pd.to_datetime(["2026-01-05"])})
    # target week 2026-01-05 - 52 weeks = 2025-01-06 -> 10 (lag52 from the origin would be 2024-12-30, absent)
    assert bc.seasonal_naive(rows, weekly).tolist() == [10.0]


def test_climatology_uses_only_targets_by_the_refit_and_series_eligible_by_then():
    pool = pd.DataFrame({**S, "origin_week_start": pd.to_datetime(["2025-01-06", "2025-02-03", "2025-12-29"]),
                         "target_week_start": pd.to_datetime(["2025-01-13", "2025-02-10", "2026-01-05"]),
                         "y_target": [100.0, 300.0, 9999.0], "eligible_d41": [True, True, True]})
    rows = pd.DataFrame({**S, "origin_week_start": pd.to_datetime(["2026-01-05"]), "target_week_start": pd.to_datetime(["2026-01-12"])})
    pred, refit = bc.climatology(rows, pool, "phase8_quarterly")
    assert str(refit.iloc[0].date()) == "2026-01-04" and pred.tolist() == [100.0]  # January median; 9999 is after the refit


def test_climatology_refit_is_an_expanding_window_over_all_targets_ended_by_the_refit():
    # a Q1 validation target (Sunday 2026-01-11) is in the 2026-04-05 refit; a target after that refit is not
    pool = pd.DataFrame({**S, "origin_week_start": pd.to_datetime(["2025-12-29", "2026-03-30"]),
                         "target_week_start": pd.to_datetime(["2026-01-05", "2026-04-06"]),
                         "y_target": [500.0, 9999.0], "eligible_d41": [True, True]})
    rows = pd.DataFrame({**S, "origin_week_start": pd.to_datetime(["2026-12-28"]), "target_week_start": pd.to_datetime(["2027-01-04"])})
    pred, refit = bc.climatology(rows, pool, "phase8_quarterly")
    assert str(refit.iloc[0].date()) == "2026-10-04" and pred.tolist() == [500.0]  # 9999's month is April, not January
    early = pd.DataFrame({**S, "origin_week_start": pd.to_datetime(["2026-03-30"]), "target_week_start": pd.to_datetime(["2026-04-06"])})
    assert np.isnan(bc.climatology(early, pool, "phase8_quarterly")[0][0])  # refit 2026-01-04: no April target yet


def test_mape_instability_flag():
    y = np.full(100, 1000.0); y[0] = 10.0  # one Rs/kg-like target
    m = bc.metrics(y, np.full(100, 1000.0))
    assert m["mape_unstable"] and m["targets_below_100"] == 1 and bc.MAPE_UNSTABLE_SHARE == 0.20


def test_metrics_and_bootstrap_are_deterministic_and_paired():
    rng = np.random.RandomState(0)
    df = pd.DataFrame({"canonical_id": np.repeat([f"m{i}" for i in range(20)], 5), "y_target": 1000 + rng.rand(100) * 100})
    df["pred_persistence"] = df.y_target + 10; df["pred_x"] = df.y_target + 5
    a, b = bc.cluster_bootstrap(df, "pred_x", reps=500), bc.cluster_bootstrap(df, "pred_x", reps=500)
    assert a == b and a["mae_diff_ci95"] == pytest.approx([-5.0, -5.0])
    m = bc.metrics(np.array([100.0, 200.0]), np.array([110.0, 180.0]))
    assert (m["mae"], m["mape_pct"]) == (15.0, 10.0)
