# Data Lineage

Tracks every derived artifact back to its original source. Updated at the end of every phase. As of Phase 1, **no processing/merging has occurred** — only read-only inspection. All nodes below marked "Future Processing" are genuinely not yet built.

```
Dataset/India Commodity Wise Mandi Dataset/ (325 CSVs, read-only)
    │
    ├── Phase 1: candidate universe, record counts, schema/date-format check
    │       → Processed_Data/phase1_mandi_file_record_counts.csv  [COMPLETED — Phase 1]
    │
    ├── Phase 2: name normalization (320 candidates) + full feasibility audit (48-crop shortlist)
    │       → Processed_Data/crop_name_mapping.csv        [COMPLETED — Phase 2]
    │       → Processed_Data/crop_feasibility_mandi.csv   [COMPLETED — Phase 2]
    │
    └── Future Processing (Phase 4: integration for Onion/Potato/Wheat only; Phase 5: cleaning)

Dataset/crop-wise-area-production-yield.csv (read-only)
    │
    ├── Phase 1: structure, coverage, codebook cross-reference
    ├── Phase 2: feasibility statistics for the 48-crop shortlist
    │       → Processed_Data/crop_feasibility_apy.csv     [COMPLETED — Phase 2]
    │
    └── Future Processing (Phase 4: integration for Onion/Potato/Wheat only; Phase 5: cleaning)

Dataset/Crop_Wise_Area_Production_Yield_codebook.xlsx (read-only)
    │
    └── read in Phase 1 for field/unit interpretation only — not a data source itself

Dataset/Agri Market Dataset.csv (read-only)
    │
    ├── Phase 1: structure, geographic/crop scope, terminology clarified
    ├── Phase 2: normalized-matched against the 48-crop shortlist
    │       → Processed_Data/crop_dataset_overlap.csv     [COMPLETED — Phase 2]
    │
    └── Future Processing (Phase 4: conditional integration — Wheat only, Maharashtra/Amravati region)

Dataset/final_data.csv (read-only)
    │
    ├── inspected in Phase 1 (confirmed: State/District/Market ID lookup table)
    │
    └── Future Processing (Phase 4: candidate for market-ID standardization)

Open-Meteo Geocoding API (external, key-less)
    │
    ├── Phase 3: geocode 46 representative (state, district) locations (top-20-by-volume per crop, de-duplicated)
    │       → Processed_Data/weather/weather_location_mapping.csv  [COMPLETED — Phase 3]  (36 mapped, 10 unresolved)
    │
    └── Future Processing (Phase 4+: could add a manual spelling-alias step to resolve some of the 10 unresolved)

Open-Meteo Historical Weather Archive API (external, key-less)
    │
    ├── Phase 1: existing test script (Code/test_openmeteo.py) reviewed, not re-run
    ├── Phase 3: daily weather collected 2001-01-01 to 2022-12-31 for the 36 mapped locations
    │       → Processed_Data/weather/raw/*.csv               [COMPLETED — Phase 3]
    │       → Processed_Data/weather/weather_collection_manifest.csv  [COMPLETED — Phase 3]
    │       → Processed_Data/weather/weather_validation_report.csv    [COMPLETED — Phase 3]
    │       → Processed_Data/weather/weather_coverage_summary.csv     [COMPLETED — Phase 3]
    │
    └── Future Processing (Phase 4: geographic/temporal alignment with mandi + APY data)

Processed_Data/crop_name_mapping.csv + crop_feasibility_mandi.csv + crop_feasibility_apy.csv + crop_dataset_overlap.csv
    │
    └── Phase 2: combined into the final selection decision
            → Processed_Data/selected_crops.csv  [COMPLETED — Phase 2]  (Onion, Potato, Wheat)
```

## Node Status Legend
- **[COMPLETED]** — artifact exists and was produced this phase.
- **Future Processing** — planned, not yet built; no file exists yet for this step.

## Derived Artifacts Produced So Far

| Artifact | Produced by | Source(s) | Contents |
|---|---|---|---|
| `Processed_Data/phase1_mandi_file_record_counts.csv` | Phase 1 | All 325 mandi CSVs (line-count only, no parsing) | `crop_file_name, approx_record_count` for each of the 325 files |
| `Outputs/Figures/phase01_top15_mandi_record_counts.png` | Phase 1 | `phase1_mandi_file_record_counts.csv` | Bar chart, top 15 crops by record count |
| `Outputs/Figures/phase01_apy_records_per_year.png` | Phase 1 | APY dataset | Bar chart, records per crop-year |
| `Outputs/Figures/phase01_agrimarket_commodity_counts.png` | Phase 1 | Agri Market Dataset | Bar chart, records per commodity |
| `Processed_Data/crop_name_mapping.csv` | Phase 2 | 320 mandi candidates vs 115 APY + 5 Agri Market crop names | Per-candidate best APY/Agri-Market match, status, method |
| `Processed_Data/crop_feasibility_mandi.csv` | Phase 2 | 48-crop shortlist (mandi CSVs) | records, years, states, districts, markets, varieties, missingness, duplicates, extreme-value counts |
| `Processed_Data/crop_feasibility_apy.csv` | Phase 2 | 48-crop shortlist (APY dataset) | records, years, states, districts, seasons, production/yield completeness |
| `Processed_Data/crop_dataset_overlap.csv` | Phase 2 | Merge of the three tables above | compatibility tier per candidate crop |
| `Processed_Data/selected_crops.csv` | Phase 2 | Final selection decision | Onion, Potato, Wheat with APY crop name + Agri Market flag |
| `Outputs/Figures/phase02_mandi_top15_matched_candidates.png` | Phase 2 | `crop_feasibility_mandi.csv` | Bar chart, top 15 shortlisted crops by mandi records |
| `Outputs/Figures/phase02_apy_years_key_candidates.png` | Phase 2 | `crop_feasibility_apy.csv` | Bar chart, APY year-coverage for key candidates including Tomato |
| `Processed_Data/weather/weather_location_mapping.csv` | Phase 3 | 46 representative (state, district) locations vs Open-Meteo Geocoding API | mapped/unresolved status, coordinates, mapping method per location |
| `Processed_Data/weather/raw/*.csv` (36 files) | Phase 3 | Open-Meteo Historical Weather Archive API | Daily temperature/rainfall/humidity/wind/ET0, 2001-01-01 to 2022-12-31, per mapped location |
| `Processed_Data/weather/weather_collection_manifest.csv` | Phase 3 | Collection run metadata | status, cache hit/miss, row count, retrieval timestamp per location |
| `Processed_Data/weather/weather_validation_report.csv` | Phase 3 | Validator over the 36 collected series | date-range/duplicate/missing-date/missing-value/coordinate checks |
| `Processed_Data/weather/weather_coverage_summary.csv` | Phase 3 | Merge of mapping + manifest + validation | per-crop coverage rollup |
| `Outputs/Figures/phase03_coverage_by_crop.png` | Phase 3 | `weather_coverage_summary.csv` | Bar chart, mapped vs unresolved locations per crop |
| `Outputs/Figures/phase03_sample_temperature_series.png` | Phase 3 | One collected weather series | Sample daily temperature plot |

## Phase 4 — Data Integration lineage

Produced by `Code/integration/pipeline.py:run_pipeline()` (run from `Notebooks/Phase_04_Data_Integration.ipynb`). Raw sources are only read; their SHA-256 hashes before and after each run are recorded in `Processed_Data/integration/audit/source_fingerprints.csv`.

```
Mandi {Onion,Potato,Wheat}.csv ──(rename to canonical names, parse dates, flag duplicate keys)──┐
Code/integration/district_aliases.csv + APY districts ──→ district_crosswalk.csv ──(m:1)──────┤
APY (3 crops) ──→ apy_season.csv ──→ apy_annual.csv ──(keys only: availability flag, m:1)──────┤
final_data.csv ──(unique normalized market key, m:1)─────────────────────────────────────────┤
Phase 3 mapping + geocoder_evidence_phase4.csv ──→ weather_location_resolution.csv           │
    └─ Phase 3 raw/*.csv (35 verified) + 11 new cache files ──→ weather_daily_panel.parquet ──(same day, m:1)──┤
                                                                                              ▼
                                         mandi_integrated_<crop>.parquet (one row per raw record)
                                                     │ aggregate to (crop, APY district, apy_year)
                                                     ▼
                         mandi_apy_district_year.csv  ←(outer 1:1)→  apy_annual.csv
Agri Market (Wheat rows) ──(1:1 vs unique-key mandi Wheat)──→ agrimarket_wheat_crosscheck.csv
```

| Artifact (`Processed_Data/integration/`) | Source(s) | Grain / contents |
|---|---|---|
| `mandi_integrated_{onion,potato,wheat}.parquet` | mandi CSVs + crosswalk + APY keys + final_data + weather panel | one row per raw mandi record (`source_row`); canonical columns, `dup_key_count`/`dup_type`, `apy_year`/`apy_year_lag1`, `apy_state`/`apy_district`/`apy_district_match`, `apy_annual_available`, `market_code`/`market_code_status`, `weather_*` keys, 7 weather variables (NaN when not matched), `weather_match` |
| `weather_daily_panel.parquet` | Phase 3 raw files (35) + Phase 4 cache files (11) | (weather_state, weather_district, date); 46 locations × 8,035 days |
| `weather_location_resolution.csv` | Phase 3 mapping + geocoder evidence | 46 locations: resolution status, accepted coordinate, admin1/admin2 evidence, correction distance |
| `geocoder_evidence_phase4.csv` | Open-Meteo Geocoding API (Phase 4 query) | every candidate returned for each search term |
| `district_crosswalk.csv` | mandi districts + APY districts + alias table | (crop, mandi state, mandi district) → APY district + method + basis |
| `apy_season.csv` | APY | (crop, state, district, apy_year, season) |
| `apy_annual.csv` | `apy_season.csv` | (crop, state, district, apy_year); `annual_method` |
| `mandi_apy_district_year.csv` | mandi integrated tables + `apy_annual.csv` | (crop, apy_state, apy_district, apy_year); mandi aggregates + APY values + `link_status` |
| `agrimarket_wheat_crosscheck.csv` | Agri Market (Wheat) + mandi Wheat | one row per Agri Market Wheat record + matched mandi values |
| `audit/` | the run itself | `merge_log`, `coverage_summary`, `unmatched_keys`, `duplicate_key_summary`, `weather_resolution_validation`, `agrimarket_crosscheck_summary`, `source_fingerprints`, `output_manifest`, `integration_run.log` |
| `Processed_Data/weather/raw/` (11 new files) | Open-Meteo Archive API via the Phase 3 collector | daily weather 2001–2022 for the 10 resolved locations and the corrected Ferozpur point (`Punjab_Ferozpur_corrected.csv`) |
| `Outputs/Figures/phase04_*.png` (4) | Phase 4 audit tables | weather match share, APY district match share, top districts without weather, APY link share by year |

## Phase 5 — Data Cleaning lineage

Produced by `Code/cleaning/pipeline.py:run_cleaning()` (run from `Notebooks/Phase_05_Data_Cleaning.ipynb`). It reads only the three Phase 4 integrated tables, which it fingerprints before and after each run, and never modifies them.

```
Processed_Data/integration/mandi_integrated_<crop>.parquet   (Phase 4, immutable)
    │  R01 collapse identical copies → removed source_rows listed
    │  R03 keep conflicting versions, flag conflict_unresolved
    │  R04–R06 zero/negative/non-finite prices → missing (+ <field>_status)
    │  R07–R08 consistency flags;  R09 price vs trailing 30-day national reference
    │  R10–R12 arrivals status; arrivals vs the market's past-365-day peak
    ▼
Processed_Data/cleaned/mandi_cleaned_<crop>.parquet   (+ usable_modal_price, usable_arrivals)
Processed_Data/cleaning_audit/*.csv
```

| Artifact | Source(s) | Grain / contents |
|---|---|---|
| `Processed_Data/cleaned/mandi_cleaned_{onion,potato,wheat}.parquet` | Phase 4 integrated tables | one row per distinct observation (2,623,671 / 2,764,417 / 2,593,279 rows); the 33 Phase 4 columns + 14 flag columns |
| `cleaning_audit/cleaning_decisions.csv` | rule table in code | R01–R14: detection, treatment, reason |
| `cleaning_audit/cleaning_summary.csv` | run | per crop × rule: affected rows/groups, removed, set-missing, flagged, excluded, rows before/after |
| `cleaning_audit/quality_metrics_before_after.csv` | run | the same quality metrics before and after cleaning |
| `cleaning_audit/missingness_before_after.csv` | run | per column, with category (measurement / weather coverage / APY coverage / key) |
| `cleaning_audit/removed_identical_copies.csv` | run | every removed `source_row` with its original values |
| `cleaning_audit/review_records.csv` | run | rows with conflict / consistency / extreme flags (exceptions only) |
| `cleaning_audit/added_columns.csv`, `output_manifest.csv`, `phase4_input_fingerprints.csv` | run | column meanings, rows + content hashes, Phase 4 immutability check |
| `Outputs/Figures/phase05_*.png` (4) | audit tables / cleaned files | arrivals-reference choice, price consistency before/after, price-ratio distribution, usable-price share |

## Phase 6 — Feature Engineering lineage

Produced by `Code/features/pipeline.py:run_features()` (run from `Notebooks/Phase_06_Feature_Engineering.ipynb`). It reads the Phase 5 cleaned tables and the Phase 4 weather panel and `apy_annual.csv`, fingerprints all of them before and after each run, and modifies none of them.

```
Processed_Data/cleaned/mandi_cleaned_<crop>.parquet (Phase 5)
    | series = crop x state x district x market x variety; history = rows dated < t with usable_* = True
    | time features; price/arrivals prev-obs, calendar lags, 7/30/90-day windows, changes
Processed_Data/integration/weather_daily_panel.parquet (Phase 4) --(prev day + full trailing windows, m:1)--+
Processed_Data/integration/apy_annual.csv (Phase 4) --(agricultural year t-2, m:1)------------------------+
    v
Processed_Data/features/features_<crop>.parquet   (same rows / source_row as Phase 5; 85 columns)
Processed_Data/features_audit/*.csv
```

| Artifact | Source(s) | Grain / contents |
|---|---|---|
| `Processed_Data/features/features_{onion,potato,wheat}.parquet` | Phase 5 cleaned + Phase 4 weather panel + APY annual | one row per Phase 5 row (2,623,671 / 2,764,417 / 2,593,279); identifiers, targets, usable flags, audit keys, 60 predictor columns |
| `features_audit/feature_registry.csv` | code | per column: role, task, definition, inputs, grouping, window, missing behaviour, prediction-time availability, leakage safeguard |
| `features_audit/row_counts.csv`, `feature_statistics.csv` | run | input/output rows and columns; dtype, missingness and min/median/max per column per crop |
| `features_audit/validation_report.csv` | run | row preservation, registry coverage, brute-force spot checks, input immutability |
| `features_audit/input_fingerprints.csv`, `output_manifest.csv` | run | SHA-256 of the inputs before and after; content hashes of the outputs |
| `Outputs/Figures/phase06_*.png` (2) | feature tables | reporting-gap distribution; trailing feature vs target for one series |

## Phase 7 — EDA lineage

Produced by `Code/eda/analysis.py:run_eda()` (run from `Notebooks/Phase_07_EDA.ipynb`). It reads the three Phase 6 feature tables, fingerprinting them before and after, plus the Phase 4 `mandi_apy_district_year.csv`. No earlier output is modified, and no model is fitted.

| Artifact (`Processed_Data/eda/`) | Contents (every table states its sample) |
|---|---|
| `sample_definitions.csv` | the six analysis samples and their row counts per crop |
| `distribution_summary.csv`, `yearly_profile.csv`, `seasonal_index.csv` | price/arrivals distributions, yearly profiles (nominal), monthly indices relative to series-year median/mean |
| `series_summary.csv`, `variety_summary.csv` | per series (crop × market × variety) coverage, density, volatility; per variety levels |
| `relationship_summary.csv`, `apy_district_year_association.csv` | within-series Spearman associations (price-arrivals, persistence, weather); district-year APY associations |
| `horizon_feasibility.csv`, `weekly_horizon_feasibility.csv`, `split_evidence.csv`, `review_flag_effect.csv` | evidence for decisions D-38 to D-40 |
| `quality_readiness.csv`, `conflict_distribution.csv` | data-quality and readiness metrics (denominators stated), conflict locations |
| `input_fingerprints.csv` | SHA-256 of the Phase 6 inputs before and after |
| `Documentation/EDA_Findings.md`, `Documentation/Modelling_Readiness_Report.md` | written findings and readiness/decision report |
| `Outputs/Figures/phase07_*.png` (6) | nominal price trend, seasonal price/arrivals, series history, horizon feasibility, APY association, split evidence |

No model or forecast exists yet. D-38 – D-41 were accepted in Phase 8 planning. The planned Phase 8 inputs and outputs are listed in `Phase_08_Modelling_Plan.md`.

**Phase 8 dataset builder (implemented):**
- `Code/modelling/dataset.py:run_build()` reads `Processed_Data/features/features_<crop>.parquet` and `features_audit/feature_registry.csv`, read-only and hash-checked against `Processed_Data/eda/input_fingerprints.csv`.
- It writes only CSV manifests to `Processed_Data/modelling/phase08/`.
- The weekly datasets are rebuilt in memory; their content hashes are in `dataset_manifest.csv`.
- `Code/modelling/baselines.py:run_baselines()` uses the same inputs and checks and writes `baseline_validation_metrics.csv` and `next_obs_validation_metrics.csv`, covering the validation years only.
- `*.parquet` and `Dataset/` are not tracked in git (`.gitignore`). They exist only locally and are regenerated by the pipelines.

## Phase 10 — District Production Context lineage (v1; D-46 – D-48, accepted 2026-10-23)

Produced by `Code/production/pipeline.py` (stages `design`, `freeze`, `build`) and `Code/production/apy_audit.py`. It writes only to `Processed_Data/production_context/`, modifies no Phase 4–9 file, and fits no model. The roadmap still calls this phase "Supply Prediction" because D-49 (renaming) is not accepted.

```
Dataset/crop-wise-area-production-yield.csv        (unit labels → R11, season keys → R12)   ┐
Processed_Data/integration/apy_annual.csv           (D-20 annual values, used as published)   ├─ verify_inputs() → load(): cut to the window
Processed_Data/integration/apy_season.csv           (audit only)                              │                    immediately after reading
Processed_Data/integration/district_crosswalk.csv   (fingerprint only; consumers join via it) ┘  → build_context(): contract + PQ-1 v1 flags
    design   (source ≤ 2018-19) → audit/*.csv, design/design_pq_summary.csv
    freeze   (once)              → pq1_freeze_manifest.csv
    build    (source ≤ 2021-22)  → production_context_v1.csv, pq1_provenance.csv, output_manifest.csv, build_log.csv
```

| Artifact (`Processed_Data/production_context/`) | Contents |
|---|---|
| `production_context_v1.csv` | contract `phase10-production-context-v1`: 31,694 rows, one per (crop, APY state, APY district, decision agricultural year); source years 1997-98 … 2021-22 |
| `pq1_provenance.csv` | the 15 PQ-1 v1 rule entries: code, name, status (specified / review-only / diagnostic / blocked), effect, condition, evidence, `active` |
| `output_manifest.csv` | input checks (recorded, recomputed and canonicalised hashes), output file and content hashes, the R4 diagnostic, counts per crop × source year × `pq_class`, the D-47 caveat. No timestamps, so it is byte-reproducible |
| `pq1_freeze_manifest.csv` | written once, before the reserved build: hashes of `pipeline.py`, the D-46/D-47/D-48 decision texts, the inputs, the rule table and the design-window rows |
| `build_log.csv` | one line per build (UTC time); reserved years as counts per `pq_class` only |
| `design/design_pq_summary.csv` | design-window counts per crop × comparability × `pq_class` × reasons |
| `audit/*.csv` (13 + `audit_manifest.csv`) | the hardened APY audit (F1–F16), design window only, no thresholds: units, key checks, yield consistency, missing/zero counts, zero-production rows, state-year sums, yield quantiles, annual methods, comparability changes, ambiguous rows, Total vs seasons, districts per year, history length |

**Contract columns:** `crop`, `apy_state`, `apy_district`, `apy_district_code` (APY's own code, not LGD/Census), `decision_agri_year`, `source_apy_year`, `available_from`, `information_rule`, `production_tonnes`, `area_ha`, `yield_t_per_ha`, `annual_method`, `seasons_reported`, `annual_comparability`, `pq_class`, `pq_reasons`, `pq_version`, `contract_version`.

**Transformations** (`build_context`)
- **Values:** values are copied as published. The only change: `yield_t_per_ha` is null where production is null, because the source encodes missing production with a yield of 0.
- **Rows:** nothing is repaired, clipped, imputed or deleted. A missing row means "not reported".
- **Timing (`apy_lag2_policy_v1`, D-47):** `decision_agri_year` = source year + 2, and `available_from` = 1 July of the decision year's start. This is a **policy assumption** (A-23), not a verified publication schedule.
- **`annual_comparability`:** `total_row` → `verified_total`; a single "Whole Year" row → `whole_year_row`; any other single season → `single_named_season`; several seasons without a Total → `ambiguous`. The four classes are never merged (A-24).
- **PQ-1 v1 (D-48):** flags only.
  - Active: R1, R2, R3, R8a (per crop and state), R9 (all crops), R10 (against the most recent earlier year with a row), R11, R12, R13.
  - R4 is a manifest diagnostic only.
  - Blocked, producing no flag: the R4 row flag, R5, R6, R7, R8b.
  - Precedence: unusable > review > annotated > ok.
- **R13 (Option 1):** all 37 annual rows of West Bengal (18) and Gujarat (19) Potato 1997-98 → `review`. No cause is asserted.

**Windows (D-47)**
- **Design:** all rule design, inspection and the audit use source years ≤ 2018-19.
- **Reserved:** 2019-20 … 2021-22 were built once, mechanically, after the freeze verified and the design-window rows came out identical to the frozen ones. They are reported only as counts. Their values are not used for rule design and are read only by approved downstream protocols.
- **Excluded:** 2022-23 rows are dropped immediately after loading.

**Input fingerprints** (checked by `verify_inputs()` before any value is used; the build fails on any mismatch)

| Input | Recorded in | Check | Result (2026-10-23) |
|---|---|---|---|
| raw APY file | `integration/audit/source_fingerprints.csv` | file SHA-256 | match |
| `apy_annual.csv` | `features_audit/input_fingerprints.csv`; `integration/audit/output_manifest.csv` | file SHA-256; content hash + shape | match |
| `apy_season.csv` | `integration/audit/output_manifest.csv` | content hash + shape | match |
| `district_crosswalk.csv` | `integration/audit/output_manifest.csv`; git HEAD | content hash + shape + schema; git blob vs HEAD | match after `alias_basis` canonicalisation; blob = HEAD |

**Crosswalk canonicalisation.** Phase 4 computed the crosswalk's content hash from the in-memory frame, where `alias_basis` held empty strings. CSV serialisation turns `""` into NaN on readback, so the plain recomputed hash (`e5aa5152…`) differs from the record (`a6d33dc8…`).
- Verification reports the recorded, the recomputed and a canonicalised hash.
- The canonicalised hash sets **only** `alias_basis` NaN to `""`, only after the expected 8-column schema is confirmed, and only for this comparison.
- It equals the record.
- The CSV, its recorded fingerprint and the Phase 4 manifest are unchanged.
- A synthetic test reproduces the discrepancy, and shows that a blank in any other column, or a schema change, still fails.

**Reproduce** (from the project root, `C:\Python313\python.exe -B`)
1. `-m Code.production.apy_audit`
2. `-m Code.production.pipeline design`
3. `-m Code.production.pipeline build`

The `freeze` stage runs once only and refuses a second run. The build refuses to run without a verified freeze or with D-46 – D-48 not recorded as ACCEPTED, and it reproduces every output byte for byte. Tests: `Code/tests/test_phase10_production_context.py`. Read-only walkthrough: `Notebooks/Phase_10_Production_Context.ipynb`, generated by `Code/utils/build_phase10_notebook.py`.

**Known limitations**
- No district-level APY release history is verified. The lag is not shown to be conservative for source years ≥ 2019-20, and the input is one 2023 vintage, so earlier years carry revised values.
- Implausible areas and yields are not flagged until R5 or R6 get their reference data.
- Boundary splits are not reconciled until R8b gets LGD or gazette history, so the trailing summary is deferred to v1.1.
- DES has not confirmed what "Whole Year" covers.

## Big Data component and dashboard lineage (course deliverables, 2026-10-23; not a numbered phase)

Produced by `Code/bigdata/` (PySpark 4.2.0, JDK 21, local mode) and read by `Code/app/` (Streamlit 1.57.0). Spark reads only; pandas writes the outputs, to the new folder `Processed_Data/bigdata/`. No Phase 4–10 artifact is modified.

```
Dataset/India Commodity Wise Mandi Dataset/{Onion,Potato,Wheat}.csv  (file SHA-256 vs integration/audit/source_fingerprints.csv)
Processed_Data/integration/district_crosswalk.csv                     (content hash, documented alias_basis canonicalisation; git blob = HEAD)
    → header check → explicit schema → try_to_date('dd MMM yyyy') → July–June year → window ≤ 2020-06-30
    → quality counts (no repair) · Spark SQL Q1 / Q2 / Q3 · RDD map/reduceByKey + word count
    → Processed_Data/bigdata/*.csv
Processed_Data/integration/mandi_apy_district_year.csv (Phase 4 pandas; shape vs record + git blob = HEAD)
    → parity vs Q1 → parity_report.csv
Code/app/data.py reads: Phase 8 validation predictions + test metrics · Phase 9 validation/test predictions + metrics
                        · Phase 10 product (source ≤ 2018-19 only) + its manifest counts · Processed_Data/bigdata/*
```

| Artifact (`Processed_Data/bigdata/`) | Contents | Rows |
|---|---|---|
| `district_year_spark.csv` | Q1: crop × APY district × agricultural year (records, markets, arrivals sum, exact median modal price, first/last date, duplicate-key rows) | 16,673 |
| `weekly_state_spark.csv` | Q2: crop × state × Monday week | 60,436 |
| `top_districts_spark.csv` | Q3: top 10 districts by arrivals per crop × year (`RANK()`) | 593 |
| `quality_checks.csv` | counts only, per crop (all-years: rows read, malformed rows, bad dates; window: every other check) | 39 |
| `parity_report.csv` | Q1 vs Phase 4 pandas: 8 checks, all 0 mismatches over 16,673 keys | 8 |
| `mapreduce_counts.csv`, `word_count.csv` | RDD `map` / `reduceByKey` (equal to SQL) and the variety word count; labelled "not Hadoop" | 93, 122 |
| `run_manifest.csv` | tool versions, window, input checks, row counts, output hashes (no timestamps; byte-reproducible) | — |
| `run_log.csv` | observed seconds per stage (append-only; not reproducible by design) | — |

**Dashboard outputs:** none. The app is read-only. Screenshots taken from the running app are in `Documentation/Final/screenshots/`.

**Reproduce:** follow `Documentation/Final/README_Setup.md`. Tests: `Code/tests/test_bigdata_spark.py` (synthetic fixture, compared with Phase 4's own pandas functions; the real-data parity test runs with `BDA_SPARK_REAL=1`) and `Code/tests/test_app.py`.
