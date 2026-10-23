"""
Phase 10 — district production context, contract `phase10-production-context-v1` (D-46, D-47, D-48, accepted 2026-10-23).

  inputs       = Phase 4 apy_annual.csv (values), the raw APY file (unit labels for R11, season keys for R12),
                 apy_season.csv (used by the audit) and the D-18 crosswalk (fingerprint only; consumers join through it).
                 verify_inputs() checks every input against its recorded fingerprint before any value is used.
  crosswalk    = Phase 4 recorded its content hash from the in-memory frame, where `alias_basis` held empty strings.
                 CSV serialisation turns "" into NaN on readback, so the plain recomputed hash differs. Verification
                 reports the recorded, the recomputed and a canonicalised hash (only `alias_basis` NaN -> "", after the
                 schema is confirmed). Nothing is rewritten: neither the CSV nor the Phase 4 manifest.
  availability = apy_lag2_policy_v1 (D-47): APY year Y1-Y2 is usable from 1 July of Y2 + 1, so decision year t uses
                 source year t - 2 only. This is a POLICY ASSUMPTION, not a verified publication schedule, and it is not
                 shown to be conservative for source years >= 2019-20.
  windows      = design: source years <= 2018-19 (all rule design and inspection; run_design()). Reserved: 2019-20 ..
                 2021-22, built only by build_full() after freeze() and verify_freeze(); they are logged as counts per
                 pq_class only. 2022-23 is excluded: rows after the window are dropped immediately after loading.
  PQ-1 v1      = flags only (D-48). No value is repaired, clipped, imputed or deleted. The only change to a value is the
                 contract yield set to null where production is null (D-46). Blocked rules (R4 row flag, R5, R6, R7, R8b)
                 are listed as inactive in pq1_provenance.csv and produce no flag. No numerical threshold is active.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from Code.integration.pipeline import (APY_ANNUAL_KEY, APY_COLUMNS, APY_SEASON_KEY, APY_UNITS, file_sha256,
                                       frame_fingerprint)

CONTRACT_VERSION = "phase10-production-context-v1"
PQ_VERSION = "pq1-v1"
INFORMATION_RULE = "apy_lag2_policy_v1"
LAG_YEARS = 2
DESIGN_END = "2018-2019"                                   # D-47: last source year for design and inspection
RESERVED = ("2019-2020", "2020-2021", "2021-2022")         # D-47: built mechanically after the freeze
BUILD_END = RESERVED[-1]                                   # 2022-23 is excluded from v1
CROPS = ["Onion", "Potato", "Wheat"]
DECISIONS = ["D-46", "D-47", "D-48"]

RAW = Path("Dataset/crop-wise-area-production-yield.csv")
INTEGRATION = Path("Processed_Data/integration")
ANNUAL, SEASON, CROSSWALK = INTEGRATION / "apy_annual.csv", INTEGRATION / "apy_season.csv", INTEGRATION / "district_crosswalk.csv"
SOURCE_FP = INTEGRATION / "audit/source_fingerprints.csv"          # raw APY file hash (Phase 4)
FEATURES_FP = Path("Processed_Data/features_audit/input_fingerprints.csv")   # apy_annual.csv file hash (Phase 6)
INTEGRATION_MANIFEST = INTEGRATION / "audit/output_manifest.csv"   # content hashes (Phase 4)
DECISION_LOG = Path("Documentation/Decision_Log.md")
OUT_DIR = Path("Processed_Data/production_context")
CODE_FILES = [Path("Code/production/pipeline.py")]
CROSSWALK_COLUMNS = ["state", "district", "apy_state", "apy_district", "apy_district_match", "alias_basis", "crop",
                     "mandi_records"]

AMBIGUOUS = "ambiguous_multi_season_no_total"
COMPARABILITY = ["verified_total", "whole_year_row", "single_named_season", "ambiguous"]
PQ_CLASSES = ["ok", "annotated", "review", "unusable"]
CAVEAT = ("apy_lag2_policy_v1 is a policy assumption, not a verified publication schedule; it is not shown to be "
          "conservative for source years >= 2019-20. The input is one 2023 vintage: earlier years carry revised, "
          "not first-published, values.")

# (code, name, status, effect, condition, evidence). Active rules first, in pq_reasons order.
RULES = [
    ("R1", "missing_value", "specified", "unusable",
     "production_tonnes null, or area_ha null, or annual_method == ambiguous_multi_season_no_total", "F4, F11, D-20"),
    ("R2", "yield_zero_encodes_missing", "specified", "annotated",
     "production null and published yield == 0; the contract yield is null", "F4"),
    ("R3", "zero_production", "review-only", "review", "production == 0 and area > 0", "F5"),
    ("R8a", "first_reported_after_state_start", "specified", "annotated",
     "first source year of (crop, state, district) > first source year of (crop, state); earlier years only", "F14"),
    ("R9", "single_season_annual", "specified", "annotated", "annual_comparability == single_named_season (all crops)", "F9"),
    ("R10", "method_change", "specified", "annotated",
     "annual_comparability differs from the most recent earlier source year with a row for the same crop, state "
     "and district", "F10"),
    ("R11", "unit_label", "specified", "unusable",
     "a raw season row has unit labels other than Hectare / Tonnes / Tonnes/Hectare", "F1"),
    ("R12", "duplicate_conflict", "specified", "unusable",
     "a raw season row key (crop, state, district, year, season) is duplicated", "F2"),
    ("R13", "provider_query_pending", "review-only", "review",
     "crop Potato, source year 1997-98, state West Bengal or Gujarat (D-48 Option 1); no cause asserted", "F6, F7"),
    ("R4", "yield_inconsistent", "diagnostic", "none",
     "manifest only, per crop: rows with area > 0 and production > 0 (non-null), and max |yield - production/area| / "
     "(production/area); no row flag, no tolerance", "F3"),
    ("R4-flag", "yield_inconsistent_flag", "blocked", "none", "inactive: no justified tolerance", "F3"),
    ("R5", "implausible_area", "blocked", "none", "inactive: needs official district/state geographic areas", "F6"),
    ("R6", "implausible_yield", "blocked", "none", "inactive: needs reference yields", "F6-F8"),
    ("R7", "area_jump", "blocked", "none", "inactive: needs a robust reference design", "revision 1 candidates"),
    ("R8b", "boundary_split", "blocked", "none", "inactive: needs LGD / gazette split history", "F15"),
]
ACTIVE = [r for r in RULES if r[3] != "none"]
R13_SCOPE = {"crop": "Potato", "apy_year": "1997-1998", "states": ("West Bengal", "Gujarat")}

CONTRACT_COLUMNS = ["crop", "apy_state", "apy_district", "apy_district_code", "decision_agri_year", "source_apy_year",
                    "available_from", "information_rule", "production_tonnes", "area_ha", "yield_t_per_ha",
                    "annual_method", "seasons_reported", "annual_comparability", "pq_class", "pq_reasons",
                    "pq_version", "contract_version"]
CONTEXT_KEY = ["crop", "apy_state", "apy_district", "decision_agri_year"]


class ProductionError(RuntimeError):
    pass


def start_year(label: pd.Series) -> pd.Series:
    if not label.str.fullmatch(r"\d{4}-\d{4}").all():
        raise ProductionError("APY year labels are not all 'YYYY-YYYY'")
    y1, y2 = label.str[:4].astype(int), label.str[5:].astype(int)
    if not (y2 == y1 + 1).all():
        raise ProductionError("an APY year label does not span consecutive years")
    return y1


def within(df: pd.DataFrame, col: str, last: str) -> pd.DataFrame:
    """Drop rows after `last` immediately after loading, and assert the cut."""
    out = df[start_year(df[col]) <= int(last[:4])]
    assert start_year(out[col]).max() <= int(last[:4])
    return out


def write_csv(df: pd.DataFrame, path: Path) -> str:
    """Deterministic CSV (LF line endings); returns the file sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n")
    return file_sha256(path)


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _posix(p) -> str:
    return str(p).replace("\\", "/")


# ---------------------------------------------------------------- input integrity
def recorded_fingerprints(source_fp: Path = SOURCE_FP, features_fp: Path = FEATURES_FP,
                          manifest: Path = INTEGRATION_MANIFEST) -> dict:
    """The fingerprints Phases 4 and 6 recorded for the Phase 10 inputs (never recomputed here)."""
    def file_rec(path, target):
        df = pd.read_csv(path)
        vals = df.loc[df["path"].map(_posix) == _posix(target), "sha256_after"].unique()
        if len(vals) != 1:
            raise ProductionError(f"no unique recorded file hash for {target} in {path}")
        return vals[0]
    man = pd.read_csv(manifest).set_index("file")
    content = {n: {"content_sha256": man.loc[p.name, "content_sha256"], "rows": int(man.loc[p.name, "rows"]),
                   "columns": int(man.loc[p.name, "columns"])} for n, p in [("annual", ANNUAL), ("season", SEASON),
                                                                            ("crosswalk", CROSSWALK)]}
    content["raw"] = {"file_sha256": file_rec(source_fp, RAW)}
    content["annual"]["file_sha256"] = file_rec(features_fp, ANNUAL)
    return content


def git_blob_matches_head(path: Path) -> bool:
    """The working file, after git's own filters, equals the blob committed at HEAD."""
    run = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout.strip()
    return run("hash-object", _posix(path)) == run("rev-parse", f"HEAD:{_posix(path)}")


def verify_inputs(paths: dict, records: dict, git_tracked: tuple = ()) -> pd.DataFrame:
    """One row per check. Raises ProductionError on any mismatch; the report is returned only when all pass."""
    rows = []
    add = lambda name, check, recorded, recomputed, status, canonical="": rows.append(
        {"input": name, "path": _posix(paths[name]), "check": check, "recorded": recorded, "recomputed": recomputed,
         "canonicalised": canonical, "status": status})
    for name, rec in records.items():
        p = Path(paths[name])
        if "file_sha256" in rec:
            got = file_sha256(p)
            add(name, "file_sha256", rec["file_sha256"], got, "match" if got == rec["file_sha256"] else "MISMATCH")
        if "content_sha256" in rec:
            df = pd.read_csv(p)
            shape_ok = df.shape == (rec["rows"], rec["columns"])
            add(name, "shape", f"{rec['rows']}x{rec['columns']}", f"{df.shape[0]}x{df.shape[1]}",
                "match" if shape_ok else "MISMATCH")
            got, canon = frame_fingerprint(df), ""
            if name == "crosswalk":
                # CSV turns the in-memory "" of alias_basis into NaN on readback; canonicalise only that column,
                # only after the schema is confirmed, only for this comparison.
                if list(df.columns) != CROSSWALK_COLUMNS or df["alias_basis"].dtype != object:
                    raise ProductionError(f"crosswalk schema differs from the expected {CROSSWALK_COLUMNS}")
                canon = frame_fingerprint(df.fillna({"alias_basis": ""}))
            status = ("match" if got == rec["content_sha256"] else
                      "match_after_alias_basis_canonicalisation" if canon == rec["content_sha256"] else "MISMATCH")
            add(name, "content_sha256", rec["content_sha256"], got, status, canon)
    for name in git_tracked:
        ok = git_blob_matches_head(paths[name])
        add(name, "git_blob_vs_HEAD", "HEAD", "working file", "match" if ok else "MISMATCH")
    report = pd.DataFrame(rows)
    if (report["status"] == "MISMATCH").any():
        raise ProductionError(f"input fingerprint mismatch:\n{report[report['status'] == 'MISMATCH'].to_string()}")
    return report


def default_spec() -> dict:
    return {"paths": {"raw": RAW, "annual": ANNUAL, "season": SEASON, "crosswalk": CROSSWALK},
            "records": recorded_fingerprints(), "git_tracked": ("crosswalk",), "decision_log": DECISION_LOG,
            "code_files": CODE_FILES, "out_dir": OUT_DIR}


# ---------------------------------------------------------------- loading and the contract
def load(paths: dict, last: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """apy_annual and the raw APY season rows (selected crops), cut to source years <= `last` on load."""
    annual = within(pd.read_csv(paths["annual"]), "apy_year", last)
    raw = pd.read_csv(paths["raw"])
    raw = within(raw[raw["crop_name"].isin(CROPS)], "year", last).rename(columns=APY_COLUMNS)
    return annual.reset_index(drop=True), raw.reset_index(drop=True)


def comparability(annual: pd.DataFrame) -> pd.Series:
    m, s = annual["annual_method"], annual["seasons_reported"]
    out = pd.Series(np.select([m == "total_row", (m == "single_season") & (s == "Whole Year"), m == "single_season",
                               m == AMBIGUOUS], COMPARABILITY, default=""), index=annual.index)
    if (out == "").any():
        raise ProductionError(f"unknown annual_method values: {sorted(m[out == ''].unique())}")
    return out


def flags(a: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """Boolean column per active rule. Every rule reads only the row's own and earlier source years."""
    prod, area, y1 = a["production_tonnes"], a["area_ha"], start_year(a["apy_year"])
    district, state = ["crop", "state", "district"], ["crop", "state"]
    # group minima of earlier-or-equal years equal the plain group minima: a later year can never lower a minimum
    first_d, first_s = y1.groupby([a[c] for c in district]).transform("min"), y1.groupby([a[c] for c in state]).transform("min")
    order = a.assign(_y=y1).sort_values(district + ["_y"])
    prev = order.groupby(district)["annual_comparability"].shift().reindex(a.index)
    bad_units = np.logical_or.reduce([raw[c] != u for c, u in APY_UNITS.items()])
    dup = raw.duplicated(APY_SEASON_KEY, keep=False)
    in_keys = lambda r: pd.MultiIndex.from_frame(a[APY_ANNUAL_KEY]).isin(pd.MultiIndex.from_frame(r[APY_ANNUAL_KEY]))
    f = {"missing_value": prod.isna() | area.isna() | (a["annual_method"] == AMBIGUOUS),
         "yield_zero_encodes_missing": prod.isna() & (a["yield_t_per_ha"] == 0),
         "zero_production": (prod == 0) & (area > 0),
         "first_reported_after_state_start": first_d > first_s,
         "single_season_annual": a["annual_comparability"] == "single_named_season",
         "method_change": prev.notna() & (prev != a["annual_comparability"]),
         "unit_label": in_keys(raw[bad_units]),
         "duplicate_conflict": in_keys(raw[dup]),
         "provider_query_pending": (a["crop"] == R13_SCOPE["crop"]) & (a["apy_year"] == R13_SCOPE["apy_year"])
                                   & a["state"].isin(R13_SCOPE["states"])}
    return pd.DataFrame(f, index=a.index)[[r[1] for r in ACTIVE]]


def build_context(annual: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """The v1 contract rows: one per apy_annual district-year, values as published (yield null where production null)."""
    if annual.duplicated(APY_ANNUAL_KEY).any():
        raise ProductionError("apy_annual key (crop, state, district, apy_year) is not unique")
    a = annual.assign(annual_comparability=comparability(annual))
    fl = flags(a, raw)
    effect = {r[1]: r[3] for r in ACTIVE}
    pq = np.select([fl[[n for n in fl if effect[n] == c]].any(axis=1) for c in ["unusable", "review", "annotated"]],
                   ["unusable", "review", "annotated"], default="ok")
    y1 = start_year(a["apy_year"])
    out = pd.DataFrame({
        "crop": a["crop"], "apy_state": a["state"], "apy_district": a["district"],
        "apy_district_code": a["district_code"].astype("Int64"),
        "decision_agri_year": (y1 + LAG_YEARS).astype(str) + "-" + (y1 + LAG_YEARS + 1).astype(str),
        "source_apy_year": a["apy_year"],
        "available_from": (y1 + LAG_YEARS).astype(str) + "-07-01",   # 1 July of Y2 + 1, Y2 = y1 + 1
        "information_rule": INFORMATION_RULE,
        "production_tonnes": a["production_tonnes"], "area_ha": a["area_ha"],
        "yield_t_per_ha": a["yield_t_per_ha"].where(a["production_tonnes"].notna()),
        "annual_method": a["annual_method"], "seasons_reported": a["seasons_reported"],
        "annual_comparability": a["annual_comparability"], "pq_class": pq,
        "pq_reasons": fl.apply(lambda r: "|".join(n for n in fl.columns if r[n]), axis=1) if len(fl) else "",
        "pq_version": PQ_VERSION, "contract_version": CONTRACT_VERSION})
    return out[CONTRACT_COLUMNS].sort_values(CONTEXT_KEY).reset_index(drop=True)


def check_contract(ctx: pd.DataFrame, n_annual: int, last: str) -> None:
    src, dec = start_year(ctx["source_apy_year"]), start_year(ctx["decision_agri_year"])
    checks = {"one row per apy_annual row": len(ctx) == n_annual,
              "unique key": not ctx.duplicated(CONTEXT_KEY).any(),
              "source = decision - 2": (src == dec - LAG_YEARS).all(),
              "available_from = 1 July of decision start": (ctx["available_from"] == dec.astype(str) + "-07-01").all(),
              f"no source year after {last}": (src <= int(last[:4])).all(),
              "no 2022-23 source row": not (ctx["source_apy_year"] == "2022-2023").any(),
              "known classes": ctx["pq_class"].isin(PQ_CLASSES).all() and ctx["annual_comparability"].isin(COMPARABILITY).all(),
              "yield null where production null": ctx.loc[ctx["production_tonnes"].isna(), "yield_t_per_ha"].isna().all()}
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise ProductionError(f"contract checks failed: {failed}")


def r4_diagnostic(annual: pd.DataFrame) -> pd.DataFrame:
    """R4, diagnostic only (design window): computable rows and the max relative yield difference, per crop."""
    a = within(annual, "apy_year", DESIGN_END)
    ok = a["area_ha"].notna() & a["production_tonnes"].notna() & a["yield_t_per_ha"].notna() \
        & (a["area_ha"] > 0) & (a["production_tonnes"] > 0)
    a = a[ok]
    calc = a["production_tonnes"] / a["area_ha"]
    rel = ((a["yield_t_per_ha"] - calc).abs() / calc).groupby(a["crop"])
    return pd.DataFrame({"rows_computable": rel.size(), "max_abs_rel_diff": rel.max()}).reindex(CROPS).fillna(
        {"rows_computable": 0}).astype({"rows_computable": int}).rename_axis("crop").reset_index()


def provenance() -> pd.DataFrame:
    return pd.DataFrame(RULES, columns=["code", "name", "status", "effect", "condition", "evidence"]).assign(
        active=lambda d: d["effect"] != "none", pq_version=PQ_VERSION, decision="D-48")


# ---------------------------------------------------------------- approvals, freeze, stages
def decisions_accepted(log_path: Path = DECISION_LOG) -> bool:
    text = Path(log_path).read_text(encoding="utf-8") if Path(log_path).exists() else ""
    return all(re.search(rf"^### {d} — \[ACCEPTED", text, re.M) for d in DECISIONS)


def decision_section(text: str, decision: str) -> str:
    m = re.search(rf"^### {re.escape(decision)} .*?(?=^### |\Z)", text, re.M | re.S)
    if not m:
        raise ProductionError(f"{decision} not found in the decision log")
    return m.group(0)


def build_freeze(spec: dict) -> pd.DataFrame:
    """Hashes of the code, the accepted decisions, the inputs and the design-window context (item, name, value)."""
    report = verify_inputs(spec["paths"], spec["records"], spec["git_tracked"])
    annual, raw = load(spec["paths"], DESIGN_END)
    design = build_context(annual, raw)
    rows = [{"item": "meta", "name": "contract_version", "value": CONTRACT_VERSION},
            {"item": "meta", "name": "pq_version", "value": PQ_VERSION},
            {"item": "meta", "name": "information_rule", "value": INFORMATION_RULE},
            {"item": "window", "name": "design_end", "value": DESIGN_END},
            {"item": "window", "name": "reserved", "value": "|".join(RESERVED)},
            {"item": "rules", "name": "pq1_provenance", "value": frame_fingerprint(provenance())}]
    rows += [{"item": "file", "name": _posix(f), "value": file_sha256(f)} for f in spec["code_files"]]
    log = Path(spec["decision_log"]).read_text(encoding="utf-8")
    rows += [{"item": "decision", "name": d, "value": _sha_text(decision_section(log, d))} for d in DECISIONS]
    rows += [{"item": "input", "name": f"{r.input}:{r.check}", "value": r.recorded} for r in report.itertuples()
             if r.check in ("file_sha256", "content_sha256")]
    rows += [{"item": "design", "name": "rows", "value": str(len(design))},
             {"item": "design", "name": "content_sha256", "value": frame_fingerprint(design)}]
    return pd.DataFrame(rows)


def freeze(spec: dict | None = None) -> pd.DataFrame:
    spec = spec or default_spec()
    path = Path(spec["out_dir"]) / "pq1_freeze_manifest.csv"
    if not decisions_accepted(spec["decision_log"]):
        raise ProductionError("D-46, D-47 and D-48 must be recorded as ACCEPTED before PQ-1 is frozen")
    if path.exists():
        raise ProductionError(f"{path} already exists; the freeze is written once")
    man = build_freeze(spec)
    write_csv(man, path)
    return man


def verify_freeze(spec: dict) -> None:
    path = Path(spec["out_dir"]) / "pq1_freeze_manifest.csv"
    if not path.exists():
        raise ProductionError("no PQ-1 freeze manifest: reserved source years may not be built")
    s = pd.read_csv(path, dtype=str).set_index(["item", "name"])["value"]
    n = build_freeze(spec).astype(str).set_index(["item", "name"])["value"]
    diff = [k for k in s.index.union(n.index) if s.get(k) != n.get(k)]
    if diff:
        raise ProductionError(f"PQ-1 freeze mismatch: {diff[:5]}")


def _log(out_dir: Path, stage: str, detail: str) -> None:
    row = pd.DataFrame([{"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": stage, "detail": detail}])
    p = Path(out_dir) / "build_log.csv"
    row.to_csv(p, mode="a", header=not p.exists(), index=False, lineterminator="\n")


def counts(ctx: pd.DataFrame) -> pd.DataFrame:
    """Counts only (no values): crop x source year x pq_class."""
    return (ctx.groupby(["crop", "source_apy_year", "pq_class"]).size().rename("rows").reset_index()
            .sort_values(["crop", "source_apy_year", "pq_class"]).reset_index(drop=True))


def run_design(spec: dict | None = None) -> pd.DataFrame:
    """Design window only (source <= 2018-19): counts per crop x comparability x pq_class x reason, for inspection."""
    spec = spec or default_spec()
    if not decisions_accepted(spec["decision_log"]):
        raise ProductionError("D-46, D-47 and D-48 are not recorded as ACCEPTED")
    verify_inputs(spec["paths"], spec["records"], spec["git_tracked"])
    annual, raw = load(spec["paths"], DESIGN_END)
    ctx = build_context(annual, raw)
    check_contract(ctx, len(annual), DESIGN_END)
    summary = (ctx.assign(pq_reasons=ctx["pq_reasons"].replace("", "(none)"))
               .groupby(["crop", "annual_comparability", "pq_class", "pq_reasons"]).size().rename("rows").reset_index())
    write_csv(summary, Path(spec["out_dir"]) / "design" / "design_pq_summary.csv")
    return summary


def build_full(spec: dict | None = None) -> pd.DataFrame:
    """The v1 product for source years <= 2021-22. Runs only after the freeze verifies; reserved years: counts only."""
    spec = spec or default_spec()
    out = Path(spec["out_dir"])
    if not decisions_accepted(spec["decision_log"]):
        raise ProductionError("D-46, D-47 and D-48 are not recorded as ACCEPTED")
    verify_freeze(spec)                                   # also re-verifies every input fingerprint
    report = verify_inputs(spec["paths"], spec["records"], spec["git_tracked"])
    annual, raw = load(spec["paths"], BUILD_END)
    ctx = build_context(annual, raw)
    check_contract(ctx, len(annual), BUILD_END)
    design = ctx[start_year(ctx["source_apy_year"]) <= int(DESIGN_END[:4])].reset_index(drop=True)
    frozen = pd.read_csv(out / "pq1_freeze_manifest.csv", dtype=str).set_index(["item", "name"])["value"]
    if frame_fingerprint(design) != frozen[("design", "content_sha256")]:
        raise ProductionError("design-window rows changed when later years were added (look-ahead)")

    ctx_sha = write_csv(ctx, out / "production_context_v1.csv")
    prov_sha = write_csv(provenance(), out / "pq1_provenance.csv")
    r4 = r4_diagnostic(annual)
    man = [{"item": "meta", "name": n, "value": v} for n, v in
           [("contract_version", CONTRACT_VERSION), ("pq_version", PQ_VERSION), ("information_rule", INFORMATION_RULE),
            ("caveat", CAVEAT), ("design_end", DESIGN_END), ("reserved", "|".join(RESERVED)),
            ("excluded_source_years", "2022-2023 and later"), ("freeze_manifest_sha256", file_sha256(out / "pq1_freeze_manifest.csv"))]]
    man += [{"item": "input", "name": f"{r.input}:{r.check}", "value": f"{r.status}; recorded={r.recorded}; "
             f"recomputed={r.recomputed}" + (f"; canonicalised={r.canonicalised}" if r.canonicalised else "")}
            for r in report.itertuples()]
    man += [{"item": "output", "name": "production_context_v1.csv", "value": f"rows={len(ctx)}; file_sha256={ctx_sha}; "
             f"content_sha256={frame_fingerprint(ctx)}"},
            {"item": "output", "name": "pq1_provenance.csv", "value": f"rows={len(provenance())}; file_sha256={prov_sha}"}]
    man += [{"item": "r4_diagnostic", "name": r.crop, "value": f"rows_computable={r.rows_computable}; "
             f"max_abs_rel_diff={r.max_abs_rel_diff!r}; design window only; no flag"} for r in r4.itertuples()]
    man += [{"item": "counts", "name": f"{r.crop}|{r.source_apy_year}|{r.pq_class}", "value": str(r.rows)}
            for r in counts(ctx).itertuples()]
    man = pd.DataFrame(man)
    write_csv(man, out / "output_manifest.csv")

    if file_sha256(spec["paths"]["raw"]) != spec["records"]["raw"]["file_sha256"] or \
            file_sha256(spec["paths"]["annual"]) != spec["records"]["annual"]["file_sha256"]:
        raise ProductionError("an input changed during the build")
    reserved = ctx[ctx["source_apy_year"].isin(RESERVED)]
    _log(out, "build_full", "reserved rows by pq_class (counts only): "
         + "; ".join(f"{c}={n}" for c, n in reserved["pq_class"].value_counts().sort_index().items())
         + f"; total rows={len(ctx)}; max source year={ctx['source_apy_year'].max()}")
    return man


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    {"design": run_design, "freeze": freeze, "build": build_full}[stage]()
    print(f"phase 10 stage '{stage}' finished")
