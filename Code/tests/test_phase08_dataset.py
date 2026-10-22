"""
Phase 8 dataset-builder tests: hand-calculated synthetic series (weeks, targets, origin-safe
eligibility, splits, registry roles, review sensitivity, weather configs, input hashes) plus
negative leakage tests. Real-output checks are skipped until run_build() has written its manifests.
No model is fitted anywhere in these tests.
"""

import numpy as np
import pandas as pd
import pytest

from Code.features import pipeline as f6
from Code.integration.pipeline import file_sha256
from Code.modelling import dataset as m

REGISTRY = pd.read_csv(m.REGISTRY_PATH)
REG = m.registry_columns(REGISTRY)
PRED = REG.loc[REG["role"] == "predictor", "column"].tolist()
needs_outputs = pytest.mark.skipif(not (m.MODEL_DATA_DIR / "dataset_manifest.csv").exists(),
                                   reason="run Code/modelling/dataset.py:run_build() first")


def frame(rows, market="M"):
    """rows: (date, modal[, usable_price, review]). Every predictor = the row's date ordinal, so the
    anchor row of each example can be read back from any predictor value."""
    recs = []
    for i, r in enumerate(rows):
        d = pd.Timestamp(r[0])
        usable = r[2] if len(r) > 2 else True
        rec = {c: float(d.toordinal()) for c in PRED}
        rec.update({"source_row": i, "crop": "Onion", "state": "S", "district": "D", "market": market,
                    "variety": "V", "commodity_group": "G", "reported_date": d, "market_code": 1,
                    f6.MODAL: r[1], f6.MIN: r[1] - 10, f6.MAX: r[1] + 10, f6.ARR: 1.0,
                    "usable_modal_price": usable, "usable_arrivals": True, "dup_status": "unique",
                    "price_extreme_level": "review" if len(r) > 3 and r[3] else "none",
                    "arrivals_extreme_level": "none", "weather_match": "exact", "weather_state": "S",
                    "weather_district": "D", "apy_state": "S", "apy_district": "D", "apy_year": "2009-2010",
                    "apy_year_lag2": "2007-2008", "imd_season": "winter"})
        recs.append(rec)
    return pd.DataFrame(recs)[REG["column"].tolist()]


def daily(start, n, price=100.0, market="M"):
    return frame([(pd.Timestamp(start) + pd.Timedelta(days=i), price + i) for i in range(n)], market)


def build(df, horizons=m.HORIZONS):
    m.validate_schema(df, REG, "Onion")
    by_h, origins = m.build_examples(df, REG, horizons)
    for ex in by_h.values():
        m.validate_examples(ex, df["reported_date"].max(), m.feature_columns(REG, "weather"))
    return by_h, origins


# ---------------------------------------------------------------- weeks and targets
def test_weekly_boundaries_and_target_alignment():
    # week W = Mon 2010-03-01 .. Sun 03-07; the Sunday price belongs to W, the next Monday to W+1
    df = frame([("2010-03-03", 100), ("2010-03-07", 120), ("2010-03-08", 200), ("2010-03-12", 300),
                ("2010-03-29", 500), ("2010-03-31", 700)])
    by_h, _ = build(df)
    e1 = by_h[1].set_index("week_start").loc[pd.Timestamp("2010-03-01")]
    assert e1["origin_date"] == pd.Timestamp("2010-03-07") and e1["origin_week_median"] == 110
    assert e1["origin_week_last"] == 120 and e1["anchor_date"] == pd.Timestamp("2010-03-07")
    assert e1["target_median"] == 250 and e1["target_first_date"] == pd.Timestamp("2010-03-08")
    assert e1[PRED[0]] == pd.Timestamp("2010-03-07").toordinal()       # predictors come from the anchor row
    assert pd.Timestamp("2010-03-01") not in set(by_h[2]["week_start"])  # week 03-15 has no price: no example
    e4 = by_h[4].set_index("week_start").loc[pd.Timestamp("2010-03-01")]
    assert e4["target_median"] == 600 and e4["target_week_start"] == pd.Timestamp("2010-03-29")
    assert e4["tw_month"] == 4                                           # Thursday 2010-04-01 names the month


def test_targets_strictly_after_origin_and_predictors_at_or_before_it():
    by_h, _ = build(daily("2010-01-01", 120))
    for ex in by_h.values():
        assert (ex["target_first_date"] > ex["origin_date"]).all()
        assert (ex["anchor_date"] <= ex["origin_date"]).all()
        assert (ex[PRED[0]] == ex["anchor_date"].map(pd.Timestamp.toordinal)).all()


def test_unusable_rows_never_form_targets_or_origins():
    df = frame([("2010-03-03", 100), ("2010-03-10", 9999, False), ("2010-03-11", 200)])
    e = build(df)[0][1].iloc[0]
    assert e["target_median"] == 200 and e["target_n"] == 1


# ---------------------------------------------------------------- origin-safe eligibility (D-41)
def test_origin_safe_eligibility_counts_distinct_dates_up_to_origin():
    df = daily("2010-01-04", 400)                        # Monday start, one usable price per day
    df = pd.concat([df, df.iloc[[10]].assign(source_row=999)], ignore_index=True)  # same date twice counts once
    _, origins = build(df)
    o = origins.set_index("week_start")
    assert (o["n_usable_dates_to_origin"] == np.minimum(7 * (np.arange(len(o)) + 1), 400)).all()
    first = o.index[o["eligible_at_origin"]].min()
    assert o.loc[first, "n_usable_dates_to_origin"] >= 365 > o.loc[first - pd.Timedelta(weeks=1), "n_usable_dates_to_origin"]
    assert o["eligible_full_history"].all()               # the retrospective flag is true even in week 1


def test_future_rows_change_neither_predictors_nor_eligibility():
    base = daily("2015-01-05", 900)
    cut = pd.Timestamp("2016-06-05")                       # a Sunday
    fut = base["reported_date"] > cut
    tampered = base.copy()
    tampered.loc[fut, f6.MODAL] *= 10
    tampered.loc[fut, PRED] = -1.0
    tampered.loc[fut & (tampered.index % 3 == 0), "usable_modal_price"] = False
    extra = daily("2017-01-02", 400, market="M").assign(source_row=lambda x: x["source_row"] + 10_000)
    tampered = pd.concat([tampered, extra], ignore_index=True)
    cols = ["n_usable_dates_to_origin", "eligible_at_origin", "anchor_date"] + m.ORIGIN_WEEK_PREDICTORS + PRED
    _, o_base = build(base)
    _, o_tamp = build(tampered)
    a = o_base[o_base["origin_date"] <= cut].set_index("week_start")[cols]
    b = o_tamp[o_tamp["origin_date"] <= cut].set_index("week_start")[cols]
    pd.testing.assert_frame_equal(a, b)
    assert a["eligible_at_origin"].any() and not a["eligible_at_origin"].all()   # threshold crossed before cut
    # the retrospective full-history flag does depend on the future, which is why it is never used to select
    early = base[base["reported_date"] <= pd.Timestamp("2015-10-04")]           # 273 dates
    assert o_base["eligible_full_history"].all() and not build(early)[1]["eligible_full_history"].any()


# ---------------------------------------------------------------- periods, refits and gaps
def test_periods_follow_target_sunday():
    s = pd.Series(pd.to_datetime(["2001-12-30", "2002-01-06", "2018-12-30", "2019-01-06", "2019-12-29",
                                  "2020-01-05", "2020-12-27", "2021-01-03", "2022-12-25", "2023-01-01",
                                  "2024-01-28", "2024-02-04"]))
    got = m.assign_period(s, pd.Timestamp("2024-02-02")).tolist()
    assert got == ["outside", "train", "train", "val_2019", "val_2019", "val_2020", "val_2020", "test", "test",
                   "holdout_no_weather", "holdout_no_weather", "outside"]


def test_horizon_gap_training_targets_end_before_each_evaluated_origin():
    by_h, _ = build(daily("2018-06-04", 300))
    sched = m.refit_schedule()
    for h, ex in by_h.items():
        ev = ex[ex["period"] == "val_2019"]
        assert len(ev) and (ev["origin_date"] < pd.Timestamp("2019-01-06")).any()   # origin may precede its period
        refit = m.refit_date_for(ev["origin_date"], sched)
        assert (refit <= ev["origin_date"]).all()
        for r, grp in ev.groupby(refit):
            tr = m.training_examples(ex, r)
            assert len(tr) and tr["target_sunday"].max() <= r <= grp["origin_date"].min() < grp["target_first_date"].min()
            assert not tr["period"].isin(["val_2020", "test", "holdout_no_weather"]).any()


def test_refit_schedule_is_first_sunday_of_each_quarter():
    s = m.refit_schedule("2019-01-01", "2019-12-31")
    assert list(s.strftime("%Y-%m-%d")) == ["2019-01-06", "2019-04-07", "2019-07-07", "2019-10-06"]
    assert (s.dayofweek == 6).all()


# ---------------------------------------------------------------- registry roles and schema
def test_feature_columns_follow_registry_roles():
    for cfg in m.CONFIGS:
        cols = m.feature_columns(REG, cfg)
        roles = REG.set_index("column")["role"]
        assert all(roles[c] == "predictor" for c in cols if c in roles.index)
        assert not set(cols) & (set(m.RESERVED) | set(m.META) | {m.TARGET})


def test_registry_marking_a_target_as_predictor_is_rejected():
    bad = REGISTRY.copy()
    bad.loc[bad["feature"] == f6.MODAL, "role"] = "predictor"
    with pytest.raises(m.ModellingError, match="reserved"):
        m.registry_columns(bad)
    bad = REGISTRY.copy()
    bad.loc[0, "role"] = "maybe"
    with pytest.raises(m.ModellingError, match="unknown registry roles"):
        m.registry_columns(bad)


@pytest.mark.parametrize("tamper, msg", [
    (lambda d: d.assign(extra_col=1), "unexpected"),
    (lambda d: d.drop(columns=["modal_lag_7d"]), "missing"),
    (lambda d: d.assign(usable_modal_price=d["usable_modal_price"].astype(int)), "not boolean"),
    (lambda d: d.assign(reported_date=d["reported_date"].astype(str)), "datetime"),
    (lambda d: d.assign(crop=["Onion"] * (len(d) - 1) + ["Potato"]), "unexpected crop"),
    (lambda d: d.assign(**{f6.MODAL: 0.0}), "> 0"),
])
def test_invalid_schemas_are_rejected(tamper, msg):
    with pytest.raises(m.ModellingError, match=msg):
        m.validate_schema(tamper(daily("2010-01-04", 20)), REG, "Onion")


# ---------------------------------------------------------------- negative leakage tests
@pytest.mark.parametrize("tamper", [
    lambda e: e.assign(target_first_date=e["origin_date"]),                       # target on the origin day
    lambda e: e.assign(anchor_date=e["origin_date"] + pd.Timedelta(days=1)),      # predictor row after origin
    lambda e: e.assign(target_week_start=e["target_week_start"] - pd.Timedelta(days=7)),
    lambda e: e.assign(period="train"),                                           # wrong split label
    lambda e: e.assign(eligible_at_origin=True),                                  # eligibility not from the origin count
    lambda e: e.assign(n_usable_dates_to_origin=e["n_usable_dates_to_origin"][::-1].to_numpy()),
    lambda e: e.assign(origin_date=e["origin_date"] - pd.Timedelta(days=1)),       # origin not a Sunday
    lambda e: pd.concat([e, e.iloc[[0]]]),                                        # duplicated example
])
def test_validate_rejects_injected_leakage(tamper):
    ex = build(daily("2018-12-03", 500))[0][1]
    last = ex["target_last_date"].max()
    m.validate_examples(ex, last, m.feature_columns(REG, "weather"))
    with pytest.raises(m.ModellingError, match="checks failed"):
        m.validate_examples(tamper(ex), last, m.feature_columns(REG, "weather"))


@pytest.mark.parametrize("col", [m.TARGET, f6.MODAL, "target_has_review", "reported_date", "eligible_full_history"])
def test_validate_rejects_target_or_bookkeeping_columns_as_predictors(col):
    ex = build(daily("2010-01-04", 60))[0][1]
    with pytest.raises(m.ModellingError, match="no target, identifier or audit column"):
        m.validate_examples(ex, ex["target_last_date"].max(), m.feature_columns(REG, "weather") + [col])


# ---------------------------------------------------------------- review sensitivity and weather configs
def test_review_rows_kept_in_primary_and_dropped_in_sensitivity():
    rows = [(pd.Timestamp("2018-01-01") + pd.Timedelta(days=i), 100.0 + i, True, i == 400) for i in range(460)]
    ex = build(frame(rows))[0][1]
    hit = ex["target_first_date"].le(pd.Timestamp("2018-01-01") + pd.Timedelta(days=400)) & \
          ex["target_last_date"].ge(pd.Timestamp("2018-01-01") + pd.Timedelta(days=400))
    assert ex.loc[hit, "target_has_review"].all() and hit.sum() == 1
    prim = m.select(ex, REG, "no_weather", "primary", "all")
    sens = m.select(ex, REG, "no_weather", "review_sensitivity", "all")
    assert len(prim) - len(sens) == 1 and not sens["target_has_review"].any()


def test_weather_and_no_weather_configs():
    df = daily("2022-06-06", 300)
    sunday = pd.Timestamp("2022-06-12")
    df.loc[df["reported_date"] == sunday, "wx_rain_sum_30d"] = np.nan   # one missing weather value on an anchor row
    ex = build(df)[0][1]
    w = m.select(ex, REG, "weather", population="all")
    nw = m.select(ex, REG, "no_weather", population="all")
    assert any(c.startswith("wx_") for c in w.columns) and not any(c.startswith("wx_") for c in nw.columns)
    assert "holdout_no_weather" not in set(w["period"]) and "holdout_no_weather" in set(nw["period"])
    assert ex.loc[ex["anchor_date"] == sunday, "weather_covered"].tolist() == [False]
    assert ex.loc[ex["anchor_date"] != sunday, "weather_covered"].all()
    with pytest.raises(m.ModellingError):
        m.feature_columns(REG, "satellite")


# ---------------------------------------------------------------- input hashes, determinism, end to end
def _write(tmp_path, df):
    p = tmp_path / "features" / "features_onion.parquet"
    p.parent.mkdir()
    df.to_parquet(p, index=False)
    return p


def test_input_hash_mismatch_fails_before_anything_is_written(tmp_path):
    p = _write(tmp_path, daily("2018-01-01", 500))
    with pytest.raises(m.ModellingError, match="recorded hashes"):
        m.run_build(p.parent, tmp_path / "out", ["Onion"], {str(p): "0" * 64})
    assert not (tmp_path / "out").exists()
    with pytest.raises(m.ModellingError, match="no recorded hash"):
        m.run_build(p.parent, tmp_path / "out", ["Onion"], {})


def test_protected_output_directory_is_refused(tmp_path):
    p = _write(tmp_path, daily("2018-01-01", 30))
    with pytest.raises(m.ModellingError, match="protected"):
        m.run_build(p.parent, m.FEATURE_DIR / "phase08", ["Onion"], {str(p): file_sha256(p)})


def test_run_build_end_to_end_is_deterministic_and_leaves_inputs_unchanged(tmp_path):
    df = pd.concat([daily("2018-01-01", 1500), daily("2020-06-01", 200, market="N")], ignore_index=True)
    df["source_row"] = range(len(df))
    p = _write(tmp_path, df)
    exp = {str(p): file_sha256(p)}
    a = m.run_build(p.parent, tmp_path / "a", ["Onion"], exp)
    b = m.run_build(p.parent, tmp_path / "b", ["Onion"], exp)
    assert file_sha256(p) == exp[str(p)]
    assert a["input_fingerprints"]["unchanged"].all()
    for name in ["dataset_manifest", "sample_counts", "eligibility_summary", "split_definition", "feature_columns"]:
        assert (tmp_path / "a" / f"{name}.csv").read_bytes() == (tmp_path / "b" / f"{name}.csv").read_bytes()
    sc = a["sample_counts"]
    assert (sc["examples_origin_eligible"] + sc["examples_not_origin_eligible"] == sc["examples_target_observed"]).all()
    assert (sc["examples_target_observed"] <= sc["origin_series_weeks"]).all()
    el = a["eligibility_summary"].set_index("measure")["value"]
    assert el.filter(like="retrospective").iloc[0] == 1          # market N has only 200 dates
    assert (a["provenance"].set_index("key").loc["models_fitted", "value"]) == "none"


# ---------------------------------------------------------------- real outputs (manifests only; cheap)
@needs_outputs
def test_real_inputs_unchanged_and_match_phase7_hashes():
    fp = pd.read_csv(m.MODEL_DATA_DIR / "input_fingerprints.csv")
    assert fp["unchanged"].all()
    feats = fp[fp["sha256_recorded_phase7"].notna()]
    assert len(feats) == 3 and (feats["sha256_before"] == feats["sha256_recorded_phase7"]).all()
    for p, s in zip(feats["path"], feats["sha256_after"]):
        assert file_sha256(p) == s


@needs_outputs
def test_real_retrospective_counts_match_phase7_and_origin_counts_are_smaller():
    el = pd.read_csv(m.MODEL_DATA_DIR / "eligibility_summary.csv")
    retro = el[el["measure"].str.contains("retrospective")].set_index("crop")["value"].to_dict()
    assert retro == {"Onion": 1473, "Potato": 1551, "Wheat": 1540}
    q = pd.read_csv("Processed_Data/eda/quality_readiness.csv")
    q = q[q["metric"] == "series with >= 365 usable price rows"].set_index("crop")["value"].astype(int).to_dict()
    assert retro == q
    anyo = el[el["measure"] == "series origin-eligible at any origin"].set_index("crop")["value"].to_dict()
    assert all(anyo[c] <= retro[c] for c in retro)


@needs_outputs
def test_real_manifest_covers_every_crop_and_horizon():
    man = pd.read_csv(m.MODEL_DATA_DIR / "dataset_manifest.csv")
    assert sorted(zip(man["crop"], man["horizon_weeks"])) == sorted((c, h) for c in ["Onion", "Potato", "Wheat"]
                                                                    for h in m.HORIZONS)
    assert (man["rows"] > 0).all() and man["content_sha256"].str.len().eq(64).all()
