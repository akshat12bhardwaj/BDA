"""
Phase 9 — freeze of the D-45 arrivals selection and the ONE-TIME reserved 2021-2022 arrivals test.

  selection   = D-45 (accepted 2026-10-23): conservative HGB (arrivals_models.CANDIDATES["hgb_conservative"])
                for Onion/Potato/Wheat x h = 1, 2, 4; persistence is the comparison
  freeze      = build_manifest(): SHA-256 of the code, protocol, inputs, AQ-1 files and validation outputs, plus the
                text of the D-44 and D-45 decision sections (line endings normalised to \\n) and hashes of the
                selected model settings and feature list. The manifest never contains its own hash; its file hash is
                written to the run log instead (no circularity).
  run once    = a persistent run log (run_log.csv) beside the outputs: ANY earlier attempt - completed or failed -
                blocks another run until a person reviews it; a failure is logged as 'failed', never 'completed'.
                Re-running a notebook cell or restarting a kernel cannot bypass it.
  test scope  = target weeks whose Sunday is 2021-01-03 .. 2022-12-25. Rows are read with a parquet filter
                reported_date <= 2022-12-25, so no 2023+ (holdout) row is ever loaded. Quarterly expanding refits as in
                validation (D-40/D-44): a model refitted at T trains only on targets ending <= T.
  populations = primary aq1_likely; sensitivities: original, and aq1_likely + all provider_query_pending rows (U3).
                AQ-1 flags are recomputed with the unchanged AQ-1 v1 rules on rows <= 2022-12-25 (test targets need
                flags); a flag cleans a training target only once knowable by the refit date.
Test metrics are written only to the test directory and are never read by any selection or tuning code.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from Code.features.pipeline import FEATURE_DIR, SERIES
from Code.integration.pipeline import file_sha256
from Code.modelling import arrivals as ar
from Code.modelling import arrivals_aq1 as a1
from Code.modelling import arrivals_models as am
from Code.modelling import dataset as d
from Code.modelling import uncertainty as u

VERSION = "phase9-arrivals-test-v1"
TEST_DIR = am.OUT_DIR / "test_2021_2022"
FREEZE = TEST_DIR / "arrivals_freeze_manifest.csv"
RUN_LOG = TEST_DIR / "run_log.csv"
RESULTS = "test_metrics.csv"
TEST_FIRST, TEST_LAST = pd.Timestamp("2021-01-03"), pd.Timestamp("2022-12-25")   # target Sundays
DATA_END = TEST_LAST                                                              # no row after this is read
TEST_YEARS = {"test_2021": ("2021-01-03", "2021-12-26"), "test_2022": ("2022-01-02", "2022-12-25")}
CROPS = ["Onion", "Potato", "Wheat"]
CANDIDATE = "hgb_conservative"
SELECTED = {(c, h): CANDIDATE for c in CROPS for h in d.HORIZONS}                 # D-45
POPULATIONS = {"primary": am.PRIMARY_POPULATION, "original": am.SENSITIVITY_POPULATION,
               "mp_excluded": am.MP_SENSITIVITY_POPULATION}
CODE_FILES = [Path("Code/modelling") / f for f in ["dataset.py", "baselines.py", "uncertainty.py", "arrivals.py",
                                                   "arrivals_quality.py", "arrivals_aq1.py", "arrivals_models.py",
                                                   "arrivals_final.py"]] + [Path("Code/features/pipeline.py"),
                                                                            Path("Code/integration/pipeline.py")]
VAL_FILES = [am.OUT_DIR / f for f in ["experiment_config.json", "candidate_selection.csv", "candidate_metrics.csv",
                                      "candidate_bootstrap_primary.csv", "candidate_bootstrap_original.csv",
                                      "candidate_bootstrap_mp_excluded.csv", "candidate_predictions.parquet"]]
AQ1_FILES = [a1.AQ_DIR / "aq1_flags_v1_manifest.csv"] + [a1.AQ_DIR / f"aq1_flags_v1_{c.lower()}.parquet" for c in CROPS]
DOC_FILES = [Path("Documentation/Phase_09_Model_Protocol.md"), d.REGISTRY_PATH]


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def decision_section(log_text: str, decision: str) -> str:
    """The text of one '### D-xx' entry, up to the next '### ' heading."""
    m = re.search(rf"^### {re.escape(decision)} .*?(?=^### |\Z)", log_text, re.M | re.S)
    if not m:
        raise d.ModellingError(f"{decision} not found in the decision log")
    return m.group(0)


def selection_accepted(decision_log: Path = am.DECISION_LOG) -> bool:
    text = Path(decision_log).read_text(encoding="utf-8") if Path(decision_log).exists() else ""
    return re.search(r"^### D-45 — \[ACCEPTED", text, re.M) is not None


def default_spec() -> dict:
    return {"files": CODE_FILES + DOC_FILES + AQ1_FILES + VAL_FILES, "decision_log": am.DECISION_LOG,
            "inputs": {str(d.FEATURE_DIR / f"features_{c.lower()}.parquet"): None for c in CROPS}}


def build_manifest(spec: dict) -> pd.DataFrame:
    """Rows (item, name, value). Raises if an input does not match its Phase 7 record."""
    rows = [{"item": "meta", "name": "version", "value": VERSION},
            {"item": "meta", "name": "hashing", "value": "sha256 of file bytes; decision sections: sha256 of section text "
                                                         "with CRLF->LF; manifest file hash kept in run_log, not here"},
            {"item": "window", "name": "selection_training_cutoff", "value": ar.CUTOFF.date().isoformat()},
            {"item": "window", "name": "test_target_sundays", "value": f"{TEST_FIRST.date()}..{TEST_LAST.date()}"},
            {"item": "window", "name": "data_read_end", "value": DATA_END.date().isoformat()}]
    for f in spec["files"]:
        rows.append({"item": "file", "name": Path(f).as_posix(), "value": file_sha256(f)})
    log = Path(spec["decision_log"]).read_text(encoding="utf-8")
    for dec in ["D-44", "D-45"]:
        rows.append({"item": "decision", "name": dec, "value": _sha_text(decision_section(log, dec))})
    expected = d.phase7_expected_hashes()
    for p, exp in spec["inputs"].items():
        got = file_sha256(p)
        want = exp if exp is not None else expected.get(str(Path(p)))
        if want is not None and got != want:
            raise d.ModellingError(f"input {p} differs from its recorded hash")
        rows.append({"item": "input", "name": Path(p).as_posix(), "value": got})
    params = json.dumps(am.CANDIDATES[CANDIDATE]().get_params(), sort_keys=True, default=str)
    for (c, h), cand in SELECTED.items():
        rows.append({"item": "selection", "name": f"{c} h={h}", "value": f"{cand}|{_sha_text(params)}"})
    rows += [{"item": "config", "name": "features", "value": _sha_text(json.dumps(am.FEATURES))},
             {"item": "config", "name": "populations", "value": json.dumps(POPULATIONS, sort_keys=True)},
             {"item": "config", "name": "metric_and_rule", "value": f"log MAE; bootstrap B={u.B} seed {am.SEED}; selection fixed by D-45"},
             {"item": "config", "name": "refits", "value": "first Sunday of each quarter; train on targets ending <= refit date"}]
    return pd.DataFrame(rows)


def freeze(spec: dict | None = None, path: Path = FREEZE) -> pd.DataFrame:
    if Path(path).exists():
        raise d.ModellingError(f"{path} already exists; the freeze is written once")
    man = build_manifest(spec or default_spec())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    man.to_csv(path, index=False)
    return man


def verify_freeze(spec: dict | None = None, path: Path = FREEZE) -> None:
    if not Path(path).exists():
        raise d.ModellingError("no freeze manifest")
    stored = pd.read_csv(path).astype(str)
    now = build_manifest(spec or default_spec()).astype(str)
    s = stored.set_index(["item", "name"])["value"]
    n = now.set_index(["item", "name"])["value"]
    diff = [k for k in s.index.union(n.index) if s.get(k) != n.get(k)]
    if diff:
        raise d.ModellingError(f"freeze manifest mismatch: {diff[:5]}")


def _log(run_log: Path, status: str, detail: str = "") -> None:
    row = pd.DataFrame([{"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": status, "detail": detail}])
    row.to_csv(run_log, mode="a", header=not Path(run_log).exists(), index=False)


def preflight(spec: dict | None = None, freeze_path: Path = FREEZE, out_dir: Path = TEST_DIR,
              window: tuple = (TEST_FIRST, TEST_LAST)) -> None:
    """Every condition that must hold before the reserved period may be read."""
    spec = spec or default_spec()
    if not selection_accepted(spec["decision_log"]):
        raise d.ModellingError("D-45 is not recorded as ACCEPTED: the arrivals test may not run")
    am.require_approved()                                        # D-44 gate, unchanged
    verify_freeze(spec, freeze_path)
    test = [p for p in d.PERIODS if p[0] == "test"][0]
    if (pd.Timestamp(window[0]), pd.Timestamp(window[1])) != (pd.Timestamp(test[1]), pd.Timestamp(test[2])) \
            or pd.Timestamp(window[1]) >= pd.Timestamp("2023-01-01"):
        raise d.ModellingError(f"test window {window} differs from the D-40 test period or reaches the holdout")
    run_log = Path(out_dir) / "run_log.csv"
    if run_log.exists() and len(pd.read_csv(run_log)):
        last = pd.read_csv(run_log)["status"].tolist()
        raise d.ModellingError(f"the arrivals test was already attempted ({last}); it runs once - review required")
    if (Path(out_dir) / RESULTS).exists():
        raise d.ModellingError("test results already exist; the arrivals test runs once")


def test_year(target_sunday: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=target_sunday.index, dtype=object)
    for name, (a, z) in TEST_YEARS.items():
        out[target_sunday.between(pd.Timestamp(a), pd.Timestamp(z))] = name
    if out.isna().any():
        raise d.ModellingError("a scored target lies outside the test years")
    return out


def metrics_table(p: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (crop, h, pop), g in p.groupby(["crop", "horizon_weeks", "population"], sort=True):
        for period, part in [(y, g[g["period"] == y]) for y in TEST_YEARS] + [("test_combined", g)]:
            mm, pm = ar.metrics(part["y"], part[CANDIDATE]), ar.metrics(part["y"], part["persistence"])
            rows.append({"crop": crop, "horizon_weeks": h, "population": pop, "period": period, "n": mm["n"],
                         "n_series": part[["state", "district", "market", "variety"]].drop_duplicates().shape[0],
                         "log_mae": mm["log_mae"], "persistence_log_mae": pm["log_mae"],
                         "rel_log_mae_improvement_pct": 100 * (1 - mm["log_mae"] / pm["log_mae"]),
                         "mae_t_per_day": mm["mae_t_per_day"], "persistence_mae_t_per_day": pm["mae_t_per_day"],
                         "median_ae_t_per_day": mm["median_ae_t_per_day"], "persistence_median_ae_t_per_day": pm["median_ae_t_per_day"],
                         "wape_pct": mm["wape_pct"], "persistence_wape_pct": pm["wape_pct"]})
    out = pd.DataFrame(rows)
    return out.assign(meets_2pct_practical_minimum=out["rel_log_mae_improvement_pct"] >= am.MIN_REL)


def run_test(feature_dir: Path = FEATURE_DIR, out_dir: Path = TEST_DIR, crops: list[str] | None = None,
             spec: dict | None = None, freeze_path: Path = FREEZE, registry_path: Path = d.REGISTRY_PATH,
             b: int | None = None) -> dict:
    """The one authorised evaluation. Preflight first; any exception is logged as 'failed' and re-raised."""
    spec = spec or default_spec()
    out_dir = Path(out_dir)
    preflight(spec, freeze_path, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_log = out_dir / "run_log.csv"
    _log(run_log, "started", f"freeze_manifest_sha256={file_sha256(freeze_path)}")
    t0 = time.time()
    try:
        crops = crops or CROPS
        reg = d.registry_columns(pd.read_csv(registry_path))
        inputs = {c: Path(feature_dir) / f"features_{c.lower()}.parquet" for c in crops}
        before = {c: file_sha256(p) for c, p in inputs.items()}
        preds, audit = [], []
        for crop, path in inputs.items():
            df = pd.read_parquet(path, filters=[("reported_date", "<=", DATA_END)])   # holdout rows never loaded
            if df["reported_date"].max() > DATA_END:
                raise d.ModellingError("a row after the test window was read")
            d.validate_schema(df, reg, crop)
            flags = a1.flag_table(df, cutoff=DATA_END)
            by_h, origins = ar.build_arrivals_examples(df, cutoff=DATA_END)
            feats = am.origin_features(origins, df)
            for h, ex in by_h.items():
                ar.validate_arrivals_examples(ex, cutoff=DATA_END)
                for pop_name, pop in POPULATIONS.items():
                    p = am.fit_predict(ex, origins, feats, am.population_weeks(flags, pop), CANDIDATE, crop, h, periods=("test",))
                    p = p.assign(period=test_year(ex.loc[p["row"], "target_sunday"]).to_numpy(), population=pop_name)
                    preds.append(p)
                scored = ex[ex["period"] == "test"]
                audit.append({"crop": crop, "horizon_weeks": h, "rows_read": len(df),
                              "max_reported_date_read": df["reported_date"].max().date().isoformat(),
                              "rows_after_2022_12_25_read": int((df["reported_date"] > DATA_END).sum()),
                              "first_scored_target_sunday": scored["target_sunday"].min().date().isoformat(),
                              "last_scored_target_sunday": scored["target_sunday"].max().date().isoformat(),
                              "aq1_test_window_flags_sha": hashlib.sha256(pd.util.hash_pandas_object(flags, index=False).values.tobytes()).hexdigest()})
            del df, flags
        if {c: file_sha256(p) for c, p in inputs.items()} != before:
            raise d.ModellingError("inputs changed during the test")
        allp = pd.concat(preds, ignore_index=True)
        boot = pd.concat([ar.bootstrap_log_mae(g, candidate=CANDIDATE, b=b, periods=tuple(TEST_YEARS), combined="test_combined")
                          .assign(population=pop) for pop, g in allp.groupby("population", sort=True)], ignore_index=True)
        met = metrics_table(allp)
        allp.to_parquet(out_dir / "test_predictions.parquet", index=False)
        boot.to_csv(out_dir / "test_bootstrap.csv", index=False)
        pd.DataFrame(audit).to_csv(out_dir / "test_access_audit.csv", index=False)
        met.to_csv(out_dir / RESULTS, index=False)
        _log(run_log, "completed", f"seconds={round(time.time() - t0, 1)}; rows_scored={len(allp)}")
        return {"metrics": met, "bootstrap": boot, "audit": pd.DataFrame(audit), "predictions": allp}
    except Exception as e:
        _log(run_log, "failed", repr(e)[:500])
        raise
