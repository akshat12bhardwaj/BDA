# Forecast Output Contract — `phase8-forecast-v1`

**Status: [IMPLEMENTED as a batch interface over historical data, 2026-10-22].** `Code/modelling/forecast_output.py` builds and validates forecast tables for a chosen forecast origin. **It is not a live forecasting service:**
- nothing is scheduled;
- no forecast file is published;
- no forecast for any 2023+ origin has been generated (that period is the reserved holdout, `Phase_08_Modelling_Plan.md` §P).

The empirical error profile is `phase8-error-profile-v1` (`Code/modelling/error_profile.py`, §5 below).

## 1. What this is, and what it is not

| | Forecast output (this contract) | Training / validation artifacts |
|---|---|---|
| Purpose | consumed by downstream decision support (`Phase_09_Integration_Plan.md`) | model development and evaluation evidence |
| Content | one predicted weekly median price per series × origin × horizon, plus eligibility metadata | actual targets, residuals, metrics, bootstrap results |
| Location | built in memory by `forecast_table()`; a planned published location is `Processed_Data/forecasts/` (does not exist) | `Processed_Data/modelling/phase08/` |
| Contains actual outcomes? | **never** | yes |

## 2. Approach per cell (fixed by D-42)

| Crop | 1 week | 2 weeks | 4 weeks |
|---|---|---|---|
| Onion | `hgb_conservative` (feature_config `weather`) | persistence | persistence |
| Potato | persistence | persistence | persistence |
| Wheat | persistence | persistence | persistence |

- **Persistence** = the median usable modal price of the origin week. It is computed directly and needs no model.
- **`hgb_conservative`:** no fitted model artifact is saved, and building one would need a training run, which is not authorised. Its rows therefore carry `prediction_status = model_artifact_unavailable` with a **null price**, unless versioned predictions are supplied (`learned=`). Supplied rows are accepted **only** for D-42 learned cells, and must state a `model_version`.
- **Test-period result for this cell:** it did not beat persistence on MAE (−1.6% combined, D-42), so downstream users should know that.

## 3. Columns

| Column | Type | Nullable | Unit | Meaning |
|---|---|---|---|---|
| `contract_version` | str | no | – | always `phase8-forecast-v1` |
| `crop` | str | no | – | Onion / Potato / Wheat |
| `state` | str | no | – | series key (D-33) |
| `district` | str | no | – | series key (D-33) |
| `market` | str | no | – | series key (D-33) |
| `variety` | str | no | – | series key (D-33) |
| `origin_week_start` | date | no | date | Monday of the origin week W |
| `origin_date` | date | no | date | Sunday of W; the forecast is made at the end of this day using only data dated ≤ it |
| `horizon_weeks` | int | no | weeks | 1, 2 or 4 |
| `target_week_start` | date | no | date | Monday of week W + h |
| `target_week_end` | date | no | date | Sunday of week W + h |
| `predicted_median_price_rs_per_quintal` | float | yes | Rs/quintal, nominal | forecast of the target week's median usable modal price; null unless `prediction_status = ok` |
| `approach` | str | no | – | `persistence` or `hgb_conservative` (D-42) |
| `feature_config` | str | no | – | `none` (persistence) or `weather` |
| `selection_decision` | str | no | – | always `D-42` |
| `model_version` | str | yes | – | version of supplied learned predictions; null for persistence |
| `prediction_status` | str | no | – | `ok`, `model_artifact_unavailable` or `model_prediction_missing` |
| `in_primary_population` | bool | no | – | ≥ 365 distinct usable price dates on or before the origin (D-41) |
| `n_usable_price_dates_to_origin` | int | no | days | distinct usable price dates dated ≤ origin |
| `origin_week_usable_price_count` | int | no | rows | usable price rows in week W (≥ 1) |
| `origin_week_median_rs_per_quintal` | float | no | Rs/quintal, nominal | median usable modal price in week W |
| `anchor_date` | date | no | date | last usable price date in week W |
| `weather_covered` | bool | no | – | all weather predictors present on the anchor row (relevant to `hgb_conservative` only) |
| `prediction_interval_available` | bool | no | – | always `False`; no interval method has been validated |
| `error_profile_key` | str | no | – | `phase8-error-profile-v1\|<crop>\|h<h>\|<approach>`, the row key in `forecast_error_profile.csv` |

**Uniqueness key:** (`crop`, `state`, `district`, `market`, `variety`, `origin_date`, `horizon_weeks`).

**Row presence:** a row exists only for series with at least one usable price in the origin week. A series that did not report that week has no row; it is absent, not represented by a null row.

## 4. Validation rules (`validate_forecasts()`, enforced on every table built)

1. **Shape:** the columns are exactly those listed above, in that order; non-nullable columns have no nulls; each column has its stated type.
2. **Uniqueness:** the uniqueness key is unique.
3. **Weeks:**
   - `origin_date` is a Sunday and equals `origin_week_start` + 6 days.
   - The target week is W + h (Monday–Sunday), with h ∈ {1, 2, 4}.
   - `anchor_date` lies inside the origin week.
4. **Approach:** `approach` and `feature_config` equal the D-42 assignment for (crop, h), and `selection_decision = D-42`.
5. **Price and status:** `prediction_status = ok` exactly when the price is present and > 0. Persistence prices equal the origin-week median, and persistence has no `model_version`.
6. **Population:** `in_primary_population` equals `n_usable_price_dates_to_origin ≥ 365`, and `origin_week_usable_price_count ≥ 1`.
7. **No intervals:** `prediction_interval_available` is `False` everywhere, and no interval columns exist.
8. **Profile key:** `error_profile_key` matches the row's version, crop, horizon and approach.
9. **Origin bounds (refused when building):** an origin that is not a Sunday or is after the input's last reported date; learned predictions for a cell D-42 assigns to persistence.

## 5. Empirical error profile `phase8-error-profile-v1`

**Files:** `Processed_Data/modelling/phase08/forecast_error_profile.csv`, plus `forecast_error_profile_provenance.csv`, which records the SHA-256 of the input prediction files.

**Source:**
- 2019–2020 validation residuals only, from origin-eligible rows in the primary experiment.
- For each crop × horizon, the residuals are those of its D-42 approach: persistence, or `hgb_conservative` (weather) for Onion h = 1.
- **The 2021–2022 test results were not used**, and the holdout was not touched.
- Rows and MAE match `model_validation_metrics.csv` / `hgb_conservative_validation_metrics.csv` exactly; a test checks this.

**Columns per crop × horizon × period** (2019, 2020, combined):
- `n_obs`, `n_series`, `max_series_share_pct`
- `mae_rs_per_quintal`, `mape_pct`
- quantiles 5/10/25/50/75/90/95 of `ratio_error` = actual / predicted − 1 (unitless; actual = predicted × (1 + ratio_error))
- quantiles 50/80/90/95 of absolute error (Rs/quintal) and of absolute percentage error

**Label:** these are **empirical validation-period error quantiles, NOT calibrated prediction intervals.** Their coverage on any later period has not been tested.

**Key figures** (combined 2019–2020):

| Crop | h | n (series) | MAE (Rs/q) | ratio_error q05 / q50 / q95 | 90th pct abs % error |
|---|---|---|---|---|---|
| Onion | 1 (hgb_conservative) | 55,138 (868) | 234.3 | −0.197 / −0.006 / +0.258 | 22.3 |
| Onion | 2 | 53,747 (861) | 405.1 | −0.293 / 0.000 / +0.515 | 37.0 |
| Onion | 4 | 51,754 (857) | 627.9 | −0.403 / +0.020 / +0.833 | 53.3 |
| Potato | 1 | 55,600 (890) | 112.4 | −0.171 / 0.000 / +0.214 | 19.4 |
| Potato | 2 | 54,607 (878) | 165.6 | −0.230 / 0.000 / +0.310 | 25.0 |
| Potato | 4 | 53,368 (863) | 235.3 | −0.297 / +0.033 / +0.455 | 34.6 |
| Wheat | 1 | 57,148 (932) | 39.1 | −0.053 / 0.000 / +0.045 | 5.0 |
| Wheat | 2 | 55,868 (923) | 52.0 | −0.070 / 0.000 / +0.056 | 6.4 |
| Wheat | 4 | 54,548 (913) | 71.3 | −0.094 / 0.000 / +0.074 | 8.5 |

**What the figures show:**
- **Lopsided errors.** Onion and Potato errors are right-skewed: price rises beyond the forecast are larger than falls (Onion h = 4: q95 +83% vs q05 −40%).
- **Year differences.** The two years differ a lot: Onion h = 4 q05 is −23% in 2019 and −47% in 2020; Potato h = 4 MAE is 147 and 340 Rs/q. **Use the per-year rows, not only the combined row, to see the range.**

**Limitations:**
- **Coverage:** origin-eligible series only (857–932 series per cell). No single series supplies more than 0.22% of rows, but large-market and frequently reporting series dominate the pooled quantiles. Series outside the primary population, or with no recent usable price, are not represented.
- **Temporal dependence:**
  - consecutive weekly residuals of one series are strongly correlated;
  - h = 2 and h = 4 targets overlap across consecutive origins;
  - all series share national shocks in the same weeks.

  The effective sample is therefore far smaller than `n_obs`, and the tails (q05 and q95) are the least stable.
- **Regimes:** two validation years are two market regimes. 2021–2022 test errors were larger in some cells (for example Onion h = 4 MAE 532 in 2021), so the profile can understate future errors.
- **Nominal prices:** errors in Rs/q scale with the price level, so prefer `ratio_error` or percentage columns across years.
- **Intended use:** as a documented, approximate risk margin, for example a downstream rule that requires a spread to exceed the 90th-percentile absolute percentage error. **It is not a probability statement.**
- **Proper intervals** would need a method (for example conformal or quantile models) fitted on validation and checked once for coverage on independent data. That needs a separate, approved protocol.
