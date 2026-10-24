"""
Big Data component — PySpark / Spark SQL ETL over the raw mandi files (spec: Documentation/BigData_and_Dashboard_Spec.md).

  input    = Dataset/India Commodity Wise Mandi Dataset/{Onion,Potato,Wheat}.csv (about 8.0M rows), read with an
             explicit schema after an exact header check, plus the D-18 crosswalk. Every input is verified against its
             recorded fingerprint first (Code/production/pipeline.verify_inputs; crosswalk via its documented alias_basis
             canonicalisation). Nothing is repaired: bad values are counted, never fixed.
  window   = reported_date <= PARITY_END (2020-06-30, i.e. agricultural years <= 2019-20), applied right after
             parsing: before the 2021-2022 test period, the 2023+ holdout and the Phase 9 data cutoff (2020-12-27).
             Rows outside the window enter only the all-rows counts (row and unparseable-date totals).
  queries  = Spark SQL: Q1 district-year (the parity target), Q2 weekly state summary, Q3 top districts by arrivals.
  parity   = Q1 against Phase 4's pandas output mandi_apy_district_year.csv on the same window (parity.py).
  output   = Processed_Data/bigdata/: deterministic CSVs written by pandas (Spark itself never writes: on Windows
             that needs Hadoop native binaries), run_manifest.csv (no timestamps) and run_log.csv (observed runtime).
Runtimes are single-machine local-mode observations, not evidence of cluster performance.
Run from the project root, with JAVA_HOME set for this process to a JDK that Spark supports (17/21/25):
    python -B -m Code.bigdata.mandi_spark
"""

from __future__ import annotations

import csv
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Code.integration.pipeline import MANDI_COLUMNS, MANDI_VALUES, file_sha256
from Code.production.pipeline import _posix, verify_inputs, write_csv
from Code.utils.data_audit import MANDI_DIR

CROPS = ["Onion", "Potato", "Wheat"]
PARITY_END = "2020-06-30"
DATE_FORMAT = "dd MMM yyyy"                        # A-05: every Onion/Potato/Wheat date is 'DD Mon YYYY'
INTEGRATION = Path("Processed_Data/integration")
CROSSWALK = INTEGRATION / "district_crosswalk.csv"
REFERENCE = INTEGRATION / "mandi_apy_district_year.csv"
SOURCE_FP = INTEGRATION / "audit/source_fingerprints.csv"
INTEGRATION_MANIFEST = INTEGRATION / "audit/output_manifest.csv"
OUT_DIR = Path("Processed_Data/bigdata")
RAW_COLUMNS = list(MANDI_COLUMNS)                  # exact header of the three crop files
KEY = ["state", "district", "market", "variety", "commodity_group", "reported_date"]   # Phase 4 MANDI_KEY

Q1_DISTRICT_YEAR = """
SELECT m.crop, c.apy_state, c.apy_district, m.apy_year,
       COUNT(*)                                     AS mandi_records,
       COUNT(DISTINCT m.market)                     AS mandi_markets,
       COALESCE(SUM(m.arrivals_tonnes), 0D)         AS mandi_arrivals_tonnes_sum,
       percentile(m.modal_price_rs_per_quintal, 0.5) AS mandi_modal_price_median,
       MIN(m.reported_date)                         AS mandi_first_date,
       MAX(m.reported_date)                         AS mandi_last_date,
       SUM(CASE WHEN m.dup_key_count > 1 THEN 1 ELSE 0 END) AS mandi_duplicate_key_rows
FROM mandi m JOIN crosswalk c
  ON m.crop = c.crop AND m.state = c.state AND m.district = c.district
WHERE c.apy_district IS NOT NULL AND m.apy_year IS NOT NULL
GROUP BY m.crop, c.apy_state, c.apy_district, m.apy_year
"""

Q2_WEEKLY_STATE = """
SELECT crop, state, CAST(date_trunc('week', reported_date) AS DATE) AS week_start,
       COUNT(*) AS records, COUNT(DISTINCT market) AS markets,
       SUM(arrivals_tonnes) AS arrivals_tonnes_sum,
       percentile(modal_price_rs_per_quintal, 0.5) AS modal_price_median
FROM mandi
GROUP BY crop, state, CAST(date_trunc('week', reported_date) AS DATE)
"""

Q3_TOP_DISTRICTS = """
SELECT * FROM (
  SELECT crop, apy_year, apy_state, apy_district, mandi_arrivals_tonnes_sum, mandi_records,
         RANK() OVER (PARTITION BY crop, apy_year ORDER BY mandi_arrivals_tonnes_sum DESC) AS arrivals_rank
  FROM district_year)
WHERE arrivals_rank <= 10
"""


class BigDataError(RuntimeError):
    pass


def session(master: str = "local[8]"):
    """Local SparkSession. JAVA_HOME must point at a JDK Spark supports; it is never changed globally here."""
    from pyspark.sql import SparkSession
    if not os.environ.get("JAVA_HOME"):
        raise BigDataError("set JAVA_HOME (for this process only) to a JDK 17/21/25 before starting Spark")
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")       # Spark's Python workers ignore -B
    spark = (SparkSession.builder.master(master).appName("bda-mandi-etl")
             .config("spark.ui.enabled", "false").config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.shuffle.partitions", "8").config("spark.driver.memory", "4g").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def schema():
    from pyspark.sql import types as T
    fields = [T.StructField(c, T.DoubleType() if MANDI_COLUMNS[c] in MANDI_VALUES else T.StringType()) for c in RAW_COLUMNS]
    return T.StructType(fields + [T.StructField("_corrupt", T.StringType())])


def check_header(path: Path) -> None:
    """Spark's enforceSchema=false does not reject a renamed header, so the header is checked exactly here."""
    with open(path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    if header != RAW_COLUMNS:
        raise BigDataError(f"{path.name}: header {header} differs from the expected {RAW_COLUMNS}")


def read_mandi(spark, mandi_dir: Path = MANDI_DIR, crops: list[str] = CROPS):
    """All rows of the crop files: schema-typed, renamed to the Phase 4 names, date parsed, agricultural year added."""
    from pyspark.sql import functions as F
    parts = []
    for crop in crops:
        path = Path(mandi_dir) / f"{crop}.csv"
        check_header(path)
        df = spark.read.csv(str(path), schema=schema(), header=True, mode="PERMISSIVE",
                            columnNameOfCorruptRecord="_corrupt")
        parts.append(df.select(F.lit(crop).alias("crop"), *[F.col(f"`{c}`").alias(MANDI_COLUMNS[c]) for c in RAW_COLUMNS],
                               "_corrupt"))
    df = parts[0]
    for p in parts[1:]:
        df = df.unionByName(p)
    df = df.withColumnRenamed("reported_date", "reported_date_raw")
    d = F.try_to_date("reported_date_raw", DATE_FORMAT)
    start = F.year(d) - F.when(F.month(d) < 7, 1).otherwise(0)          # Phase 4 agri_year_start (July-June)
    return (df.withColumn("reported_date", d)
            .withColumn("apy_year", F.when(d.isNotNull(), F.concat(start.cast("string"), F.lit("-"),
                                                                   (start + 1).cast("string")))))


def windowed(df):
    """Rows dated on or before PARITY_END (unparseable dates excluded), with the Phase 4 duplicate-key count.
    The key includes the date, so every copy of an in-window key is itself in the window."""
    from pyspark.sql import Window, functions as F
    w = df.filter(F.col("reported_date") <= F.lit(PARITY_END).cast("date"))
    return w.withColumn("dup_key_count", F.count(F.lit(1)).over(Window.partitionBy("crop", *KEY)))


def read_crosswalk(spark, path: Path = CROSSWALK):
    return spark.read.csv(str(path), header=True, inferSchema=False).select("crop", "state", "district", "apy_state",
                                                                            "apy_district")


def quality_checks(all_rows, win) -> pd.DataFrame:
    """Counts only. All-rows counts cover the whole file; every other check covers the window."""
    from pyspark.sql import functions as F
    c = lambda cond: F.sum(F.when(cond, 1).otherwise(0))
    a = all_rows.groupBy("crop").agg(F.count("state").alias("_n_state"), F.count(F.lit(1)).alias("rows_read_all_years"),
                                     c(F.col("_corrupt").isNotNull()).alias("malformed_rows_all_years"),
                                     c(F.col("reported_date").isNull()).alias("unparseable_or_missing_date_all_years"))
    m, lo, hi = "modal_price_rs_per_quintal", "min_price_rs_per_quintal", "max_price_rs_per_quintal"
    b = win.groupBy("crop").agg(F.count(F.lit(1)).alias("rows_in_window"),
                                c(F.col("arrivals_tonnes").isNull()).alias("missing_arrivals"),
                                c(F.col("arrivals_tonnes") == 0).alias("zero_arrivals"),
                                c(F.col("arrivals_tonnes") < 0).alias("negative_arrivals"),
                                c(F.col(m).isNull() | (F.col(m) == 0)).alias("missing_or_zero_modal_price"),
                                c(F.col(lo) > F.col(hi)).alias("min_price_above_max_price"),
                                c(F.col("dup_key_count") > 1).alias("duplicate_key_rows"),
                                F.min("reported_date").alias("first_date"), F.max("reported_date").alias("last_date"))
    out = a.join(b, "crop", "left").drop("_n_state").toPandas()
    long = out.melt(id_vars="crop", var_name="check", value_name="value").astype({"value": str})
    return long.sort_values(["check", "crop"]).reset_index(drop=True)


def unmatched_rows(win, cw) -> pd.DataFrame:
    from pyspark.sql import functions as F
    j = win.join(cw, ["crop", "state", "district"], "left")
    return (j.groupBy("crop").agg(F.sum(F.when(F.col("apy_district").isNull(), 1).otherwise(0)).alias("rows_without_apy_district"))
            .toPandas().sort_values("crop").reset_index(drop=True))


def run_queries(spark, win, cw) -> dict[str, pd.DataFrame]:
    win.createOrReplaceTempView("mandi")
    cw.createOrReplaceTempView("crosswalk")
    q1 = spark.sql(Q1_DISTRICT_YEAR)
    q1.createOrReplaceTempView("district_year")
    keys = {"q1": ["crop", "apy_state", "apy_district", "apy_year"], "q2": ["crop", "state", "week_start"],
            "q3": ["crop", "apy_year", "arrivals_rank", "apy_state", "apy_district"]}
    out = {"q1": q1.toPandas(), "q2": spark.sql(Q2_WEEKLY_STATE).toPandas(), "q3": spark.sql(Q3_TOP_DISTRICTS).toPandas()}
    for k, df in out.items():
        for col in df.columns:
            if col.endswith("_date") or col == "week_start":
                df[col] = df[col].astype(str)
        out[k] = df.sort_values(keys[k]).reset_index(drop=True)
    return out


def default_inputs(mandi_dir: Path = MANDI_DIR, crops: list[str] = CROPS) -> tuple[dict, dict]:
    """Paths and the Phase 4 records: raw files by file hash, the crosswalk by its content hash."""
    src = pd.read_csv(SOURCE_FP)
    src["p"] = src["path"].map(_posix)
    paths, records = {}, {}
    for crop in crops:
        p = Path(mandi_dir) / f"{crop}.csv"
        rec = src.loc[src["p"] == _posix(p), "sha256_after"].unique()
        if len(rec) != 1:
            raise BigDataError(f"no unique recorded hash for {p}")
        paths[f"mandi_{crop.lower()}"], records[f"mandi_{crop.lower()}"] = p, {"file_sha256": rec[0]}
    man = pd.read_csv(INTEGRATION_MANIFEST).set_index("file")
    paths["crosswalk"] = CROSSWALK
    records["crosswalk"] = {"content_sha256": man.loc[CROSSWALK.name, "content_sha256"],
                            "rows": int(man.loc[CROSSWALK.name, "rows"]), "columns": int(man.loc[CROSSWALK.name, "columns"])}
    return paths, records


def run(out_dir: Path = OUT_DIR, mandi_dir: Path = MANDI_DIR, crops: list[str] = CROPS, master: str = "local[8]",
        paths: dict | None = None, records: dict | None = None, git_tracked: tuple = ("crosswalk",),
        reference: Path | None = REFERENCE, spark=None) -> dict:
    """The whole ETL. Inputs verified first; outputs written by pandas; parity checked when a reference is given.
    A caller-supplied SparkSession (tests) is reused and left running; otherwise one is started and stopped here."""
    from Code.bigdata import mapreduce_demo, parity
    if paths is None:
        paths, records = default_inputs(mandi_dir, crops)
    t0, times = time.time(), {}
    report = verify_inputs(paths, records, git_tracked)
    times["verify_inputs"] = time.time() - t0
    own = spark is None
    spark = spark or session(master)
    try:
        t = time.time()
        all_rows = read_mandi(spark, mandi_dir, crops)
        win = windowed(all_rows)
        cw = read_crosswalk(spark, paths["crosswalk"])
        qc = quality_checks(all_rows, win)
        unmatched = unmatched_rows(win, cw)
        times["read_and_quality_checks"] = time.time() - t
        t = time.time()
        q = run_queries(spark, win, cw)
        times["spark_sql_q1_q3"] = time.time() - t
        t = time.time()
        mr = mapreduce_demo.run(spark, win)
        times["rdd_mapreduce_pattern"] = time.time() - t
        versions = {"spark": spark.version, "java": spark.sparkContext._jvm.System.getProperty("java.version"),
                    "python": platform.python_version(), "pandas": pd.__version__, "master": master}
    finally:
        if own:
            spark.stop()
    qc = pd.concat([qc, unmatched.melt(id_vars="crop", var_name="check", value_name="value").astype({"value": str})])
    qc = qc.sort_values(["check", "crop"]).reset_index(drop=True)
    if q["q1"]["mandi_last_date"].max() > PARITY_END or q["q2"]["week_start"].max() > PARITY_END:
        raise BigDataError("a Spark result lies after the parity window")

    t = time.time()
    par = None
    if reference is not None:
        ref_report = parity.verify_reference(Path(reference))
        report = pd.concat([report, ref_report], ignore_index=True)
        par = parity.compare(q["q1"], parity.reference_rows(Path(reference)))
    times["parity"] = time.time() - t

    out_dir = Path(out_dir)
    fmt = "%.12g"                       # partial sums merge in task order; 12 significant digits keep files byte-stable
    files = {"district_year_spark.csv": q["q1"], "weekly_state_spark.csv": q["q2"], "top_districts_spark.csv": q["q3"],
             "quality_checks.csv": qc, "mapreduce_counts.csv": mr["counts"], "word_count.csv": mr["word_count"]}
    if par is not None:
        files["parity_report.csv"] = par
    hashes = {}
    for name, df in files.items():
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_dir / name, index=False, lineterminator="\n", float_format=fmt)
        hashes[name] = file_sha256(out_dir / name)
    man = ([{"item": "meta", "name": k, "value": v} for k, v in versions.items()]
           + [{"item": "meta", "name": "window", "value": f"reported_date <= {PARITY_END}"},
              {"item": "meta", "name": "note", "value": "local single-machine run; not evidence of cluster performance"},
              {"item": "meta", "name": "mapreduce_label", "value": mapreduce_demo.LABEL}]
           + [{"item": "input", "name": f"{r.input}:{r.check}", "value": f"{r.status}; recorded={r.recorded}"}
              for r in report.itertuples()]
           + [{"item": "rows", "name": k, "value": str(len(v))} for k, v in files.items()]
           + [{"item": "output", "name": k, "value": v} for k, v in hashes.items()])
    write_csv(pd.DataFrame(man), out_dir / "run_manifest.csv")
    for name in ("mandi_" + c.lower() for c in crops):
        if file_sha256(paths[name]) != records[name]["file_sha256"]:
            raise BigDataError(f"{name} changed during the run")
    times["total"] = time.time() - t0
    log = pd.DataFrame([{"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": k,
                         "seconds": round(v, 1), "master": master} for k, v in times.items()])
    log.to_csv(out_dir / "run_log.csv", mode="a", header=not (out_dir / "run_log.csv").exists(), index=False,
               lineterminator="\n")
    return {"files": files, "parity": par, "times": times, "versions": versions}


if __name__ == "__main__":
    res = run()
    print(res["versions"])
    print({k: round(v, 1) for k, v in res["times"].items()})
    if res["parity"] is not None:
        print(res["parity"].to_string())
