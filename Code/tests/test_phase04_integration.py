"""
Phase 4 integration tests.

Unit tests use small synthetic frames for edge cases; the "real output" tests
re-open the files written by Code/integration/pipeline.py:run_pipeline() and
are skipped if the pipeline has not been run yet.
Run from the project root:  python -m pytest Code/tests -q
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from Code.integration import pipeline as p
from Code.utils.data_audit import mandi_file_record_count
from Code.weather.config import DAILY_VARIABLES

OUT = p.OUT_DIR
AUDIT = OUT / "audit"
needs_outputs = pytest.mark.skipif(not (AUDIT / "output_manifest.csv").exists(),
                                   reason="run Code/integration/pipeline.py:run_pipeline() first")


# ---------------------------------------------------------------- synthetic unit tests
def test_agri_year_boundaries_and_missing_dates():
    d = pd.Series(pd.to_datetime(["2022-06-30", "2022-07-01", "2023-01-15", None]))
    start = p.agri_year_start(d)
    assert p.agri_year_label(start).astype(object).tolist()[:3] == ["2021-2022", "2022-2023", "2022-2023"]
    assert pd.isna(p.agri_year_label(start).iloc[3])
    assert p.agri_year_label(start - 1).astype(object).tolist()[1] == "2021-2022"


def _season(rows):
    cols = ["crop", "state", "district", "apy_year", "season", "state_code", "district_code",
            "area_ha", "production_tonnes", "yield_t_per_ha"]
    return pd.DataFrame(rows, columns=cols)


def test_apy_annual_uses_total_never_double_counts_and_keeps_ambiguity():
    s = _season([
        ("Onion", "S", "A", "2010-2011", "Kharif", 1, 1, 10, 100, 10.0),
        ("Onion", "S", "A", "2010-2011", "Rabi", 1, 1, 20, 300, 15.0),
        ("Onion", "S", "A", "2010-2011", "Total", 1, 1, 30, 400, 13.3),
        ("Onion", "S", "B", "2010-2011", "Whole Year", 1, 2, 5, 50, 10.0),
        ("Onion", "S", "C", "2010-2011", "Rabi", 1, 3, 5, 50, 10.0),
        ("Onion", "S", "C", "2010-2011", "Whole Year", 1, 3, 7, 70, 10.0),
        ("Onion", "S", "D", "2010-2011", "Total", 1, 4, 9, np.nan, 0.0),
    ])
    a = p.apy_annual(s).set_index("district")
    assert len(a) == 4 and a.loc["A", "production_tonnes"] == 400 and a.loc["A", "annual_method"] == "total_row"
    assert a.loc["B", "annual_method"] == "single_season" and a.loc["B", "production_tonnes"] == 50
    assert a.loc["C", "annual_method"] == "ambiguous_multi_season_no_total"
    assert pd.isna(a.loc["C", "production_tonnes"])     # not summed, not zero
    assert pd.isna(a.loc["D", "production_tonnes"])     # missing stays missing
    assert (a["apy_year"] == "2010-2011").all()         # original year label preserved


def test_checked_merge_logs_counts_and_rejects_many_to_many():
    log = []
    left = pd.DataFrame({"k": [1, 1, 2, 3], "v": range(4)})
    right = pd.DataFrame({"k": [1, 2], "w": ["a", "b"]})
    out = p.checked_merge(left, right, on=["k"], how="left", validate="m:1", step="t", merge_log=log)
    assert len(out) == 4 and log[0]["left_rows"] == 4 and log[0]["result_rows"] == 4
    assert out["w"].isna().sum() == 1
    with pytest.raises(p.IntegrationError, match="cardinality"):
        p.checked_merge(left, pd.DataFrame({"k": [1, 1], "w": [0, 1]}), on=["k"], how="left",
                        validate="m:1", step="t", merge_log=log)


def test_duplicate_keys_flagged_not_dropped():
    base = dict(state="S", district="D", market="M", variety="V", commodity_group="G",
                reported_date=pd.Timestamp("2010-01-01"), arrivals_tonnes=1.0,
                min_price_rs_per_quintal=1.0, max_price_rs_per_quintal=2.0, modal_price_rs_per_quintal=1.5)
    df = pd.DataFrame([base, base, {**base, "market": "N"}, {**base, "market": "N", "modal_price_rs_per_quintal": 9},
                       {**base, "market": "O"}])
    out = p.flag_duplicate_keys(df)
    assert len(out) == 5
    assert out["dup_type"].tolist() == ["exact_duplicate", "exact_duplicate", "conflicting", "conflicting", "unique"]
    assert out["dup_key_count"].tolist() == [2, 2, 2, 2, 1]


def test_district_crosswalk_rules():
    apy = pd.DataFrame({"state": ["Punjab", "Punjab", "Punjab", "Uttarakhand", "Uttar Pradesh", "Uttar Pradesh"],
                        "district": ["Bathinda", "Rupnagar", "Ludhiana", "Dehradun", "Kanpur Nagar", "Kanpur Dehat"]})
    aliases = pd.DataFrame({"mandi_state": ["Punjab", "Uttar Pradesh"], "mandi_district": ["Bhatinda", "Kanpur"],
                            "apy_district": ["Bathinda", np.nan], "basis": ["spelling", "EXCLUDED - ambiguous"]})
    mandi = pd.DataFrame({"state": ["Punjab", "Punjab", "Punjab", "Uttrakhand", "Uttar Pradesh", "NCT of Delhi", "Punjab"],
                          "district": ["Bhatinda", "Ropar (Rupnagar)", "LUDHIANA", "Dehradun", "Kanpur", "Delhi", "Moga"]})
    cw = p.build_district_crosswalk(mandi, apy, aliases).set_index("district")
    assert cw.loc["Bhatinda", "apy_district_match"] == "reviewed_alias"
    assert cw.loc["Ropar (Rupnagar)", "apy_district"] == "Rupnagar"
    assert cw.loc["LUDHIANA", "apy_district_match"] == "exact_normalized"
    assert cw.loc["Dehradun", "apy_state"] == "Uttarakhand"            # state alias Uttrakhand
    assert cw.loc["Kanpur", "apy_district_match"] == "excluded_by_review" and pd.isna(cw.loc["Kanpur", "apy_district"])
    assert cw.loc["Delhi", "apy_district_match"] == "state_not_in_apy"
    assert cw.loc["Moga", "apy_district_match"] == "unmatched"          # no fuzzy auto-accept
    bad = aliases.assign(apy_district=["Bathinda Typo", np.nan])
    with pytest.raises(p.IntegrationError, match="not found in APY"):
        p.build_district_crosswalk(mandi, apy, bad)


def test_weather_location_rule_rejects_wrong_district_and_never_guesses():
    phase3 = pd.DataFrame({
        "state": ["Punjab", "Punjab", "Gujarat"], "district": ["Ferozpur", "Bhatinda", "Nowhere"],
        "crops": ["Onion"] * 3, "mandi_records": [1, 2, 3], "mapping_status": ["mapped", "unresolved", "unresolved"],
        "latitude": [32.30391, np.nan, np.nan], "longitude": [75.06932, np.nan, np.nan]})
    ev = pd.DataFrame({
        "state": ["Punjab", "Punjab", "Punjab", "Gujarat"], "district": ["Ferozpur", "Ferozpur", "Bhatinda", "Nowhere"],
        "query": ["Ferozpur", "Firozpur", "Bathinda", "Nowhere"], "id": [1, 2, 3, 4],
        "name": ["Ferozpura", "Firozpur", "Bathinda", "Nowhere"], "latitude": [32.30391, 30.92574, 30.20747, 22.0],
        "longitude": [75.06932, 74.61311, 74.93893, 72.0], "feature_code": ["PPL"] * 4,
        "admin1": ["Punjab", "Punjab", "Punjab", "Rajasthan"],
        "admin2": ["Narowal District", "Firozpur", "Bathinda", "Nowhere"], "population": [np.nan, 110313, 285788, 5]})
    cw = pd.DataFrame({"state": ["Punjab"], "district": ["Bhatinda"], "apy_district": ["Bathinda"]})
    r = p.resolve_weather_locations(phase3, ev, cw).set_index("district")
    assert r.loc["Ferozpur", "resolution_status"] == "phase3_rejected_corrected"
    assert r.loc["Ferozpur", "latitude"] == 30.92574 and r.loc["Ferozpur", "phase3_point_admin2"] == "Narowal District"
    assert r.loc["Bhatinda", "resolution_status"] == "phase4_resolved_alias"
    assert r.loc["Nowhere", "resolution_status"] == "unresolved" and pd.isna(r.loc["Nowhere", "latitude"])


def test_unmatched_weather_stays_missing_not_zero(tmp_path):
    mandi = pd.DataFrame({
        "State Name": ["Punjab", "Punjab", "Goa"], "District Name": ["Ludhiana", "Ludhiana", "North Goa"],
        "Market Name": ["Ludhiana", "Ludhiana", "Mapusa"], "Variety": ["Other"] * 3, "Group": ["Vegetables"] * 3,
        "Arrivals (Tonnes)": [1.0, 2.0, 3.0], "Min Price (Rs./Quintal)": [1.0] * 3,
        "Max Price (Rs./Quintal)": [2.0] * 3, "Modal Price (Rs./Quintal)": [1.5] * 3,
        "Reported Date": ["05 Jan 2010", "05 Jan 2024", "05 Jan 2010"]})
    mandi.to_csv(tmp_path / "Onion.csv", index=False)
    cw = pd.DataFrame({"crop": ["Onion"] * 2, "state": ["Punjab", "Goa"], "district": ["Ludhiana", "North Goa"],
                       "apy_state": ["Punjab", None], "apy_district": ["Ludhiana", None],
                       "apy_district_match": ["exact_normalized", "state_not_in_apy"]})
    apy_ann = pd.DataFrame({"crop": ["Onion"], "state": ["Punjab"], "district": ["Ludhiana"],
                            "apy_year": ["2009-2010"], "production_tonnes": [10.0]})
    res = pd.DataFrame({"state": ["Punjab"], "district": ["Ludhiana"], "resolution_status": ["phase3_verified"],
                        "weather_status": ["ok"]})
    panel = pd.DataFrame({"weather_state": ["Punjab"], "weather_district": ["Ludhiana"],
                          "reported_date": [pd.Timestamp("2010-01-05")], **{v: [0.0] for v in DAILY_VARIABLES}})
    log = []
    out = p.integrate_mandi_crop("Onion", cw, apy_ann, res, panel, log, mandi_dir=tmp_path)
    assert len(out) == 3 and len(log) == 5
    assert out["weather_match"].astype(str).tolist() == [
        "exact_district", "exact_district_outside_weather_window", "no_weather_location"]
    assert (out.loc[0, DAILY_VARIABLES] == 0.0).all()        # a genuine 0 survives ...
    assert out.loc[1:, DAILY_VARIABLES].isna().all().all()    # ... and missing is NaN, never 0
    assert out["apy_annual_available"].tolist() == [True, False, False]
    assert out["apy_year"].astype(str).tolist() == ["2009-2010", "2023-2024", "2009-2010"]


# ---------------------------------------------------------------- real-output tests
@pytest.fixture(scope="module")
def manifest():
    return pd.read_csv(AUDIT / "output_manifest.csv")


@needs_outputs
def test_outputs_reopen_with_recorded_rows(manifest):
    for r in manifest.itertuples():
        path = OUT / r.file
        f = pd.read_parquet(path) if r.file.endswith(".parquet") else pd.read_csv(path)
        assert len(f) == r.rows and f.shape[1] == r.columns, r.file


@needs_outputs
@pytest.mark.parametrize("crop", ["Onion", "Potato", "Wheat"])
def test_mandi_integrated_is_row_preserving_and_valid(crop):
    df = pd.read_parquet(OUT / f"mandi_integrated_{crop.lower()}.parquet")
    assert set(df["crop"].astype(str)) == {crop}
    assert len(df) == mandi_file_record_count(f"{crop}.csv")             # nothing dropped or duplicated
    assert (df["source_row"].to_numpy() == np.arange(len(df))).all()
    assert df["reported_date"].notna().all()
    assert df["reported_date"].between("2000-01-01", "2024-12-31").all()
    exact = df["weather_match"] == "exact_district"
    assert df.loc[exact, DAILY_VARIABLES].notna().all().all()
    assert df.loc[~exact, DAILY_VARIABLES].isna().all().all()
    assert df.loc[exact, "reported_date"].between(p.WEATHER_START, p.WEATHER_END).all()
    assert (df.loc[exact, "weather_state"].astype(str) == df.loc[exact, "state"].astype(str)).all()
    assert (df.loc[exact, "weather_district"].astype(str) == df.loc[exact, "district"].astype(str)).all()
    assert set(df["weather_match"].astype(str)) <= {"exact_district", "exact_district_outside_weather_window",
                                                     "no_weather_location"}       # no proxy matches
    assert set(df["dup_type"].astype(str)) <= {"unique", "exact_duplicate", "conflicting"}
    yr = df["apy_year"].dropna().astype(str)
    assert yr.str.fullmatch(r"\d{4}-\d{4}").all()


@needs_outputs
def test_apy_outputs_keep_year_and_grain():
    s = pd.read_csv(OUT / "apy_season.csv")
    a = pd.read_csv(OUT / "apy_annual.csv")
    for f, key in [(s, p.APY_SEASON_KEY), (a, p.APY_ANNUAL_KEY)]:
        assert not f.duplicated(key).any()
        assert set(f["crop"]) == {"Onion", "Potato", "Wheat"}
        assert f["apy_year"].str.fullmatch(r"\d{4}-\d{4}").all()
    raw = pd.read_csv(p.APY_PATH, usecols=["crop_name"])
    assert len(s) == raw["crop_name"].isin(["Onion", "Potato", "Wheat"]).sum()
    m = pd.read_csv(OUT / "mandi_apy_district_year.csv")
    assert not m.duplicated(["crop", "apy_state", "apy_district", "apy_year"]).any()
    assert set(m["link_status"]) <= {"mandi_and_apy", "mandi_only", "apy_only"}


@needs_outputs
def test_weather_coordinates_all_come_from_geocoder_evidence():
    r = pd.read_csv(OUT / "weather_location_resolution.csv")
    ev = pd.read_csv(p.GEOCODER_EVIDENCE_PATH)
    mapped = r[r["latitude"].notna()]
    keys = set(zip(ev["latitude"].round(5), ev["longitude"].round(5)))
    assert all((la, lo) in keys for la, lo in zip(mapped["latitude"].round(5), mapped["longitude"].round(5)))
    assert r.loc[r["resolution_status"] == "unresolved", ["latitude", "longitude"]].isna().all().all()
    panel = pd.read_parquet(OUT / "weather_daily_panel.parquet")
    assert not panel.duplicated(["weather_state", "weather_district", "reported_date"]).any()
    assert panel[DAILY_VARIABLES].notna().all().all()


@needs_outputs
def test_merge_log_has_no_row_multiplication():
    m = pd.read_csv(AUDIT / "merge_log.csv")
    left = m[m["how"] == "left"]
    assert (left["left_rows"] == left["result_rows"]).all()
    assert set(m["validate"]) <= {"m:1", "1:1"}


@needs_outputs
def test_raw_sources_unchanged():
    fp = pd.read_csv(AUDIT / "source_fingerprints.csv")
    assert fp["unchanged"].all()
    for r in fp.itertuples():
        assert p.file_sha256(Path(r.path)) == r.sha256_after, r.path


@needs_outputs
def test_rerun_reproduces_identical_output(tmp_path, manifest):
    p.run_pipeline(out_dir=tmp_path, crops=["Wheat"])
    again = pd.read_csv(tmp_path / "audit" / "output_manifest.csv").set_index("file")
    main = manifest.set_index("file")
    name = "mandi_integrated_wheat.parquet"
    assert again.loc[name, "content_sha256"] == main.loc[name, "content_sha256"]
