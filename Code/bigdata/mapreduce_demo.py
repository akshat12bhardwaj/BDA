"""
Spark RDD map / reduceByKey: a MapReduce-style processing pattern in Spark local mode.
This is NOT Hadoop MapReduce and does not run on a cluster; it shows the map -> shuffle -> reduce idea of the course
topics C6-C7 on the windowed mandi rows, and cross-checks the result against Spark SQL.
"""

from __future__ import annotations

import re
from operator import add

import pandas as pd

LABEL = "Spark RDD map/reduceByKey - MapReduce-style processing pattern, Spark local mode; not Hadoop MapReduce, not a cluster"


def _add_pairs(a, b):
    return a[0] + b[0], a[1] + b[1]


def crop_state_counts(df) -> pd.DataFrame:
    """map(row -> ((crop, state), (1, arrivals or 0))) then reduceByKey: records and arrivals per crop x state."""
    rdd = df.select("crop", "state", "arrivals_tonnes").rdd
    pairs = rdd.map(lambda r: ((r.crop, r.state), (1, r.arrivals_tonnes or 0.0))).reduceByKey(_add_pairs)
    out = pd.DataFrame([(c, s, n, a) for (c, s), (n, a) in pairs.collect()],
                       columns=["crop", "state", "records", "arrivals_tonnes_sum"])
    return out.sort_values(["crop", "state"], na_position="first").reset_index(drop=True)


def variety_word_count(df) -> pd.DataFrame:
    """The word-count problem (C7) on Variety names: flatMap to lower-case tokens, map(w -> (w, 1)), reduceByKey(+)."""
    words = (df.select("variety").rdd.flatMap(lambda r: re.findall(r"[a-z0-9]+", (r.variety or "").lower()))
             .map(lambda w: (w, 1)).reduceByKey(add))
    out = pd.DataFrame(words.collect(), columns=["word", "count"])
    return out.sort_values(["count", "word"], ascending=[False, True]).reset_index(drop=True)


def sql_crop_state_counts(df) -> pd.DataFrame:
    from pyspark.sql import functions as F
    out = (df.groupBy("crop", "state").agg(F.count(F.lit(1)).alias("records"),
                                           F.coalesce(F.sum("arrivals_tonnes"), F.lit(0.0)).alias("arrivals_tonnes_sum"))
           .toPandas())
    return out.sort_values(["crop", "state"], na_position="first").reset_index(drop=True)


def run(spark, df) -> dict[str, pd.DataFrame]:
    """Both RDD jobs, and the check that map/reduceByKey equals the Spark SQL GROUP BY."""
    mr, sql = crop_state_counts(df), sql_crop_state_counts(df)
    same_keys = mr[["crop", "state"]].equals(sql[["crop", "state"]]) and mr["records"].equals(sql["records"])
    close = ((mr["arrivals_tonnes_sum"] - sql["arrivals_tonnes_sum"]).abs()
             <= 1e-9 * sql["arrivals_tonnes_sum"].abs().clip(lower=1)).all()
    if not (same_keys and close):
        raise RuntimeError("RDD map/reduceByKey result differs from the Spark SQL GROUP BY")
    return {"counts": mr.assign(matches_spark_sql=True, label=LABEL), "word_count": variety_word_count(df)}
