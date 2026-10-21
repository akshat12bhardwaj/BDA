"""
Phase 5 cleaning tests: synthetic edge cases + checks on the real cleaned outputs.
Real-output tests are skipped until Code/cleaning/pipeline.py:run_cleaning() has run.
"""

import numpy as np
import pandas as pd
import pytest

from Code.cleaning import pipeline as c
from Code.integration import pipeline as p4
from Code.weather.config import DAILY_VARIABLES

needs_outputs = pytest.mark.skipif(not (c.AUDIT_DIR / "output_manifest.csv").exists(),
                                   reason="run Code/cleaning/pipeline.py:run_cleaning() first")
CROPS = ["Onion", "Potato", "Wheat"]


def frame(rows):
    """rows: (source_row, market, date, arrivals, min, max, modal)."""
    df = pd.DataFrame(rows, columns=["source_row", "market", "reported_date", "arrivals_tonnes",
                                     "min_price_rs_per_quintal", "max_price_rs_per_quintal",
                                     "modal_price_rs_per_quintal"])
    df["reported_date"] = pd.to_datetime(df["reported_date"])
    return df.assign(crop="Onion", state="S", district="D", variety="V", commodity_group="G")


# ---------------------------------------------------------------- synthetic
def test_value_status_distinguishes_zero_missing_negative_nonfinite():
    v = pd.Series([1200.0, 0.0, np.nan, -5.0, np.inf])
    price, st = c.value_status(v, zero_is_missing=True)
    assert st.astype(str).tolist() == ["ok", "zero_set_missing", "missing_in_source",
                                       "negative_set_missing", "nonfinite_set_missing"]
    assert price.iloc[0] == 1200.0 and price.iloc[1:].isna().all()
    arr, st = c.value_status(pd.Series([0.0, 2.5]), zero_is_missing=False)
    assert arr.tolist() == [0.0, 2.5] and st.astype(str).tolist() == ["zero_retained", "ok"]


def test_duplicates_collapsed_only_when_identical_and_conflicts_kept():
    df = frame([
        (5, "M", "2010-01-01", 2.0, 100, 200, 150),   # identical pair -> keep source_row 3
        (3, "M", "2010-01-01", 2.0, 100, 200, 150),
        (7, "N", "2010-01-01", 1.0, 100, 200, 150),   # conflict: arrivals equal, prices differ
        (8, "N", "2010-01-01", 1.0, 120, 220, 170),
        (9, "O", "2010-01-01", 1.0, 100, 200, 150),   # A, A, B -> A collapsed, B kept, both conflict
        (10, "O", "2010-01-01", 1.0, 100, 200, 150),
        (11, "O", "2010-01-01", 1.0, 300, 400, 350),
        (12, "P", "2010-01-01", 1.0, 100, 200, 150),
    ])
    out, removed = c.clean_crop(df)
    assert len(out) + len(removed) == len(df)
    assert sorted(removed["source_row"]) == [5, 10]
    s = out.set_index("source_row")
    assert s.loc[3, "dup_status"] == "exact_copies_collapsed" and s.loc[3, "n_identical_copies"] == 2
    assert s.loc[[7, 8, 9, 11], "dup_status"].eq("conflict_unresolved").all()
    assert not s.loc[[7, 8, 9, 11], ["usable_modal_price", "usable_arrivals"]].any().any()
    assert s.loc[12, "dup_status"] == "unique" and s.loc[12, "usable_modal_price"]
    with pytest.raises(c.CleaningError, match="already"):
        c.clean_crop(out)                                   # never re-clean cleaned data


def test_zero_prices_become_missing_and_consistency_is_rechecked():
    df = frame([
        (1, "M", "2010-01-01", 1.0, 1200, 0, 0),       # min>max only because of zero placeholders
        (2, "M", "2010-01-02", 1.0, 100, 200, 500),    # modal outside range
        (3, "M", "2010-01-03", 0.0, 100, 200, 150),    # genuine zero arrivals
    ])
    out, _ = c.clean_crop(df)
    s = out.set_index("source_row")
    assert pd.isna(s.loc[1, "max_price_rs_per_quintal"]) and pd.isna(s.loc[1, "modal_price_rs_per_quintal"])
    assert s.loc[1, "max_price_status"] == "zero_set_missing" and not s.loc[1, "min_gt_max"]
    assert s.loc[1, "min_price_rs_per_quintal"] == 1200 and not s.loc[1, "usable_modal_price"]
    assert s.loc[2, "modal_outside_range"] and not s.loc[2, "usable_modal_price"]
    assert s.loc[2, "modal_price_rs_per_quintal"] == 500             # value kept, only flagged
    assert s.loc[3, "arrivals_tonnes"] == 0.0 and s.loc[3, "arrivals_status"] == "zero_retained"
    assert s.loc[3, "usable_arrivals"]


def test_price_reference_uses_no_future_data_and_flags_scale_errors():
    days = pd.date_range("2010-01-01", periods=40)
    rows = [(i, "M", d, 1.0, 900, 1100, 1000) for i, d in enumerate(days)]
    rows[20] = (20, "M", days[20], 1.0, 90000, 110000, 100000)         # 100x entry
    out, _ = c.clean_crop(frame(rows))
    s = out.set_index("source_row")
    assert s.loc[20, "price_extreme_level"] == "scale_error_suspected" and not s.loc[20, "usable_modal_price"]
    assert s.loc[20, "modal_price_rs_per_quintal"] == 100000
    assert (s.drop(index=20)["price_extreme_level"] == "none").all()
    # changing a later value must not change earlier references
    rows2 = rows.copy()
    rows2[39] = (39, "M", days[39], 1.0, 9, 11, 10)
    out2, _ = c.clean_crop(frame(rows2))
    pd.testing.assert_series_equal(out["price_ratio_to_ref"].iloc[:39], out2["price_ratio_to_ref"].iloc[:39])


def test_arrivals_reference_is_strictly_past_market_peak():
    days = pd.date_range("2010-01-01", periods=30)
    rows = [(i, "M", d, 5.0, 900, 1100, 1000) for i, d in enumerate(days)]
    rows[25] = (25, "M", days[25], 5000.0, 900, 1100, 1000)            # 1000x past peak
    out, _ = c.clean_crop(frame(rows))
    s = out.set_index("source_row")
    assert s.loc[:9, "arrivals_extreme_level"].eq("insufficient_history").all()   # < 10 past obs
    assert s.loc[25, "arrivals_extreme_level"] == "entry_error_suspected"
    assert s.loc[25, "arrivals_tonnes"] == 5000.0 and not s.loc[25, "usable_arrivals"]
    assert s.loc[26, "arrivals_extreme_level"] == "none"      # the outlier itself raises later peaks
    assert s.loc[24, "arrivals_ratio_to_ref"] == 1.0


def test_arrivals_reference_matches_brute_force_with_categorical_markets():
    rng = np.random.default_rng(0)
    n = 400
    df = pd.DataFrame({
        "state": "S", "district": "D",
        "market": pd.Categorical(rng.choice(["Zeta", "Alpha", "Mid"], n), categories=["Zeta", "Mid", "Alpha"]),
        "reported_date": pd.to_datetime("2010-01-01") + pd.to_timedelta(rng.integers(0, 800, n), unit="D"),
        "arrivals_tonnes": rng.gamma(2.0, 50.0, n).round(1)}).sample(frac=1, random_state=1)
    got = c.trailing_market_arrivals(df)
    for i, row in df.sample(60, random_state=2).iterrows():
        past = df[(df["market"] == row["market"]) & (df["reported_date"] < row["reported_date"])
                  & (df["reported_date"] >= row["reported_date"] - pd.Timedelta("365D"))]["arrivals_tonnes"]
        expected = past.max() if len(past) >= c.ARR_REF_MIN_OBS else np.nan
        assert (np.isnan(expected) and np.isnan(got[i])) or got[i] == expected, (i, got[i], expected)


# ---------------------------------------------------------------- real outputs
@needs_outputs
def test_phase4_outputs_unchanged():
    man = pd.read_csv(p4.OUT_DIR / "audit" / "output_manifest.csv").set_index("file")
    for crop in CROPS:
        name = f"mandi_integrated_{crop.lower()}.parquet"
        assert p4.frame_fingerprint(pd.read_parquet(p4.OUT_DIR / name)) == man.loc[name, "content_sha256"]
    assert pd.read_csv(c.AUDIT_DIR / "phase4_input_fingerprints.csv")["unchanged"].all()


@needs_outputs
@pytest.mark.parametrize("crop", CROPS)
def test_cleaned_output_reconciles_with_phase4(crop):
    raw = pd.read_parquet(p4.OUT_DIR / f"mandi_integrated_{crop.lower()}.parquet")
    cl = pd.read_parquet(c.CLEAN_DIR / f"mandi_cleaned_{crop.lower()}.parquet")
    removed = pd.read_csv(c.AUDIT_DIR / "removed_identical_copies.csv")
    removed = removed[removed["crop"] == crop]

    assert set(cl["crop"].astype(str)) == {crop}
    assert list(cl.columns) == list(raw.columns) + list(c.ADDED_COLUMNS)          # keys and schema kept
    assert len(cl) + len(removed) == len(raw)
    assert set(cl["source_row"]) | set(removed["source_row"]) == set(raw["source_row"])
    assert not set(cl["source_row"]) & set(removed["source_row"])
    assert cl["reported_date"].notna().all()

    r = raw.set_index("source_row").loc[cl["source_row"]]
    cl_i = cl.set_index("source_row")
    keep_cols = p4.MANDI_KEY + DAILY_VARIABLES + ["apy_state", "apy_district", "apy_year", "apy_year_lag1",
                                                  "market_code", "weather_match", "apy_annual_available"]
    for col in keep_cols:                                   # keys, weather, APY untouched (nothing invented)
        pd.testing.assert_series_equal(cl_i[col], r[col], check_names=False, check_categorical=False)
    for col, st in [(c.PRICES[0], "min_price_status"), (c.PRICES[1], "max_price_status"),
                    (c.MODAL, "modal_price_status"), (c.ARR, "arrivals_status")]:
        ok = cl_i[st].isin(["ok", "zero_retained"])
        assert (cl_i.loc[ok, col] == r.loc[ok, col]).all()        # untouched values are bit-identical
        assert cl_i.loc[~ok, col].isna().all()                    # changed values are missing, never 0
        assert (r.loc[cl_i[st] == "zero_set_missing", col] == 0).all()
    assert (cl[c.ARR] == 0).sum() == (raw[c.ARR] == 0).sum() - (removed[c.ARR] == 0).sum()

    conflicts = raw[raw["dup_type"] == "conflicting"]
    kept = cl[cl["dup_status"] == "conflict_unresolved"]
    assert len(kept) == len(conflicts) - removed["source_row"].isin(conflicts["source_row"]).sum()
    assert not kept["usable_modal_price"].any()
    dup_keys = cl[p4.MANDI_KEY].duplicated(keep=False)
    assert (cl.loc[dup_keys, "dup_status"] == "conflict_unresolved").all()


@needs_outputs
@pytest.mark.parametrize("crop", CROPS)
def test_real_arrivals_reference_matches_brute_force(crop):
    cl = pd.read_parquet(c.CLEAN_DIR / f"mandi_cleaned_{crop.lower()}.parquet",
                         columns=c.MARKET + ["reported_date", c.ARR, "arrivals_ratio_to_ref"])
    sample = cl[cl["arrivals_ratio_to_ref"].notna()].sample(40, random_state=0)
    sample = pd.concat([sample, cl.loc[cl["arrivals_ratio_to_ref"].nlargest(10).index]])
    for i, row in sample.iterrows():
        m = cl[(cl["state"] == row["state"]) & (cl["district"] == row["district"]) & (cl["market"] == row["market"])]
        past = m[(m["reported_date"] < row["reported_date"])
                 & (m["reported_date"] >= row["reported_date"] - pd.Timedelta("365D"))][c.ARR]
        assert np.isclose(row[c.ARR] / past.max(), row["arrivals_ratio_to_ref"]), (crop, i)


@needs_outputs
def test_audit_counts_reconcile():
    s = pd.read_csv(c.AUDIT_DIR / "cleaning_summary.csv")
    man = pd.read_csv(c.AUDIT_DIR / "output_manifest.csv")
    removed = pd.read_csv(c.AUDIT_DIR / "removed_identical_copies.csv")
    for crop in CROPS:
        sc = s[s["crop"] == crop]
        rows_after = man.loc[man["file"] == f"mandi_cleaned_{crop.lower()}.parquet", "rows"].item()
        assert (sc["rows_after"] == rows_after).all()
        assert sc["rows_before"].iloc[0] - sc["rows_removed"].sum() == rows_after
        assert sc.loc[sc["rule_id"] == "R01", "rows_removed"].item() == (removed["crop"] == crop).sum()
    for f in ["cleaning_decisions.csv", "added_columns.csv", "missingness_before_after.csv", "review_records.csv",
              "quality_metrics_before_after.csv"]:
        assert len(pd.read_csv(c.AUDIT_DIR / f)) > 0, f


@needs_outputs
def test_rerun_is_reproducible(tmp_path):
    c.run_cleaning(clean_dir=tmp_path / "cleaned", audit_dir=tmp_path / "audit", crops=["Wheat"])
    a = pd.read_csv(tmp_path / "audit" / "output_manifest.csv").set_index("file")
    b = pd.read_csv(c.AUDIT_DIR / "output_manifest.csv").set_index("file")
    name = "mandi_cleaned_wheat.parquet"
    assert a.loc[name, "content_sha256"] == b.loc[name, "content_sha256"]
