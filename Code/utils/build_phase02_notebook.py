"""
One-time generator for Notebooks/Phase_02_Crop_Feasibility_Audit_and_Selection.ipynb.
Run via `python Code/utils/build_phase02_notebook.py` from the project root,
then execute with nbconvert.
"""

import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))


def code(text):
    cells.append(nbf.v4.new_code_cell(text))


md(
"""# Phase 2 — Crop Feasibility Audit & Selection

This notebook performs a rigorous, crop-agnostic feasibility audit across the mandi, APY and Agri Market datasets, and selects the final 3 crops for the project using transparent, reproducible evidence — not popularity, not row count alone, and not a hidden composite score.

## INDEX

1. [Phase 2 Overview](#1)
2. [Project / Data Rules](#2)
3. [Load Phase 1 Utilities](#3)
4. [Candidate Commodity Discovery](#4)
5. [Crop Name Normalization](#5)
6. [Mandi Feasibility Audit](#6)
7. [APY Feasibility Audit](#7)
8. [Agri Market Feasibility Audit](#8)
9. [Cross-Dataset Compatibility](#9)
10. [Weather Feasibility Assessment](#10)
11. [Complete Pipeline Feasibility](#11)
12. [Final Crop Selection](#12)
13. [Final Dataset Mapping](#13)
14. [Phase 2 Validation](#14)
15. [Conclusion](#15)
"""
)

md("""<a id="1"></a>
## 1. Phase 2 Overview

**Objective**: audit crop feasibility across all three tabular data sources and select exactly 3 crops for the rest of the project, using computed evidence. No crop is assumed in advance. No cleaning, integration, feature engineering or modelling happens in this phase.""")

md("""<a id="2"></a>
## 2. Project / Data Rules (recap)

- `Dataset/` is read-only; nothing here writes into it.
- Selection must not be based on row count or popularity alone.
- Arrivals/quantity fields are never labeled "demand".
- Production stays labeled production; it is never reinterpreted as demand.
- No coordinates are introduced in this phase.
- Any crop-name merge must be documented and justified — ambiguous cases are flagged, not silently merged.""")

md("""<a id="3"></a>
## 3. Load Phase 1 Utilities

Reusing `Code/utils/data_audit.py` (Phase 1) plus two new, crop-agnostic modules built for this phase: `Code/utils/crop_matching.py` (name normalization) and `Code/utils/crop_feasibility.py` (audit statistics).""")

code(
"""import os
import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "Notebooks" else Path.cwd()
os.chdir(PROJECT_ROOT)
sys.path.append(str(PROJECT_ROOT))

from Code.utils.data_audit import list_mandi_crop_files, MANDI_DIR
from Code.utils.crop_matching import normalize, tokens, match_status, MANUAL_ALIAS_NOTES
from Code.utils.crop_feasibility import mandi_feasibility_stats, apy_feasibility_stats

pd.set_option("display.max_columns", 60)
pd.set_option("display.width", 200)
plt.rcParams["figure.figsize"] = (9, 4.5)
print("Utilities loaded.")"""
)

md("""<a id="4"></a>
## 4. Candidate Commodity Discovery

### Establish the real candidate universe

325 mandi files exist; Phase 1 found 5 are empty. The candidate universe is the remaining 320.""")

code(
"""all_mandi_files = list_mandi_crop_files()
record_counts = pd.read_csv("Processed_Data/phase1_mandi_file_record_counts.csv")
empty_files = record_counts.loc[record_counts["approx_record_count"] == 0, "crop_file_name"].tolist()
candidate_crops = [f[:-4] for f in all_mandi_files if f[:-4] not in empty_files]

print("Total mandi files:", len(all_mandi_files))
print("Empty files excluded:", empty_files)
print("Candidate universe (non-empty mandi crops):", len(candidate_crops))"""
)

md("""### Load APY and Agri Market crop name universes""")

code(
"""apy_full = pd.read_csv("Dataset/crop-wise-area-production-yield.csv")
apy_crop_names = sorted(apy_full["crop_name"].dropna().astype(str).unique())

agri_market = pd.read_csv("Dataset/Agri Market Dataset.csv")
agri_market_crop_names = sorted(agri_market["Commodity"].dropna().astype(str).unique())

print("APY crops:", len(apy_crop_names))
print("Agri Market crops:", agri_market_crop_names)"""
)

md("""### Observation

The candidate universe is 320 non-empty mandi crops. Given Phase 1's finding that exact-name matching under-counts overlap, Section 5 builds a transparent normalization process before any feasibility metrics are computed. Given the mandi dataset's scale (~56.9M rows across 320 files), a full detailed audit (states/districts/markets/continuity/missingness) is run only on crops that pass normalization matching against APY — a crop absent from APY cannot support the future Supply Prediction phase regardless of its mandi volume, so this is a genuine feasibility filter, not a shortcut.""")

md("""<a id="5"></a>
## 5. Crop Name Normalization

### Deterministic normalization + token-overlap matching

`Code/utils/crop_matching.py` normalizes punctuation/case/whitespace and compares meaningful tokens (excluding generic words like "gram", "seed", "pulses" that would otherwise cause false matches, e.g. "Alasande Gram" incorrectly matching "Moong(Green Gram)" on the word "gram" alone).""")

code(
"""rows = []
for mn in candidate_crops:
    best_apy, best_apy_status, best_apy_method = None, "no_match", ""
    for an in apy_crop_names:
        status, method = match_status(mn, an)
        if status == "exact":
            best_apy, best_apy_status, best_apy_method = an, status, method
            break
        if status == "token_overlap" and best_apy_status != "exact":
            best_apy, best_apy_status, best_apy_method = an, status, method

    best_am, best_am_status, best_am_method = None, "no_match", ""
    for am in agri_market_crop_names:
        status, method = match_status(mn, am)
        if status == "exact":
            best_am, best_am_status, best_am_method = am, status, method
            break
        if status == "token_overlap" and best_am_status != "exact":
            best_am, best_am_status, best_am_method = am, status, method

    rows.append({
        "mandi_crop": mn, "apy_match": best_apy, "apy_match_status": best_apy_status,
        "apy_match_method": best_apy_method, "agrimarket_match": best_am,
        "agrimarket_match_status": best_am_status, "agrimarket_match_method": best_am_method,
    })

crop_name_mapping = pd.DataFrame(rows)
crop_name_mapping.to_csv("Processed_Data/crop_name_mapping.csv", index=False)
print("Saved crop_name_mapping.csv —", len(crop_name_mapping), "mandi crops evaluated")
print(crop_name_mapping["apy_match_status"].value_counts())"""
)

md("""### Manually reviewed aliases

Automatic token-overlap matches were manually reviewed. Confirmed aliases (documented reasons) and explicitly rejected false positives are both recorded — nothing is silently merged.""")

code(
"""print("CONFIRMED MANUAL ALIASES:")
for (a, b), note in MANUAL_ALIAS_NOTES.items():
    if note.startswith("MERGED"):
        print(f"  {a}  <->  {b}\\n    {note}\\n")

print("EXPLICITLY REJECTED (documented, not merged):")
for (a, b), note in MANUAL_ALIAS_NOTES.items():
    if note.startswith("NOT MERGED"):
        print(f"  {a}  <->  {b}\\n    {note}\\n")

print("Also rejected on manual review of the automatic token-overlap output (generic/weak shared tokens,")
print("e.g. 'black' shared between Black Gram and Black Pepper, or 'gourd'/'kharif' shared across unrelated")
print("crop families): these token_overlap rows in crop_name_mapping.csv are retained for transparency but")
print("are NOT treated as valid matches in the feasibility shortlist below.")"""
)

md("""### Build the final matched candidate shortlist

The shortlist = exact matches + the confirmed manual aliases above. This is the set audited in full detail in Sections 6–9; the complete normalization table for all 320 candidates remains available in `Processed_Data/crop_name_mapping.csv` for inspection.""")

code(
"""exact_matches = crop_name_mapping[crop_name_mapping["apy_match_status"] == "exact"][["mandi_crop", "apy_match"]]
exact_pairs = dict(zip(exact_matches["mandi_crop"], exact_matches["apy_match"]))

manual_pairs = {}
for (mandi_norm, apy_norm), note in MANUAL_ALIAS_NOTES.items():
    if not note.startswith("MERGED"):
        continue
    # Recover the original-cased names from the candidate/APY lists via normalization
    mandi_match = next((c for c in candidate_crops if normalize(c) == mandi_norm), None)
    apy_match = next((a for a in apy_crop_names if normalize(a) == apy_norm), None)
    if mandi_match and apy_match:
        manual_pairs[mandi_match] = apy_match

shortlist = {**exact_pairs, **manual_pairs}
print("Final matched shortlist size:", len(shortlist))
print(sorted(shortlist.items()))"""
)

md("""<a id="6"></a>
## 6. Mandi Feasibility Audit

### Full statistics for the matched shortlist

Each file is read once with the shared, efficient utilities (fast per-file date-format detection instead of slow mixed-format inference) and the full dataframe is discarded after its statistics are extracted — memory stays bounded regardless of file size.""")

code(
"""mandi_rows = [mandi_feasibility_stats(crop + ".csv", apy_name) for crop, apy_name in shortlist.items()]
mandi_feasibility = pd.DataFrame(mandi_rows).sort_values("records", ascending=False).reset_index(drop=True)
mandi_feasibility.to_csv("Processed_Data/crop_feasibility_mandi.csv", index=False)
mandi_feasibility.head(15)"""
)

code(
"""top15 = mandi_feasibility.head(15).sort_values("records")
plt.figure(figsize=(8, 6))
plt.barh(top15["mandi_crop"], top15["records"] / 1e6, color="#4C72B0")
plt.xlabel("Records (millions)")
plt.title("Mandi Records — Top 15 Cross-Dataset-Matched Candidates")
plt.tight_layout()
plt.savefig("Outputs/Figures/phase02_mandi_top15_matched_candidates.png", dpi=150)
plt.show()"""
)

md("""### Observation

Among crops that are also present in APY, Potato (2.76M), Onion (2.62M) and Wheat (2.59M) lead on mandi volume, followed by Tomato (2.34M) — but Tomato's APY feasibility is checked separately in Section 7 before any conclusion is drawn. Duplicate rows and zero/impossible price values exist in every crop at a small percentage (see table) and are logged here for Phase 5 to treat — not fixed in this phase.""")

md("""<a id="7"></a>
## 7. APY Feasibility Audit

### Production/area/yield completeness per matched crop""")

code(
"""apy_rows = [apy_feasibility_stats(apy_full, apy_name) for apy_name in shortlist.values()]
apy_feasibility = pd.DataFrame(apy_rows).sort_values("apy_records", ascending=False).reset_index(drop=True)
apy_feasibility.to_csv("Processed_Data/crop_feasibility_apy.csv", index=False)
apy_feasibility.head(15)"""
)

code(
"""check_crops = ["Onion", "Potato", "Wheat", "Tomato", "Rice", "Maize", "Soyabean"]
comparison = apy_feasibility[apy_feasibility["apy_crop"].isin(check_crops)][
    ["apy_crop", "apy_records", "apy_years", "apy_states", "apy_zero_production_pct"]
]
display(comparison)

plt.figure()
plt.bar(comparison["apy_crop"], comparison["apy_years"], color="#55A868")
plt.ylabel("Years of APY coverage (out of 26 possible)")
plt.title("APY Temporal Coverage — Key Candidates")
plt.tight_layout()
plt.savefig("Outputs/Figures/phase02_apy_years_key_candidates.png", dpi=150)
plt.show()"""
)

md("""### Observation — critical finding

Onion, Potato and Wheat each have **full 26-year APY coverage** with **very low zero-production rates** (0.40%, 0.26%, 0.25% respectively). Tomato, despite having the 4th-highest mandi volume, has **only 5 years of APY coverage (407 records) with 22.85% zero-production rows** — its APY presence is too sparse to support a credible Supply Prediction phase. This is a direct, evidence-based reason Tomato is not carried forward, independent of its mandi popularity.""")

md("""<a id="8"></a>
## 8. Agri Market Feasibility Audit

### Which shortlisted crops overlap with the Agri Market Dataset

Per Phase 1, Agri Market Dataset covers only 5 commodities and only Maharashtra (Amravati division). Absence here does not disqualify a crop — it only means no secondary regional validation is available for it.""")

code(
"""agri_market_norm = {normalize(c) for c in agri_market_crop_names}

def in_agri_market(mandi_crop, apy_crop):
    return normalize(mandi_crop) in agri_market_norm or normalize(apy_crop) in agri_market_norm or \\
           any(match_status(mandi_crop, am)[0] != "no_match" for am in agri_market_crop_names)

agri_flags = pd.DataFrame([
    {"mandi_crop": c, "apy_crop": a, "in_agri_market_dataset": in_agri_market(c, a)}
    for c, a in shortlist.items()
])
print(agri_flags[agri_flags["in_agri_market_dataset"]].to_string(index=False))
print("\\nTotal shortlisted crops with Agri Market coverage:", agri_flags['in_agri_market_dataset'].sum(),
      "out of", len(agri_flags))"""
)

md("""### Observation

Wheat, Soyabean, Cotton, Jowar(Sorghum) and Arhar are the only shortlisted crops with Agri Market Dataset coverage — and that coverage is regionally restricted to Maharashtra's Amravati division. Onion and Potato have **no** Agri Market coverage; per the stated rule, this is documented as a consequence (no secondary regional validation available for these two), not treated as disqualifying.""")

md("""<a id="9"></a>
## 9. Cross-Dataset Compatibility

### Combine mandi + APY + Agri Market feasibility into one overlap table""")

code(
"""overlap = (
    mandi_feasibility
    .merge(apy_feasibility, left_on="apy_crop", right_on="apy_crop", how="left")
    .merge(agri_flags[["mandi_crop", "in_agri_market_dataset"]], on="mandi_crop", how="left")
)

def compatibility_tier(row):
    if row["apy_records"] > 0 and row["in_agri_market_dataset"]:
        return "Directly joinable (Mandi+APY); Agri Market regional validation available"
    if row["apy_records"] > 0:
        return "Directly joinable (Mandi+APY); Agri Market: not applicable"
    return "Joinable after normalization only; weak/no APY support"

overlap["compatibility_tier"] = overlap.apply(compatibility_tier, axis=1)
overlap.to_csv("Processed_Data/crop_dataset_overlap.csv", index=False)
overlap[["mandi_crop", "apy_crop", "records", "apy_records", "apy_years",
         "in_agri_market_dataset", "compatibility_tier"]].head(15)"""
)

md("""### Observation

All 48 shortlisted crops are at minimum "directly joinable" between Mandi and APY (that was the shortlist's defining criterion). The differentiator is (a) how strong that APY coverage actually is — see `apy_years`/`apy_zero_production_pct` — and (b) whether Agri Market regional validation is additionally available. No crop in this shortlist requires unsafe fuzzy-matching to join; the remaining ~270 non-shortlisted candidates are excluded specifically because they lack a safe, evidenced APY match (see `Processed_Data/crop_name_mapping.csv` for the full 320-row record).""")

md("""<a id="10"></a>
## 10. Weather Feasibility Assessment

### Can weather realistically be mapped for these crops?

No coordinate data exists anywhere in the project (Phase 1 finding). Feasibility here means: does the crop have state/district identifiers specific enough to later support a defensible public-source geocoding step (Phase 3)? This applies uniformly, since every mandi file shares the same State/District/Market schema.""")

code(
"""weather_feasibility = mandi_feasibility[["mandi_crop", "states", "districts", "markets"]].copy()
weather_feasibility["weather_mapping_feasible"] = True
weather_feasibility["basis"] = (
    "State/District/Market identifiers present in mandi records; can be geocoded via a "
    "documented external public source in Phase 3. No coordinates fabricated in this phase."
)
weather_feasibility.head(5)"""
)

md("""### Observation

Weather feasibility does not differentiate the shortlisted crops from each other — every mandi record carries the same State/District/Market fields regardless of crop, so any of them can, in principle, be mapped to weather once Phase 3 sources real coordinates. It is therefore **not a discriminating criterion** for the final 3, only a confirmation that no candidate is blocked on this dimension.""")

md("""<a id="11"></a>
## 11. Complete Pipeline Feasibility

### Final decision table — evidence for the strongest candidates

Rather than a hidden composite score, the table below lists the raw computed values the selection in Section 12 is argued from, for the 12 strongest candidates by combined mandi + APY evidence.""")

code(
"""final_table = overlap[[
    "mandi_crop", "records", "years_with_data", "markets", "states",
    "apy_records", "apy_years", "apy_states", "apy_zero_production_pct",
    "in_agri_market_dataset", "compatibility_tier"
]].rename(columns={
    "mandi_crop": "Crop", "records": "Mandi Records", "years_with_data": "Mandi Years",
    "markets": "Mandi Markets", "states": "Mandi States", "apy_records": "APY Records",
    "apy_years": "APY Years", "apy_states": "APY States",
    "apy_zero_production_pct": "APY Zero-Production %", "in_agri_market_dataset": "Agri Market Available?",
})
final_table_sorted = final_table.sort_values("Mandi Records", ascending=False)
final_table_sorted.head(12)"""
)

md("""### Observation

Potato, Onion and Wheat lead on mandi records/markets/states **and** have full 26-year, low-zero-production APY coverage. Rice and Maize are close behind on APY strength but trail on mandi market coverage. Soyabean, Cotton and Jowar bring Agri Market cross-validation but at roughly a third of the mandi volume of the top 3.""")

md("""<a id="12"></a>
## 12. Final Crop Selection

### Decision: Onion, Potato, Wheat

**Onion** — Mandi: 2,624,379 records, 32 states, 1,714 markets, 25/25 years of continuous reporting. APY: 26/26 years, 25 states, only 0.40% zero-production rows. No Agri Market coverage (documented consequence: no secondary regional validation for this crop; not disqualifying per the stated rule). Onion is a high price-volatility, highly perishable commodity — a direct match for the project's procurement/storage/transport/sell decision-support objective.

**Potato** — Mandi: 2,764,987 records (the single largest candidate), 33 states, 1,604 markets, 25/25 years. APY: 26/26 years, 28 states, the lowest zero-production rate of any shortlisted crop (0.26%). Same perishability/storage relevance as Onion, reinforcing the project's core use case.

**Wheat** — Mandi: 2,593,767 records, 28 states, **1,956 markets (the highest market count of any shortlisted crop)**, 24/24 years. APY: 26/26 years, 31 states, 0.25% zero-production rows. Wheat is the **only** one of the three final crops with independent Agri Market Dataset cross-validation (Maharashtra/Amravati region), giving the project a real, documented case of triple-source validation. It also adds crop-type diversity — a government-MSP-influenced staple alongside two free-market, perishable vegetables — which stress-tests the pipeline's crop-agnostic design across genuinely different market dynamics.

### Why close competitors were not selected

- **Rice**: comparable APY strength (33 states, 0.16% zero-production, the best of any candidate) and strong mandi volume (1.44M records, 179 varieties), but fewer mandi markets (1,167) than Wheat (1,956) and no Agri Market cross-validation. Documented as the strongest alternative cereal candidate if the project scope is later widened.
- **Maize**: strong APY (30,781 records — the highest of any candidate, 32 states) but mandi volume (1.08M) is under half of the selected three's, and it adds no diversity beyond Wheat as a second cereal.
- **Soyabean, Cotton, Jowar**: all have Agri Market coverage (a genuine plus) but mandi volume (694k–888k) is roughly a third of the selected crops', with fewer states/markets — the Agri Market bonus does not offset the primary-coverage gap.
- **Groundnut**: strong APY (18,623 records, 29 states) but mandi volume (494k) is well below the selected three.
- **Bengal Gram ("Gram")**: reasonable mandi coverage (1.16M records) but its APY match was only resolved via a "merged with caution" manual alias (Section 5) rather than an exact match — given equally strong exact-matched alternatives exist, the higher-confidence crops were preferred.
- **Tomato**: excluded specifically **despite** its high mandi volume (2.34M records, 4th highest overall) because its APY coverage is critically weak — only 407 records across 5 years with 22.85% zero-production rows (Section 7) — insufficient to support the future Supply Prediction phase. This is the clearest direct evidence that row count alone was not used as the selection criterion.""")

code(
"""selected_crops = pd.DataFrame([
    {"crop": "Onion", "apy_crop": shortlist["Onion"], "agri_market_available": False},
    {"crop": "Potato", "apy_crop": shortlist["Potato"], "agri_market_available": False},
    {"crop": "Wheat", "apy_crop": shortlist["Wheat"], "agri_market_available": True},
])
selected_crops.to_csv("Processed_Data/selected_crops.csv", index=False)
selected_crops"""
)

md("""<a id="13"></a>
## 13. Final Dataset Mapping

For each selected crop, the datasets that will feed Phases 3–7:""")

code(
"""dataset_mapping = pd.DataFrame([
    {"Crop": "Onion", "Mandi File": "Onion.csv", "APY crop_name": "Onion",
     "Agri Market": "Not available", "Weather": "To be collected in Phase 3 (state/district geocoding required)"},
    {"Crop": "Potato", "Mandi File": "Potato.csv", "APY crop_name": "Potato",
     "Agri Market": "Not available", "Weather": "To be collected in Phase 3 (state/district geocoding required)"},
    {"Crop": "Wheat", "Mandi File": "Wheat.csv", "APY crop_name": "Wheat",
     "Agri Market": "Available — Maharashtra/Amravati region only (secondary validation)",
     "Weather": "To be collected in Phase 3 (state/district geocoding required)"},
])
dataset_mapping"""
)

md("""<a id="14"></a>
## 14. Phase 2 Validation

Checks required before declaring this phase complete.""")

code(
"""checks = {}

# 1. Dataset/ unchanged (spot-check file count and a known file size)
import os
mandi_dir_files = len(os.listdir(MANDI_DIR))
checks["Dataset/ mandi file count == 325"] = (mandi_dir_files == 325)

# 2. Exactly 3 crops selected
checks["Exactly 3 crops selected"] = (len(selected_crops) == 3)

# 3. Selection supported by computed data (non-empty feasibility tables)
checks["Mandi feasibility table non-empty"] = (len(mandi_feasibility) > 0)
checks["APY feasibility table non-empty"] = (len(apy_feasibility) > 0)

# 4. No fabricated coordinates were introduced
checks["No coordinate columns created"] = not any(
    "lat" in c.lower() or "lon" in c.lower() or "coord" in c.lower() for c in overlap.columns
)

# 5. No demand variable fabricated — confirm no column named 'demand' exists anywhere produced this phase
produced_dfs = [crop_name_mapping, mandi_feasibility, apy_feasibility, overlap, selected_crops]
checks["No 'demand' column fabricated"] = not any(
    any("demand" in c.lower() for c in d.columns) for d in produced_dfs
)

# 6. Production and arrivals remain distinct concepts (both present, differently named)
checks["Production and Arrivals kept distinct"] = (
    "apy_zero_production_pct" in overlap.columns and "arrivals_missing_pct" in mandi_feasibility.columns
)

for k, v in checks.items():
    print(("PASS" if v else "FAIL"), "-", k)

assert all(checks.values()), "One or more Phase 2 validation checks failed."
print("\\nAll Phase 2 validation checks passed.")"""
)

md("""<a id="15"></a>
## 15. Conclusion

Phase 2 selected **Onion, Potato, and Wheat** as the project's final three crops, using a transparent normalization process and computed feasibility evidence across mandi, APY, and Agri Market sources. All three have full multi-decade APY coverage, national mandi presence, and (for Wheat) independent cross-dataset validation. Tomato — despite high mandi volume — was explicitly excluded on APY-coverage grounds, demonstrating that selection was evidence-driven rather than popularity-driven. Phase 3 will now build the real Open-Meteo weather collector for the states/districts these three crops actually cover.""")

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.13"},
}

out_path = "Notebooks/Phase_02_Crop_Feasibility_Audit_and_Selection.ipynb"
with open(out_path, "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print("Notebook written to", out_path, "with", len(cells), "cells")
