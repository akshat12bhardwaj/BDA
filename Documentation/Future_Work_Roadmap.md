# Future Work Roadmap — Phases 8–14

**Status: none of the phases below are implemented.** This document is a technical specification only, written so that a future session can begin implementation directly without re-investigating the data. Every "what we plan to do" statement here must remain phrased as a plan, never rewritten as a completed-work claim, until the corresponding phase is actually executed.

This roadmap was originally written after Phase 1 and has been updated after Phases 2 and 3. **The three selected crops are known: Onion, Potato, Wheat** (see `Documentation/Crop_Feasibility_Audit.md`). **Weather data now exists** for 36 representative districts across these crops, 2001–2022 (see `Documentation/Weather_Data_Collection.md`) — Phase 8/10's weather-feature plans below remain valid, but should now reference the actual collected variables (temperature mean/max/min, rain_sum, relative humidity, wind speed, ET0 — soil moisture was investigated and excluded) rather than a hypothetical list. Nothing in Phase 2 or 3's findings contradicts the structure below. This document will be revisited again after Phases 4–7 as the cleaned schema and feature catalogue become concrete. **Update after Phase 4**: integration outputs now exist in `Processed_Data/integration/` (Decision Log D-15 to D-23). Weather now covers all 46 representative locations, after 10 were resolved and Ferozpur was corrected. The dependency structure below is unchanged; the specific Phase 4 inputs are noted per phase. **Update after Phase 5**: cleaned tables now exist (`Processed_Data/cleaned/mandi_cleaned_<crop>.parquet`, D-25 to D-31). Phases 6–10 should build price features only from rows with `usable_modal_price` and quantity features only from rows with `usable_arrivals`, or justify any other choice. Zero prices are now missing, not 0 (A-16), so MAPE-type metrics no longer meet artificial zero prices. 338 conflicting rows remain unresolved and are excluded from both usable views. **Update after Phase 6**: the Phase 8–10 input is now `Processed_Data/features/features_<crop>.parquet`, with roles defined in `Processed_Data/features_audit/feature_registry.csv` (D-32 to D-37). Every history feature assumes a forecast for day t is made with data up to t−1 (A-20). For the 7–30-day horizons planned in Phase 8, features must be taken from the forecast-origin row or recomputed with a t−h cutoff. APY features use lag 2 (A-19), not lag 1. Same-day weather is not a predictor. **Update after Phase 7**: EDA findings are in `Documentation/EDA_Findings.md` and readiness in `Documentation/Modelling_Readiness_Report.md`. Three proposals must be reviewed before Phase 8 starts: D-38 (weekly median target, h = 1/2/4 weeks, origin cutoff), D-39 (usable views; keep review rows plus a sensitivity run) and D-40 (chronological split: train 2002–2018, validation 2019–2020, test 2021–2022, no-weather holdout 2023–Feb 2024; no random splits). EDA also indicates that weather associations may be seasonal confounding, so Phase 8 should compare any weather model with a calendar-only baseline. APY features are realistic mainly for Wheat (lag-2 missing 51% Onion / 34% Potato / 4% Wheat). **Update for Phase 8 planning (2026-10-22):** D-38 and D-39 are accepted, D-40 is accepted with 2019, 2020 and combined validation reported separately, and D-41 sets the primary population to series with ≥ 365 usable price observations. The full plan is in `Documentation/Phase_08_Modelling_Plan.md`. Where the Phase 8 section below differs from that plan, the plan wins. Nothing is implemented yet.

---

## Dependency Graph

```
Phases 1–7 (Data Prep + EDA)
        │
        ▼
Processed_Data/ (cleaned, integrated, feature-engineered dataset per selected crop)
        │
        ├──────────────┬──────────────┐
        ▼              ▼              ▼
   Phase 8         Phase 9         Phase 10
   Price           Market          Supply
   Forecasting     Activity        Prediction
        │              │              │
        └──────────────┼──────────────┘
                        ▼
              Predictions consumed by:
                        │
                        ▼
                   Phase 11
              Logistics / Dijkstra
                        │
                        ▼
                   Phase 12
                MILP Optimization
                        │
                        ▼
                   Phase 13
               Dynamic Feedback
                        │
                        ▼
                   Phase 14
             Final End-to-End Evaluation
```

Phase 12 (MILP) is the integration point: it consumes Phase 8's predicted price, Phase 9's predicted market activity, Phase 10's predicted supply, and Phase 11's transport cost/route matrix simultaneously.

---

## Phase 8 — Price Forecasting

**Objective**: Forecast future mandi modal price per selected crop (and per market or market-cluster, TBD after Phase 7 EDA shows whether market-level series are dense enough) to support the MILP's revenue estimate.

**Input dataset**: The Phase 6 feature table (`Processed_Data/features_<crop>.csv`, exact filename TBD after Phase 6), containing cleaned, integrated mandi price/arrivals + APY + weather features at the chosen date/geographic granularity (granularity itself is a Phase 4 decision, to be recorded in `Decision_Log.md` and referenced here once made). **Phase 4 outcome**: the integrated base is record-level (`mandi_integrated_<crop>.parquet`, one row per raw mandi record), with same-day weather for ~24–25% of records and APY linked only at (crop, APY district, agricultural year) via `mandi_apy_district_year.csv`. Any APY-derived feature must use a lag of at least `apy_year_lag1` (D-19). Weather features must be lagged too.

**Target variable**: `Modal Price (Rs./Quintal)` (or its cleaned/aggregated equivalent) — confirmed present and numeric for all mandi crops per Phase 1 inspection.

**Forecast granularity & horizon**: To be finalized in Phase 6/7 based on observed reporting frequency and continuity for the selected crops; a short-to-medium horizon (e.g. 7–30 days ahead) is anticipated given the mandi data's typically frequent-but-irregular reporting cadence (confirmed non-uniform date formats in Phase 1; continuity itself is a Phase 2 metric). **Finalized (D-38, D-41):**
- Input: `Processed_Data/features/features_<crop>.parquet`.
- Target: the weekly median usable modal price per series, h = 1, 2 and 4 weeks, with origin at the end of week W.
- Population: series with ≥ 365 usable price observations.
- Split (D-40): train 2002–2018; validation 2019 and 2020 reported separately and combined; test 2021–2022; no-weather holdout 2023 – Feb 2024.
- Candidate models are re-scoped in `Phase_08_Modelling_Plan.md` §D: scikit-learn tabular models first. ARIMA-family models need statsmodels, which is not installed.

**Candidate models**: ARIMA, ARIMAX (with arrivals/weather/season as exogenous regressors), N-BEATSX, Stacked LSTM. No model is preferred in advance.

**Feature requirements from Phase 7**: lagged price, rolling price statistics, arrivals (lagged, to avoid leakage), season/month, market/variety identifiers, weather variables found in Phase 7 to correlate with price. Exact feature list depends on the Feature Catalogue produced at the end of Phase 6.

**Train/validation/test strategy**: Strict chronological split (train → validation → test in date order); no shuffling; scalers/encoders fit on train only.

**Evaluation metrics**: MAE, RMSE, MAPE (or sMAPE if zero/near-zero prices are present), with explicit forecast horizon stated per reported metric.

**Expected visualizations**: historical price plot, actual-vs-predicted overlay per model, model comparison bar chart, residual plot, error distribution histogram.

**Model comparison method**: same test period, same metrics, across all four candidate models; the winning model is chosen by evidence, not assumption.

**Expected output format** (feeds Phase 9/10/12 and is the authoritative schema until Phase 8 is implemented and may refine it):
```
crop, market, date, predicted_price, forecast_horizon, model_name,
confidence_interval_lower, confidence_interval_upper
```

**Data leakage precautions**: rolling/lag features computed strictly on past observations; no test-period data used in scaling or feature computation; no future arrivals used to predict current-period price.

**Potential risks**: sparse/irregular per-market reporting (observed as a candidate concern in Phase 1's date-format findings); mixed date formats requiring careful chronological ordering; crop-specific seasonality not yet quantified.

**Dependencies**: consumes Phase 6/7 outputs. Produces predicted price consumed by Phase 12 (MILP revenue term) and referenced by Phase 13 (dynamic re-forecasting).

---

## Phase 9 — Market Activity / Demand Modeling

**Objective**: Predict future market activity (arrivals/traded quantity) per crop/market as a supply-side signal usable by the MILP's market-capacity/selling-quantity constraints.

**Target definition — critical**: Phase 1 confirmed that **no dataset in this project contains a genuine consumer-demand variable**. The only available signal is `Arrivals (Tonnes)` (mandi and, regionally, Agri Market Dataset), which represents **quantity physically arriving at the market**, not demand. Phase 9's target must therefore be explicitly named `predicted_market_arrivals` (or equivalent), and any documentation, chart, or variable name must avoid the word "demand" unless a genuine demand-side source is found before this phase begins.

**Data source**: primarily the mandi `Arrivals (Tonnes)` field (all crops, national coverage). Agri Market Dataset's `Arrivals (Tonnes)` may be used as a secondary validation/cross-check signal **only if** the selected crop falls within its Maharashtra/Amravati/5-crop scope (per Phase 1 Assumption A-04) — it must not be relied upon as a primary source for crops outside that scope. **Concretely, of the three selected crops (Onion, Potato, Wheat — Phase 2), only Wheat has this regional cross-validation available; Onion and Potato have none and must rely solely on national mandi arrivals.**

**Proxy limitations to document alongside any result**: (1) arrivals reflect what farmers/traders chose to bring to market, which is a function of both supply and expected price, not pure consumer demand; (2) no information exists on unsold quantity, consumer purchases, or price elasticity of demand.

**Candidate model**: XGBoost Regression.

**Candidate features**: lagged arrivals, lagged price, rolling arrival statistics, season/month, market/crop/variety identifiers, weather (rainfall/temperature near harvest), APY production (as a slower-moving supply anchor). Final feature list depends on Phase 6/7.

**Validation**: chronological split, consistent with Phase 8.

**Metrics**: MAE, RMSE, MAPE against held-out arrivals.

**Expected output schema**:
```
crop, market, date, predicted_market_quantity, target_definition
```
where `target_definition` is a fixed string such as `"mandi_arrivals_tonnes (supply-side market activity proxy; not consumer demand)"`, carried through so downstream consumers (Phase 12) cannot mistake it for demand.

**Expected visualizations**: actual-vs-predicted quantity, seasonal quantity pattern, market-level quantity comparison, feature importance chart.

**Dependencies**: consumes Phase 6/7 outputs. Produces the arrivals/market-activity prediction consumed by Phase 12 (as a market-capacity/selling constraint input, not a revenue driver).

---

## Phase 10 — Supply Prediction

**Objective**: Predict future crop supply (production-side) per region to inform the MILP's procurement-availability constraint.

**Target**: production (Tonnes) or a derived supply quantity, at the granularity decided in Phase 4 (state/district-year from APY, or a finer interpolation if justified).

**Candidate inputs**: APY production/area/yield (lagged/historical), mandi arrivals (as a leading indicator), weather (rainfall/temperature over the relevant growing season, from Phase 3), season, geography.

**Candidate model**: XGBoost Regression.

**Validation**: chronological split respecting the yearly grain of APY data (train on earlier years, validate/test on later years — not a random split, consistent with the project's no-random-split-for-time-series rule).

**Metrics**: MAE, RMSE, MAPE; R² may be reported additionally given APY's more stable year-over-year structure.

**Expected output schema**:
```
crop, region, date, predicted_supply
```

**Expected visualizations**: production trend, actual-vs-predicted supply, state-level supply comparison, seasonal supply pattern, feature importance.

**Known limitation to carry forward**: APY data is annual and district-level, while mandi/weather data is daily/sub-daily and market-level — Phase 4/6 must resolve this granularity mismatch (e.g. via a documented interpolation or by keeping supply prediction at the coarser annual/district grain and joining down when needed for the MILP). This is not yet resolved and must be decided explicitly, not silently assumed. **Partly resolved in Phase 4**: the APY↔mandi link is defined at APY's own grain (crop, district, July–June agricultural year) with no interpolation and no repetition of annual values onto daily rows (D-19, D-20). Phase 10 should therefore model supply at the annual district grain. Caveat: APY annual values exist for only ~47% of Onion mandi records' district-years (Potato ~62%, Wheat ~94%).

**Dependencies**: consumes Phase 6/7 outputs (plus Phase 3 weather). Produces predicted supply consumed by Phase 12 (procurement-availability constraint).

---

## Phase 11 — Logistics / Dijkstra

**Objective**: Build a routing graph (mandi → warehouse → destination market) and compute shortest/cheapest routes to feed transport cost into the MILP.

**Nodes**: mandi markets relevant to the selected crops (from the mandi dataset's `Market Name`/`District Name`/`State Name`), warehouse locations (placement methodology TBD — see below), destination markets (candidate selling markets for the selected crops).

**Critical finding from Phase 1**: **no coordinate data exists anywhere in the provided datasets** (`final_data.csv` has only names/codes, no lat/long). **Update from Phase 3**: 36 district-level coordinates (via the Open-Meteo Geocoding API) already exist for the selected crops' highest-volume districts (`Processed_Data/weather/weather_location_mapping.csv`) and can be reused directly as mandi-node coordinates for those districts, avoiding a duplicate geocoding effort. The remaining districts (including the 10 that failed geocoding in Phase 3) still need resolution before they can be used as graph nodes. **Update from Phase 4**: all 46 representative coordinates are now admin2-verified (`Processed_Data/integration/weather_location_resolution.csv`). The 10 were resolved and Phase 3's Ferozpur point was corrected (it was in the wrong district), so Phase 11 should use the Phase 4 resolution table, not the Phase 3 mapping. **Coordinates must never be fabricated or guessed.**

**Edges & distance methodology**: road distance from a real public source (e.g. a routing API or published road-distance table) is preferred; if unavailable, a documented straight-line (haversine) distance with an explicit disclosed limitation is an acceptable fallback — but the fallback and its limitation must be stated in the notebook and in `Assumptions.md`, not silently used as if authoritative.

**Cost methodology**: `Transportation Cost = Distance × Cost per km × Quantity`, with the cost-per-km figure sourced and documented (e.g. published logistics-cost benchmarks) — never an arbitrary invented constant without a cited basis.

**Warehouse placement**: to be decided in Phase 11 based on the selected crops' actual market geography (e.g. district centroids of top-volume markets); documented as an explicit assumption, not fabricated infrastructure data.

**Procedure**: Dijkstra's shortest-path algorithm over the constructed graph, computing cheapest route per mandi→market corridor.

**Expected output schema**:
```
source, destination, distance, transport_cost, route
```

**Expected visualizations**: network/route map, selected-route highlight, route distance/cost comparison across candidate corridors.

**Dependencies**: independent of Phases 8–10 for graph construction, but its cost output is consumed by Phase 12.

---

## Phase 12 — MILP Optimization

**Objective**: Determine procurement, storage, transportation, and selling quantities (and destination market) that maximize expected profit, consuming the actual outputs of Phases 8–11.

**Sets** (finalized once selected crops/markets are known): `Crops`, `SourceMarkets` (mandis), `Warehouses`, `DestinationMarkets`, `TimePeriods`.

**Parameters**:
| Parameter | Source |
|---|---|
| Predicted price | Phase 8 output |
| Predicted market activity / arrivals | Phase 9 output (explicitly labeled as arrivals proxy, not demand) |
| Predicted supply | Phase 10 output |
| Transport cost per route | Phase 11 output |
| Storage cost / warehouse capacity | Documented external input or explicit assumption (not yet sourced — to be added to `Assumptions.md` when Phase 12 begins) |
| Market capacity | Documented external input or explicit assumption |
| Procurement cost | Derived from Phase 8's predicted price at the source market |

**Decision variables**: procurement quantity (per crop, source market, period), storage quantity (per crop, warehouse, period), transportation quantity (per crop, route, period), selling quantity (per crop, destination market, period), destination market selection.

**Objective function**:
```
Maximize: Σ (Selling Price × Selling Quantity)
        − Σ (Procurement Cost × Procurement Quantity)
        − Σ (Transport Cost × Transport Quantity)
        − Σ (Storage Cost × Storage Quantity)
```

**Constraints**: procurement ≤ predicted supply; selling ≤ predicted market activity/capacity at destination; warehouse capacity limits; inventory balance (procured = stored + transported, period over period); transport capacity per route; non-negativity on all decision variables.

**Expected output schema**:
```
crop, procurement_quantity, storage_quantity, transport_quantity, selling_quantity,
destination, revenue, cost, expected_profit
```

**Tooling**: PuLP or Google OR-Tools (choice deferred to Phase 12 based on problem size after crop/market selection is final).

**Dependencies**: consumes Phases 8, 9, 10, 11 outputs directly — cannot be implemented correctly until all four exist.

---

## Phase 13 — Dynamic Feedback

**Objective**: Demonstrate that the system updates its recommendation as new historical data becomes available, via a rolling historical simulation (not a static diagram).

**Mechanism**:
```
New period's historical data arrives
        ↓
Features recomputed (respecting Phase 6's leakage-safe lag/rolling definitions)
        ↓
Phase 8/9/10 models re-predict for the new period (retrain-on-schedule or rolling-window re-fit — exact cadence TBD)
        ↓
Phase 11 route/cost matrix reused or refreshed if new markets are in scope
        ↓
Phase 12 MILP re-solved with updated parameters
        ↓
New decision recorded and compared to the previous period's decision
        ↓
(repeat for next historical period)
```

**Specification to fill in during implementation**: update frequency (e.g. weekly/monthly, matching the selected crops' actual reporting cadence from Phase 2's continuity findings), rolling window length for feature recomputation, whether models are fully retrained or incrementally updated each step, and how many historical periods the simulation will cover.

**Expected outputs**: a period-by-period log of predictions, MILP decisions, and expected profit, plus a visualization showing how the recommended decision changed over time in response to real historical data shifts.

**Evaluation**: compare the rolling simulation's realized decisions against what a static (single-shot) model/optimization would have recommended, to demonstrate the value of the dynamic update.

**Dependencies**: requires Phases 8–12 fully implemented first.

---

## Phase 14 — Final End-to-End Evaluation

**Objective**: Produce one interpretable, traceable end-to-end demonstration (crop → predicted price/activity/supply → procurement/storage/transport decision → route → revenue/cost/expected profit), using real pipeline outputs only.

**Planned content**: end-to-end prediction accuracy summary (from Phases 8–10), optimization-quality summary (from Phase 12), route validation (from Phase 11), a baseline comparison if a sensible naive baseline can be defined (e.g. "procure/sell at last known price with no optimization"), a basic sensitivity analysis (e.g. how expected profit changes if predicted price is off by ±X%), documented limitations, and final visualizations culminating in the demonstration card described in the Master Project Plan.

**Dependencies**: requires all of Phases 8–13 complete.

---

## Notes for Whoever Resumes at Phase 8

1. Read `Master_Project_Context.md` for current status and the final selected crops (set in Phase 2).
2. Read `Processed_Data/features_audit/feature_registry.csv` (the Phase 6 feature catalogue; no separate `Feature_Catalogue.md` was produced) before choosing Phase 8/9/10 features — do not recompute features that already exist. For Phase 8, read `Phase_08_Modelling_Plan.md` first.
3. Read `EDA_Findings.md` (produced at the end of Phase 7) for which relationships are actually supported by evidence — do not assume a feature matters just because it is listed as "candidate" above.
4. This document's schemas are **proposed, not final** — Phase 6/7 findings may require adjusting column names or granularity; update this file when that happens, don't silently diverge from it.
5. Never label an arrivals/traded-quantity output as "demand" anywhere in code, plots, or documentation, per Phase 1/Assumption A-02.
