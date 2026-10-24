"""
Weather experiment runner: refuses a changed protocol, its bootstrap reproduces the registered 95% interval exactly and adds
a wider Bonferroni interval from the same draws, and the acceptance rule is the registered one. Synthetic data only.
"""

import numpy as np
import pandas as pd
import pytest

from Code.candidates import baselines_candidate as bc, weather_experiment_run as wr


def test_protocol_digest_is_the_full_registered_value_and_a_changed_file_stops_the_run(tmp_path, monkeypatch):
    assert wr.PROTOCOL_SHA256.startswith("ac013ab7a3f7d6ba") and len(wr.PROTOCOL_SHA256) == 64
    monkeypatch.setattr(wr, "PROTOCOL", tmp_path / "p.json")
    (tmp_path / "p.json").write_bytes(b"{}")
    with pytest.raises(bc.GuardError, match="registered digest"):
        wr.verify(tmp_path)


def frame(seed=0):
    rng = np.random.RandomState(seed)
    df = pd.DataFrame({"canonical_id": np.repeat([f"m{i}" for i in range(25)], 8), "y_target": 1000 + rng.rand(200) * 100})
    df["pred_persistence"] = df.y_target + rng.normal(0, 20, 200)
    df["pred_x"] = df.y_target + rng.normal(0, 15, 200)
    return df


def test_bootstrap_95_matches_the_registered_procedure_and_bonferroni_is_wider():
    df = frame()
    mine = wr.bootstrap_both(df, "pred_x", reps=2000)
    ref = bc.cluster_bootstrap(df, "pred_x", reps=2000)
    assert mine["skill_ci95"] == pytest.approx(ref["skill_ci95"])
    lo, hi = mine["skill_ci_bonferroni"]
    assert lo <= mine["skill_ci95"][0] and hi >= mine["skill_ci95"][1] and mine["bonferroni_level_pct"] == 99.17


def test_acceptance_rule_is_the_registered_one():
    q = pd.DataFrame([{"Commodity": "Wheat", "quarter": qt, "model": m, "mae": mae, "skill_vs_persistence": 1 - mae / 100}
                      for qt in ("2026Q1", "2026Q2") for m, mae in (("price_weather", 95.0), ("persistence", 100.0))])
    b = pd.DataFrame([{"crop": "Wheat", "period": qt, "model": "price_weather", "skill_ci95": [0.01, 0.09], "skill_ci_bonferroni": [-0.01, 0.1]}
                      for qt in ("2026Q1", "2026Q2")])
    assert wr.acceptance(q, b).passes_preregistered_rule.item()  # Bonferroni interval is reported, not a gate
    b.at[0, "skill_ci95"] = [-0.001, 0.09]
    assert not wr.acceptance(q, b).passes_preregistered_rule.item()
