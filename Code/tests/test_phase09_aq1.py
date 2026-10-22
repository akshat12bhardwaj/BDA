"""
Phase 9 AQ-1 v1 tests: derived flag table (reproducibility, provenance, no mutation, availability dates),
variant exclusion rules, leakage safety of cleaned targets and refit training, identical comparison rows,
separate outputs from the original baseline, and cutoff enforcement. Synthetic data only.
"""

import numpy as np
import pandas as pd
import pytest

from Code.integration.pipeline import file_sha256, frame_fingerprint
from Code.modelling import arrivals as ar
from Code.modelling import arrivals_aq1 as a1
from Code.modelling import dataset as m
from Code.tests.test_phase09_arrivals import daily_arr
from Code.tests.test_phase09_arrivals_quality import series


def spiked(start="2016-01-04", n=1820, crop="Onion", spikes=(("2019-03-27", 1e5),)):
    df = daily_arr(start, n).assign(crop=crop)
    for day, v in spikes:
        df.loc[df["reported_date"] == pd.Timestamp(day), "arrivals_tonnes"] = v
    return df


# ---------------------------------------------------------------- flag table
def test_flag_table_is_reproducible_and_never_mutates_its_input():
    df = spiked()
    before = df.copy()
    a, b = a1.flag_table(df), a1.flag_table(df)
    pd.testing.assert_frame_equal(df, before)
    assert frame_fingerprint(a) == frame_fingerprint(b)
    assert (a["aq1_version"] == a1.AQ1_VERSION).all()
    m_ = a.merge(df[["source_row", "arrivals_tonnes", "arrivals_extreme_level"]], on="source_row", suffixes=("", "_src"))
    assert (m_["arrivals_tonnes"] == m_["arrivals_tonnes_src"]).all()                      # raw values untouched
    assert (m_["arrivals_extreme_level"].astype(str) == m_["arrivals_extreme_level_src"].astype(str)).all()  # Phase 5 kept


def test_provider_query_marker_is_kept_without_implying_exclusion():
    df = series([100] * 8 + [0.01] + [100] * 6, start="2019-01-07").assign(state="Madhya Pradesh")
    f = a1.flag_table(df)
    hit = f[f["provider_query_pending"]]
    assert len(hit) == 1 and hit["arrivals_tonnes"].iloc[0] == 0.01
    other = a1.flag_table(df.assign(state="Punjab"))
    assert not other["provider_query_pending"].any()
    marked_only = f.assign(aq1_class="ok")
    assert not a1.excluded(marked_only, "aq1_likely").any()                 # the marker alone never excludes


def test_flags_cover_reported_usable_rows_only_and_respect_the_cutoff():
    late = series([10] * 20 + [1e6], start="2021-01-04").assign(source_row=lambda x: x["source_row"] + 100_000)
    df = pd.concat([series([10] * 60, start="2019-06-03"), late], ignore_index=True)
    df.loc[3, "usable_arrivals"] = False
    f = a1.flag_table(df)
    assert len(f) == int((df["usable_arrivals"] & (df["reported_date"] <= ar.CUTOFF)).sum())   # no rows invented for gaps
    assert f["reported_date"].max() <= ar.CUTOFF and f["aq1_available_from"].max() <= ar.CUTOFF


def test_availability_date_is_the_sunday_of_the_fourth_following_reported_week():
    f = a1.flag_table(series([10] * 8 + [10_000] + [10] * 6, start="2019-01-07")).set_index("reported_date")
    spike = f.iloc[8]
    assert spike["aq1_class"] == "likely_unit_error"
    assert spike["aq1_available_from"] == f.index[12] + pd.Timedelta(days=6)                   # 4th following week's Sunday
    assert f.iloc[-1]["aq1_available_from"] == ar.CUTOFF                                       # fewer than 4 weeks follow


def test_a_rows_class_does_not_depend_on_data_after_its_availability_date():
    vals = [10] * 8 + [10_000] + [10] * 20
    base = series(vals, start="2019-01-07")
    f0 = a1.flag_table(base).set_index("reported_date")
    day = f0.index[8]
    avail = f0.loc[day, "aq1_available_from"]
    changed = base.assign(arrivals_tonnes=base["arrivals_tonnes"].where(base["reported_date"] <= avail, 1e7))
    f1 = a1.flag_table(changed).set_index("reported_date")
    assert f0.loc[day, "aq1_class"] == "likely_unit_error" and f1.loc[day, "aq1_class"] == f0.loc[day, "aq1_class"]
    assert (f1.loc[f1.index > avail, "arrivals_tonnes"] == 1e7).all()                        # later data really changed


def test_start_of_series_flags_are_never_knowable_at_their_own_origin():
    f = a1.flag_table(series([100_000] + [10] * 10, start="2019-01-07"))
    first = f.iloc[0]
    assert first["aq1_class"] == "likely_unit_error_forward_only"
    assert first["aq1_available_from"] > first["reported_date"] + pd.Timedelta(days=6)


# ---------------------------------------------------------------- variants
def test_variant_exclusion_rules():
    f = pd.DataFrame({"crop": ["Wheat"] * 5,
                      "aq1_class": ["likely_unit_error", "likely_unit_error", "isolated_spike", "sustained_shift", "likely_unit_error_low"],
                      "high_side": [True, True, False, False, False], "march_to_may": [True, True, True, True, True],
                      "unit_factor_signature": [True, False, False, False, False]})
    assert a1.excluded(f, "original").sum() == 0
    assert a1.excluded(f, "aq1_likely").tolist() == [True, True, False, False, True]
    assert a1.excluded(f, "aq1_likely_and_spikes").tolist() == [True, True, True, False, True]
    assert a1.excluded(f, "aq1_wheat_marmay_review_except_unitsig").tolist() == [True, False, False, False, True]
    assert a1.excluded(f, "aq1_wheat_marmay_review_all").tolist() == [False, False, False, False, True]
    assert a1.excluded(f.assign(crop="Onion"), "aq1_wheat_marmay_review_all").tolist()[:2] == [True, True]  # Wheat-only rule
    with pytest.raises(m.ModellingError):
        a1.excluded(f, "everything")


def test_original_variant_reproduces_the_original_baseline_exactly():
    df = spiked()
    by_h, o = ar.build_arrivals_examples(df)
    flags = a1.flag_table(df)
    for h, ex in by_h.items():
        ref, _ = ar.validation_predictions(ex, o, "Onion", h)
        got = a1.variant_predictions(ex, o, a1.clean_weeks(flags, a1.excluded(flags, "original")), "Onion", h).set_index("row")
        assert np.allclose(got["y"], ref["y"]) and np.allclose(got["persistence"], ref["persistence"])
        assert np.allclose(got["calendar_adjusted_persistence"], ref["calendar_adjusted_persistence"])


def test_aq1_cleans_targets_but_never_origin_inputs_or_eligibility():
    df = spiked()
    by_h, o = ar.build_arrivals_examples(df)
    flags = a1.flag_table(df)
    ex = by_h[1]
    orig = a1.variant_predictions(ex, o, a1.clean_weeks(flags, a1.excluded(flags, "original")), "Onion", 1).set_index("row")
    cln = a1.variant_predictions(ex, o, a1.clean_weeks(flags, a1.excluded(flags, "aq1_likely")), "Onion", 1).set_index("row")
    common = cln.index.intersection(orig.index)
    assert np.allclose(cln.loc[common, "persistence"], orig.loc[common, "persistence"])       # origin input unchanged
    changed = common[cln.loc[common, "y"] != orig.loc[common, "y"]]
    assert len(changed) == 1                                                                 # the spike's target week only
    assert ex.loc[changed, "target_week_start"].iloc[0] == pd.Timestamp("2019-03-25")
    assert cln["calendar_adjusted_persistence"].notna().all()                                 # identical rows for both baselines


def test_refit_training_uses_a_flag_only_once_it_is_knowable():
    # spike in the week before the 2019-04-07 refit: its flag becomes knowable only weeks later
    df = spiked(spikes=(("2019-03-27", 1e5),))
    by_h, o = ar.build_arrivals_examples(df)
    flags = a1.flag_table(df)
    assert flags.loc[flags["aq1_class"] == "likely_unit_error", "aq1_available_from"].min() > pd.Timestamp("2019-04-07")
    ex = by_h[1]
    orig = a1.variant_predictions(ex, o, a1.clean_weeks(flags, a1.excluded(flags, "original")), "Onion", 1)
    cln = a1.variant_predictions(ex, o, a1.clean_weeks(flags, a1.excluded(flags, "aq1_likely")), "Onion", 1)
    refit = m.refit_date_for(ex.loc[orig["row"], "origin_date"], m.refit_schedule())
    at = orig["row"][refit.to_numpy() == pd.Timestamp("2019-04-07")]
    a = orig.set_index("row").loc[at, "calendar_adjusted_persistence"]
    b = cln.set_index("row").reindex(at)["calendar_adjusted_persistence"].dropna()
    assert len(b) and np.allclose(a.loc[b.index], b)


def test_fully_excluded_target_week_produces_no_example():
    df = series([10] * 10 + [1e5] + [10] * 10, start="2018-12-03", every=7)   # one report per week
    by_h, o = ar.build_arrivals_examples(df)
    flags = a1.flag_table(df)
    w = a1.clean_weeks(flags, a1.excluded(flags, "aq1_likely"))
    spike_week = flags.loc[flags["aq1_class"] == "likely_unit_error", "week_start"].iloc[0]
    assert w.set_index("week_start").loc[spike_week, "clean_median"] != w.set_index("week_start").loc[spike_week, "clean_median"]  # NaN


# ---------------------------------------------------------------- end to end
def test_run_writes_separate_reproducible_outputs_and_keeps_original_artifacts(tmp_path):
    df = pd.concat([spiked(n=1900), spiked(n=1900).assign(market="N", source_row=lambda x: x["source_row"] + 9000)], ignore_index=True)
    (tmp_path / "f").mkdir()
    path = tmp_path / "f" / "features_onion.parquet"
    df.to_parquet(path, index=False)
    exp = {str(path): file_sha256(path)}
    a = a1.run_aq1(tmp_path / "f", tmp_path / "a", ["Onion"], exp, b=100)
    a1.run_aq1(tmp_path / "f", tmp_path / "b", ["Onion"], exp, b=100)
    names = {p.name for p in (tmp_path / "a").iterdir()}
    assert {"arrivals_aq1_baseline_metrics.csv", "arrivals_aq1_bootstrap.csv", "aq1"} <= names
    assert not names & {"arrivals_baseline_metrics.csv", "arrivals_bootstrap.csv", "arrivals_dataset_manifest.csv"}
    for name in ["arrivals_aq1_baseline_metrics.csv", "arrivals_aq1_population_changes.csv", "arrivals_aq1_bootstrap.csv"]:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    man = a["flags_manifest"].iloc[0]
    assert man["file_sha256"] == file_sha256(tmp_path / "a" / "aq1" / man["file"])
    assert set(a["arrivals_aq1_baseline_metrics"]["period"]) == {"val_2019", "val_2020", "val_combined"}
    pop = a["arrivals_aq1_population_changes"]
    orig = pop[pop["variant"] == "original"]
    assert (orig["examples_dropped"] == 0).all() and (orig["examples_target_changed"] == 0).all()
    assert file_sha256(path) == exp[str(path)]
