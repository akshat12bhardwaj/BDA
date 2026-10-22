# Arrivals Forecast Output Contract — `phase9-arrivals-forecast-v1`

**Status: [IMPLEMENTED as a batch interface over historical data; approach PROVISIONAL, 2026-10-22].** `Code/modelling/arrivals.py:arrivals_forecast_table()` builds and validates the tables.
- It is **not a live service**, and no forecast table is published.
- The approach is **provisional persistence**: no Phase 9 selection decision exists, which every row states.
- **Arrivals are supply-side market activity, not consumer demand** (A-02). The `target_definition` column says so on every row.

## 1. Compatibility with `phase8-forecast-v1`

**Same key, enabling a one-to-one join:** (`crop`, `state`, `district`, `market`, `variety`, `origin_date`, `horizon_weeks`).

**Same conventions:**
- Monday–Sunday weeks, with the origin at the end of Sunday of week W.
- `target_week_start` / `target_week_end` = week W + h, with h ∈ {1, 2, 4}.

**Separate components.** The two tables are joined only by consumers. No combined recommendation is produced.

**Row sets can differ:**
- A price row needs a usable price in the origin week; an arrivals row needs a usable arrivals record.
- `has_usable_price_in_origin_week` shows the overlap.
- An inner join keeps only series-weeks that have both.

## 2. Columns

| Column | Type | Nullable | Unit / values |
|---|---|---|---|
| `contract_version` | str | no | `phase9-arrivals-forecast-v1` |
| `crop`, `state`, `district`, `market`, `variety` | str | no | series key (D-33) |
| `origin_week_start` | date | no | Monday of W |
| `origin_date` | date | no | Sunday of W (forecast made at end of day) |
| `horizon_weeks` | int | no | 1, 2, 4 |
| `target_week_start`, `target_week_end` | date | no | Monday / Sunday of W + h |
| `predicted_median_daily_arrivals_tonnes` | float | no | tonnes per reported day, ≥ 0 |
| `target_definition` | str | no | fixed text: median usable daily arrivals in the target week, tonnes per reported day, supply-side market-activity proxy, not consumer demand |
| `approach` | str | no | `persistence` |
| `selection_decision` | str | no | `provisional: no Phase 9 selection decision` |
| `prediction_status` | str | no | `ok` |
| `in_primary_population` | bool | no | ≥ 365 distinct usable arrival dates on or before the origin |
| `n_usable_arrival_dates_to_origin` | int | no | days |
| `origin_week_reported_days` | int | no | 1–7 |
| `origin_week_median_arrivals_tonnes` | float | no | tonnes per reported day |
| `anchor_date` | date | no | last usable arrivals date in W |
| `has_usable_price_in_origin_week` | bool | no | price-series overlap flag |
| `prediction_interval_available` | bool | no | always `False` |

## 3. Validation rules (`validate_arrivals_forecasts()`)

1. **Shape:** exact columns, types and non-null values; unique key.
2. **Weeks:** Sunday origin ending W; target week W + h; anchor inside W.
3. **Forecast value:** ≥ 0 and equal to the origin-week median (provisional persistence).
4. **Labels:** the fixed approach, selection and target-definition labels.
5. **Population and reporting:** the eligibility rule holds, and reported days are between 1 and 7.
6. **No intervals.**

**Refused when building:** a non-Sunday origin, and an origin after the input's last reported date.

## 4. Use and limits

- **Volumes:** to turn the target into a weekly volume, multiply by an explicitly assumed number of trading days. The data cannot tell closures from non-reporting.
- **Accuracy:** validation errors are in `Phase_09_Arrivals_Plan.md` §9 (log MAE 0.15–0.63 by crop and horizon). No error profile has been built for arrivals yet.
- **Data quality:** magnitudes include unflagged unit or entry errors (§1 of that plan). Downstream volume caps should use robust (median-based) values and explicit caps.
