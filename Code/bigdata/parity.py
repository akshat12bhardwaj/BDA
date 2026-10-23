"""
Spark / Pandas parity: Spark SQL Q1 against Phase 4's pandas aggregation (mandi_apy_district_year.csv) on the window.

The Phase 4 manifest records a content hash taken from the in-memory frame; it cannot be reproduced from the CSV
(dates, booleans and nullable integers change type on readback, and no narrow canonicalisation reproduces it).
The reference is therefore verified by its shape against that record and by its git blob against HEAD.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from Code.production.pipeline import _posix, git_blob_matches_head

KEY = ["crop", "apy_state", "apy_district", "apy_year"]
EXACT = ["mandi_records", "mandi_markets", "mandi_first_date", "mandi_last_date", "mandi_duplicate_key_rows"]
CLOSE = ["mandi_arrivals_tonnes_sum", "mandi_modal_price_median"]
REL_TOL = 1e-9
LAST_YEAR = "2019-2020"
MANIFEST = Path("Processed_Data/integration/audit/output_manifest.csv")


def verify_reference(path: Path, manifest: Path = MANIFEST, git: bool = True) -> pd.DataFrame:
    man = pd.read_csv(manifest).set_index("file").loc[Path(path).name]
    df = pd.read_csv(path)
    rows = [{"input": "reference", "path": _posix(path), "check": "shape", "recorded": f"{man.rows}x{man.columns}",
             "recomputed": f"{df.shape[0]}x{df.shape[1]}", "canonicalised": "",
             "status": "match" if df.shape == (man.rows, man.columns) else "MISMATCH"}]
    if git:
        ok = git_blob_matches_head(path)
        rows.append({"input": "reference", "path": _posix(path), "check": "git_blob_vs_HEAD", "recorded": "HEAD",
                     "recomputed": "working file", "canonicalised": "", "status": "match" if ok else "MISMATCH"})
    rep = pd.DataFrame(rows)
    if (rep["status"] != "match").any():
        raise RuntimeError(f"parity reference failed verification:\n{rep.to_string()}")
    return rep


def reference_rows(path: Path, last_year: str = LAST_YEAR) -> pd.DataFrame:
    """Phase 4 rows with mandi data in the window (apy_only rows have no mandi values)."""
    ref = pd.read_csv(path)
    ref = ref[(ref["link_status"] != "apy_only") & (ref["apy_year"] <= last_year)]
    return ref[KEY + EXACT + CLOSE].reset_index(drop=True)


def _examples(rows: pd.DataFrame) -> str:
    return "; ".join("|".join(map(str, k)) for k in rows[KEY].head(10).itertuples(index=False))


def compare(spark_q1: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """One row per compared column: rows compared, mismatches, max abs difference, first mismatching keys."""
    m = spark_q1.merge(ref, on=KEY, how="outer", suffixes=("_spark", "_pandas"), indicator=True)
    rows = [{"column": "key_set", "rows_compared": len(m), "mismatches": int((m["_merge"] != "both").sum()),
             "max_abs_diff": "", "example_keys": _examples(m[m["_merge"] != "both"])}]
    both = m[m["_merge"] == "both"]
    for c in EXACT + CLOSE:
        s, p = both[f"{c}_spark"], both[f"{c}_pandas"]
        if c in CLOSE:
            s, p = s.astype(float), p.astype(float)
            diff = (s - p).abs()
            bad = ~((diff <= REL_TOL * p.abs().clip(lower=1)) | (s.isna() & p.isna()))
            mx = float(diff.max()) if len(diff) else 0.0
        else:
            if c.endswith("_date"):
                s, p = s.astype(str).str[:10], p.astype(str).str[:10]
            else:
                s, p = s.astype("int64"), p.astype("int64")
            bad, mx = s != p, ""
        rows.append({"column": c, "rows_compared": len(both), "mismatches": int(bad.sum()), "max_abs_diff": mx,
                     "example_keys": _examples(both[bad])})
    return pd.DataFrame(rows)
