"""
Generator for Notebooks/Phase_10_Production_Context.ipynb (read-only walkthrough of Phase 10 v1).
Run `C:\\Python313\\python.exe Code/utils/build_phase10_notebook.py` from the project root, then execute it with
`C:\\Python313\\python.exe Code/utils/run_notebook.py Notebooks/Phase_10_Production_Context.ipynb`.
All logic lives in the tested module Code/production/pipeline.py. The notebook verifies and explains the frozen outputs:
it writes nothing, freezes nothing and never reads reserved-year values (only their counts from the output manifest).
"""

import nbformat as nbf

cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))


def code(text):
    cells.append(nbf.v4.new_code_cell(text))


md("""# Phase 10 — District Production Context (v1)

A **descriptive**, leakage-safe district production context from APY for Onion, Potato and Wheat: contract `phase10-production-context-v1` with the PQ-1 v1 quality flags. **No production-forecasting model** is built (D-46). The phase is still named "Supply Prediction" in the roadmap, because the renaming decision D-49 is not accepted.

**This notebook is read-only.**
- It verifies the frozen outputs in `Processed_Data/production_context/` and explains them. It does not rebuild them, freeze anything or write any file.
- Rows are shown only for the **design window** (source years ≤ 2018-19), rebuilt in memory with the frozen code.
- The reserved source years 2019-20 … 2021-22 appear **only as counts** taken from the output manifest. Their values are never read or displayed here.

## INDEX
1. Objective and accepted decisions
2. Data contract and provenance
3. Input and output integrity
4. Design-window rows and quality classes
5. Annual comparability and class changes
6. R4 diagnostic (diagnostic only)
7. R13: provider query pending (no cause asserted)
8. Reserved years: counts only
9. Limitations and downstream implications""")

md("## 1. Objective and accepted decisions")
code("""import os, sys, re
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "Notebooks" else Path.cwd()
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 120)

from Code.production import pipeline as pc
from Code.integration.pipeline import file_sha256, frame_fingerprint

OUT = pc.OUT_DIR
log_text = pc.DECISION_LOG.read_text(encoding="utf-8")
print("D-46, D-47, D-48 recorded as ACCEPTED:", pc.decisions_accepted())
for d in pc.DECISIONS + ["D-49"]:
    m = re.search(rf"^### {d} — .*$", log_text, re.M)
    print(m.group(0)[:150] if m else f"{d}: not in the decision log (proposal only, in the Phase 10 plan)")""")
md("""**Accepted on 2026-10-23** (full text in `Documentation/Decision_Log.md`):
- **D-46:** Option A (descriptive context, no forecasting model). The v1 contract keeps the four comparability classes separate, defers the 3-year trailing summary to v1.1, and authorises **no** procurement cap or marketable-surplus estimate.
- **D-47:** `apy_lag2_policy_v1`. APY year Y1–Y2 is usable from 1 July of Y2 + 1, so decision year t uses source year t − 2. This is a **policy assumption, not a verified publication schedule**, and it is not shown to be conservative for source years ≥ 2019-20. The design window is ≤ 2018-19; 2019-20 … 2021-22 are reserved; 2022-23 is excluded.
- **D-48:** PQ-1 v1 only flags, with no numerical threshold. It includes the R8a and R10 clarifications and R13 Option 1. Blocked rules stay inactive.

D-49 (phase names) is **not** accepted.""")

md("## 2. Data contract and provenance")
code("""print("contract:", pc.CONTRACT_VERSION, "| quality rules:", pc.PQ_VERSION, "| information rule:", pc.INFORMATION_RULE)
print("grain: one row per", pc.CONTEXT_KEY)
print("columns:", pc.CONTRACT_COLUMNS)
print("design window: source years <=", pc.DESIGN_END, "| reserved:", pc.RESERVED, "| excluded: 2022-2023 onward")
prov = pd.read_csv(OUT / "pq1_provenance.csv")
prov[["code", "name", "status", "effect", "active", "condition"]]""")
md("""**Provenance.**
- `apy_annual.csv` is the Phase 4 D-20 annual table. Values are used **as published**; the only change is that yield is set to null where production is null (the source encodes missing production with a yield of 0).
- The raw APY file supplies the unit labels (R11) and the season keys (R12).
- `apy_season.csv` is read by the audit, and the D-18 crosswalk is fingerprint-checked only.
- **`pq_class` precedence:** unusable (R1, R11, R12) > review (R3, R13) > annotated (R2, R8a, R9, R10) > ok.
- **Blocked:** the R4 row flag, R5, R6, R7 and R8b produce no flag. Activating one needs a new decision and a new PQ version.""")

md("## 3. Input and output integrity")
code("""spec = pc.default_spec()
inputs = pc.verify_inputs(spec["paths"], spec["records"], spec["git_tracked"])   # raises on any mismatch
inputs[["input", "path", "check", "status"]]""")
code("""# The crosswalk: Phase 4 hashed the in-memory frame, where alias_basis held ""; CSV readback turns "" into NaN.
# Only alias_basis is canonicalised (NaN -> ""), only for this comparison; the file and the record stay unchanged.
inputs.loc[inputs["check"] == "content_sha256", ["input", "recorded", "recomputed", "canonicalised", "status"]]""")
code("""pc.verify_freeze(spec)    # code, accepted decision texts, inputs, rule table and design rows still equal the freeze
man = pd.read_csv(OUT / "output_manifest.csv", dtype=str)
outs = man[man["item"] == "output"].copy()
outs["file_sha256_now"] = [file_sha256(OUT / n) for n in outs["name"]]
outs["recorded_matches"] = [f"file_sha256={h}" in v for h, v in zip(outs["file_sha256_now"], outs["value"])]
print("freeze verified; freeze manifest hash recorded in output manifest:",
      man.set_index("name").loc["freeze_manifest_sha256", "value"] == file_sha256(OUT / "pq1_freeze_manifest.csv"))
outs[["name", "recorded_matches"]]""")
md("""The freeze (`pq1_freeze_manifest.csv`) was written once, **before** the reserved years were built. The full build refuses to run unless the freeze verifies and the design-window rows come out identical, which shows there is no look-ahead. Rebuilding reproduces every output byte for byte.

**Reproduce from the project root:**
1. `C:\\Python313\\python.exe -B -m Code.production.apy_audit`
2. `… -m Code.production.pipeline design`
3. `… -m Code.production.pipeline build`

The freeze stage runs once only, and has already been run.""")

md("## 4. Design-window rows and quality classes")
code("""annual, raw = pc.load(spec["paths"], pc.DESIGN_END)          # cut to source years <= 2018-19 on load
design = pc.build_context(annual, raw)
frozen = pd.read_csv(OUT / "pq1_freeze_manifest.csv", dtype=str).set_index(["item", "name"])["value"]
assert design["source_apy_year"].max() == pc.DESIGN_END
print("design rows:", len(design), "| equal to the frozen design rows:",
      frame_fingerprint(design) == frozen[("design", "content_sha256")])
pd.crosstab(design["crop"], design["pq_class"], margins=True)""")
code("""reasons = design.assign(rule=design["pq_reasons"].str.split("|")).explode("rule")
reasons = reasons[reasons["rule"] != ""]
pd.crosstab(reasons["rule"], reasons["crop"], margins=True)""")
md("""**Reading the classes.**
- **Almost every Wheat row is `annotated`.** Wheat is reported as a single Rabi row, and R9 annotates single named seasons for all crops. The Wheat exception was withdrawn under D-48, so this is the accepted rule working as intended, not a data problem.
- **R8a annotates every row of a district that first appears after its state's first year** (computed per crop and state). The source re-labels history with present-day geography (F15), so this is **not** evidence of a boundary split; R8b, which would identify splits, is blocked.
- **`unusable` rows** have missing values or are ambiguous (R1). Their rows are kept, never deleted.""")

md("## 5. Annual comparability and class changes")
code("""pd.crosstab(design["crop"], design["annual_comparability"], margins=True)""")
code("""changes = pd.read_csv(OUT / "audit" / "comparability_changes.csv")
changes""")
md("""**Why the four classes stay separate.**
- `verified_total` is APY's Total row; it equals the sum of the seasons in 99.9% of groups (D-20).
- `whole_year_row` is a single "Whole Year" row; DES has not confirmed that it is the full-year total.
- `single_named_season` is one Rabi, Kharif or similar row, and may cover only part of the year.
- `ambiguous` means several seasons and no Total; its value is left missing (D-20).

Putting them in one column would compare unlike quantities, so a consumer must state which classes it accepts. R10 marks a change of class from the district's most recent earlier year. Within the design window, such changes occur in a large share of Onion and Potato districts.""")

md("## 6. R4 diagnostic (diagnostic only)")
code("""r4 = man[man["item"] == "r4_diagnostic"][["name", "value"]].rename(columns={"name": "crop"})
season_level = pd.read_csv(OUT / "audit" / "yield_consistency.csv")
display(r4)
season_level""")
md("""**R4 is diagnostic only.** It reports the number of rows where the check can be made (area > 0 and production > 0, non-null), and the largest relative difference between the published yield and production ÷ area. This covers the design window, at the annual grain (manifest) and the season grain (audit). **No row is flagged, nothing is excluded, and no tolerance is active.** The 1% cut-off of revision 1 was withdrawn.""")

md("## 7. R13: provider query pending (no cause asserted)")
code("""r13 = design[design["pq_reasons"].str.contains("provider_query_pending")]
print("R13 rows:", len(r13), r13.groupby("apy_state").size().to_dict())
r13[["crop", "apy_state", "apy_district", "source_apy_year", "area_ha", "production_tonnes", "yield_t_per_ha",
     "annual_comparability", "pq_class", "pq_reasons"]].head(10)""")
code("""sums = pd.read_csv(OUT / "audit" / "state_year_sums.csv")
sums[(sums["crop"] == "Potato") & sums["state"].isin(["West Bengal", "Gujarat"])
     & sums["apy_year"].isin(["1997-1998", "1998-1999"])]""")
md("""**R13 (D-48, Option 1)** covers **all** annual rows of West Bengal and Gujarat Potato for 1997-98: 18 + 19 rows.
- These rows are `review`. They are **not excluded** and their values are **unchanged**.
- **No cause is asserted.** In particular, this does not say the values are a unit error. The West Bengal district areas sum far above the 1998-99 total, and several Gujarat yields are very low, but only DES can explain them.
- The DES enquiry is drafted in the plan (§15) and **has not been sent**. R13 stays until an answer is recorded under a new decision.""")

md("## 8. Reserved years: counts only")
code("""cnt = man[man["item"] == "counts"].copy()
cnt[["crop", "source_apy_year", "pq_class"]] = cnt["name"].str.split("|", expand=True)
cnt["rows"] = cnt["value"].astype(int)
reserved = cnt[cnt["source_apy_year"].isin(pc.RESERVED)]
print("reserved rows in the product:", reserved["rows"].sum(), "| 2022-23 rows in the product:",
      int(cnt["source_apy_year"].eq("2022-2023").sum()))
reserved.pivot_table(index=["crop", "source_apy_year"], columns="pq_class", values="rows", aggfunc="sum", fill_value=0)""")
md("""These are **counts only**, from the output manifest. No reserved value was used to design or tune any rule, and none is displayed here. The values exist in `production_context_v1.csv`, to be read only by downstream protocols that are themselves approved. Any result that uses them must repeat the D-47 caveat on publication timing.""")

md("""## 9. Limitations and downstream implications

**Limitations**
- **The two-year lag is an assumption.** No district-level release history has been verified, and secondary metadata suggests that recent years were published late. The input is one December 2023 vintage, so earlier years carry revised values, not first-published ones.
- **Blocked rules:** R5 needs official geographic areas, R6 needs reference yields, R7 needs a robust reference, R8b needs LGD or gazette split history, and the R4 row flag needs a justified tolerance. Until then, implausible areas or yields are visible only through R13 and the audit.
- **Geography:** history is re-labelled with present-day names (for example, Telangana before 2014). Split districts are not reconciled, which is why the trailing summary is deferred to v1.1.
- **Coverage:** APY annual values exist for only part of the mandi district-years (Phase 4: roughly 47% Onion, 62% Potato, 94% Wheat).

**Downstream (Phase 11/12, not started)**
- **Allowed:** a slow, annual prior for ranking or shortlisting source districts, joined only through the D-18 crosswalk, with `pq_class` and `annual_comparability` as explicit filters and sensitivity splits.
- **Not allowed:** treating production as marketable surplus, weekly supply or market capacity; any production-based cap (D-46); guessed coordinates or fuzzy joins.
- **Phase 12 is still blocked** by missing inputs: transport and storage costs, capacities, fees and demand.""")

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"] = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                  "language_info": {"name": "python", "version": "3.13"}}
out_path = "Notebooks/Phase_10_Production_Context.ipynb"
with open(out_path, "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print("Notebook written to", out_path, "with", len(cells), "cells")
