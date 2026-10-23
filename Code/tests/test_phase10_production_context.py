"""
Phase 10 production context (D-46 / D-47 / D-48) tests. Synthetic inputs in temporary directories, except the two
real-file guards at the end, which only hash the real inputs and read the decision log.
"""

import re

import numpy as np
import pandas as pd
import pytest

from Code.integration.pipeline import APY_COLUMNS, apy_annual, file_sha256, frame_fingerprint
from Code.production import apy_audit as au
from Code.production import pipeline as pc

ACCEPTED = "".join(f"### {d} — [ACCEPTED 2026-10-23 by the project owner] x\nbody {d}\n" for d in pc.DECISIONS)
UNITS = {"area_unit": "Hectare", "production_unit": "Tonnes", "yield_unit": "Tonnes/Hectare"}


def raw_row(i, year, state, district, crop, season, area, prod, yld=None, code=None):
    return {"id": i, "year": year, "state_name": state, "state_code": 1, "district_name": district,
            "district_code": code or sum(map(ord, district)), "crop_name": crop, "crop_code": 1.0,
            "crop_type": "Vegetable", "season": season, "area": area, "production": prod,
            "yield": (prod / area if prod is not None and prod == prod else 0.0) if yld is None else yld, **UNITS}


def raw_rows():
    r = [
        # Maharashtra Onion, district A: Total row, Whole Year, then a named season, then missing production
        ("1997-1998", "Maharashtra", "A", "Onion", "Total", 100.0, 2000.0),
        ("1997-1998", "Maharashtra", "A", "Onion", "Rabi", 60.0, 1200.0),
        ("1997-1998", "Maharashtra", "A", "Onion", "Kharif", 40.0, 800.0),
        ("1998-1999", "Maharashtra", "A", "Onion", "Whole Year", 90.0, 1800.0),
        ("1999-2000", "Maharashtra", "A", "Onion", "Rabi", 80.0, 1600.0),
        ("2000-2001", "Maharashtra", "A", "Onion", "Rabi", 80.0, np.nan),
        ("2001-2002", "Maharashtra", "A", "Onion", "Rabi", 30.0, 0.0),
        ("2002-2003", "Maharashtra", "A", "Onion", "Kharif", 10.0, 100.0),
        ("2002-2003", "Maharashtra", "A", "Onion", "Whole Year", 20.0, 300.0),
        # district B first appears after the state's first year (R8a)
        ("1999-2000", "Maharashtra", "B", "Onion", "Whole Year", 50.0, 1000.0),
        ("2000-2001", "Maharashtra", "B", "Onion", "Whole Year", 50.0, 1000.0),
        # R13 scope and its near misses
        ("1997-1998", "West Bengal", "W1", "Potato", "Whole Year", 4_000_000.0, 3_000_000.0),
        ("1998-1999", "West Bengal", "W1", "Potato", "Whole Year", 20_000.0, 400_000.0),
        ("1997-1998", "Gujarat", "G1", "Potato", "Whole Year", 134_000.0, 706.0),
        ("1997-1998", "Gujarat", "G2", "Potato", "Whole Year", 1_000.0, 25_000.0),
        ("1998-1999", "Gujarat", "G1", "Potato", "Whole Year", 1_000.0, 25_000.0),
        ("1997-1998", "West Bengal", "W1", "Onion", "Whole Year", 1_000.0, 15_000.0),
        ("1997-1998", "Bihar", "P1", "Potato", "Whole Year", 1_000.0, 25_000.0),
        # Wheat: a single Rabi row is still a named season (no Wheat exception)
        ("1997-1998", "Punjab", "L", "Wheat", "Rabi", 1_000.0, 4_000.0),
        ("2018-2019", "Punjab", "L", "Wheat", "Rabi", 1_000.0, 4_500.0),
        # reserved and excluded years
        ("2019-2020", "Punjab", "L", "Wheat", "Total", 1_000.0, 4_600.0),
        ("2019-2020", "Punjab", "L", "Wheat", "Rabi", 1_000.0, 4_600.0),
        ("2021-2022", "Punjab", "L", "Wheat", "Rabi", 1_000.0, 4_700.0),
        ("2022-2023", "Punjab", "L", "Wheat", "Rabi", 1_000.0, 999_999.0),
        ("2021-2022", "Punjab", "N", "Wheat", "Rabi", 500.0, 2_000.0),
        # an unrelated crop is ignored
        ("1997-1998", "Punjab", "L", "Rice", "Kharif", 1_000.0, 3_000.0),
    ]
    rows = [raw_row(i + 1, *t) for i, t in enumerate(r)]
    rows[5]["yield"] = 0.0                                          # missing production encoded as yield 0 (F4)
    return pd.DataFrame(rows)


def crosswalk_frame():
    return pd.DataFrame({"state": ["Maharashtra", "Punjab"], "district": ["A", "Ludhiana"],
                         "apy_state": ["Maharashtra", "Punjab"], "apy_district": ["A", "L"],
                         "apy_district_match": ["exact_normalized", "reviewed_alias"], "alias_basis": ["", "spelling"],
                         "crop": ["Onion", "Wheat"], "mandi_records": [10, 20]})


def sub(tmp_path, name):
    (tmp_path / name).mkdir()
    return tmp_path / name


def make_spec(tmp_path, raw=None, decision=ACCEPTED):
    raw = raw_rows() if raw is None else raw
    d = tmp_path / "in"
    d.mkdir(exist_ok=True)
    season = (raw[raw["crop_name"].isin(pc.CROPS)].rename(columns=APY_COLUMNS)[list(APY_COLUMNS.values())]
              .sort_values(["crop", "state", "district", "apy_year", "season"]).reset_index(drop=True))
    paths = {"raw": d / "raw.csv", "annual": d / "apy_annual.csv", "season": d / "apy_season.csv",
             "crosswalk": d / "district_crosswalk.csv"}
    raw.to_csv(paths["raw"], index=False)
    apy_annual(season).to_csv(paths["annual"], index=False)
    season.to_csv(paths["season"], index=False)
    cw = crosswalk_frame()
    cw.to_csv(paths["crosswalk"], index=False)
    rec = lambda p: {"content_sha256": frame_fingerprint(pd.read_csv(p)), "rows": len(pd.read_csv(p)),
                     "columns": pd.read_csv(p).shape[1]}
    records = {"raw": {"file_sha256": file_sha256(paths["raw"])},
               "annual": {**rec(paths["annual"]), "file_sha256": file_sha256(paths["annual"])},
               "season": rec(paths["season"]),
               # as Phase 4: hashed in memory, where alias_basis holds "" (CSV readback gives NaN)
               "crosswalk": {"content_sha256": frame_fingerprint(cw), "rows": 2, "columns": 8}}
    log = tmp_path / "Decision_Log.md"
    log.write_text(decision, encoding="utf-8")
    code = tmp_path / "code.py"
    code.write_text("x = 1\n", encoding="utf-8")
    return {"paths": paths, "records": records, "git_tracked": (), "decision_log": log, "code_files": [code],
            "out_dir": tmp_path / "out"}


def context(spec, last=pc.BUILD_END):
    annual, raw = pc.load(spec["paths"], last)
    return pc.build_context(annual, raw), annual


def row(ctx, crop, state, district, year):
    r = ctx[(ctx["crop"] == crop) & (ctx["apy_state"] == state) & (ctx["apy_district"] == district)
            & (ctx["source_apy_year"] == year)]
    assert len(r) == 1
    return r.iloc[0]


# ---------------------------------------------------------------- input integrity
def test_fingerprints_verified_and_changes_detected(tmp_path):
    spec = make_spec(tmp_path)
    rep = pc.verify_inputs(spec["paths"], spec["records"])
    assert set(rep["status"]) <= {"match", "match_after_alias_basis_canonicalisation"}
    with open(spec["paths"]["raw"], "ab") as f:
        f.write(b"\n")
    with pytest.raises(pc.ProductionError, match="mismatch"):
        pc.verify_inputs(spec["paths"], spec["records"])


def test_crosswalk_roundtrip_discrepancy_reproduced_and_canonicalised_narrowly(tmp_path):
    spec = make_spec(tmp_path)
    rep = pc.verify_inputs(spec["paths"], spec["records"]).set_index(["input", "check"])
    cw = rep.loc[("crosswalk", "content_sha256")]
    assert cw["recomputed"] != cw["recorded"]                       # the plain readback hash differs ...
    assert cw["canonicalised"] == cw["recorded"]                    # ... only alias_basis "" -> NaN explains it
    assert cw["status"] == "match_after_alias_basis_canonicalisation"
    assert pd.read_csv(spec["paths"]["crosswalk"])["alias_basis"].isna().sum() == 1   # source file untouched
    # a blank in any other column is not canonicalised
    bad = crosswalk_frame().assign(apy_district=["", "L"])
    bad.to_csv(spec["paths"]["crosswalk"], index=False)
    spec["records"]["crosswalk"]["content_sha256"] = frame_fingerprint(bad)
    with pytest.raises(pc.ProductionError, match="mismatch"):
        pc.verify_inputs(spec["paths"], spec["records"])
    # a schema change stops verification before any canonicalisation
    crosswalk_frame().rename(columns={"alias_basis": "basis"}).to_csv(spec["paths"]["crosswalk"], index=False)
    with pytest.raises(pc.ProductionError, match="schema"):
        pc.verify_inputs(spec["paths"], spec["records"])


# ---------------------------------------------------------------- windows and availability
def test_cutoff_applied_on_load(tmp_path):
    spec = make_spec(tmp_path)
    annual, raw = pc.load(spec["paths"], pc.DESIGN_END)
    assert annual["apy_year"].max() == pc.DESIGN_END and raw["apy_year"].max() == pc.DESIGN_END
    annual, raw = pc.load(spec["paths"], pc.BUILD_END)
    assert "2022-2023" not in set(annual["apy_year"]) | set(raw["apy_year"])
    assert set(raw["crop"]) == set(pc.CROPS)
    with pytest.raises(pc.ProductionError):
        pc.start_year(pd.Series(["2019-2021"]))


def test_temporal_availability_and_contract_checks(tmp_path):
    spec = make_spec(tmp_path)
    ctx, annual = context(spec)
    r = row(ctx, "Wheat", "Punjab", "L", "2018-2019")
    assert (r["decision_agri_year"], r["available_from"], r["information_rule"]) == ("2020-2021", "2020-07-01",
                                                                                      "apy_lag2_policy_v1")
    assert ctx["decision_agri_year"].min() == "1999-2000" and ctx["source_apy_year"].max() == "2021-2022"
    pc.check_contract(ctx, len(annual), pc.BUILD_END)
    for col, val in [("decision_agri_year", "2019-2020"), ("available_from", "2020-06-30")]:
        bad = ctx.copy()
        bad.loc[0, col] = val
        with pytest.raises(pc.ProductionError, match="contract"):
            pc.check_contract(bad, len(annual), pc.BUILD_END)


def test_no_look_ahead_design_rows_unchanged_by_later_years(tmp_path):
    spec = make_spec(tmp_path)
    design, _ = context(spec, pc.DESIGN_END)
    full, _ = context(spec)
    part = full[pc.start_year(full["source_apy_year"]) <= 2018].reset_index(drop=True)
    pd.testing.assert_frame_equal(part, design)


# ---------------------------------------------------------------- values, classes and rules
def test_source_values_preserved(tmp_path):
    spec = make_spec(tmp_path)
    ctx, annual = context(spec)
    m = ctx.merge(annual, left_on=["crop", "apy_state", "apy_district", "source_apy_year"],
                  right_on=["crop", "state", "district", "apy_year"], validate="1:1")
    assert len(m) == len(annual) == len(ctx)
    pd.testing.assert_series_equal(m["production_tonnes_x"], m["production_tonnes_y"], check_names=False)
    pd.testing.assert_series_equal(m["area_ha_x"], m["area_ha_y"], check_names=False)
    has = m["production_tonnes_x"].notna()
    pd.testing.assert_series_equal(m.loc[has, "yield_t_per_ha_x"], m.loc[has, "yield_t_per_ha_y"], check_names=False)
    assert m.loc[~has, "yield_t_per_ha_x"].isna().all()             # the only change: null yield where production null
    assert row(ctx, "Potato", "West Bengal", "W1", "1997-1998")["area_ha"] == 4_000_000.0   # nothing clipped


def test_annual_comparability_classes(tmp_path):
    ctx, _ = context(make_spec(tmp_path))
    assert row(ctx, "Onion", "Maharashtra", "A", "1997-1998")["annual_comparability"] == "verified_total"
    assert row(ctx, "Onion", "Maharashtra", "A", "1998-1999")["annual_comparability"] == "whole_year_row"
    assert row(ctx, "Onion", "Maharashtra", "A", "1999-2000")["annual_comparability"] == "single_named_season"
    assert row(ctx, "Onion", "Maharashtra", "A", "2002-2003")["annual_comparability"] == "ambiguous"
    assert row(ctx, "Wheat", "Punjab", "L", "1997-1998")["annual_comparability"] == "single_named_season"
    with pytest.raises(pc.ProductionError, match="annual_method"):
        pc.comparability(pd.DataFrame({"annual_method": ["other"], "seasons_reported": ["Rabi"]}))


def test_null_and_zero_production(tmp_path):
    ctx, _ = context(make_spec(tmp_path))
    miss = row(ctx, "Onion", "Maharashtra", "A", "2000-2001")
    assert miss["pq_class"] == "unusable" and pd.isna(miss["yield_t_per_ha"])
    assert miss["pq_reasons"].split("|")[:2] == ["missing_value", "yield_zero_encodes_missing"]
    zero = row(ctx, "Onion", "Maharashtra", "A", "2001-2002")
    assert zero["pq_class"] == "review" and "zero_production" in zero["pq_reasons"] and zero["production_tonnes"] == 0
    amb = row(ctx, "Onion", "Maharashtra", "A", "2002-2003")
    assert amb["pq_class"] == "unusable" and amb["pq_reasons"].startswith("missing_value")


def test_active_rules_and_precedence(tmp_path):
    ctx, _ = context(make_spec(tmp_path))
    reasons = lambda *k: set(row(ctx, *k)["pq_reasons"].split("|")) - {""}
    assert reasons("Onion", "Maharashtra", "A", "1997-1998") == set()                      # verified total: ok
    assert row(ctx, "Onion", "Maharashtra", "A", "1997-1998")["pq_class"] == "ok"
    assert reasons("Onion", "Maharashtra", "A", "1998-1999") == {"method_change"}          # R10
    assert reasons("Onion", "Maharashtra", "A", "1999-2000") == {"single_season_annual", "method_change"}
    assert reasons("Onion", "Maharashtra", "A", "2000-2001") >= {"missing_value"}           # R10: same class as 1999-00
    assert "method_change" not in reasons("Onion", "Maharashtra", "A", "2000-2001")
    assert reasons("Onion", "Maharashtra", "B", "1999-2000") == {"first_reported_after_state_start"}   # R8a
    assert row(ctx, "Onion", "Maharashtra", "B", "1999-2000")["pq_class"] == "annotated"
    assert "single_season_annual" in reasons("Wheat", "Punjab", "L", "1997-1998")         # R9 applies to Wheat
    # R8a is per crop and state: W1 Onion and Potato each start in their own first year
    assert "first_reported_after_state_start" not in reasons("Onion", "West Bengal", "W1", "1997-1998")
    # precedence: unusable > review > annotated > ok
    assert row(ctx, "Onion", "Maharashtra", "A", "2000-2001")["pq_class"] == "unusable"
    assert set(ctx["pq_class"]) <= set(pc.PQ_CLASSES)


def test_r10_compares_most_recent_earlier_row_across_gaps(tmp_path):
    raw = raw_rows()
    raw = raw[~((raw["district_name"] == "L") & (raw["year"] == "2019-2020"))]   # L: 2018-19 Rabi, then 2021-22 Rabi
    ctx, _ = context(make_spec(tmp_path, raw))
    assert "method_change" not in row(ctx, "Wheat", "Punjab", "L", "2021-2022")["pq_reasons"]
    ctx2, _ = context(make_spec(sub(tmp_path, "b")))
    assert "method_change" in row(ctx2, "Wheat", "Punjab", "L", "2019-2020")["pq_reasons"]   # Rabi -> Total
    assert "method_change" in row(ctx2, "Wheat", "Punjab", "L", "2021-2022")["pq_reasons"]   # Total -> Rabi


def test_r13_scope_is_exactly_option_1(tmp_path):
    ctx, _ = context(make_spec(tmp_path))
    hit = ctx["pq_reasons"].str.contains("provider_query_pending")
    got = set(map(tuple, ctx.loc[hit, ["crop", "apy_state", "apy_district", "source_apy_year"]].values))
    assert got == {("Potato", "West Bengal", "W1", "1997-1998"), ("Potato", "Gujarat", "G1", "1997-1998"),
                   ("Potato", "Gujarat", "G2", "1997-1998")}                      # G2 looks normal: still in scope
    assert (ctx.loc[hit, "pq_class"] == "review").all()
    assert not ctx.loc[hit, "pq_reasons"].str.contains("unit").any()             # no cause asserted


def test_duplicate_keys_and_unit_labels(tmp_path):
    ctx, annual = context(make_spec(tmp_path))
    with pytest.raises(pc.ProductionError, match="not unique"):
        pc.build_context(pd.concat([annual, annual.iloc[:1]]), pc.load(make_spec(tmp_path)["paths"], pc.BUILD_END)[1])
    annual, raw = pc.load(make_spec(tmp_path)["paths"], pc.BUILD_END)
    raw2 = pd.concat([raw, raw[raw["district"] == "B"].iloc[:1]], ignore_index=True)
    raw2.loc[raw2["district"] == "L", "area_unit"] = "Acre"
    ctx2 = pc.build_context(annual, raw2)
    b = row(ctx2, "Onion", "Maharashtra", "B", "1999-2000")
    assert b["pq_class"] == "unusable" and "duplicate_conflict" in b["pq_reasons"]
    assert (ctx2.loc[ctx2["apy_district"] == "L", "pq_reasons"].str.contains("unit_label")).all()
    assert not ctx["pq_reasons"].str.contains("unit_label|duplicate_conflict").any()


def test_blocked_rules_inactive_and_r4_diagnostic_only(tmp_path):
    prov = pc.provenance()
    blocked = prov[prov["status"] == "blocked"]
    assert set(blocked["code"]) == {"R4-flag", "R5", "R6", "R7", "R8b"} and not blocked["active"].any()
    ctx, annual = context(make_spec(tmp_path))
    names = set("|".join(ctx["pq_reasons"]).split("|")) - {""}
    assert names <= set(prov.loc[prov["active"], "name"]) and "yield_inconsistent" not in names
    r4 = pc.r4_diagnostic(annual).set_index("crop")
    onion = annual[(annual["crop"] == "Onion") & (annual["area_ha"] > 0) & (annual["production_tonnes"] > 0)
                   & (annual["apy_year"] <= pc.DESIGN_END)]
    assert r4.loc["Onion", "rows_computable"] == len(onion)
    assert r4.loc["Onion", "max_abs_rel_diff"] == pytest.approx(0.0, abs=1e-12)
    assert r4.loc["Wheat", "rows_computable"] == 2                 # 2019-20+ rows never enter the diagnostic


# ---------------------------------------------------------------- freeze, build, manifest, determinism
def test_freeze_gates_the_reserved_build(tmp_path):
    spec = make_spec(tmp_path)
    with pytest.raises(pc.ProductionError, match="no PQ-1 freeze"):
        pc.build_full(spec)
    proposed = make_spec(sub(tmp_path, "p"),
                         decision=ACCEPTED.replace("D-48 — [ACCEPTED", "D-48 — [PROPOSED"))
    with pytest.raises(pc.ProductionError, match="ACCEPTED"):
        pc.freeze(proposed)
    pc.freeze(spec)
    with pytest.raises(pc.ProductionError, match="once"):
        pc.freeze(spec)
    spec["code_files"][0].write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(pc.ProductionError, match="freeze mismatch"):
        pc.build_full(spec)


def test_build_outputs_manifest_and_determinism(tmp_path):
    spec = make_spec(tmp_path)
    pc.freeze(spec)
    out = spec["out_dir"]
    man = pc.build_full(spec)
    first = {p.name: p.read_bytes() for p in [out / "production_context_v1.csv", out / "pq1_provenance.csv",
                                              out / "output_manifest.csv"]}
    pc.build_full(spec)
    assert first == {n: (out / n).read_bytes() for n in first}                       # byte-for-byte rerun
    m = man.set_index(["item", "name"])["value"]
    assert f"file_sha256={file_sha256(out / 'production_context_v1.csv')}" in m[("output", "production_context_v1.csv")]
    assert m[("meta", "freeze_manifest_sha256")] == file_sha256(out / "pq1_freeze_manifest.csv")
    assert "policy assumption" in m[("meta", "caveat")]
    ctx = pd.read_csv(out / "production_context_v1.csv")
    assert list(ctx.columns) == pc.CONTRACT_COLUMNS and "2022-2023" not in set(ctx["source_apy_year"])
    assert 999_999.0 not in set(ctx["production_tonnes"])
    detail = pd.read_csv(out / "build_log.csv")["detail"].iloc[-1]
    assert re.fullmatch(r"reserved rows by pq_class \(counts only\): (\w+=\d+; )+total rows=\d+; "
                        r"max source year=2021-2022", detail)


def test_design_stage_writes_design_window_only(tmp_path):
    spec = make_spec(tmp_path)
    summary = pc.run_design(spec)
    assert summary["rows"].sum() == len(pc.load(spec["paths"], pc.DESIGN_END)[0])
    assert not (spec["out_dir"] / "production_context_v1.csv").exists()


def test_audit_cutoff_reproducible_and_verified_first(tmp_path):
    spec = make_spec(tmp_path)
    au.run_audit(spec)
    out = spec["out_dir"] / "audit"
    first = {p.name: p.read_bytes() for p in sorted(out.glob("*.csv"))}
    au.run_audit(spec)
    assert first == {p.name: p.read_bytes() for p in sorted(out.glob("*.csv"))}
    for name, data in first.items():
        assert not re.search(rb"2019-2020|2020-2021|2021-2022|2022-2023|999999", data), name
    assert pd.read_csv(out / "yield_consistency.csv").columns.tolist() == ["crop", "rows_computable", "max_abs_rel_diff"]
    spec2 = make_spec(sub(tmp_path, "c"))
    spec2["records"]["annual"]["file_sha256"] = "0" * 64
    with pytest.raises(pc.ProductionError, match="mismatch"):
        au.run_audit(spec2)
    assert not (spec2["out_dir"] / "audit").exists()                                # nothing written


# ---------------------------------------------------------------- real-file guards (hashes and the log only)
def test_real_inputs_match_recorded_fingerprints():
    rep = pc.verify_inputs(pc.default_spec()["paths"], pc.recorded_fingerprints(), ("crosswalk",))
    s = rep.set_index(["input", "check"])["status"]
    assert s[("crosswalk", "content_sha256")] == "match_after_alias_basis_canonicalisation"
    assert s.drop(("crosswalk", "content_sha256")).eq("match").all()


def test_real_decision_log_accepts_d46_to_d48_only():
    text = pc.DECISION_LOG.read_text(encoding="utf-8")
    assert pc.decisions_accepted()
    assert not re.search(r"^### D-49 — \[ACCEPTED", text, re.M)


def test_phase10_notebook_is_read_only_and_shows_reserved_years_as_counts_only():
    import json
    from Code.tests.test_notebooks import FORBIDDEN
    nb = json.loads(pc.Path("Notebooks/Phase_10_Production_Context.ipynb").read_text(encoding="utf-8"))
    code = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert nb["metadata"]["language_info"]["version"].startswith("3.13") and all(c.get("execution_count") for c in code)
    assert not any(o.get("output_type") == "error" for c in code for o in c.get("outputs", []))
    src = "\n".join("".join(c["source"]) for c in code)
    assert "PROJECT_ROOT" in src and "C:/" not in src
    assert not [f for f in FORBIDDEN + ["build_full(", "run_design(", "write_csv("] if f in src.replace("verify_freeze(", "")]
    assert "BUILD_END" not in src and "read_csv(OUT / \"production_context_v1.csv\"" not in src   # design rows only
    for c in code:
        out = "".join("".join(o.get("text", "")) + "".join(o.get("data", {}).get("text/plain", "")) for o in c.get("outputs", []))
        assert not re.search(r"[A-Za-z]:[\/]|Users|AppData", out)
        if re.search(r"20(19|20|21)-20(20|21|22)", out):                  # reserved labels: constants or counts only
            assert "reserved rows in the product" in out or "design window: source years" in out
