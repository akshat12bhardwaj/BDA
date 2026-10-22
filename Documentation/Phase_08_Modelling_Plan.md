# Phase 8 Modelling Plan — Price Forecasting

**Status: [PHASE 8 EVALUATION COMPLETE].**
- The model selection is frozen (D-42), and the 2021–2022 test was run once (§N). The close-out is in §O, and the 2023+ holdout is reserved under §P.
- Sections A–F are the original plan, kept as written. §G–§N record what was implemented and found.
- The inference interface (§E) is still planned, and every path marked **(planned)** still does not exist.
- This plan applies the accepted decisions D-38 to D-42 (`Decision_Log.md`).

**Repository state when this plan was written (verified with git, 2026-10-22):** Git repository at the project root, branch `main`, HEAD `0716ab6` ("Initial commit"). Uncommitted at that time: `Documentation/EDA_Findings.pdf` deleted (intentional, to be committed later) and one tracked pytest bytecode file under `Code/tests/__pycache__/` rewritten by a test run. Phase 7 artifacts are at `Code/eda/analysis.py`, `Code/tests/test_phase07_eda.py`, `Code/utils/build_phase07_notebook.py`, `Notebooks/Phase_07_EDA.ipynb`, `Documentation/EDA_Findings.md` and `Documentation/Modelling_Readiness_Report.md`.

---

## A. Data contract

### A.1 Inputs (read-only)

| Input | Content | Expected SHA-256 (from `Processed_Data/eda/input_fingerprints.csv`) |
|---|---|---|
| `Processed_Data/features/features_onion.parquet` | 2,623,671 rows × 85 columns | `c480a598…35f9` |
| `Processed_Data/features/features_potato.parquet` | 2,764,417 rows × 85 columns | `3909e59f…c22f` |
| `Processed_Data/features/features_wheat.parquet` | 2,593,279 rows × 85 columns | `a01beaee…4beb` |
| `Processed_Data/features_audit/feature_registry.csv` | role of every column | — |

Phase 8 must hash the three feature files before and after building its dataset, refuse to run if they differ from the values above, and write the hashes to its own manifest. It must never write to `Dataset/` or to any Phase 4–7 output.

### A.2 Column roles (from `feature_registry.csv`)

| Role | Columns | Phase 8 use |
|---|---|---|
| `identifier` | `crop, state, district, market, variety, commodity_group, reported_date, market_code, source_row` | keys, week assignment and traceability only; never predictors |
| `target` | `modal_price_rs_per_quintal` (also min/max price, arrivals) | weekly target built from modal price only |
| `eligibility_flag` | `usable_modal_price`, `usable_arrivals` | decide which rows form targets and history |
| `audit_only` | `dup_status, price_extreme_level, arrivals_extreme_level, weather_*, apy_state, apy_district, apy_year, apy_year_lag2` | `price_extreme_level == "review"` drives the D-39 sensitivity run; never predictors |
| `predictor` | calendar, price history, arrivals history, `wx_*`, `apy_*_lag2` | candidate inputs, subject to Section B |

**Series key (D-33):** `(crop, state, district, market, variety)`, the same as `SERIES` in `Code/features/pipeline.py`. "Crop × market × variety" elsewhere in the documentation is shorthand for this key.

### A.3 Weeks, origins and targets (D-38)

- **Week:** Monday 00:00 to Sunday 23:59, the convention Phase 7 used in `weekly_horizon_feasibility.csv`. `week_start = reported_date − dayofweek` (pandas, Monday = 0).
- **Forecast origin `o(W)`:** the end of Sunday of week W. An origin exists for a series only when the series has at least one `usable_modal_price` row in week W. This matches Phase 7's denominator: 611,072 / 603,287 / 662,171 origin series-weeks (O/P/W).
- **Target `y(s, W, h)`:** the median of `modal_price_rs_per_quintal` over the series' `usable_modal_price` rows dated in week W + h, for h ∈ {1, 2, 4}. Each horizon is a separate dataset and model.
- **Missing target:** when week W + h has no usable price, the example is not scored and is never imputed. The target-availability share per crop, horizon and period is reported. Phase 7 measured 81–92% (Onion 91/88/86%, Potato 92/89/87%, Wheat 87/84/81% for h = 1/2/4).
- **Secondary task:** the next reported usable price after the origin. It is evaluated separately as a baseline task (D-38), never mixed with the weekly metrics.

### A.4 Series eligibility (D-41)

A series is in the **primary modelling population** if it has **≥ 365 rows with `usable_modal_price == True`** over the full feature-table history (2000-10-19 to 2024-02-02). Usable rows are unique per series and date (verified: usable row count equals distinct usable dates for every series), so this equals 365 distinct usable reporting days.

Recounted from the feature tables on 2026-10-22 (read-only); this matches Phase 7 `quality_readiness.csv`:

| Crop | Series total | Eligible series | Usable price rows kept | Share of usable rows |
|---|---|---|---|---|
| Onion | 3,924 | 1,473 | 2,420,920 of 2,595,611 | 93.27% |
| Potato | 4,003 | 1,551 | 2,539,948 of 2,731,271 | 93.00% |
| Wheat | 5,279 | 1,540 | 2,335,262 of 2,579,015 | 90.55% |

**Excluded series are not dropped from reporting.** Models are global per crop and horizon and use no series identifiers, so they can score excluded series. Phase 8 reports the excluded series' target availability and baseline/model errors in a separate table, labelled as outside the primary population.

**Origin-safe eligibility (implemented; clarifies D-41):** the full-history count above uses the validation, test and holdout years, so it is **retrospective and used for reporting only**. For modelling and evaluation, an example (series, origin W) is in the primary population when the series has **≥ 365 distinct usable price dates dated on or before the origin** (`eligible_at_origin`). A series therefore enters the population at the week its history reaches 365 dates and stays in it. Counts (`Processed_Data/modelling/phase08/eligibility_summary.csv`):

| Crop | Retrospective (full history) | Origin-eligible by end of train (2018-12-30) | … by end of validation (2020-12-27) | … by end of test (2022-12-25) | At any origin |
|---|---|---|---|---|---|
| Onion | 1,473 | 1,173 | 1,322 | 1,440 | 1,473 |
| Potato | 1,551 | 1,199 | 1,377 | 1,502 | 1,551 |
| Wheat | 1,540 | 1,297 | 1,423 | 1,507 | 1,540 |

**Training uses the refit date (implemented, D-41 clarification 2).** A model refitted at T trains on all examples (target week ended ≤ T) of series that had ≥ 365 usable dates by T, including their earlier weeks. This is decided by `eligible_from_origin <= T`: the first Sunday with ≥ 365 dates, which data dated ≤ T settles. Evaluation stays origin-eligible. Training examples recovered compared with origin-only eligibility (`training_population.csv`):

| Crop | h = 1 (2018-12-30 / 2020-12-27) | h = 2 | h = 4 |
|---|---|---|---|
| Onion | 101,290 / 115,151 | 98,375 / 111,912 | 95,268 / 108,534 |
| Potato | 96,097 / 110,623 | 93,394 / 107,582 | 90,533 / 104,402 |
| Wheat | 110,701 / 122,043 | 107,207 / 118,131 | 103,648 / 114,189 |

**Possible future sensitivity rule (not implemented):** span ≥ 2 years and reporting density ≥ 0.5 (491 / 592 / 335 series; `Modelling_Readiness_Report.md` §2).

### A.5 Flagged observations (D-39)

- Targets and history use only `usable_modal_price` (price) and `usable_arrivals` (arrivals) rows. This keeps suspected scale/entry errors and the 338 unresolved conflicts out. Phase 6 features already follow this rule (D-34).
- **Primary experiment:** eligible `review` rows (`price_extreme_level == "review"`) count in targets.
- **Sensitivity experiment:** drop every example whose target week contains a `review` price row, in both training and evaluation. Primary-model errors are also reported on this reduced sample, so the two runs compare like with like. History features are unchanged, because Phase 6 computed them with review rows included and Phase 6 is not regenerated.
- No flagged row is deleted from any file. `source_row` traces every target row back to Phases 4/5.

### A.6 Reproducible counts and fingerprints

For each crop × horizon × period, Phase 8 writes **(implemented, §G)** `Processed_Data/modelling/phase08/sample_counts.csv` with: origin series-weeks, examples with an observed target, eligible-population examples, excluded-population examples, review-sensitivity examples, and the weather-covered subset. It also writes `input_fingerprints.csv` (before/after hashes of the A.1 inputs) and `dataset_manifest.csv` (hash, rows and columns of each built dataset).

---

## B. Leakage-safe dataset construction

1. **Anchor row.** For each origin (series s, week W), the anchor is the series' last `usable_modal_price` row dated in week W, which is ≤ o(W).
2. **Predictors available at the origin:**
   - **Phase 6 features of the anchor row.** They use only data dated strictly before the anchor date (D-34), so before o(W).
   - **Origin-week aggregates** (median, last and count of usable modal prices; sum and count of usable arrivals in week W). They use rows dated ≤ o(W) only.
   - **Calendar features of the target week** (month, week of year, IMD season). They are deterministic from the date and carry no observed data.
   - Phase 6 feature *values* are used as they are. No Phase 6 calculation is changed or recomputed.
3. **Target strictly after the origin.** Every target row is dated in [o(W) + 1 day, o(W) + 7h days]. The dataset builder asserts `min(target date) > anchor date` and `> o(W)` for every example.
4. **Weather.** `wx_*` values come from the anchor row, so they cover days before the anchor date. They are NaN for windows that reach past 2022-12-31 (`feature_registry.csv`), and same-day weather is never used. Models for the holdout period use the **no-weather configuration**: all `wx_*` columns are removed, not NaN-filled.
5. **APY.** `apy_*_lag2` comes from the anchor row: production for agricultural year (origin agricultural year − 2), assumed published by then (A-19, D-36). It is one value per example, not repeated per day. When the target week crosses 1 July, the origin's value is still used; the target year's APY is never used.
6. **No imputation inside the dataset.** Missing predictors stay NaN. Any imputer or scaler a model needs is fitted on that fit's training examples only (Section C).
7. **Temporal boundaries and overlap.** Each example is assigned to the period that contains its **target week's Sunday**. A model fitted at refit date T uses only examples whose target Sunday is ≤ T. This purges training examples whose target window would overlap the evaluation period, which gives a gap of h weeks between the last training target and the first evaluated origin. Within one horizon, each (series, target week) appears once, so target windows do not overlap.
8. **Leakage tests (implemented, `Code/tests/test_phase08_dataset.py`; §G).**
   - Synthetic series with known weekly medians.
   - Perturbing every row after o(W) must not change any predictor.
   - The target must be strictly after the origin.
   - The period assignment must follow the target Sunday.
   - No identifier or `audit_only` column may be used as a predictor.
   - The holdout configuration must contain no `wx_*` column.
   - The input fingerprints must be unchanged.

---

## C. Evaluation protocol (D-40)

| Period | Target-week Sundays | Purpose |
|---|---|---|
| Train | 2002-01-06 – 2018-12-30 | fitting (expanding window). Rows before 2002 serve only as feature history |
| Validation 2019 | 2019-01-06 – 2019-12-29 | model selection, reported alone |
| Validation 2020 | 2020-01-05 – 2020-12-27 | model selection, reported alone (2020 market disruption; Wheat reporting −27%) |
| Validation combined | 2019 + 2020 | model selection, reported alongside the two years |
| Test | 2021-01-03 – 2022-12-25 | final evaluation, **used once** |
| No-weather holdout | 2023-01-01 – the last Sunday with complete target data (data ends 2024-02-02 for Onion/Potato and 2024-02-01 for Wheat; the partial final week is excluded) | no-weather models only |

**Rolling origins and refits:**
- Every week is an origin.
- Models are refitted quarterly, at the first Sunday of each quarter. Each refit uses all examples whose target Sunday is ≤ that date (expanding window, purge rule B.7).
- Preprocessing is fitted inside each refit, on that refit's training examples only.
- **No random row split** anywhere, including in hyper-parameter search, which uses the validation periods only.

**Model selection versus the final test:**
- Choose the model and hyper-parameters on combined-validation MAE.
- Report whether the winner changes under 2019-only or 2020-only ranking. If it does, say so; the choice is then not robust to 2020.
- Freeze the choice in a decision entry before the test is run.
- The test is then run once, refitted on examples with target Sunday ≤ 2020-12-27, with quarterly refits through 2021–2022. Test results are not used to change the model.

**Metrics** (on identical example sets for every model compared):
- MAE and RMSE in Rs/quintal.
- MAPE: prices are > 0 after Phase 5, so it is defined.
- Skill relative to persistence: 1 − MAE_model / MAE_persistence.
- All reported per crop × horizon × period, with the example count.

**Breakdowns:**
- Primary vs excluded series population.
- Training-only-eligible subgroup (A.4 caveat).
- Series history at the origin: usable observations before the origin < 365, 365–1,094, ≥ 1,095.
- Reporting coverage: anchor-row `modal_roll30d_count` 0–9, 10–19, ≥ 20.
- Primary vs review-sensitivity experiment (A.5).

**Weather ablation:**
- Each learner is fitted with and without `wx_*` features.
- Both versions are evaluated on the **same** weather-covered examples (anchor row has non-missing weather), in validation and test.
- The weather model must also beat the calendar-only baseline on that subset.
- EDA weather associations line up with the seasonal calendar and are treated as descriptive, not as evidence of predictive value (`EDA_Findings.md`).

---

## D. Baselines and candidate models (original plan; implemented and evaluated in §H–§N)

**Baselines** (all scored on the same examples as the models):
1. **Persistence:** predict the origin-week median of week W for every h.
2. **Seasonal naive:** the series' weekly median 52 weeks before the target week. It is scored only where that value exists; its coverage is reported.
3. **Next reported observation** (secondary task): the anchor price predicts the next usable price after o(W).
4. **Calendar-only:**
   - Prediction = persistence × the crop-level seasonal ratio (median price index of the target week's month / that of the origin week's month).
   - The index is estimated on training examples only, using each price relative to its series-year median (as in Phase 7 `seasonal_index.csv`, which itself is not used as an input).

**Candidate supervised models.** One global model per crop × horizon, trained on the pooled eligible series. Recommended target: log(y / origin-week median), inverted for metrics. Installed and usable without new packages: scikit-learn 1.8.0 and torch 2.12.0.
- `HistGradientBoostingRegressor`: handles NaN natively, which matches the no-imputation policy.
- `Ridge` on the same target, with a training-fitted median imputer and missing-value indicators.

**Deferred:**
- ARIMA/ARIMAX: statsmodels is not installed, and per-series fitting over about 4,500 series × quarterly refits is costly.
- N-BEATSX / LSTM (torch is available): considered only after the tabular models and baselines are in place.

No package is installed for this plan.

---

## E. Future inference and dashboard interface (contract only)

**Planned function** `Code/modelling/inference.py:predict_price(crop, state, district, market, variety=None, horizon_weeks, as_of=None)`:
- Loads a frozen model from `Outputs/Models/phase08/<model_version>/` (planned). That folder holds the model file, `model_card.json` (training period, feature configuration, input fingerprints, validation and test metrics) and the feature list.
- Builds the origin features with the Section B code, using data ≤ `as_of`. The default is the latest complete week.
- `variety=None` returns every variety of that market that has a series.
- `horizon_weeks` ∈ {1, 2, 4}.

**Output schema** (extends the roadmap's Phase 8 schema):

```
crop, state, district, market, variety, origin_date, target_week_start, target_week_end,
horizon_weeks, predicted_price, model_name, model_version, feature_config,
in_primary_population, prediction_status
```

- `prediction_status` is one of `ok`, `no_usable_price_in_origin_week`, `unknown_series` or `horizon_not_supported`. No value is returned without a trained model.
- Interval columns (`confidence_interval_lower/upper`) are added only once a calibrated method has been evaluated on validation data.
- The dashboard is not built in Phase 8 planning. Predictions must come from a versioned trained model through this interface, never from hardcoded values.

**Planned Phase 8 artifacts.** Only the dataset builder `Code/modelling/dataset.py`, its tests and the `Processed_Data/modelling/phase08/` manifests exist so far (§G). Still planned:
- `Code/modelling/` baselines, models and inference
- further `Code/tests/test_phase08_*.py`
- `Code/utils/build_phase08_notebook.py`
- `Notebooks/Phase_08_Price_Forecasting.ipynb`
- `Processed_Data/modelling/phase08/`
- `Outputs/Models/phase08/`
- `Outputs/Figures/phase08_*.png`

---

## F. Open items and risks

1. **Look-ahead in eligibility — resolved.** Evaluation uses `eligible_at_origin` and training uses eligibility at the refit date. The retrospective count is never used to select examples (A.4).
2. **Changing market coverage.** The set of reporting markets changes over time, so period-level metrics mix model quality with coverage (A-22, `EDA_Findings.md`). Per-period example counts are always reported.
3. **Nominal prices.** Log-ratio targets limit inflation effects at 1–4 week horizons. Level-based metrics in later years are larger partly because of inflation.
4. **Missing feature catalogue.** `Feature_Catalogue.md` is referenced in older documentation but does not exist. `Processed_Data/features_audit/feature_registry.csv` is the authoritative feature list.

---

## G. Implemented: dataset builder (`Code/modelling/dataset.py`)

**What it does:**
- **`run_build()`**
  - Hashes the three feature files and checks them against `Processed_Data/eda/input_fingerprints.csv` before reading.
  - Validates each table against `feature_registry.csv`: the same column set, boolean usable flags, datetime dates, a single crop, and usable prices > 0.
  - Builds the examples and runs the leakage checks.
  - Re-hashes all inputs, including the registry, and writes **CSV manifests only** to `Processed_Data/modelling/phase08/`: `input_fingerprints`, `dataset_manifest` (rows, columns and content hash per crop × horizon), `sample_counts`, `eligibility_summary`, `split_definition`, `feature_columns` and `provenance`.
  - Refuses an output directory inside any protected folder.
  - Fits nothing.
- **`build_examples()`** implements §A.3, §A.5 and §B:
  - Monday–Sunday weeks; the anchor row is the last usable-price row of week W.
  - Week-W aggregates come from rows dated ≤ origin.
  - Target-week calendar columns (`tw_*`).
  - The target is the week W + h median, inner-joined, so missing targets are not imputed.
  - Columns `target_has_review`, `weather_covered`, `eligible_at_origin` and the reporting-only `eligible_full_history`.
- **`validate_examples()`** raises unless all of these hold:
  - Weeks start on Monday and origins are Sundays.
  - The anchor row lies in week W, at or before the origin.
  - The target week is W + h, and all target data lie strictly after the origin and inside the target week.
  - The period matches the target Sunday.
  - Eligibility equals the origin count, and the count never decreases.
  - There is one example per series, origin and horizon.
  - No target, identifier, audit or bookkeeping column is a predictor.
- **`select()`** gives the modelling view per config (weather excludes the holdout and keeps `wx_*`; no_weather drops `wx_*`), experiment (primary / review_sensitivity) and population.
- **`refit_schedule()`, `refit_date_for()`, `training_examples()`** implement the quarterly expanding-window refits and the target-Sunday gap of §B.7.

**Results of the first build (2026-10-22):**
- Run time 36 s; inputs unchanged; the feature hashes equal Phase 7's record.
- A rebuild produced byte-identical manifests.
- Each crop × horizon dataset has 91 columns. Example counts (h = 1/2/4):
  - Onion: 554,377 / 540,178 / 523,004
  - Potato: 552,969 / 539,539 / 523,375
  - Wheat: 576,907 / 558,444 / 536,149
- Onion h = 1 equals Phase 7's 611,072 origin weeks × 90.72% target availability.

**Tests:** `Code/tests/test_phase08_dataset.py` has 37 tests, including negative tests that inject leakage and invalid inputs.
- Run it with `PYTHONDONTWRITEBYTECODE=1 python -m pytest Code/tests/test_phase08_dataset.py -p no:cacheprovider`.
- These settings stop tracked cache files from being rewritten.

**Not implemented yet:** the notebook and inference (§E). The calendar baselines and first models are in §I–J.

## H. Implemented: validation baselines (`Code/modelling/baselines.py`)

**What it does:**
- `run_baselines()` rebuilds the datasets with the hash-checked builder and scores, on **2019, 2020 and 2019–2020 combined only**:
  - persistence (origin-week median)
  - seasonal naive (the series' weekly median 52 weeks before the target week, where it exists)
  - persistence on the same seasonal subset
  - next-reported-observation (last known price → next usable price)
- Populations: origin-eligible (primary), review-sensitivity, and not-origin-eligible.
- The test and holdout periods are refused, both in code and in tests.
- Nothing is fitted.
- Outputs: `baseline_validation_metrics.csv`, `next_obs_validation_metrics.csv`.

**Results** (primary experiment, origin-eligible series), MAPE % for 2019 / 2020 / combined:

| Crop | Persistence h = 1 | h = 2 | h = 4 | Seasonal naive h = 1 |
|---|---|---|---|---|
| Onion | 8.8 / 12.1 / 10.4 | 12.9 / 19.7 / 16.1 | 19.0 / 33.3 / 25.6 | 65.5 / 44.2 / 55.6 |
| Potato | 7.0 / 8.0 / 7.5 | 10.0 / 12.6 / 11.2 | 14.5 / 18.5 / 16.3 | 33.6 / 50.0 / 41.2 |
| Wheat | 1.8 / 2.3 / 2.0 | 2.3 / 3.2 / 2.7 | 3.1 / 4.5 / 3.7 | 9.3 / 12.5 / 10.7 |

**Findings:**
- Persistence beats seasonal naive everywhere, by a wide margin. Year-on-year price levels move too much for last year's week to be a useful forecast.
- Seasonal-naive coverage is 86–91%.
- 2020 is clearly harder than 2019 for every crop and horizon (Onion h = 4 MAE 441 → 844 Rs/quintal). This is the reason to report the two years separately.
- The next-reported-observation baseline (median 1 day ahead) has MAPE 9.6 / 7.0 / 2.6% for Onion / Potato / Wheat over the combined validation years.

The test period (2021–2022) has not been scored.

## I. Model evaluation protocol (implemented in `Code/modelling/models.py`)

1. **Origin and target:** as §A.3. Weeks run Monday–Sunday, the origin is the end of Sunday of week W, and the target is the median usable price of week W + h (h = 1, 2, 4). Learned models predict log(target / origin-week median), converted back to a price for scoring.
2. **Features:**
   - The `feature_columns()` contract only: Phase 6 predictors of the anchor row, origin-week aggregates and target-week calendar fields (`tw_*`, fixed by the origin date and h).
   - Identifiers, targets, eligibility flags, audit columns and every `target_*` field are excluded and checked by `validate_examples()`.
   - `design_matrix()` is row-wise with no fitted state:
     - Prices are divided by the origin-week median.
     - Arrivals and APY quantities are put on a signed log1p scale.
     - The origin-week median becomes its log.
     - IMD season is one-hot over its four fixed categories.
3. **Populations:**
   - Training at refit T: `training_examples(ex, T)`, meaning target week ended ≤ T and the series reached ≥ 365 usable dates by T (D-41, clarification 2).
   - Evaluation: origin-eligible validation examples only.
4. **Refits and gaps:**
   - Refits fall on the first Sunday of each quarter. Each validation origin uses the latest refit on or before it.
   - The code checks:
     - Every training target ends ≤ the refit date ≤ the origin < the first target date.
     - No training target ends after 2020-12-27.
5. **No fitted state leaks across the split:**
   - Ridge's imputer and scaler sit inside the model pipeline, so they are fitted on training rows only.
   - The calendar benchmarks' monthly statistics come from training rows only.
   - Boosting runs with internal early stopping off, because it would draw a random split.
   - There is no random splitting anywhere.
6. **Validation years:** 2019, 2020 and combined, each assigned by the target Sunday.
7. **Metrics:** MAE and RMSE (Rs/quintal) and MAPE (%; every target is > 0 by the schema check). Every example has equal weight. Each model is compared with persistence on **identical rows** (`skill_mae_vs_persistence` = 1 − MAE / persistence MAE). Results are also reported on the weather-covered subset (weather ablation).
8. **Missing targets and review flags:**
   - Weeks without a usable target produce no example (§A.3).
   - The review-sensitivity run drops examples whose target week contains a `review` row, from both training and evaluation.
9. **Selection rule** (`select_models()`, validation only):
   - A candidate must beat persistence on MAE in **both** 2019 and 2020.
   - Among those, the highest **worst-year** skill wins, with combined skill as the tie-break.
   - If no candidate qualifies, persistence is kept.
   - So a model that does well in only one year cannot be selected.
   - The proposal is frozen in a decision entry before the test period is ever scored.

## J. First validation results (2026-10-22; validation only, test unscored)

**Models** (`models.py`):
- **Calendar climatology:** the only input is the target month. The prediction is that month's median training target, crop level. It is the only truly calendar-only forecast.
- **Calendar-adjusted persistence:** the last weekly median × the training median price change for the target month. It uses a historical price.
- **Ridge** (α = 1): with an imputer, missing-value indicators and a scaler, all fitted on training rows only.
- **HistGradientBoosting:** 200 iterations, 31 leaves, at least 100 rows per leaf, L2 = 1, early stopping off, seed 0.
- **Not included:** Random Forest was left out. On roughly 300k–400k training rows × 81 refits it is slow and adds little alongside boosting.

**Run details:**
- 9 quarterly refits per crop × horizon (2018-10-07 … 2020-10-04).
- 297k–406k training rows per refit. The last training target ends 2020-10-04.
- Total time 35 min.
- Per-refit sizes and timings are in `model_refit_log.csv`; the feature list is in `model_features.csv`.

**MAPE %, 2019 / 2020 / combined** (primary experiment, origin-eligible rows):

| Crop, h | Persistence | Calendar climatology | Calendar-adj. persistence | Ridge (weather) | HGB (weather) |
|---|---|---|---|---|---|
| Onion 1 | 8.8 / 12.1 / 10.4 | 46.5 / 45.7 / 46.1 | 8.8 / 12.1 / 10.4 | 8.7 / 10.8 / 9.7 | 8.7 / 13.6 / 11.1 |
| Onion 2 | 12.9 / 19.7 / 16.1 | 46.4 / 45.1 / 45.8 | 13.0 / 19.1 / 15.9 | 13.0 / 16.7 / 14.8 | 14.2 / 21.1 / 17.5 |
| Onion 4 | 19.0 / 33.3 / 25.6 | 46.4 / 44.3 / 45.4 | 18.9 / 30.2 / 24.1 | 18.4 / 25.1 / 21.5 | 20.2 / 34.4 / 26.7 |
| Potato 1 | 7.0 / 8.0 / 7.5 | 31.3 / 59.8 / 44.5 | 7.2 / 7.8 / 7.5 | 7.6 / 7.8 / 7.7 | 7.3 / 8.2 / 7.7 |
| Potato 2 | 10.0 / 12.6 / 11.2 | 31.3 / 59.9 / 44.5 | 10.5 / 12.0 / 11.2 | 11.0 / 12.1 / 11.5 | 11.3 / 14.4 / 12.7 |
| Potato 4 | 14.5 / 18.5 / 16.3 | 31.3 / 59.9 / 44.4 | 14.9 / 17.3 / 16.0 | 15.4 / 18.2 / 16.7 | 16.5 / 21.6 / 18.8 |
| Wheat 1 | 1.8 / 2.3 / 2.0 | 26.4 / 19.1 / 23.2 | 1.8 / 2.3 / 2.0 | 1.8 / 2.7 / 2.2 | 1.7 / 2.3 / 1.9 |
| Wheat 2 | 2.3 / 3.2 / 2.7 | 26.3 / 19.0 / 23.1 | 2.3 / 3.2 / 2.7 | 2.3 / 3.7 / 2.9 | 2.2 / 3.4 / 2.7 |
| Wheat 4 | 3.1 / 4.5 / 3.7 | 26.1 / 18.9 / 23.0 | 3.1 / 4.6 / 3.7 | 2.9 / 6.2 / 4.3 | 2.8 / 4.8 / 3.7 |

**Findings:**
- **Persistence is hard to beat.** Calendar climatology has 2.4–14.6× persistence's MAE: series price levels differ widely, and it uses no price information. Calendar-adjusted persistence is about equal to persistence (skill −0.09 to +0.11).
- **Onion: Ridge is the only consistent gain,** with MAE skill +0.01 / +0.14 (h = 1) and +0.03 / +0.28 (h = 4) for 2019 / 2020. The gain comes mostly from 2020; 2019 gains are 1–3%.
- **Wheat h = 1: HGB is the only gain,** at +0.06 / +0.01. Ridge is clearly worse than persistence on Wheat in 2020 (−0.14 to −0.33).
- **Potato: no model beats persistence in either year at any horizon.**
- **Stability:** the 2019 and 2020 rankings often disagree (for example HGB on Onion h = 4: −0.04 / +0.10). This is why the selection rule requires gains in both years.
- **Weather:** weather features change skill by at most a few points on the weather-covered rows, and not consistently. There is no evidence they add predictive value beyond the calendar and price history, which matches the EDA.
- **Review sensitivity:** dropping review-target weeks leaves the conclusions unchanged (`model_validation_metrics.csv`, experiment `review_sensitivity`).

**Selection proposal** (`model_selection_validation.csv`; not frozen and not test-scored):
- Onion h = 1: Ridge (no_weather)
- Onion h = 4: Ridge (weather)
- Wheat h = 1: HGB (weather)
- Every other crop × horizon keeps persistence.

**Limitations:**
- The 2019 skill of the proposed models is small (+0.01 to +0.06), and no uncertainty interval has been computed yet.
- Settings are fixed, with no tuning.
- Prices are nominal.
- Each model is a single global model per crop × horizon, with no series identity.

**Recommended next experiment** (step 1 done in §K):
1. Add a series-blocked bootstrap (or Diebold–Mariano) interval for the skill vs persistence, and require it to exclude zero in both years before freezing any selection.
2. Then try a small, pre-registered HGB variant that is shallower and more strongly regularized on the same protocol, because HGB overfits Potato.
- Keep the 2021–2022 test period untouched until a decision entry freezes the choice.

## K. Uncertainty of improvement over persistence (`Code/modelling/uncertainty.py`; validation only)

**Inputs:**
- `validation_predictions.parquet` (git-ignored; 4,417,497 rows from 2019–2020 only). Each row holds a model prediction and the persistence prediction for the same example.
- It was regenerated with unchanged settings. The regenerated `model_validation_metrics.csv`, `model_selection_validation.csv` and `model_features.csv` are byte-identical to the earlier run, and `model_refit_log.csv` differs only in wall-clock fit times. No new model was trained.
- The bootstrap runs in 44 s.

**Method:**
- **Resampling unit:** the series (state, district, market, variety within a crop).
  - All of a series' weekly examples in a year are resampled together. This keeps the strong within-series dependence over time (consecutive weeks share prices and overlapping history) inside a cluster.
  - Sensitivity: **market** clusters, which keep all varieties of one market together.
  - Every estimate has 699–932 clusters (minimum allowed 30), so no interval was suppressed.
- **Pairing:** a drawn cluster contributes all its rows, each with both the model and the persistence prediction.
  - The code checks that every model in a (crop, horizon, experiment, year) group is scored on identical rows and clusters.
  - All models in a group share the same bootstrap draws.
- **Repeated sampling:** a series drawn k times counts k times (multinomial weights over clusters).
  - A series that has no rows in a year is simply absent from that year's resampling.
  - 2019 and 2020 are resampled separately; "combined" resamples clusters with both years kept together.
- **Statistics:** example-weighted ratios of sums, the same as `score()`. Positive means the model reduces error.
  - MAE improvement = MAE(persistence) − MAE(model), in Rs/quintal.
  - Relative improvement = 1 − MAE(model) / MAE(persistence). It is defined because persistence MAE is never 0 here.
  - MAPE improvement in percentage points.
  - Series with more weeks carry more weight, as in the headline metrics.
- **Interval:** percentile 95% from **10,000 replicates**, seed 20261022, with a separate deterministic stream per group.
  - With 2,000 replicates, interval ends moved by up to 4.5% of their width and one borderline verdict flipped. With 10,000, the run still takes under a minute.
- **Verdict:** "better" or "worse" if the 95% interval excludes zero, otherwise "inconclusive".
- **Multiple comparisons:** there are 108 per-year primary comparisons, so a Bonferroni-style flag is also given: estimate / bootstrap SE > 3.55. A percentile far out in the tail would be too noisy for this.
- **Outputs:** `bootstrap_improvement.csv` (all crop × horizon × experiment × year × cluster level × model rows, with `n_obs`, `n_clusters`, three statistics with intervals, SE and flags), `bootstrap_selection_check.csv` and `bootstrap_provenance.csv`.

**Results for the proposed choices** (§J; primary experiment, series clusters). MAE improvement in Rs/quintal [95% CI] (relative improvement):

| Proposal | 2019 | 2020 | Supported in both years? |
|---|---|---|---|
| Onion h = 1, Ridge (no_weather) | +2.0 [−0.1, +3.9] (+1.0%); 796 series / 28,603 rows | +45.9 [+41.3, +49.5] (+14.0%); 789 / 26,535 | **No: inconclusive in 2019** |
| Onion h = 4, Ridge (weather) | +12.1 [+7.7, +16.1] (+2.7%); 785 / 27,790 | +232.8 [+223.1, +242.1] (+27.6%); 770 / 23,964 | **Yes**, also with market clusters and after Bonferroni (z = 5.7 / 47.9) |
| Wheat h = 1, HGB (weather) | +2.3 [+1.5, +3.0] (+6.4%); 860 / 31,847 | +0.4 [−0.3, +1.1] (+1.0%); 861 / 25,301 | **No: inconclusive in 2020** |

- **MAPE improvement (percentage points), 2019 / 2020:**
  - Onion h = 1: +0.06 [−0.07, +0.16] / +1.32 [+0.99, +1.53]
  - Onion h = 4: +0.64 [+0.43, +0.84] / +8.23 [+7.84, +8.61]
  - Wheat h = 1: +0.11 [+0.07, +0.14] / +0.02 [−0.01, +0.06]
- **Onion h = 4, Ridge (no_weather)** is also better in both years: +11.3 [+6.6, +15.6] / +231.3 [+221.5, +240.8]. Its result is almost identical to the weather version.

**Across all models:**
- Of the 108 per-year primary comparisons, 29 are "better", 69 "worse" and 10 "inconclusive". 27 remain "better" after the Bonferroni flag.
- Only Onion h = 4 Ridge (both configs) is better in **both** years.
- Potato: every learned model is worse than persistence in both years.
- Wheat h = 2 and h = 4: every model is better in 2019 and worse in 2020.
- Ridge on Wheat h = 4 in 2020 has a wide, skewed interval [−56.9, −12.1]. A few series with very large errors dominate it, so tail risk matters there.

**Review-row sensitivity:** with review-target weeks excluded, the conclusions are the same, with one exception. Onion h = 1 Ridge becomes barely "better" in 2019 (+2.2 [+0.1, +4.2]), which shows how fragile that estimate is.

**What these intervals do and do not measure:**
- They measure uncertainty **across series within one validation year**, given that year's market conditions.
- They do **not** capture shocks shared by all series in the same weeks: national supply shocks, policy and 2020 lockdowns. Those make series dependent, so the intervals are **too narrow** for a statement about the market as a whole. Market clustering covers only local dependence.
- They say nothing about **other years**. 2019 and 2020 are two draws of market conditions, and the sign of the improvement often flips between them (Wheat h = 2/4, Onion h = 2). Year-to-year variation is clearly larger than the within-year interval widths, and two years cannot estimate it.
- Uneven series lengths: series with more weeks weigh more, by design (example-weighted). A series-weighted view could differ.

**Status:** Onion h = 4 Ridge is the only proposal supported in both validation years. The Onion h = 1 Ridge and Wheat h = 1 HGB proposals are **inconclusive**. No choice is frozen, no decision entry has been added, and 2021–2022 and the holdout remain unscored.

## L. Pre-specified before fitting (2026-10-22): one conservative HGB run and the selection criteria

Written before the conservative model was fitted or any of its results were seen. The selection criteria below are written after the §J/§K results for the existing models were known; that is stated plainly here, not hidden.

**L.1 The single conservative configuration** (`hgb_conservative` in `models.py`; the existing `hgb` stays as the control):

| Setting | Control `hgb` | `hgb_conservative` | Why more regularized |
|---|---|---|---|
| `learning_rate` | 0.1 | 0.05 | Half the step size, same 200 iterations: smaller total boosting effect (0.05 × 200 = 10 vs 20). |
| `max_leaf_nodes` | 31 | 15 | Shallower trees, so fewer feature interactions. About 90 inputs and a noisy weekly log-ratio target do not support deep interactions. |
| `min_samples_leaf` | 100 | 1,000 | Each leaf averages ≥ 1,000 series-weeks, about 0.3% of a 300k–400k-row training set, instead of a few series' weeks. Leaves fitted to a handful of series were the likely cause of the Potato losses. |
| `l2_regularization` | 1.0 | 10.0 | Shrinks leaf values towards zero, that is, towards persistence, because the target is the log-ratio to the origin-week median. |
| `max_iter`, `early_stopping`, `random_state` | 200, off, 0 | unchanged | Same budget; no random internal validation split. |

**Everything else is unchanged:**
- Features (`design_matrix`), training population (eligibility judged at the refit date), quarterly refits, horizons, origin-eligible validation rows, 2019 / 2020 / combined.
- Runs: weather and no_weather (primary), and weather (review sensitivity), the same runs as the control.
- Outputs use the prefix `hgb_conservative_`, so no existing output is overwritten.

**Stopping rule:** this is the only configuration. If it does not meet L.2 anywhere, no further boosting configurations will be tried on 2019–2020.

**L.2 Criteria for proposing a learned model over persistence**, applied to every crop × horizon. All four must hold:

1. **Within-year evidence:** the 95% paired bootstrap interval for the MAE improvement is above 0 in **both** 2019 and 2020, with **both** series and market clusters.
2. **Multiplicity:** estimate / bootstrap SE > 3.58 in both years. This is the two-sided Bonferroni cut-off for the expanded family of 144 per-year primary comparisons: 8 model/configs × 9 crop-horizons × 2 years. The original 3.55 is also reported.
3. **Practical size:** relative MAE improvement ≥ **2.0%** in **each** year. Smaller gains are within the quarter-to-quarter swings seen in §K and would not change trading decisions.
4. **Review robustness:** criteria 1 and 3 also hold in the review-sensitivity run. That run exists only for the weather configuration, so only weather-config candidates can pass all four.

**Reported but not a gate:** the share of the 9 refit quarters with a positive improvement, which gives a coarse view of stability over time. Nine blocks inside two years cannot measure robustness across years or market-wide shocks, so this stays descriptive.

## M. Audit, the conservative-HGB result and a selection proposal for human review (2026-10-22; validation only)

**M.1 Audit of §K (checked against the saved artifacts):**
- **Pairing:** correct. In every (crop, horizon, experiment) group, all models are scored on one identical row set with the same persistence value per row. Cluster and row counts agree across models (0 mismatching groups).
- **Clusters:** series = (state, district, market, variety); market = (state, district, market).
- **Bonferroni:** the family is the 108 per-year primary comparisons: 6 model/configs (calendar climatology, calendar-adjusted persistence, Ridge and HGB, each with and without weather) × 9 × 2. **Discrepancy:** the code's 3.55 is described as the two-sided cut-off for 108 tests, but the exact value is 3.50 (one-sided 3.31). 3.55 is slightly more conservative. It is kept unchanged and only the description is corrected here. No verdict depends on the difference.
- **Sensitivity coverage:**
  - Review-sensitivity runs exist only for calendar-adjusted persistence, Ridge (weather) and HGB (weather).
  - The weather ablation on the weather-covered subset has point metrics only; it was **not** bootstrapped.
- **Pre-specification, stated plainly:**
  - The §I rule (beat persistence in both years) was written before the first model results.
  - The interval requirement (§J step 1) was added after the point results, but before any interval was seen.
  - The §L.2 criteria, including the **2% practical threshold, were written after the Ridge and HGB intervals were known.** Onion h = 4 Ridge's 2019 gain (+2.7%) is just above that threshold, so criterion 3 is **not independent evidence** for Ridge. It is independent for `hgb_conservative`, which was fitted after §L was written.
- **Stability of Onion h = 4 Ridge:**
  - Relative improvement by refit quarter: −19.3, +1.4, +10.2, +12.8, −3.7, +46.0, +8.8, +9.8 and +25.7%, positive in 7 of 9 quarters.
  - The 2019 gain is small (+2.7%) and comes from Q2–Q3. The 2020 gain (+27.6%) is concentrated in the 2020 price spike.

**M.2 The single conservative HGB run** (§L.1 settings; control unchanged):
- **Runtime:** 11 min of fitting across 3 runs × 81 refits. The last training target ends 2020-10-04. Files use the prefix `hgb_conservative_`, and all 18 earlier Phase 8 outputs were checked byte-identical afterwards.
- **Skill vs persistence (MAE), 2019 / 2020, weather config, primary:**

| Crop | h = 1 control → conservative | h = 2 | h = 4 |
|---|---|---|---|
| Onion | +0.01 / −0.06 → **+0.06 / +0.14** | −0.13 / +0.03 → −0.06 / +0.13 | −0.04 / +0.10 → −0.01 / +0.15 |
| Potato | −0.07 / −0.03 → −0.03 / +0.04 | −0.17 / −0.13 → −0.13 / −0.06 | −0.19 / −0.12 → −0.13 / −0.08 |
| Wheat | +0.06 / +0.01 → +0.07 / −0.00 | +0.07 / −0.05 → +0.07 / −0.04 | +0.11 / −0.06 → +0.10 / −0.03 |

  MAPE and RMSE move the same way (`hgb_conservative_validation_metrics.csv`).
- **Effect of regularization:** it helped in every Onion and Potato cell, and roughly tied the control on Wheat.
- **Potato:** still worse than persistence in 2019 at every horizon, and in 2020 at h = 2 and 4. The only positive cell is 2020 at h = 1: +5.4 [+3.7, +7.2] Rs/q (+3.5%), with 2019 at −3.1%.
- **The negative result stands:** per the §L stopping rule, no further configurations are tried.
- **Paired bootstrap (series clusters), Onion h = 1 weather:**
  - 2019: +11.0 [+8.5, +13.4] Rs/q (+5.5%, z = 9.0)
  - 2020: +44.7 [+41.5, +47.9] Rs/q (+13.7%, z = 27.2)
  - Review sensitivity: +10.3 [+7.8, +12.7] / +41.8 [+38.5, +45.0]
  - Positive in 8 of 9 refit quarters
  - Full table: `hgb_conservative_bootstrap_improvement.csv`

**M.3 Proposed selection, for human review and not frozen** (`selection_proposal.csv`, `selection_candidates.csv`). Persistence is the default unless a candidate passes all four §L.2 criteria:

| Crop, h | Proposal | Within-year evidence (95% CI, both years) | Practical size (≥ 2% both years) | Without review targets | Quarters positive | Robustness across years / shocks |
|---|---|---|---|---|---|---|
| Onion 1 | **hgb_conservative (weather)**, provisional | yes (z 9.0 / 27.2) | yes (+5.5 / +13.7%) | yes | 8/9 | untested beyond 2019–2020 |
| Onion 2 | persistence | no candidate positive in 2019 | – | – | – | – |
| Onion 4 | **Ridge (weather)**, provisional | yes (z 5.7 / 47.9) | marginal (+2.7 / +27.6%); threshold set post hoc | yes | 7/9 | gain driven by 2020 |
| Potato 1 | persistence | every learned model worse in 2019 | – | – | – | – |
| Potato 2 | persistence | every learned model worse in both years | – | – | – | – |
| Potato 4 | persistence | every learned model worse in both years | – | – | – | – |
| Wheat 1 | persistence | HGB / hgb_conservative inconclusive in 2020 | – | – | – | – |
| Wheat 2 | persistence | every candidate worse in 2020 | – | – | – | – |
| Wheat 4 | persistence | every candidate worse or inconclusive in 2020 | – | – | – | – |

**What M.3 does and does not show:**
- **Statistical vs practical:** with about 25k–30k rows per year, even small gains are "significant" across series. The 2% floor and the review check guard practical relevance. The Onion h = 4 Ridge 2019 gain is significant but only marginally above that floor.
- **Within-year vs across-year:** every interval is conditional on that year's market conditions. Common national shocks are not resampled, so the intervals overstate certainty about the market as a whole. Two years cannot show robustness across regimes; 2020 was an unusual year.
- **Selection effects:** `hgb_conservative` was the 7th/8th model configuration compared on the same two years. The Bonferroni cut-off covers that family, but not the earlier decisions about which models to try.

**Recommended human decision:**
- Either accept M.3 as a provisional selection, or keep persistence for Onion h = 4 until more evidence exists, given the post-hoc threshold.
- Then freeze it in a decision entry **before** running the single 2021–2022 test evaluation.
- Do not tune further on 2019–2020. The test period is the next independent evidence.

**Outcome:** the project owner chose Onion h = 1 `hgb_conservative` and persistence everywhere else, with Onion h = 4 Ridge recorded as exploratory (D-42).

## N. Final 2021–2022 test evaluation (run once, 2026-10-22; `Code/modelling/final_evaluation.py`)

**Freeze and pre-run checks:**
- `test_freeze_manifest.csv` holds the SHA-256 of `dataset.py`, `models.py`, `baselines.py`, `uncertainty.py`, `final_evaluation.py` and `feature_registry.csv`, the D-42 selection, and the full `hgb_conservative` settings. It was written and verified before the run, and verified again afterwards.
- Before the run:
  - Both validation prediction files contained only 2019–2020 rows.
  - Every selection fit's last training target was 2020-10-04.
  - No `test_*` output existed.
- The only earlier contact with test-period rows was the example **counts** in `sample_counts.csv`. They contain no targets or errors.
- `run_test_evaluation()` refuses to start if any frozen file changed, and refuses to run a second time.

**Protocol (D-42):**
- **Rows:** eligible-at-origin test rows (target Sundays 2021-01-03 … 2022-12-25), reported for target years 2021, 2022 and combined.
- **Refits:** each origin uses the latest quarterly refit ≤ origin (2020-10-04 … 2022-10-02), trained on `training_examples(ex, refit)`. Training sets grew from 384k to 456k rows, and the last training target is 2022-10-02, so no 2023+ data was used.
- **Comparison:** each selection vs persistence on identical rows.
- **Uncertainty:** paired bootstrap as in §K (series and market clusters, 10,000 replicates, seed 20261022).
- **Runtime:** 62 s.
- **Holdout:** the 2023+ holdout was not evaluated.

**Results** (`test_results.csv`, `test_bootstrap.csv`, `test_refit_log.csv`, `test_provenance.csv`):

| Crop, h | Approach | MAE 2021 / 2022 / combined (Rs/q) | RMSE combined | MAPE % 2021 / 2022 / combined | Rows combined (series) |
|---|---|---|---|---|---|
| Onion 1 | hgb_conservative | 239.1 / 141.5 / 187.1 | 338.4 | 10.2 / 7.7 / 8.8 | 63,887 (909) |
| Onion 1 | *persistence on the same rows* | 227.3 / 146.4 / 184.2 | 354.5 | 9.8 / 8.3 / 9.0 | 63,887 (909) |
| Onion 2 | persistence | 355.3 / 213.6 / 279.7 | 481.8 | 15.5 / 12.2 / 13.7 | 63,060 (901) |
| Onion 4 | persistence | 531.7 / 314.5 / 415.8 | 675.9 | 24.5 / 18.6 / 21.3 | 61,967 (891) |
| Potato 1 | persistence | 94.9 / 93.4 / 94.1 | 196.3 | 7.7 / 6.4 / 7.0 | 61,447 (892) |
| Potato 2 | persistence | 144.9 / 132.9 / 138.6 | 258.8 | 12.1 / 9.3 / 10.6 | 60,648 (887) |
| Potato 4 | persistence | 247.5 / 186.5 / 215.3 | 369.7 | 21.6 / 13.5 / 17.3 | 59,564 (886) |
| Wheat 1 | persistence | 42.1 / 50.2 / 46.4 | 105.1 | 2.2 / 2.2 / 2.2 | 60,591 (952) |
| Wheat 2 | persistence | 56.5 / 66.7 / 62.0 | 126.2 | 3.0 / 3.0 / 3.0 | 59,690 (943) |
| Wheat 4 | persistence | 79.5 / 92.6 / 86.6 | 149.2 | 4.3 / 4.1 / 4.2 | 58,431 (935) |

For persistence cells the selected approach is persistence, so the improvement is 0 by construction.

**Onion h = 1, `hgb_conservative` vs persistence** (MAE improvement, positive = better; 95% CI, series clusters):

| Period | Rows (series) | MAE improvement (Rs/q) | Relative | MAPE (pp) | RMSE (Rs/q) | Verdict, series / market clusters |
|---|---|---|---|---|---|---|
| 2021 | 29,879 (788) | −11.7 [−14.3, −9.2] | −5.2% [−6.3, −4.1] | −0.42 [−0.52, −0.31] | +23.1 | worse / worse |
| 2022 | 34,008 (855) | +4.8 [+0.0, +8.5] | +3.3% [+0.0, +5.9] | +0.57 [+0.48, +0.67] | +8.5 | better / inconclusive |
| Combined | 63,887 (909) | −2.9 [−5.8, −0.3] | −1.6% [−3.2, −0.2] | +0.11 [+0.03, +0.19] | +16.2 | worse / worse |

**Interpretation:**
- The validation advantage (+5.5% / +13.7%) did **not** carry over. In 2021 the model is clearly worse than persistence on MAE. In 2022 it is slightly better, but that is borderline and not robust to market clustering.
- RMSE improves in both test years. The model reduces the largest misses but adds many small ones, which is consistent with damping towards seasonal or recent-trend patterns that helped in the 2020 spike.
- Under D-42 this result does **not** reopen the selection, and no setting was changed.
- What the evidence supports: across 2019–2022, persistence is the most reliable forecast for every crop and horizon. The one learned model's gains depend on the market regime.

**Limitations:**
- The intervals cover variation across series within one year. They do not cover shocks shared by all series, or other years.
- Two test years are still two regimes.
- Persistence cells carry no comparison uncertainty because they equal the benchmark.
- The test evaluation scores the primary experiment only; no review-sensitivity variant was pre-specified for the test.

## O. Phase 8 close-out (2026-10-22)

**Validation and test are kept separate.**
- **Validation (2019–2020)** was used for every modelling choice (§H–§M):
  - Onion h = 1 `hgb_conservative` (weather) passed all four §L.2 criteria: +5.5% / +13.7% relative MAE improvement over persistence.
  - Onion h = 4 Ridge also passed, but D-42 records it as exploratory only.
  - No candidate passed for any other crop or horizon.
- **Test (2021–2022)**, scored once after the freeze and never used for selection (§N):
  - **Conservative Onion one-week boosting failed to beat persistence overall:** MAE −1.6% [−3.2, −0.2] combined; −5.2% in 2021; +3.3% in 2022, borderline and not robust to market clusters.
  - Every other cell is persistence by D-42.

**The RMSE / MAE trade-off:**
- The boosted model lowered RMSE in both test years (by 23.1 and 8.5 Rs/q) while raising MAE overall. It reduces a few large misses but adds many small errors.
- MAE is the primary metric (D-40, §C), so the model is not preferred on the test.
- Users who care mainly about avoiding large misses would weigh the two differently. That is a future objective choice, not a reason to reopen D-42.

**Limitations that apply to every result above:**
- **Series-level uncertainty only:** the paired bootstrap resamples series (or markets) within one year. It does not resample weeks or shared national shocks, so its intervals are narrower than the true uncertainty about the market as a whole.
- **Market-wide shocks:** lockdowns, export policy and national supply shortfalls hit all series at once. Such a shock, rather than the model, can explain a 2020 gain that did not repeat in 2021.
- **Two test years:** 2021 and 2022 are two market regimes. Together with the two validation years, four years cannot establish performance across regimes.
- **Nominal prices**, persistence-dominated targets, and weather covering only about 25% of rows (ending 2022-12-31).

**What Phase 8 delivers to the next phases:**
- Point forecasts of the weekly median modal price per series for h = 1, 2 and 4 weeks: persistence everywhere, with Onion h = 1 by `hgb_conservative` under D-42.
- Measured error levels per crop, horizon and year (`test_results.csv`, `baseline_validation_metrics.csv`).
- No calibrated prediction intervals yet.
- **Practical reading:** the forecast for a market h weeks ahead is essentially its current weekly median. Downstream decisions must not assume forecasts carry information beyond current prices; they should carry each crop × horizon's measured error level instead.

**Unresolved items:**
- The inference interface (§E) is not built.
- The Phase 8 output schema in `Future_Work_Roadmap.md` lists confidence-interval columns. They cannot be filled until an interval method is validated.
- No literature review exists in the repository to align methods against.

## P. Pre-specified protocol for the 2023+ no-weather holdout (defined 2026-10-22; NOT evaluated)

**Purpose:** one further, independent out-of-time check, in a third market regime and without weather data, of persistence and of D-42's learned cell in a form that can run without weather. **It cannot change D-42.** Any change to the selection needs a new decision entry, and the holdout result alone is not enough evidence for one.

**Rows:**
- Origin-eligible examples (D-41 at the origin) whose target Sunday falls between 2023-01-01 and the last Sunday on or before the crop's last reported date, so that no target week is partial.
- With the current data that last Sunday is 2024-01-28 for all three crops (inputs end 2024-02-02 / 2024-02-02 / 2024-02-01).
- Primary experiment; results for target year 2023 and for 2024-01 separately, and combined.

**Approaches** (exactly these, fixed now):

| Cell | Approach |
|---|---|
| every crop × horizon | persistence (the D-42 choice) |
| Onion h = 1 | additionally, `hgb_conservative` with the **no_weather** feature config and unchanged settings |

- The weather-config model selected in D-42 cannot run: its weather features are missing after 2022-12-31.
- The no_weather variant passed validation criteria 1–3 (+5.11% / +12.55%); criterion 4 was not run for it.
- It is reported as a comparison, never as a replacement.

**Refits:**
- The latest quarterly refit on or before each origin (2022-10-02 … 2024-01-07), trained on `training_examples(ex, refit)` with no_weather features.
- Training uses targets that ended by the refit date, including 2021–2022 test targets, which are by then in the past.

**Metrics and uncertainty:**
- MAE (primary), RMSE and MAPE, compared with persistence on identical rows.
- The same paired bootstrap as §K/§N: series and market clusters, 10,000 replicates, seed 20261022.
- The same limitations apply. 2024 contributes only about four weeks.

**Safeguards (to implement before running):**
- A separate freeze manifest: code hashes plus this protocol.
- A run-once guard writing `holdout_results.csv`.
- Checks that no target after the last complete week and no row outside the holdout is scored.
- No changes to D-42, and no tuning or selection.

**When:** only after the Phase 8 checkpoint is committed and the project owner approves running it.
