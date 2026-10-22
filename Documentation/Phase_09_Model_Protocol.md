# Phase 9 Learned-Arrivals Experiment Protocol — `phase9-arrivals-protocol-v1`

**Status: [APPROVED 2026-10-22 by the project owner (D-44); proposed earlier the same day].** The text below is the protocol as proposed; the approved answers to its open questions are recorded in §9.
- The protocol is implemented in `Code/modelling/arrivals_models.py`. `PROTOCOL_STATUS = "APPROVED"`, and `fit_predict()` also requires the D-44 heading in `Decision_Log.md` to read ACCEPTED.
- **Fitting is authorised under this exact protocol only:** no added candidates, no tuning, and no change to the selection rule after results are seen.
- The protocol builds on D-43 (accepted) and the AQ-1 v1 derived flags (`Phase_09_Arrivals_Plan.md` §12–§15).
- **Not used:** any data after 2020-12-27; the 2021–2022 test and 2023+ holdout stay reserved.

## 1. Candidates and baselines (fixed before fitting; no tuning)

| Role | Name | Definition |
|---|---|---|
| Primary baseline | `persistence` | origin-week median (D-43) |
| Exploratory reference | `calendar_adjusted_persistence` | reported only; **never selectable** (D-43; it failed the 2% criterion, §13 of the arrivals plan) |
| Candidate | `ridge` | median imputer with missing-value indicators, standard scaler, `Ridge(alpha=1.0)`; imputer and scaler fitted on each refit's training rows only |
| Candidate | `hgb_conservative` | `HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=1000, l2_regularization=10.0, early_stopping=False, random_state=0)`, the Phase 8 §L.1 setting; missing values handled natively |

**Fitting:**
- One model per crop × horizon, global across series, with no series identifier.
- **Target:** log1p(target) − log1p(origin-week median). Predictions are converted back with expm1 and clipped at 0.
- **Refits:** quarterly expanding refits at the first Sunday of each quarter. Each validation origin uses the latest refit on or before it, and training targets end on or before the refit date (D-40 / D-43).

## 2. Features: as of the forecast origin (end of Sunday of week W)

All features are computed from weekly medians of **Phase 5-usable arrivals in weeks ≤ W**, and from usable prices for the price feature. An unreported week is **missing, never zero**, and nothing is carried forward. The probe `leakage_probe()` replaces every value after a probe origin with 1e9 and requires all features up to that origin to stay unchanged; this is tested and also run in the notebook.

| Feature | Construction |
|---|---|
| `f_log_origin` | log1p(origin-week median arrivals) |
| `f_origin_reported_days` | reported days in week W (1–7) |
| `f_log_n_dates` | log1p(distinct usable arrival dates ≤ W) |
| `f_lag{1,2,4,52}_logratio` | log1p(median of calendar week W − k) − `f_log_origin`; missing if that exact week was not reported |
| `f_med4_logratio`, `f_med13_logratio` | median of the previous 4 / 13 *reported* weekly medians (week W excluded), as a log ratio to the origin |
| `f_weeks_reported_13` | number of reported weeks among calendar weeks W − 12 … W |
| `f_has_price` | at least one usable price in week W |
| `f_price_logchange_4w` | log(median usable modal price in W) − log(the same in W − 4); missing if either week has no usable price |
| `tw_month_sin`, `tw_month_cos`, `tw_week_of_year` | calendar of target week W + h, which is fixed by the origin and h |

**Not used:**
- weather, because it covers only about 25% of rows and Phase 8 found no benefit;
- APY;
- identifiers;
- any AQ-1 field, because a row's flag is never knowable for the origin week.

## 3. Populations and the AQ-1 / provider-query handling (proposed)

**Primary evaluation population: AQ-1 v1 `aq1_likely`.**
- **Evaluation targets** exclude the three likely-error classes retrospectively. A target week whose rows are all excluded yields no example.
- **Training targets** at refit r are cleaned only if every excluded row of that week has `aq1_available_from` ≤ r; otherwise the original value is used.
- **Features and eligibility** stay on the Phase 5 view.

**Sensitivity population: the original** (no AQ-1). It is reported for every candidate and is part of the selection rule (§5, criterion 4).

**Handling of other classes:**
- `isolated_spike` and `sustained_shift`: review-only, kept.
- Wheat March–May exception: not applied in the primary population, because it made no measurable difference (§13).

**`provider_query_pending` rows (proposed):** handled by their AQ-1 class only. The 1,475 Wheat MP rows classed `likely_unit_error_low` are excluded as likely errors; the remaining pending rows are kept until the provider answers. A sensitivity run that excludes all pending rows from targets is proposed (open decision U3).

## 4. Metric, uncertainty and validation years

- **Primary metric:** log MAE = mean |log1p(forecast) − log1p(actual)|, on identical evaluation rows for the candidate and persistence.
- **Secondary metrics** (reported): MAE and median absolute error (t/day), and WAPE.
- **Validation years:** 2019 and 2020, **reported and judged separately**; the combined figure is shown but never used to select.
- **Uncertainty:** a paired cluster bootstrap of the log-MAE improvement over persistence (`arrivals.bootstrap_log_mae`).
  - Whole series are resampled, with markets as a second clustering.
  - 10,000 replicates, seed 20261022, percentile 95% intervals.
  - It does not capture nationwide shocks, so intervals are within-year only.

## 5. Selection rule (`arrivals_models.select`)

A candidate is proposed for a crop × horizon only if **all** of these hold:
1. The 95% interval of the improvement is above 0 in **both** 2019 and 2020, under **both** series and market clustering (primary population).
2. Estimate / SE > **3.197** in both years: the two-sided Bonferroni cut-off for the 36-test family (2 candidates × 3 crops × 3 horizons × 2 years).
3. Relative log-MAE improvement ≥ **2.0%** in **each** year, the practical criterion carried over from Phase 8 §L.2.
4. On the **original** population, the series-cluster interval is also above 0 in both years.

Among candidates that pass, the one with the higher worst-year relative improvement is proposed. Where none passes, **persistence stays**. A proposal becomes a selection only through a new decision entry made **before** any test-period evaluation.

## 6. Missing data, small series and failed fits

- **Missing features:**
  - Ridge uses a median imputer with missing indicators, fitted on training rows only.
  - HGB handles missing values natively.
  - Missing values are never filled using later data.
- **Small series:** only origin-eligible series are evaluated (≥ 365 usable arrival dates by the origin). Training uses series eligible by the refit date. Other series are not forecast by a learned model; they keep persistence.
- **Failed fits:** a fit that raises, or yields non-finite predictions, for a crop × horizon × refit is recorded as **failed** for that crop × horizon. Persistence is kept there, and there is no retry with other settings and no tuning.

## 7. Execution and environment

- **Notebook:** `Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb`, generated by `Code/utils/build_phase09_notebook.py`.
- **Before approval it:**
  - loads and validates the data
  - builds the features and runs the leakage probe
  - reproduces the frozen persistence baseline (27 cells, with identical counts and |Δ log MAE| ≤ 1e-12, the CSV float round-trip)
  - prepares the AQ-1 population
  - shows the selection rule

  The training and selection cells skip with a message.
- **Outputs** go to `Processed_Data/modelling/phase09_models/`.
- **Environment:** run with the project interpreter, Python 3.13 (pandas 2.3.3, numpy 2.3.3, scikit-learn 1.8.0), via `Code/utils/run_phase09_notebook.py`. The default `python3` Jupyter kernel on this machine resolves to Anaconda Python 3.12 (scikit-learn 1.5.1). The notebook records the interpreter it ran with.

## 8. Decisions requiring approval before any fit (unresolved)

- **U1.** Approve, amend or reject this protocol: candidates, features, target transform, refits and selection rule.
- **U2.** Approve AQ-1 v1 `aq1_likely` as the primary population, with the original population as sensitivity and criterion 4.
- **U3.** Handling of `provider_query_pending` rows until the provider answers: class-based only (proposed), or also a sensitivity run excluding all of them.
- **U4.** Keep the Wheat calendar adjustment exploratory (proposed: yes).
- **U5.** The environment for approved runs: use `run_phase09_notebook.py` (proposed), or register a named project kernel (`C:\Python313\python.exe -m ipykernel install --user --name bda-py313`), which changes your Jupyter configuration.
- **U6.** Whether the Madhya Pradesh data-provider query should be sent (a person sends it; the draft is in `Phase_09_Arrivals_Plan.md` §14).

## 9. Approval record (2026-10-22, project owner)

- **U1 / D-44:** approved as written.
- **U2:** `aq1_likely` is the primary evaluation-target population. The original population is a sensitivity analysis and is selection criterion 4.
- **U3:** the primary analysis uses class-based handling. A **separate sensitivity population** `aq1_likely_excl_mp_pending` additionally excludes every `provider_query_pending` row from targets.
  - It is **reported only** and does not enter the selection rule.
  - Training targets are cleaned with the same knowability rule as AQ-1: the week's latest `aq1_available_from`, which is conservative for the marker.
- **U4:** the Wheat calendar adjustment stays exploratory and cannot be selected.
- **U5:** approved runs use `Code/utils/run_phase09_notebook.py` (Python 3.13). The Jupyter configuration is not changed.
- **U6:** the provider query stays drafted and **unsent**.
