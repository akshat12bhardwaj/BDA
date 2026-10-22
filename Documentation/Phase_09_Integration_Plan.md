# Integration Plan — Forecasts into Mandi Decision Support (proposal)

**Status: [PROPOSAL for review, 2026-10-22; nothing implemented].** This document defines data contracts and build order only. Dijkstra, the MILP and the dashboard are **not** built.

**Numbering conflict, for the project owner to decide:** this was requested as the "Phase 9 integration plan", but `Future_Work_Roadmap.md` uses Phase 9 for market-activity (arrivals) modelling, Phase 10 for supply prediction, Phase 11 for logistics and Phase 12 for the MILP. This plan covers the **interfaces across roadmap Phases 9–12**. It does not renumber them. Two options:
- (a) keep the roadmap numbering and treat this as the integration specification for Phases 9–12;
- (b) insert an "integration" phase before roadmap Phase 9 and renumber.

**Literature alignment:** the repository has no literature review or reference list (`Documentation/` checked). This plan therefore aligns only with the project's own roadmap (Phases 9–14) and the Master Project Plan summary in `Master_Project_Context.md`. No citations are invented. The methods named below are standard problem classes:
- spatial and temporal price arbitrage under transport and storage costs
- the transportation / assignment linear programme
- shortest paths on a cost graph

They should be checked against the course or literature sources the project owner supplies.

---

## 1. What the forecasts provide (Phase 8, D-42)

- **Target:** the weekly median usable modal price (Rs/quintal) per series (crop, state, district, market, variety), forecast at the end of Sunday of week W for weeks W + 1, W + 2 and W + 4.
- **Approach:** persistence (= the current weekly median) for every crop × horizon, except Onion h = 1 (`hgb_conservative`).
- **Test result:** on 2021–2022 that model was 1.6% worse than persistence on MAE, but better on RMSE.
- **Measured error** (test MAPE, 2021–2022 combined):

| Horizon | Onion | Potato | Wheat |
|---|---|---|---|
| 1 week | ≈ 9% | ≈ 7% | ≈ 2% |
| 2 weeks | ≈ 14% | ≈ 11% | ≈ 3% |
| 4 weeks | ≈ 21% | ≈ 17% | ≈ 4% |

**Implication for decisions:** forecasts carry little information beyond the current price. Expected gains from moving goods come mostly from **current spatial price spreads** and from **seasonal storage patterns** (`EDA_Findings.md`, per-crop sections). Any decision rule must cover forecast error explicitly: Onion and Potato errors over 2–4 weeks are larger than many inter-market spreads.

## 2. Decisions the pipeline must support

| Decision | Question | Main inputs |
|---|---|---|
| Sourcing | Where and when to buy (source mandi, week) | current source price (known at the origin), market activity at the source, supply context |
| Quantity allocation | How much to buy and move per route | volume caps from arrivals, capital and capacity limits, risk margin from forecast error |
| Destination selection | Where to sell, and after how many weeks (h ∈ {1, 2, 4}) | forecast destination price at h, its error profile, transport and holding cost |
| Logistics | Route and cost between source and destination | node coordinates, distance or route cost, cost per tonne-km |
| Storage / timing | Hold vs sell now (Onion and Potato storable; Wheat MSP-influenced) | forecast price path, storage cost, spoilage per week |
| Feasibility | Which plans are allowed | the capacities, budgets and perishability limits below |

## 3. Proposed architecture (layers and contracts)

```
Phase 6 features ─► [F] price forecast service (Phase 8 §E, planned) ─► price_forecast
                    [E] forecast error profile (from validation residuals) ─► forecast_error_profile
Phase 6 arrivals ─► [A] market activity model (roadmap Ph 9) ─► arrivals_forecast   (supply-side, NOT demand)
Phase 4 APY lag-2 ─► [S] supply context (roadmap Ph 10) ─► supply_context            (annual, district)
Phase 4 coords ───► [L] logistics (roadmap Ph 11: graph + shortest paths) ─► route_costs
assumption tables ► [P] cost and constraint parameters ─► cost_parameters, constraints
        all of the above ─► [D] decision model (roadmap Ph 12 MILP) ─► decision_plan
        decision_plan + realised prices ─► [B] rolling backtest (roadmap Ph 13/14) ─► decision_evaluation
```

**Contracts:**

| Table | Grain | Key columns | Source / status |
|---|---|---|---|
| `price_forecast` | series × origin week × h | crop, state, district, market, variety, origin_date, target_week_start, horizon_weeks, predicted_price (Rs/q), approach, model_version, in_primary_population, prediction_status | Phase 8 §E schema — **inference code not built** |
| `forecast_error_profile` | crop × h | MAE, quantiles of relative error (e.g. 10/50/90%), estimation period | to derive from **2019–2020 validation residuals**; test residuals for reporting only |
| `arrivals_forecast` | series or market × week × h | predicted_market_arrivals (tonnes), target_definition | roadmap Phase 9 — **not built** |
| `supply_context` | crop × APY district × agricultural year | production_lag2 (t), area_lag2, yield_lag2 | Phase 6 `apy_*_lag2` — **available** (missing for 51% / 34% / 4% of Onion / Potato / Wheat rows) |
| `market_nodes` | market | state, district, market, latitude, longitude, coordinate_source | **only 46 admin2-verified district points exist** (`Processed_Data/integration/weather_location_resolution.csv`); district-level, not market-level |
| `route_costs` | source node × destination node | distance_km, distance_method, transport_cost (Rs/t), route | roadmap Phase 11 — **not built**; no road network in the data |
| `cost_parameters` | crop (× route) | transport Rs per tonne-km, loading, mandi fee / commission %, storage Rs per tonne-week, spoilage % per week | **all missing**; need sourced values or explicit assumptions (Assumptions.md) |
| `constraints` | various | capital budget, vehicle / route capacity, warehouse capacity, maximum share of a market's arrivals bought or sold, maximum holding weeks per crop | **all missing**; assumptions |
| `decision_plan` | crop × source × destination × week × h | buy_qty, sell_qty, hold_weeks, expected_revenue, expected_cost, expected_profit, risk_margin | roadmap Phase 12 output |
| `decision_evaluation` | plan × week | realised revenue, cost, profit, comparison with a no-forecast rule | roadmap Phases 13/14 |

**Units:** prices are in Rs/quintal and arrivals and production in tonnes; 1 tonne = 10 quintals. All costs are converted to Rs/tonne before optimisation.

## 4. Feasibility constraints and data status

| Constraint | Needed for | Data status |
|---|---|---|
| Buy quantity ≤ α × predicted arrivals at the source (α assumed) | not moving the market; realism | arrivals forecast needed (roadmap Ph 9); α is an assumption |
| Sell quantity ≤ β × predicted arrivals at the destination | the market absorbs the volume | same; arrivals are **not demand** (A-02) |
| Capital ≤ budget | sourcing | assumption |
| Vehicle / route capacity | logistics | assumption |
| Warehouse capacity and holding ≤ maximum weeks per crop | storage | assumption; perishability must be sourced (Onion and Potato differ from Wheat) |
| Only series with a forecast in the primary population (D-41 at the origin) | reliable prices | available |
| No information after the origin in any decision input | leakage safety | enforced by the Phase 8 builder; must be kept by every new layer |
| Wheat MSP / procurement windows (April peak) | Wheat pricing realism | policy dates need a source |

## 5. Evaluation of decision rules (when built)

- **Rolling historical backtest** with realised prices. At each origin, decide using information ≤ origin, then book profit at the realised target-week price.
- **Benchmarks:**
  - (i) no trade
  - (ii) a spread rule using current prices only, i.e. persistence; this is the key comparison
  - (iii) the full decision model
- **Periods** follow D-40 for the decision layer:
  - Design decision rules and parameters on **2019–2020**.
  - Evaluate them once on **2021–2022**. Those years were already used to report forecast accuracy, but no decision rule has seen them.
  - Keep the **2023+ holdout** for its own §P forecasting protocol until that has run. Decision-layer use comes only afterwards, by a separate decision.
- **Reports:**
  - profit per crop, with spread and quantile ranges
  - capital-weighted return
  - share of weeks with losses
  - results with and without forecast-error margins

## 6. Proposed build order and dependencies

1. **Commit the Phase 8 checkpoint.**
2. **Price forecast service** (Phase 8 §E):
   - `predict_price()` from the frozen D-42 selection with a model version, plus the `forecast_error_profile` from validation residuals.
   - It depends only on Phase 8.
3. **Cost and constraint assumptions:**
   - Collect sourced values (transport per tonne-km, mandi fees, storage, spoilage, capacities) into `Assumptions.md`, each with a basis.
   - **Blocker:** none of these exist in the data. This step is research, not code.
4. **Market activity forecast** (roadmap Phase 9): persistence-style baselines first, under the same leakage-safe weekly framework. It provides the volume caps.
5. **Market nodes and route costs** (roadmap Phase 11):
   - Extend verified coordinates beyond the 46 districts, using the same admin2 rule (D-16) and never guessing.
   - Use haversine distance with a disclosed limitation until a road-distance source is approved, then shortest paths.
6. **Decision model** (roadmap Phase 12): a deterministic spread / transportation LP first, then the MILP with integer vehicles or warehouse choice.
   - **Already installed:** SciPy 1.16.2 (`scipy.optimize.linprog` / `milp`, HiGHS solvers) and NetworkX 3.6.1 (Dijkstra). These cover the first LP/MILP and the shortest paths without new packages.
   - PuLP and OR-Tools (named in the roadmap) are not installed; adding either needs approval.
7. **Backtest** (roadmap Phases 13/14), then the dashboard last, reading only versioned outputs.

## 7. Open decisions for the project owner

- Phase numbering (above).
- The scope of the first decision model: spatial arbitrage only, or also storage timing.
- The sources for transport, storage, fee and spoilage parameters, and which assumptions are acceptable.
- Whether the decision objective is expected profit only, or profit with a downside-risk term. This matters because the Onion model improves RMSE but not MAE.
- Whether SciPy/NetworkX (installed) are acceptable for the first LP/MILP and the routing, or whether PuLP / OR-Tools should be approved.
- The literature sources to align against.
