# Phase 8 Modelling Plan — Price Forecasting

**Status: [PLAN — approved decisions; dataset builder IMPLEMENTED, models NOT implemented].** The dataset builder and its leakage tests exist (§G). No model has been trained, and no baseline, model or inference code exists. This plan applies the accepted decisions D-38 to D-41 (`Decision_Log.md`). Every path marked **(planned)** does not exist yet.

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

Consequence: the early weeks of each series, before it reached 365 dates, are outside the primary population. In the training period this removes about a third of examples with an observed target. At h = 1, 113,966 / 107,790 / 123,471 training examples are retrospectively eligible but not origin-eligible (`sample_counts.csv`, column `examples_full_history_but_not_origin_eligible`). Those examples stay in the dataset with `eligible_at_origin = False` and are reported as the non-eligible population.

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

## D. Baselines and candidate models (planned, not implemented)

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

1. **Look-ahead in eligibility — resolved in the builder.** Selection uses `eligible_at_origin`, never the retrospective count (A.4). **Open for approval:** whether training should use only origin-eligible examples (the current default in `select()`) or also the earlier, not-yet-eligible weeks of a series. Those weeks are leakage-safe; they are excluded only by the population rule.
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

**Not implemented yet:** baselines, models, metrics, the notebook and inference (§C–E).
