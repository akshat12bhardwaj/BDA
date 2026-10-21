# Data Quality and Modelling Readiness — Phase 7

**Status: [COMPLETED] assessment; the three decisions below are [PROPOSED] and must be reviewed before Phase 8.** Evidence: `Processed_Data/eda/` (especially `quality_readiness.csv`, `series_summary.csv`, `conflict_distribution.csv`, `horizon_feasibility.csv`, `weekly_horizon_feasibility.csv`, `split_evidence.csv` and `review_flag_effect.csv`) and `Notebooks/Phase_07_EDA.ipynb` Sections 9–12.

## 1. Data quality summary

Percentages use all Phase 6 rows of each crop as the denominator.

| Item | Onion | Potato | Wheat |
|---|---|---|---|
| Rows (= Phase 5 cleaned rows) | 2,623,671 | 2,764,417 | 2,593,279 |
| Series (crop × market × variety) / markets | 3,924 / 1,732 | 4,003 / 1,624 | 5,279 / 1,988 |
| Date coverage | 2000-10-19 – 2024-02-02 | 2000-10-19 – 2024-02-02 | 2001-03-16 – 2024-02-01 |
| Rows not in `usable_modal_price` | 28,060 (1.07%) | 33,146 (1.20%) | 14,264 (0.55%) |
| Rows not in `usable_arrivals` | 143 | 226 | 159 |
| Unresolved conflicts (Phase 5) | 68 | 164 | 106 |
| Price `scale_error_suspected` / `review` | 422 / 22,330 | 415 / 2,339 | 148 / 471 |
| Arrivals `entry_error_suspected` / `review` | 75 / 399 | 62 / 399 | 53 / 484 |
| Series with < 30 usable price rows | 1,295 | 1,215 | 2,119 |
| Series with ≥ 365 usable price rows (share of usable rows) | 1,473 (93%) | 1,551 (93%) | 1,540 (91%) |
| `modal_prev_obs` / `modal_lag_1d` missing | 0.43% / 28.8% | 0.45% / 25.3% | 0.32% / 34.3% |
| Weather features missing | 74.7% | 76.4% | 74.8% |
| APY lag-2 missing | 50.6% | 34.3% | 3.8% |

**Where the unresolved conflicts sit:** they are concentrated in Telangana (128 rows), Madhya Pradesh (68) and Punjab (52), and mostly in 2006 and 2010–2011, with none after 2018. They remain in the data, flagged and outside the usable views.

**Short series are numerous but small.** About 30–40% of series have fewer than 30 usable observations, yet they hold only 0.36% / 0.33% / 0.61% of usable rows (Onion / Potato / Wheat).

## 2. Candidate modelling scope (evidence only — not a final rule)

| Candidate rule | Series kept (O / P / W) | Share of usable price rows kept |
|---|---|---|
| ≥ 365 usable observations | 1,473 / 1,551 / 1,540 | 93% / 93% / 91% |
| ≥ 2-year span and reporting density ≥ 0.5 | 491 / 592 / 335 | 45% / 51% / 32% |

The first rule keeps nearly all the data. The second keeps only regularly reporting markets, at a large cost in coverage, especially for Wheat. Phase 8 must choose explicitly, and should report results for the excluded series separately rather than dropping them silently.

## 3. Decision A — forecast horizon and information cutoff (proposed: D-38)

**Three tasks that must not be confused:**
- **Next reported observation:** the horizon is irregular (median 1 day, p90 3–4 days). Phase 6 features are valid as-is.
- **Exact future calendar day:** the target exists only 55–78% of the time (at 30 days: 55% Wheat, 63% Onion, 66% Potato). Using it would bias evaluation toward regularly reporting periods.
- **Weekly target h weeks ahead:** at least one usable price exists in the target week 81–92% of the time (h = 1, 2, 4).

**Proposal:**
- **Primary task:** the weekly median usable modal price of a series, h = 1, 2 and 4 weeks ahead (≈ 7–28 days).
- **Forecast origin:** the end of week W, using only information dated on or before the origin.
- **Secondary baseline:** the next reported observation.
- **No exact calendar-day targets.** Phase 6 feature calculations stay unchanged; any weekly aggregation of features must keep the ≤ origin cutoff.

## 4. Decision B — flagged observations (proposed: D-39)

**Evidence:** price `review` rows are 0.86% / 0.09% / 0.02% of the usable view. They leave medians and p99 essentially unchanged, but raise standard deviations by about 7% (Onion) and 13% (Potato). Suspected errors and conflicts are already outside the usable views.

**Proposal:**
1. Use `usable_modal_price` / `usable_arrivals` rows for targets and history. This excludes suspected scale/entry errors and unresolved conflicts, consistent with Phase 6.
2. Keep `review` rows in the primary experiments, because they are plausible extreme market events.
3. Run a sensitivity analysis without `review` targets, and report both.
4. Never delete flagged rows; all flags and `source_row` stay in the data.

## 5. Decision C — evaluation split (proposed: D-40)

**Why not a random row split:** within-series persistence is about 0.95. A random split puts a test row's immediate neighbours in the training set, so the model can interpolate instead of forecast, which makes results optimistic. Rolling features would also straddle the train/test boundary.

**Evidence:**
- In 2021–2022, 87–97% of active series already had earlier usable history.
- Weather ends on 2022-12-31.
- 2001 and 2024 are partial years.
- Wheat reporting fell 27% in 2020.

**Proposal:** a chronological, out-of-time design with an expanding training window.

| Period | Years | Purpose |
|---|---|---|
| Train | 2002–2018 | model fitting (expanding window) |
| Validation | 2019–2020 | model and hyper-parameter choice |
| Test | 2021–2022 | final evaluation, used once; weather and APY available |
| Holdout | 2023-01-01 – 2024-02-02 | models without weather features only |

Within this design:
- **Use rolling forecast origins** (e.g. monthly).
- **Leave a gap of at least the forecast horizon** between the last training target and the first test origin.
- **Fit any scaler, encoder or imputer on training data only.**
- **Report results by crop and horizon**, and for long-history vs short-history series.

## 6. To finalize before Phase 8

1. Confirm or amend D-38 – D-40: target definition and horizons, flag policy, and split years.
2. Choose the series-inclusion rule (Section 2) and how excluded series are reported.
3. Decide whether weather-based models are evaluated only on the weather-covered subset, and compare them with a calendar-only baseline.
4. Define a naive baseline: last observed weekly median, and a seasonal naive.
