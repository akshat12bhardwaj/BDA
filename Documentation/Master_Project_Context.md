# Master Project Context

**This is the single source of truth for project continuation.** Any future session (human or agent) resuming this project should read this file first, then `Future_Work_Roadmap.md`, `Data_Lineage.md`, `Processed_Data/features_audit/feature_registry.csv` (the feature catalogue; no `Feature_Catalogue.md` exists), `Decision_Log.md`, `Assumptions.md`, `EDA_Findings.md`, and `Phase_08_Modelling_Plan.md`.

Last updated: Phase 8 planning (2026-10-22). Phase 7 is complete; Phase 8 is planned but not implemented.

---

## 1. Project Objective

Build a data-driven agricultural trading decision-support system for Indian agricultural markets that ultimately (Phases 8–14, future work) forecasts price, market activity and supply, then uses Dijkstra routing and MILP optimization to recommend procurement, storage, transportation and selling decisions that maximize expected profit. The current semester milestone (Phases 1–7) delivers the complete, evidence-based data preparation and EDA foundation only.

## 2. Current Status

| Phase | Name | Status |
|---|---|---|
| 1 | Project & Data Understanding | **[COMPLETED]** |
| 2 | Crop Feasibility Audit & Selection | **[COMPLETED]** |
| 3 | Weather Collection (Open-Meteo) | **[COMPLETED]** (36/46 locations; 10 unresolved and documented, not fabricated) |
| 4 | Data Integration | **[COMPLETED]** (all validation checks + 16 tests pass; see Section 8d) |
| 5 | Data Cleaning | **[COMPLETED]** (29 notebook checks + 31 tests pass; see Section 8f) |
| 6 | Feature Engineering | **[COMPLETED]** (17 notebook checks + 45 tests pass; see Section 8h) |
| 7 | EDA | **[COMPLETED]** (17 notebook checks + 57 tests pass; see Section 8j) |
| 8 | Price Forecasting | **[IN PROGRESS — dataset builder, baselines, calendar benchmarks, Ridge/HGB validated on 2019–2020, bootstrap intervals vs persistence, one conservative HGB run; selection frozen (D-42); 2021–2022 test run once (§N): Onion h = 1 HGB −1.6% MAE vs persistence, all other cells persistence; 2023+ holdout unscored]** |
| 9 | Market Activity Modeling | **[MODEL SELECTED AND TESTED ONCE — D-45 accepted 2026-10-23 (conservative HGB, all 9 cells); frozen by hash; one-time 2021–2022 test: better than persistence in all 18 cell-years (`Phase_09_Arrivals_Plan.md` §16); 2023+ holdout unused]** |
| 10 | Supply Prediction | **[v1 IMPLEMENTED 2026-10-23 — descriptive district production context `phase10-production-context-v1` (D-46 – D-48); no forecasting model; PQ-1 v1 frozen by hash; reserved years built mechanically, counts only; phase name unchanged pending D-49; see §8l]** |
| 11 | Logistics / Dijkstra | [FUTURE] |
| 12 | MILP Optimization | [FUTURE] |
| 13 | Dynamic Feedback | [FUTURE] |
| 14 | Final End-to-End Evaluation | [FUTURE] |

**Course deliverables outside the phase numbering (implemented 2026-10-23).** This is **not** Phase 11: D-49 is not accepted, so the phase names and numbers are unchanged. The deliverables are:
- a PySpark / Spark SQL ETL over the raw mandi files, with Spark/pandas parity;
- a Spark RDD MapReduce-style demonstration;
- a read-only Streamlit dashboard;
- the final report and slides (§8m).

Hadoop/HDFS is **not implemented**; that is pending instructor guidance.

## 2b. Final Selected Crops (Phase 2 outcome)

**Onion, Potato, Wheat** — selected from a 320-crop candidate universe using computed mandi + APY + Agri Market feasibility evidence (not row count or popularity alone). Full methodology and evidence: `Documentation/Crop_Feasibility_Audit.md`. Tomato was explicitly considered and excluded (2.34M mandi records, but only 407 APY records across 5 years with 22.85% zero-production — insufficient for Supply Prediction). Result saved at `Processed_Data/selected_crops.csv`.

| Crop | Mandi file | APY crop_name | Agri Market |
|---|---|---|---|
| Onion | `Onion.csv` | `Onion` | Not available |
| Potato | `Potato.csv` | `Potato` | Not available |
| Wheat | `Wheat.csv` | `Wheat` | Available (Maharashtra/Amravati region only) |

## 2c. Opening and running the notebooks (Python 3.13)

This machine has two Pythons. A plain `jupyter lab` starts Anaconda's JupyterLab 4.2.5 with a Python 3.12 kernel (scikit-learn 1.5). The project uses `C:\Python313\python.exe` (scikit-learn 1.8).

- **Interactive:** `cd <project root>`, then `C:\Python313\python.exe -m jupyterlab`. Its `python3` kernel resolves to `C:\Python313\python.exe`. Open `Notebooks/BDA_Project_Demonstration.ipynb`.
- **Execute from a clean kernel:** `C:\Python313\python.exe Code\utils\run_notebook.py Notebooks\<name>.ipynb`.
- **Regenerate a notebook:** `C:\Python313\python.exe Code\utils\build_phase08_notebook.py`, `build_phase09_notebook.py`, `build_phase10_notebook.py` or `build_demo_notebook.py`.

## 3. Actual Folder Structure (verified in Phase 1, updated Phase 2)

```
BDA/
├── Dataset/                                          ← ORIGINAL, READ-ONLY (verified untouched)
│   ├── India Commodity Wise Mandi Dataset/           (325 CSVs, ~3.5 GB)
│   ├── Agri Market Dataset.csv
│   ├── Crop_Wise_Area_Production_Yield_codebook.xlsx
│   ├── crop-wise-area-production-yield.csv
│   └── final_data.csv
├── Code/
│   ├── inspect_agriculture.py                        (legacy, kept for reference)
│   ├── inspect_top.py                                (legacy, kept for reference)
│   ├── test_openmeteo.py                             (legacy, kept for reference)
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── data_audit.py                             (Phase 1, reusable, crop-agnostic)
│   │   ├── crop_matching.py                          (Phase 2, name normalization)
│   │   ├── crop_feasibility.py                       (Phase 2, feasibility statistics)
│   │   ├── build_phase01_notebook.py                 (notebook generator, reusable pattern)
│   │   ├── build_phase02_notebook.py                 (notebook generator, reusable pattern)
│   │   ├── build_phase03_notebook.py                 (notebook generator, reusable pattern)
│   │   ├── build_phase04_notebook.py                 (notebook generator, Phase 4)
│   │   ├── build_phase05_notebook.py                 (notebook generator, Phase 5)
│   │   ├── build_phase06_notebook.py                 (notebook generator, Phase 6)
│   │   └── build_phase07_notebook.py                 (notebook generator, Phase 7)
│   ├── modelling/                                    (Phase 8)
│   │   ├── dataset.py                                (leakage-safe weekly dataset builder: run_build(); fits no model)
│   │   ├── baselines.py                              (validation-only naive baselines: run_baselines())
│   │   ├── models.py                                 (calendar benchmarks, Ridge, HGB; validation only: run_models())
│   │   ├── uncertainty.py                            (paired series-cluster bootstrap vs persistence: run_uncertainty())
│   │   ├── final_evaluation.py                       (frozen D-42 selection, one-time 2021–2022 test: run_test_evaluation())
│   │   ├── forecast_output.py                        (forecast output contract phase8-forecast-v1; batch, not a live service)
│   │   ├── error_profile.py                          (validation-only empirical error profile phase8-error-profile-v1)
│   │   ├── arrivals.py                               (Phase 9: weekly arrivals dataset, validation baselines + bootstrap, phase9-arrivals-forecast-v1)
│   │   ├── arrivals_quality.py                       (Phase 9: read-only arrivals quality audit, AQ-1 screen)
│   │   ├── arrivals_aq1.py                           (Phase 9: AQ-1 v1 derived flag table, leakage-safe baseline variants)
│   │   ├── arrivals_models.py                        (Phase 9: learned-arrivals protocol D-44, approved; gate checks status + decision log)
│   │   └── arrivals_final.py                         (Phase 9: D-45 freeze manifest, run-once guard, one-time 2021–2022 test)
│   ├── production/                                   (Phase 10, v1)
│   │   ├── pipeline.py                               (phase10-production-context-v1 + PQ-1 v1: stages design / freeze / build)
│   │   └── apy_audit.py                              (hardened APY audit, design window ≤ 2018-19 only)
│   ├── bigdata/                                      (course deliverable, 2026-10-23; not a numbered phase)
│   │   ├── mandi_spark.py                            (PySpark ETL: header check, explicit schema, quality counts, Spark SQL Q1–Q3)
│   │   ├── parity.py                                 (Spark Q1 vs the Phase 4 pandas mandi_apy_district_year.csv)
│   │   └── mapreduce_demo.py                         (Spark RDD map/reduceByKey pattern + word count; not Hadoop)
│   ├── app/                                          (course deliverable: read-only Streamlit dashboard)
│   │   ├── data.py                                   (loaders that enforce the boundaries: no holdout, no reserved production values, no writes)
│   │   └── streamlit_app.py                          (six tabs)
│   ├── eda/                                          (Phase 7)
│   │   └── analysis.py                               (EDA summary computations: run_eda())
│   ├── features/                                     (Phase 6)
│   │   └── pipeline.py                               (reusable feature pipeline: run_features(), feature_registry())
│   ├── cleaning/                                     (Phase 5)
│   │   └── pipeline.py                               (reusable cleaning pipeline: run_cleaning(), rules R01–R14)
│   ├── integration/                                  (Phase 4)
│   │   ├── pipeline.py                               (reusable integration pipeline: run_pipeline())
│   │   └── district_aliases.csv                      (131 reviewed mandi→APY district aliases/exclusions)
│   ├── tests/                                        (pytest: Phase 4-7 suites, run `python -m pytest Code/tests`)
│   └── weather/
│       ├── __init__.py
│       ├── config.py                                 (non-secret config; documents no-key-needed decision)
│       ├── location_mapper.py                        (Open-Meteo Geocoding API wrapper)
│       ├── collector.py                              (Open-Meteo Archive API collector, caching + retries)
│       └── validator.py                              (weather dataset validation checks)
├── Notebooks/
│   ├── Phase_01_Project_and_Data_Understanding.ipynb (executed, 0 errors)
│   ├── Phase_02_Crop_Feasibility_Audit_and_Selection.ipynb (executed, 0 errors, all validation checks passed)
│   ├── Phase_03_Weather_Data_Collection.ipynb        (executed, 0 errors, all validation checks passed)
│   ├── Phase_04_Data_Integration.ipynb               (executed, 0 errors, all validation checks + 16 tests passed)
│   ├── Phase_05_Data_Cleaning.ipynb                  (executed, 0 errors, 29 checks + 31 tests passed)
│   ├── Phase_06_Feature_Engineering.ipynb            (executed, 0 errors, 17 checks + 45 tests passed)
│   ├── Phase_07_EDA.ipynb                            (executed, 0 errors, 17 checks + 57 tests passed)
│   ├── Phase_08_Price_Forecasting.ipynb              (Phase 8 walkthrough, built 2026-10-23; read-only over frozen artifacts; it was planned but never built before)
│   ├── Phase_09_Arrivals_Model_Experiments.ipynb     (Phase 9; run with Python 3.13 via Code/utils/run_phase09_notebook.py; D-44 approved)
│   ├── Phase_10_Production_Context.ipynb             (Phase 10 walkthrough; read-only; reserved years as counts only)
│   └── BDA_Project_Demonstration.ipynb               (teacher demonstration; read-only; links to the phase notebooks)
├── Processed_Data/
│   ├── phase1_mandi_file_record_counts.csv           (325-row cache: crop → approx record count)
│   ├── crop_name_mapping.csv                         (320 rows: normalization result per candidate)
│   ├── crop_feasibility_mandi.csv                    (48-crop shortlist mandi audit)
│   ├── crop_feasibility_apy.csv                      (48-crop shortlist APY audit)
│   ├── crop_dataset_overlap.csv                      (cross-dataset compatibility table)
│   ├── selected_crops.csv                            (final 3 crops)
│   ├── cleaned/mandi_cleaned_{onion,potato,wheat}.parquet   (Phase 5 outputs)
│   ├── features/features_{onion,potato,wheat}.parquet       (Phase 6 outputs)
│   ├── features_audit/                               (Phase 6 registry, statistics, validation report, fingerprints, manifest)
│   ├── eda/                                          (Phase 7: 15 summary tables + input fingerprints)
│   ├── modelling/phase08/                            (Phase 8 dataset manifests, sample counts, eligibility, provenance)
│   ├── production_context/                           (Phase 10: contract CSV, PQ-1 provenance/freeze, output manifest, audit/)
│   ├── bigdata/                                      (Spark ETL outputs, parity report, run manifest/log; course deliverable)
│   ├── cleaning_audit/                               (Phase 5 rule summary, decisions, review records, removed copies, manifests)
│   ├── integration/                                  (Phase 4 outputs — see Data_Lineage.md)
│   │   ├── mandi_integrated_{onion,potato,wheat}.parquet
│   │   ├── weather_daily_panel.parquet, weather_location_resolution.csv, geocoder_evidence_phase4.csv
│   │   ├── apy_season.csv, apy_annual.csv, mandi_apy_district_year.csv, district_crosswalk.csv
│   │   ├── agrimarket_wheat_crosscheck.csv
│   │   └── audit/                                    (merge log, coverage, unmatched keys, duplicates, fingerprints, manifest)
│   └── weather/
│       ├── raw/*.csv                                 (47 cached files: 36 from Phase 3 + 11 added in Phase 4; Punjab_Ferozpur.csv superseded)
│       ├── weather_location_mapping.csv               (46 rows: 36 mapped + 10 unresolved)
│       ├── weather_collection_manifest.csv            (per-location fetch status/cache metadata)
│       ├── weather_validation_report.csv              (per-location validation results)
│       └── weather_coverage_summary.csv               (per-crop coverage rollup)
├── Outputs/
│   └── Figures/
│       ├── phase01_top15_mandi_record_counts.png
│       ├── phase01_apy_records_per_year.png
│       ├── phase01_agrimarket_commodity_counts.png
│       ├── phase02_mandi_top15_matched_candidates.png
│       ├── phase02_apy_years_key_candidates.png
│       ├── phase03_coverage_by_crop.png
│       ├── phase03_sample_temperature_series.png
│       ├── phase04_weather_match_by_crop.png
│       ├── phase04_apy_district_match_by_crop.png
│       ├── phase04_top_unmatched_weather_districts.png
│       ├── phase04_apy_link_share_by_year.png
│       ├── phase05_*.png                              (4 cleaning charts)
│       ├── phase06_*.png                              (2 feature diagnostics)
│       └── phase07_*.png                              (6 EDA figures)
└── Documentation/
    ├── Master_Project_Context.md   (this file)
    ├── Data_Lineage.md
    ├── Decision_Log.md
    ├── Assumptions.md
    ├── Crop_Feasibility_Audit.md
    ├── Weather_Data_Collection.md
    ├── EDA_Findings.md              (Phase 7)
    ├── Modelling_Readiness_Report.md (Phase 7)
    ├── Phase_08_Modelling_Plan.md   (Phase 8 plan, results, close-out §O, holdout protocol §P)
    ├── Phase_09_Integration_Plan.md (proposal: forecast → decision-support contracts)
    ├── Forecast_Output_Contract.md  (phase8-forecast-v1 schema/rules + phase8-error-profile-v1)
    ├── Phase_09_Arrivals_Plan.md    (Phase 9 data audit, target/protocol, baseline results)
    ├── Arrivals_Forecast_Contract.md (phase9-arrivals-forecast-v1; provisional persistence)
    ├── Phase_09_Model_Protocol.md   (learned-arrivals protocol, APPROVED as D-44 with U2–U6; run instructions)
    ├── Phase_10_Production_Context_Plan.md (Phase 10 plan; D-46 – D-48 accepted; implementation record §17)
    ├── BigData_and_Dashboard_Spec.md (spec for the Spark component and dashboard)
    ├── Phase_11_Routing_Plan.md      (PLAN ONLY: routing / weather / road-condition audit and roadmap; nothing implemented)
    ├── Final/                        (report, slides, demo script, contribution matrix, setup, checklist, screenshots/)
    └── Future_Work_Roadmap.md
```

## 4. Dataset Inventory (verified by direct inspection, not assumed)

### 4.1 India Commodity Wise Mandi Dataset
- **Location**: `Dataset/India Commodity Wise Mandi Dataset/`
- **Contents**: 325 CSV files, one per commodity. **320 contain data; 5 are empty** (`Jaggery.csv`, `Ladies Finger.csv`, `Nargasi.csv`, `Saffron.csv`, `Seegu.csv` — header row only, 0 data rows).
- **Schema** (not perfectly uniform): `State Name, District Name, Market Name, Variety, Group, Arrivals (Tonnes), Min Price (Rs./Quintal), Max Price (Rs./Quintal), Modal Price (Rs./Quintal), Reported Date`. Some files (e.g. `Astera.csv`) use unit-free column names (`Arrivals`, `Min Price`, etc.) instead — see Decision Log for the normalization approach.
- **Scale**: ~56.9 million data rows across all 325 files combined (computed via cheap line counts, not full loads). Largest: Potato (2,764,987 rows, 229 MB), Onion (2,624,379 rows, 217 MB), Wheat (2,593,767 rows, 213 MB), Tomato (2,338,352 rows, 195 MB).
- **Date format**: mixed — at least two formats observed (`DD Mon YYYY` e.g. `09 Feb 2006`, and ISO `YYYY-MM-DD` e.g. `2005-03-24`), varying by file.
- **Units**: Arrivals in Tonnes; prices in Rs./Quintal.
- **Role**: primary price + arrivals (supply-side market-activity) source for Phases 2, 4–9, 11.
- **Full profiling deferred to Phase 2** (missingness, temporal continuity, per-crop states/districts/markets/varieties) — Phase 1 only established the candidate universe and record-count distribution, cached at `Processed_Data/phase1_mandi_file_record_counts.csv`.

### 4.2 crop-wise-area-production-yield.csv (APY dataset)
- **Location**: `Dataset/crop-wise-area-production-yield.csv`
- **Rows**: 455,359 | **Columns**: 16 — `id, year, state_name, state_code, district_name, district_code, crop_name, crop_code, crop_type, season, area, area_unit, production, production_unit, yield, yield_unit`
- **Coverage**: 26 crop-years (1997-98 → 2022-23), 115 distinct crops, district-level granularity, 34 states.
- **Units**: area = Hectares, production = Tonnes, yield = Tonnes/Hectare (confirmed via codebook).
- **Official source**: Directorate of Economics and Statistics, Ministry of Agriculture and Farmers Welfare, Government of India, via `data.desagri.gov.in`. Data last updated 14-12-2023 (per codebook metadata).
- **Role**: primary agricultural production/supply source for Phases 2, 4, 6, 7, 10.

### 4.3 Crop_Wise_Area_Production_Yield_codebook.xlsx
- Two sheets: `Codebook` (field name/description/type/unit for all 16 APY columns) and `Metadata Information` (source, granularity = District, frequency = Yearly, methodology, retrieval/update dates).
- Read-only reference; never modified. Used to resolve field/unit ambiguity when needed.

### 4.4 Agri Market Dataset.csv
- **Rows**: 39,060 | **Columns**: 11 — same conceptual schema as the mandi files but with an explicit `Commodity` column.
- **Coverage**: **only 5 commodities** (Soyabean, Arhar (Tur/Red Gram)(Whole), Wheat, Jowar(Sorghum), Cotton), **only 1 state (Maharashtra)**, **5 districts** (Amravati, Akola, Vashim, Wardha, Yavatmal — the Amravati division), **26 markets**, dated **2020-01-01 to 2024-12-05**.
- **Data-quality note**: `Arrivals (Tonnes)` is stored as text; 169 of 39,060 values are non-numeric in their raw form (comma formatting or similar) — must be coerced/cleaned before numeric use (Phase 5).
- **Terminology (critical)**: `Arrivals (Tonnes)` = quantity arriving at market — a **supply-side market-activity measure**, exactly as in the mandi dataset. **This is not consumer demand and must never be labeled as such.**
- **Role**: regional (Maharashtra/Amravati-only) validation/cross-check signal for whichever selected crops it happens to cover — **not** a required, national market-activity source. See `Assumptions.md` A-04.

### 4.5 final_data.csv
- **Rows**: 4,151 | **Columns**: 6 — `State, State_code, District, District_code, Market_code, Market`.
- **Contents**: a State → District → Market **reference/lookup table** with administrative codes. No prices, no production, no dates, no coordinates.
- **Role**: candidate aid for market-ID standardization during Phase 4 integration, if market-name spellings differ across mandi files. Does not itself contribute price/supply/weather information.

### 4.6 Open-Meteo Historical Weather API
- **Endpoint**: `https://archive-api.open-meteo.com/v1/archive`, no API key required for this usage.
- **Existing script** (`Code/test_openmeteo.py`) proves connectivity works for one hardcoded location (Ludhiana, Punjab) and a 7-day window, requesting `temperature_2m_mean/max/min`, `rain_sum`, `relative_humidity_2m_mean`, `wind_speed_10m_mean`, `et0_fao_evapotranspiration`, timezone `Asia/Kolkata`.
- **Not yet collected at scale.** Phase 3 will build the real batch/cached collector. See `Future_Work_Roadmap.md` and Decision Log D-05.

## 5. Existing Code Status (Phase 1 audit)

| File | Disposition | Notes |
|---|---|---|
| `Code/inspect_agriculture.py` | REFACTORED | Generic audit logic (missing-value table, duplicate check, describe-stats) generalized into `Code/utils/data_audit.py`. Original file retained unmodified; not yet deleted pending Phase 2 confirmation that nothing unique remains. |
| `Code/inspect_top.py` | REFACTORED | Hardcoded Tomato/Onion/Potato logic generalized into `list_mandi_crop_files()`, `load_mandi_file()`, `mandi_file_record_count()` in `Code/utils/data_audit.py`, which work for any of the 325 files. Original retained, not deleted. |
| `Code/test_openmeteo.py` | KEEP (reference) / REPLACE functionally in Phase 3 | Confirms API access pattern works; lacks caching, multi-location support, persistence, robust error handling — to be superseded by `Code/weather/collector.py` in Phase 3. |
| `Code/utils/data_audit.py` | Phase 1, extended Phase 2 | Reusable, crop-agnostic inspection helpers (column alias normalization, date parsing, cheap record counting, generic CSV profiling). Phase 2 added `parse_dates_fast()` — per-file format detection instead of slow universal mixed-format inference — after benchmarking showed `format="mixed"` across the full shortlist did not finish in a reasonable time; `parse_dates_fast` audited 48 candidate files (~2.8 GB) in ~60 seconds. |
| `Code/utils/crop_matching.py` | **NEW (Phase 2)** | Deterministic crop-name normalization + token-overlap matching, plus a documented manual-alias table (`MANUAL_ALIAS_NOTES`) for cases requiring domain judgment (e.g. Jowar/Sorghum merged; Rice/Paddy explicitly NOT merged). |
| `Code/utils/crop_feasibility.py` | **NEW (Phase 2)** | Reusable `mandi_feasibility_stats()` / `apy_feasibility_stats()` functions — crop-agnostic, no hardcoded crop names, no scoring logic (scoring/selection judgment stays in the notebook). |
| `Code/test_openmeteo.py` | Superseded (Phase 3) | Confirmed the key-less API access pattern; its functionality is now provided generically by `Code/weather/collector.py`. Kept unmodified as historical reference. |
| `Code/weather/config.py`, `location_mapper.py`, `collector.py`, `validator.py` | **NEW (Phase 3)** | Reusable, crop-agnostic weather collection pipeline: geocoding via Open-Meteo Geocoding API, caching/retry-aware collection via the Archive API, and structural/plausibility validation. No credential handling exists because none is required (documented in `config.py`). |

## 6. Initial Cross-Dataset Compatibility Findings

- Exact-string crop-name overlap: Mandi ∩ APY = 40 names; Mandi ∩ Agri Market = 4; APY ∩ Agri Market = 2. Formatting differences (e.g. `Arhar (Tur-Red Gram)(Whole)` in mandi vs `Arhar (Tur/Red Gram)(Whole)` in Agri Market) mean **exact matching under-counts true overlap** — Phase 2 needs a normalized crop-name mapping.
- State names show reasonable exact-match overlap between a mandi sample (Onion.csv), APY, and `final_data.csv`; district/market-level matching is unverified and left to Phase 4.
- No dataset contains geographic coordinates — this affects both weather-mapping (Phase 3) and logistics (future Phase 11).

## 7. Initial Limitations (see also `Assumptions.md`)

1. Inconsistent mandi column naming across files (unit-suffixed vs not).
2. Inconsistent `Reported Date` formats across mandi files.
3. 5 of 325 mandi files are empty and must be excluded from Phase 2's candidate pool.
4. Agri Market Dataset is regionally narrow (1 state, 5 districts, 5 crops) — cannot be treated as a national market-activity source.
5. No coordinates exist anywhere in the provided data.
6. Crop-name formatting differs across sources (brackets/slashes/spacing).
7. Mandi files are large (up to ~230 MB) — full in-memory loads of all 325 at once are impractical.
8. Agri Market's `Arrivals (Tonnes)` field has 169 non-numeric raw values.
9. No true demand variable exists anywhere — only supply-side arrivals/traded-quantity proxies.

## 8. Phase 2 Outcome (completed)

Phase 2 built the crop-name normalization process (`Code/utils/crop_matching.py`), audited a 48-crop shortlist (candidates with a safe, evidenced APY match) across mandi/APY/Agri Market, and selected **Onion, Potato, Wheat** — see Section 2b above and `Documentation/Crop_Feasibility_Audit.md` for full evidence and rationale. All 7 Phase 2 validation checks passed (dataset integrity, exactly 3 crops, no fabricated coordinates/demand, production/arrivals kept distinct).

## 8b. Phase 3 Outcome (completed)

Phase 3 built `Code/weather/` (config.py, location_mapper.py, collector.py, validator.py) — a reusable, crop-agnostic Open-Meteo collector. Confirmed **no API key required**. Mapped the top-20-by-mandi-volume districts per crop (46 unique locations across Onion/Potato/Wheat) via the Open-Meteo Geocoding API: **36 mapped, 10 unresolved** (spelling mismatches, e.g. mandi "Bhatinda" vs official "Bathinda" — documented, not fabricated). Collected and validated daily weather (temperature, rainfall, humidity, wind, ET0) for 2001-01-01 to 2022-12-31 for all 36 mapped locations — zero missing dates, zero missing values. Full detail: `Documentation/Weather_Data_Collection.md`.

## 8c. Phase 4 Requirements (handoff)

Phase 4 (Data Integration) needs: (a) `Processed_Data/weather/weather_location_mapping.csv` and `Processed_Data/weather/raw/*.csv` (Phase 3 outputs); (b) a decision on how mandi records in non-mapped districts are handled (excluded vs. assigned to nearest mapped location within-state — not yet decided); (c) a decision on aligning APY's agricultural-year grain with mandi/weather's daily grain (not yet decided — flagged in Phase 3); (d) mandi data (`Onion.csv`, `Potato.csv`, `Wheat.csv`) and APY data for the three selected crops; (e) explicit before/after row-count validation at every merge step per project rules.

## 8d. Phase 4 Outcome (completed)

Built `Code/integration/pipeline.py` (`run_pipeline()`) and `Notebooks/Phase_04_Data_Integration.ipynb`. Outputs are in `Processed_Data/integration/`, each at its own verified grain (Decision Log D-15 to D-24):

| Output | Rows | Grain |
|---|---|---|
| `mandi_integrated_onion.parquet` | 2,624,379 | one row per raw mandi record |
| `mandi_integrated_potato.parquet` | 2,764,987 | one row per raw mandi record |
| `mandi_integrated_wheat.parquet` | 2,593,767 | one row per raw mandi record |
| `weather_daily_panel.parquet` | 369,610 | 46 locations × 8,035 days |
| `apy_season.csv` / `apy_annual.csv` | 41,835 / 33,011 | APY season / annual district grain |
| `mandi_apy_district_year.csv` | 38,700 | crop × APY district × agricultural year (outer 1:1) |
| `agrimarket_wheat_crosscheck.csv` | 9,569 | Agri Market Wheat records |

Key results:
- **Weather**: all 46 locations admin2-verified. 10 previously unresolved were resolved, and Phase 3's Ferozpur point (in the wrong district, 159 km off) was corrected. Same-day weather covers 25.3% of Onion, 23.6% of Potato and 25.2% of Wheat records, by exact district only. No proxy matches were made; unmatched weather stays NaN.
- **APY**: linked through a July–June agricultural-year key (`apy_year`, `apy_year_lag1`). Annual values are not repeated onto daily rows. 95.9% / 95.5% / 97.9% of records have an APY district; an APY annual value exists for 46.9% / 62.4% / 93.5% (Onion / Potato / Wheat).
- **Agri Market Wheat**: identical to mandi values where both exist (96.6% match rate), so it is a key-consistency check, not independent validation.
- **Duplicates**: flagged, not dropped (exact 3,520 rows, conflicting 339 rows across the three crops).

## 8e. Phase 5 Requirements (handoff)

Phase 5 (Data Cleaning) starts from the three `mandi_integrated_<crop>.parquet` files (traceable through `source_row`) and decides, with documented policies: exact vs conflicting duplicate keys (`dup_type`), zero prices, min > max rows, missing modal prices and outliers. It must not zero-fill missing weather or broadcast APY annual values onto daily rows. Data-quality anomalies were deliberately left untouched in Phase 4.

## 8f. Phase 5 Outcome (completed)

Built `Code/cleaning/pipeline.py` (`run_cleaning()`, rules R01–R14) and `Notebooks/Phase_05_Data_Cleaning.ipynb`. The Phase 4 tables are read-only inputs; their content hashes still equal the Phase 4 manifest. Decision Log D-25 to D-31; Assumptions A-16 to A-18.

| Crop | Phase 4 rows | Identical copies removed | Cleaned rows | Prices set missing (zero placeholders) | Conflicting rows kept + flagged | usable_modal_price | usable_arrivals |
|---|---|---|---|---|---|---|---|
| Onion | 2,624,379 | 708 | 2,623,671 | 275,188 | 68 (34 groups) | 98.93% | 99.99% |
| Potato | 2,764,987 | 570 | 2,764,417 | 294,983 | 164 (82 groups) | 98.80% | 99.99% |
| Wheat | 2,593,767 | 488 | 2,593,279 | 263,885 | 106 (53 groups) | 99.45% | 99.99% |

Key results:
- **Zero prices are "not reported" placeholders** and are now missing. With that, min > max falls from 3,282 / 3,990 / 3,436 rows to 0.
- **Implausible levels are flagged, never deleted.** Price scale errors suspected: 422 / 415 / 148. Arrivals entry errors suspected: 75 / 62 / 53.
- **Nothing was imputed.** Weather and APY gaps remain Phase 4 coverage limits.

## 8g. Phase 6 Requirements (handoff)

Phase 6 (Feature Engineering) starts from `Processed_Data/cleaned/mandi_cleaned_<crop>.parquet`. It should:
- Use `usable_modal_price` / `usable_arrivals` (or justify otherwise).
- Decide explicitly on `conflict_unresolved` rows and `review` flags.
- Keep features leakage-safe: lag weather, and use `apy_year_lag1` or later for APY.
- Never impute weather or APY by zero-filling.
- Never call arrivals "demand".

## 8h. Phase 6 Outcome (completed)

Built `Code/features/pipeline.py` (`run_features()`, `feature_registry()`) and `Notebooks/Phase_06_Feature_Engineering.ipynb`. Outputs: `Processed_Data/features/features_{onion,potato,wheat}.parquet`, with the same rows as Phase 5 (2,623,671 / 2,764,417 / 2,593,279) and 85 columns, plus `Processed_Data/features_audit/`. Decisions D-32 to D-37; assumptions A-19 to A-21.

- **Series**: crop × market × variety, keyed as (crop, state, district, market, variety) per D-33; no feature crosses a series.
- **Information cutoff**: every history feature uses only eligible (`usable_*`) rows dated strictly before t. No imputation.
- **Predictors (60 columns)**: calendar features (incl. IMD season, July–June agricultural year); price and arrivals previous-observation values, exact 1-/7-day calendar lags, changes, and 7/30/90-day calendar-window mean/median/std/count; trailing weather (prev day + full windows); APY production/area/yield at lag 2.
- **Validation**: brute-force spot checks, a leakage probe on a real series, row preservation, and Phase 4/5 immutability all pass.

## 8i. Phase 7 Requirements (handoff)

Phase 7 (EDA) starts from the feature tables and the registry. It should:
- Analyse targets only on `usable_*` rows.
- Keep `audit_only` and `eligibility_flag` columns out of predictor rankings.
- Report weather relationships only on the weather-covered subset (about 25% of rows).
- Fix, before Phase 8, the forecast horizon and cutoff (A-20), the treatment of `review` rows, and the evaluation split.

## 8j. Phase 7 Outcome (completed)

Built `Code/eda/analysis.py` (`run_eda()`) and `Notebooks/Phase_07_EDA.ipynb`. The outputs are `Processed_Data/eda/` (15 tables), six figures, `Documentation/EDA_Findings.md` and `Documentation/Modelling_Readiness_Report.md`. All analysis uses nominal prices and registry roles, and every table states its sample.

- **Onion** is the most volatile crop (CV 0.79): cheapest in April–June, dearest in October–November, with spring arrival peaks.
- **Potato** is cheapest in February–March and dearest in October–November.
- **Wheat** is stable (CV 0.31) with flat monthly prices but an April procurement arrival peak of about 2.3×.
- **Prices are highly persistent** (within-series correlation ≈ 0.95). Price–arrivals association is weak and negative for the vegetables.
- **Weather and APY associations are descriptive.** The weather ones are likely seasonal confounding.
- **Readiness:** series with ≥ 365 usable observations hold 91–93% of usable rows. Unresolved conflicts (338) are concentrated in Telangana, Madhya Pradesh and Punjab, 2006–2011.

## 8k. Phase 8 Requirements (handoff)

The decisions below were reviewed and **accepted in Phase 8 planning (2026-10-22)**. The data contract, leakage rules, evaluation protocol, baselines and inference contract are in `Documentation/Phase_08_Modelling_Plan.md`. No model has been trained.
- **D-38 (accepted):** weekly median target (Monday–Sunday weeks), h = 1/2/4 weeks, ≤ origin cutoff; next reported observation as a secondary baseline.
- **D-39 (accepted):** usable views; keep review rows, plus a sensitivity run without review targets.
- **D-40 (accepted with refinement):** train 2002–2018; validation 2019 and 2020 reported separately and combined; test 2021–2022 used once; 2023-01-01 – 2024-02-02 no-weather holdout; expanding window, rolling origins, horizon gap; no random splits.
- **D-41 (accepted):** primary population = series with ≥ 365 usable price observations (1,473 / 1,551 / 1,540 series); excluded series reported separately.
- **Baselines:** persistence, seasonal naive, next reported observation, calendar-only.

**Repository state at Phase 8 planning (verified with git):** branch `main`, HEAD `0716ab6`. The deletion of `Documentation/EDA_Findings.pdf` is intentional and still uncommitted.

**Git history (2026-10-22):**
- Before the first push to `origin` (github.com/akshat12bhardwaj/BDA), local history was rewritten so that `Dataset/`, `*.parquet` and Python caches are no longer tracked. They remain on disk and are covered by `.gitignore`.
- Commit mapping: `0716ab6` → `819e0f0`, `b8671ed` → `685e8b8`.
- The pre-rewrite commits are kept only in the local branch `backup/pre-history-rewrite`, which is not pushed.
- A fresh clone has no raw data or parquet tables. Copy `Dataset/` in and rerun the phase pipelines (Phase 4 → 6) to regenerate them.

## 8l. Phase 10 v1 Outcome (implemented 2026-10-23)

Built under D-46 – D-48, accepted 2026-10-23. The phase name stays "Supply Prediction" until D-49 is decided.

- **Product:** `Processed_Data/production_context/production_context_v1.csv`, contract `phase10-production-context-v1`.
  - 31,694 rows (crop × APY district × decision agricultural year): 27,531 in the design window (source ≤ 2018-19) and 4,163 reserved (2019-20 … 2021-22).
  - 2022-23 is excluded.
  - Descriptive only: no forecasting model, and no procurement cap or marketable-surplus estimate.
- **Availability:** `apy_lag2_policy_v1`. Source year = decision year − 2, and `available_from` = 1 July of the decision year. This is a policy assumption (A-23), not a verified publication schedule.
- **Quality (PQ-1 v1, flags only):** R1, R2, R3, R8a, R9, R10, R11, R12 and R13 are active; R4 is diagnostic only; the R4 row flag, R5, R6, R7 and R8b are blocked.
- **Design-window classes (ok / annotated / review / unusable):**

  | Crop | ok | annotated | review | unusable |
  |---|---|---|---|---|
  | Onion | 4,871 | 3,027 | 5 | 42 |
  | Potato | 4,991 | 3,834 | 41 | 35 |
  | Wheat | 5 | 10,654 | 3 | 23 |

  Wheat is a single Rabi row, so R9 annotates almost every row.
- **R13:** all 37 West Bengal and Gujarat Potato 1997-98 rows are `review`. No cause is asserted, and the DES enquiry (plan §15) is unsent.
- **Integrity:**
  - Inputs are verified against their Phase 4/6 records; the crosswalk passes through the documented `alias_basis` canonicalisation.
  - PQ-1 was frozen by hash before the reserved build, and outputs are byte-for-byte reproducible.
  - Lineage: `Data_Lineage.md`, Phase 10 section.

## 8m. Big Data component and dashboard (course deliverables, implemented 2026-10-23)

**Status:** not a numbered phase. No Phase 4–10 file, decision, freeze or evaluation boundary is changed. Spec: `Documentation/BigData_and_Dashboard_Spec.md`. Lineage: `Data_Lineage.md`, "Big Data component and dashboard" section.

**Environment:** isolated, outside the repository and outside OneDrive.
- Eclipse Temurin JDK 21.0.12.1+1 (portable zip, SHA-256 verified).
- A venv (`--system-site-packages`) with PySpark 4.2.0 and Streamlit 1.57.0.
- The global Java (24), PATH and `C:\Python313` are unchanged.
- `JAVA_HOME` is set per process. Setup steps: `Documentation/Final/README_Setup.md`.

**PySpark ETL (`Code/bigdata/mandi_spark.py`)**
- **Header and schema:** an exact header check runs before the explicit schema is applied. In a probe, Spark's `enforceSchema=false` did not reject a renamed header, so the module checks it itself.
- **Rows read:** 7,983,133 (Onion 2,624,379 · Potato 2,764,987 · Wheat 2,593,767). Malformed rows: 0. Unparseable dates: 0.
- **Window:** dates ≤ 2020-06-30, i.e. agricultural years ≤ 2019-20. It ends before the 2021–2022 test and the 2023+ holdout. Rows in the window: 1,965,939 · 2,097,137 · 2,063,216.

**Quality counts in the window** (counted, never repaired)

| Check | Onion | Potato | Wheat |
|---|---|---|---|
| Duplicate-key rows | 1,484 | 1,296 | 1,077 |
| Min price > max price | 2,235 | 3,047 | 2,992 |
| Missing or zero modal price | 27,475 | 32,512 | 13,307 |
| Zero arrivals | 9 | 3 | 14 |
| Rows without an APY district | 80,402 | 92,087 | 42,002 |

**Spark SQL**

| Query | Grouping | Rows |
|---|---|---|
| Q1 | district × agricultural year (the parity target) | 16,673 |
| Q2 | weekly, by crop × state (state rather than market, to keep the output small) | 60,436 |
| Q3 | top 10 districts by arrivals per crop × year, via `RANK()` | 593 |

**Parity against Phase 4**
- **Reference:** Phase 4's pandas `mandi_apy_district_year.csv`.
- **Result:** all **16,673** district-years, **0 mismatches** across **8 checks**.
  - Exact: the key set, records, markets, first date, last date and duplicate-key rows.
  - Within a 1e-9 relative tolerance: the arrivals sum and the median modal price.
- **Reference verification:** the recorded Phase 4 content hash can't be reproduced from the CSV (types change on readback). The reference is therefore checked by its shape against the record and by its git blob against HEAD.

**MapReduce-style demonstration (`mapreduce_demo.py`)**
- Spark RDD `map` / `reduceByKey` gives records and arrivals per crop × state (93 rows), equal to the Spark SQL `GROUP BY`.
- A word count over variety names (122 words).
- This is a Spark pattern in local mode: **not Hadoop MapReduce, not a cluster**.

**Runtime and reproducibility**
- Observed: 108–116 s end to end on `local[8]`, on one machine (28 logical cores, 32 GB). This is not a cluster benchmark.
- Two runs produced byte-identical files (8 outputs; `run_log.csv` excluded by design).

**Dashboard (`Code/app/`)**
- **Six tabs:** Overview, Price forecasting, Arrivals forecasting, Production context, Big Data (Spark), Limitations.
- **Restrictions enforced in `data.py`:**
  - price predictions: validation only (origin ≤ 2020-12-27); the 2021–2022 test appears as metrics only;
  - arrivals: `val_2019`, `val_2020`, `test_2021` and `test_2022` only;
  - production values: source years ≤ 2018-19 only; reserved years as counts from the Phase 10 manifest;
  - no 2023+ data; no file writes.
- **Screenshots:** `Documentation/Final/screenshots/app_1_overview.png` … `app_6_limitations.png`.

**Tests (2026-10-23)**
- Full suite in the venv: 279 passed, 1 skipped (opt-in real-data parity). Project Python: 268 passed, 3 skipped (the Spark and Streamlit tests skip without the venv).
- The dashboard starts without the three git-ignored prediction parquet files: the Prices and Arrivals charts show a notice and every other tab still renders (tested). The 2021–2022 arrivals `test_predictions.parquet` cannot be regenerated on a fresh clone (run-once guard); see `Documentation/Final/README_Setup.md` §1.
- Opt-in real-data parity: passed.
- Integrity checks passed: 62 protected hashes, the D-42 / D-45 freezes, AQ-1 and the Phase 10 freeze.

**Run** (from the project root, `JAVA_HOME` set):
- `<venv>\Scripts\python.exe -B -m Code.bigdata.mandi_spark`
- `<venv>\Scripts\streamlit.exe run Code\app\streamlit_app.py --server.headless true --browser.gatherUsageStats false`

**Correction recorded (Onion, one week ahead, D-42 test).** A working-session course-alignment audit, which is not a repository document, said this model had "1.6% lower MAE". That is wrong. As D-42, `Phase_08_Modelling_Plan.md` and `test_results.csv` record:
- combined test: **1.58% worse** than persistence on MAE;
- 2021: **5.16% worse**;
- 2022: **3.31% better**.

The dashboard, report and slides state this correctly. No repository document had the wrong figure.

**Deliverables** (`Documentation/Final/`)
- `Final_Report.md`
- `Final_Presentation.pptx`, generated by `Code/utils/build_final_slides.py` with numbers read from the outputs
- `Demo_Script.md`, including the video plan
- `Contribution_Matrix.md` (a template)
- `README_Setup.md`
- `Requirements_Checklist.md`

**Limitations**
- **Hadoop/HDFS:** not implemented, pending instructor guidance. No WSL distro or Docker is installed.
- **Local only:** the run and the dashboard are local.
- **Untracked inputs:** the dashboard reads local parquet predictions that are not in Git, so a fresh clone must rerun the pipelines.
- **To be supplied by the team:** names, roles, the contribution matrix, and the report's AI-assistance disclosure (§10).

## 9. Future-Phase Dependency Context

See `Future_Work_Roadmap.md` for full Phase 8–14 specifications and `Documentation/Data_Lineage.md` for the dependency chain from raw sources through to the future optimization output. No future phase has been implemented; this section exists only to record that the dependency structure has been planned and is unaffected by Phase 1 findings.
