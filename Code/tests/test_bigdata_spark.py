"""
Big Data component tests (Code/bigdata). Synthetic mandi files in temporary directories; the expected district-year
table comes from Phase 4's own pandas functions run on the same fixture. Skipped when pyspark or JAVA_HOME is missing
(the project interpreter has no pyspark; run them with the isolated venv). The real-data parity check runs only with
BDA_SPARK_REAL=1.
"""

import os
import re

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyspark")

from Code.bigdata import mandi_spark as ms
from Code.bigdata import mapreduce_demo as mr
from Code.bigdata import parity
from Code.integration import pipeline as ip
from Code.production.pipeline import CROSSWALK_COLUMNS

if not os.environ.get("JAVA_HOME"):
    pytest.skip("JAVA_HOME is not set for this process", allow_module_level=True)

P = (100.0, 200.0, 150.0)
ONION = [  # state, district, market, variety, group, arrivals, (min, max, modal), date
    ("Maharashtra", "Pune", "Market One", "Red Nashik", "Vegetables", 10.0, P, "30 Jun 2019"),
    ("Maharashtra", "Pune", "Market One", "Red Nashik", "Vegetables", 20.0, P, "01 Jul 2019"),
    ("Maharashtra", "Pune", "Market Two", "Local", "Vegetables", 5.0, P, "01 Jul 2019"),
    ("Maharashtra", "Pune", "Market One", "Red Nashik", "Vegetables", 20.0, P, "01 Jul 2019"),   # exact duplicate
    ("Maharashtra", "Pune", "Market Two", "Local", "Vegetables", 6.0, P, "01 Jul 2019"),         # conflicting duplicate
    ("Maharashtra", "Pune", "Market One", "Red Nashik", "Vegetables", None, (0.0, 0.0, 0.0), "15 Aug 2019"),
    ("Maharashtra", "Nashik", "Lasalgaon", "Red", "Vegetables", None, P, "10 Sep 2019"),         # all arrivals missing
    ("Maharashtra", "Unknown District", "M4", "Red", "Vegetables", 3.0, P, "10 Sep 2019"),       # no crosswalk match
    ("Maharashtra", "Pune", "Market One", "Red Nashik", "Vegetables", 9.0, P, "01 Jul 2020"),    # after the window
    ("Maharashtra", "Pune", "Market One", "Red Nashik", "Vegetables", 9.0, P, "bad date"),       # unparseable
    ("Maharashtra", "Pune", "Market Two", "Local", "Vegetables", 4.0, (300.0, 200.0, 250.0), "20 Sep 2019"),  # min > max
    ("Andhra Pradesh", "West Godavari", "Tadepalli Gudem", "Bellary Red", "Vegetables", 7.5, P, "05 Jan 2015"),
]
WHEAT = [
    ("Punjab", "Ludhiana", "Khanna", "Dara", "Cereals", 100.0, (1800.0, 1900.0, 1850.0), "15 Apr 2018"),
    ("Punjab", "Ludhiana", "Khanna", "Dara", "Cereals", 50.0, (1800.0, 1900.0, 1860.0), "16 Apr 2018"),
    ("Punjab", "Ludhiana", "Khanna", "Dara", "Cereals", 70.0, (1900.0, 2000.0, 1950.0), "15 Apr 2021"),  # after window
]


def write_crop(path, rows):
    recs = [{"State Name": s, "District Name": d, "Market Name": m, "Variety": v, "Group": g, "Arrivals (Tonnes)": a,
             "Min Price (Rs./Quintal)": lo, "Max Price (Rs./Quintal)": hi, "Modal Price (Rs./Quintal)": mo,
             "Reported Date": dt} for s, d, m, v, g, a, (lo, hi, mo), dt in rows]
    pd.DataFrame(recs, columns=ms.RAW_COLUMNS).to_csv(path, index=False)


def crosswalk():
    rows = [("Maharashtra", "Pune", "Maharashtra", "Pune", "exact_normalized", "", "Onion", 9),
            ("Maharashtra", "Nashik", "Maharashtra", "Nashik", "exact_normalized", "", "Onion", 1),
            ("Maharashtra", "Unknown District", None, None, "unmatched", "", "Onion", 1),
            ("Andhra Pradesh", "West Godavari", "Andhra Pradesh", "West Godavari", "exact_normalized", "", "Onion", 1),
            ("Punjab", "Ludhiana", "Punjab", "Ludhiana", "reviewed_alias", "spelling", "Wheat", 3)]
    return pd.DataFrame(rows, columns=CROSSWALK_COLUMNS)


@pytest.fixture(scope="module")
def fixture(tmp_path_factory):
    d = tmp_path_factory.mktemp("mandi")
    write_crop(d / "Onion.csv", ONION)
    write_crop(d / "Wheat.csv", WHEAT)
    cw = crosswalk()
    cw.to_csv(d / "district_crosswalk.csv", index=False)
    paths = {"mandi_onion": d / "Onion.csv", "mandi_wheat": d / "Wheat.csv", "crosswalk": d / "district_crosswalk.csv"}
    records = {"mandi_onion": {"file_sha256": ip.file_sha256(paths["mandi_onion"])},
               "mandi_wheat": {"file_sha256": ip.file_sha256(paths["mandi_wheat"])},
               "crosswalk": {"content_sha256": ip.frame_fingerprint(cw), "rows": len(cw), "columns": cw.shape[1]}}
    return {"dir": d, "paths": paths, "records": records, "crosswalk": cw, "crops": ["Onion", "Wheat"]}


@pytest.fixture(scope="module")
def spark():
    s = ms.session("local[2]")
    yield s
    s.stop()


@pytest.fixture(scope="module")
def result(fixture, spark, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    res = ms.run(out, fixture["dir"], fixture["crops"], paths=fixture["paths"], records=fixture["records"],
                 git_tracked=(), reference=None, spark=spark)
    return res, out


def phase4_reference(fixture) -> pd.DataFrame:
    """Phase 4's pandas path on the fixture: load, duplicate flags, July-June year, crosswalk, mandi_district_year."""
    parts = []
    for crop in fixture["crops"]:
        df = ip.flag_duplicate_keys(ip.load_mandi_crop(crop, fixture["dir"]))
        df["apy_year"] = ip.agri_year_label(ip.agri_year_start(df["reported_date"]))
        for c in ["state", "district", "market"]:
            df[c] = df[c].astype(str)
        cw = fixture["crosswalk"]
        df = df.merge(cw[cw["crop"] == crop][["state", "district", "apy_state", "apy_district"]], on=["state", "district"],
                      how="left", validate="m:1")
        df["apy_year"] = df["apy_year"].astype(str).replace("nan", np.nan)
        parts.append(ip.mandi_district_year(df, df["reported_date"].min(), df["reported_date"].max()))
    ref = pd.concat(parts, ignore_index=True)
    return ref[ref["apy_year"] <= parity.LAST_YEAR][parity.KEY + parity.EXACT + parity.CLOSE].reset_index(drop=True)


def qc(res) -> dict:
    q = res["files"]["quality_checks.csv"]
    return {(r.crop, r.check): r.value for r in q.itertuples()}


def test_schema_and_header_check(fixture, spark, tmp_path):
    df = ms.read_mandi(spark, fixture["dir"], ["Onion"])
    types = dict(df.dtypes)
    assert types["arrivals_tonnes"] == "double" and types["modal_price_rs_per_quintal"] == "double"
    assert types["state"] == "string" and types["reported_date"] == "date"
    bad = tmp_path / "Onion.csv"
    pd.read_csv(fixture["paths"]["mandi_onion"]).rename(columns={"State Name": "State"}).to_csv(bad, index=False)
    with pytest.raises(ms.BigDataError, match="header"):
        ms.read_mandi(spark, tmp_path, ["Onion"])


def test_agricultural_year_boundary_and_window(result):
    res, _ = result
    q1 = res["files"]["district_year_spark.csv"]
    pune = q1[(q1["crop"] == "Onion") & (q1["apy_district"] == "Pune")].set_index("apy_year")
    assert set(pune.index) == {"2018-2019", "2019-2020"}                     # 30 Jun vs 1 Jul 2019; 2020-21 excluded
    assert pune.loc["2018-2019", "mandi_records"] == 1
    assert q1["mandi_last_date"].max() <= ms.PARITY_END
    assert not (q1["crop"].eq("Wheat") & q1["apy_year"].eq("2020-2021")).any()


def test_quality_counts(result):
    c = qc(result[0])
    assert c[("Onion", "rows_read_all_years")] == "12" and c[("Wheat", "rows_read_all_years")] == "3"
    assert c[("Onion", "unparseable_or_missing_date_all_years")] == "1"
    assert c[("Onion", "rows_in_window")] == "10" and c[("Wheat", "rows_in_window")] == "2"
    assert c[("Onion", "duplicate_key_rows")] == "4"
    assert c[("Onion", "missing_arrivals")] == "2" and c[("Onion", "missing_or_zero_modal_price")] == "1"
    assert c[("Onion", "min_price_above_max_price")] == "1"
    assert c[("Onion", "rows_without_apy_district")] == "1" and c[("Wheat", "rows_without_apy_district")] == "0"
    assert c[("Onion", "malformed_rows_all_years")] == "0"


def test_spark_sql_equals_phase4_pandas_on_fixture(result, fixture):
    rep = parity.compare(result[0]["files"]["district_year_spark.csv"], phase4_reference(fixture))
    assert rep["mismatches"].sum() == 0, rep.to_string()
    assert rep.loc[rep["column"] == "key_set", "rows_compared"].item() == 5


def test_all_missing_arrivals_sum_to_zero_like_pandas(result):
    q1 = result[0]["files"]["district_year_spark.csv"]
    nashik = q1[q1["apy_district"] == "Nashik"].iloc[0]
    assert nashik["mandi_arrivals_tonnes_sum"] == 0 and nashik["mandi_records"] == 1


def test_parity_detects_differences(result, fixture):
    ref = phase4_reference(fixture)
    ref.loc[0, "mandi_records"] += 1
    ref.loc[1, "mandi_arrivals_tonnes_sum"] += 0.5
    rep = parity.compare(result[0]["files"]["district_year_spark.csv"], ref.iloc[:-1]).set_index("column")
    assert rep.loc["mandi_records", "mismatches"] == 1 and rep.loc["mandi_arrivals_tonnes_sum", "mismatches"] == 1
    assert rep.loc["key_set", "mismatches"] == 1 and rep.loc["key_set", "example_keys"]


def test_mapreduce_pattern_matches_sql_and_word_count(result, fixture, spark):
    res, _ = result
    counts = res["files"]["mapreduce_counts.csv"]
    assert counts["matches_spark_sql"].all() and (counts["label"] == mr.LABEL).all() and "not Hadoop" in mr.LABEL
    mh = counts[(counts["crop"] == "Onion") & (counts["state"] == "Maharashtra")].iloc[0]
    assert mh["records"] == 9 and mh["arrivals_tonnes_sum"] == pytest.approx(10 + 20 + 5 + 20 + 6 + 3 + 4)
    win = ms.windowed(ms.read_mandi(spark, fixture["dir"], fixture["crops"])).select("variety").toPandas()
    words = pd.Series([w for v in win["variety"] for w in re.findall(r"[a-z0-9]+", v.lower())]).value_counts()
    got = res["files"]["word_count.csv"].set_index("word")["count"]
    assert got.sort_index().to_dict() == words.sort_index().to_dict()


def test_outputs_deterministic_and_only_in_out_dir(fixture, spark, result, tmp_path):
    _, out1 = result
    ms.run(tmp_path, fixture["dir"], fixture["crops"], paths=fixture["paths"], records=fixture["records"],
           git_tracked=(), reference=None, spark=spark)
    names = sorted(p.name for p in out1.iterdir())
    assert names == sorted(p.name for p in tmp_path.iterdir())
    for n in names:
        if n != "run_log.csv":                                                   # observed runtime: not reproducible
            assert (out1 / n).read_bytes() == (tmp_path / n).read_bytes(), n
    assert set(fixture["dir"].iterdir()) == {fixture["dir"] / f for f in ["Onion.csv", "Wheat.csv", "district_crosswalk.csv"]}


def test_changed_input_is_refused(fixture, spark, tmp_path):
    recs = {k: dict(v) for k, v in fixture["records"].items()}
    recs["mandi_onion"]["file_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="mismatch"):
        ms.run(tmp_path, fixture["dir"], fixture["crops"], paths=fixture["paths"], records=recs, git_tracked=(),
               reference=None, spark=spark)
    assert not any(tmp_path.iterdir())


@pytest.mark.skipif(os.environ.get("BDA_SPARK_REAL") != "1", reason="real-data parity: set BDA_SPARK_REAL=1")
def test_real_data_parity_zero_mismatches(tmp_path, spark):
    res = ms.run(tmp_path, spark=spark)
    assert res["parity"]["mismatches"].sum() == 0 and res["parity"]["rows_compared"].iloc[0] == 16673
