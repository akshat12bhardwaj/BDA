"""
Phase 10 APY audit (hardened from the planning-session script; plan §16). Reproduces the design-window findings F1-F16.

  - every input is verified against its recorded fingerprint before any value is read (pipeline.verify_inputs);
  - rows after 2018-19 (DESIGN_END) are dropped immediately after loading, and the cut is asserted;
  - no reserved-year value or count is written: every table covers the design window only;
  - deterministic CSVs (sorted, LF) are written to Processed_Data/production_context/audit/ only;
  - no withdrawn threshold is used (the old 1% / 10% / 0.1x-median cuts are gone): only counts, maxima and quantiles.
Run from the project root: C:\\Python313\\python.exe -B -m Code.production.apy_audit
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from Code.integration.pipeline import APY_ANNUAL_KEY, APY_SEASON_KEY, APY_UNITS, file_sha256
from Code.production import pipeline as pc


def tables(annual: pd.DataFrame, raw: pd.DataFrame, season: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """All audit tables from design-window frames (raw is renamed to the Phase 4 season schema)."""
    by = lambda df, keys: df.groupby(keys).size().rename("rows").reset_index()
    units = by(raw, ["crop"] + list(APY_UNITS))
    c2n = raw.groupby(["state", "district_code"])["district"].nunique()
    n2c = raw.groupby(["state", "district"])["district_code"].nunique()
    keys = pd.DataFrame({"check": ["duplicated_season_key_rows", "id_unique", "district_code_with_several_names",
                                   "district_name_with_several_codes"],
                         "value": [int(raw.duplicated(APY_SEASON_KEY, keep=False).sum()), bool(raw["id"].is_unique),
                                   int((c2n > 1).sum()), int((n2c > 1).sum())]})
    ok = (raw["area_ha"] > 0) & (raw["production_tonnes"] > 0) & raw["yield_t_per_ha"].notna()
    r = raw[ok]                                   # filter the frame on itself (the old script's reindex warning)
    calc = r["production_tonnes"] / r["area_ha"]
    rel = ((r["yield_t_per_ha"] - calc).abs() / calc).groupby(r["crop"])
    consistency = pd.DataFrame({"rows_computable": rel.size(), "max_abs_rel_diff": rel.max()}).reset_index()
    missing = pd.DataFrame([{"crop": c, "column": col, "missing": int(g[col].isna().sum()), "zero": int((g[col] == 0).sum())}
                            for c, g in raw.groupby("crop") for col in ["area_ha", "production_tonnes", "yield_t_per_ha"]])
    zero_prod = raw.loc[raw["production_tonnes"] == 0, ["id"] + APY_SEASON_KEY + ["area_ha", "production_tonnes",
                                                                                  "yield_t_per_ha"]]
    state_sums = raw[raw["season"] != "Total"].groupby(["crop", "state", "apy_year"])[["area_ha", "production_tonnes"]] \
        .sum(min_count=1).reset_index()
    quant = raw.groupby("crop")["yield_t_per_ha"].quantile([0.5, 0.99, 0.999]).rename("yield_t_per_ha") \
        .rename_axis(["crop", "quantile"]).reset_index()
    a = annual.assign(annual_comparability=pc.comparability(annual))
    methods = by(a, ["crop", "annual_method", "annual_comparability", "seasons_reported"])
    nmeth = a.groupby(["crop", "state", "district"])["annual_comparability"].nunique()
    changes = pd.DataFrame({"districts": nmeth.groupby(level=0).size(),
                            "districts_with_class_change": (nmeth > 1).groupby(level=0).sum()}).reset_index()
    ambiguous = a.loc[a["annual_method"] == pc.AMBIGUOUS, APY_ANNUAL_KEY + ["seasons_reported"]]
    tot = season[season["season"] == "Total"].set_index(APY_ANNUAL_KEY)["production_tonnes"]
    oth = season[season["season"] != "Total"].groupby(APY_ANNUAL_KEY)["production_tonnes"].sum(min_count=1)
    j = pd.concat([tot.rename("total"), oth.rename("sum_other")], axis=1, join="inner").dropna()
    j = j[j["total"] > 0]
    tdiff = ((j["total"] - j["sum_other"]).abs() / j["total"]).groupby(level="crop")
    total_check = pd.DataFrame({"groups": tdiff.size(), "max_abs_rel_diff": tdiff.max()}).reset_index()
    per_year = raw.groupby("apy_year")["district"].nunique().rename("districts").reset_index()
    hist = a.dropna(subset=["production_tonnes"]).groupby(["crop", "state", "district"])["apy_year"].nunique()
    history = hist.groupby(level=0).agg(["median", "min", "max"]).rename_axis("crop").reset_index()
    return {"units.csv": units, "key_checks.csv": keys, "yield_consistency.csv": consistency,
            "missing_zero.csv": missing, "zero_production_rows.csv": zero_prod, "state_year_sums.csv": state_sums,
            "yield_quantiles.csv": quant, "annual_methods.csv": methods, "comparability_changes.csv": changes,
            "ambiguous_rows.csv": ambiguous, "total_vs_seasons.csv": total_check,
            "districts_per_year.csv": per_year, "history_length.csv": history}


def run_audit(spec: dict | None = None) -> pd.DataFrame:
    spec = spec or pc.default_spec()
    report = pc.verify_inputs(spec["paths"], spec["records"], spec["git_tracked"])   # before any value is read
    annual, raw = pc.load(spec["paths"], pc.DESIGN_END)
    season = pc.within(pd.read_csv(spec["paths"]["season"]), "apy_year", pc.DESIGN_END)
    for df, col in [(annual, "apy_year"), (raw, "apy_year"), (season, "apy_year")]:
        assert pc.start_year(df[col]).max() <= int(pc.DESIGN_END[:4])
    out = Path(spec["out_dir"]) / "audit"
    rows = []
    for name, df in sorted(tables(annual, raw, season).items()):
        df = df.sort_values(list(df.columns[:min(5, df.shape[1])])).reset_index(drop=True)
        rows.append({"file": name, "rows": len(df), "file_sha256": pc.write_csv(df, out / name)})
    rows += [{"file": f"input {r.input}:{r.check}", "rows": "", "file_sha256": f"{r.status}; recorded={r.recorded}"}
             for r in report.itertuples()]
    man = pd.DataFrame(rows)
    pc.write_csv(man.assign(design_end=pc.DESIGN_END), out / "audit_manifest.csv")
    if file_sha256(spec["paths"]["raw"]) != spec["records"]["raw"]["file_sha256"]:
        raise pc.ProductionError("the raw APY file changed during the audit")
    return man


if __name__ == "__main__":
    print(run_audit().to_string())
