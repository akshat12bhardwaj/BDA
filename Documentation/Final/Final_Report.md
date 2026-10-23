# Agricultural Market Decision Support for Onion, Potato and Wheat — Final Project Report

**Course:** CSE 3712 Big Data Analytics · **Team:** [names, roll numbers] · **Date:** [submission date]
**Repository:** https://github.com/akshat12bhardwaj/BDA · **Demonstration:** local Streamlit dashboard (`Documentation/Final/README_Setup.md`)

## 1. Problem and objectives

A trader deciding where and when to buy and sell produce needs evidence on three things:
- **prices**;
- **market arrivals** (how much reaches each market);
- **district production**.

India publishes all three as open government data. The data is large, messy and inconsistent across sources.

**Objectives:**
1. Integrate and clean the heterogeneous sources reproducibly.
2. Forecast weekly prices and arrivals, and evaluate the forecasts honestly against a persistence baseline.
3. Build a descriptive production context that respects when the data would really have been available.
4. Process the raw data with Big Data tools (PySpark and Spark SQL).
5. Deliver a working application.

**Scope:** the project is decision support, not an automated trading engine. Routing and optimisation were planned but are not built (§9).

## 2. Data

| Source | Format | Size | Role |
|---|---|---|---|
| Mandi daily prices and arrivals (325 commodity files) | CSV | 4.5 GB; 7,983,133 rows for the three crops | prices, arrivals |
| APY district area / production / yield (DES, Ministry of Agriculture) | CSV + Excel codebook | 455,359 rows | production context |
| Open-Meteo historical weather | REST API (JSON) | 46 verified district locations, 2001–2022 | weather features |

**Crop selection:** Onion, Potato and Wheat were chosen from 320 candidates on mandi, APY and weather feasibility (Phase 2).

## 3. Methodology

The pipeline (Phases 1–10) runs as follows. Each phase has a tested module, an executed notebook and logged decisions (`Documentation/Decision_Log.md`, D-01 – D-48).

| Phase | What it does |
|---|---|
| 1–3 | data understanding, crop selection, weather API collection with verified geocoding |
| 4 | integration at each source's own grain: mandi to APY district through a reviewed crosswalk (no fuzzy matching), and the July–June agricultural year |
| 5 | cleaning with flags, not deletion: zero prices treated as "not reported", duplicates and implausible values flagged |
| 6 | leakage-safe features: trailing windows and APY lagged two years |
| 7 | EDA: seasonality, persistence, the association between quality and readiness |
| 8 | weekly price forecasting (1, 2 and 4 weeks ahead) |
| 9 | weekly arrivals forecasting |
| 10 | descriptive district production context with quality flags (PQ-1) |

**Evaluation protocol (D-40)**
- **Split:** chronological. Train 2002–2018, validation 2019 and 2020, test 2021–2022, and a 2023+ holdout.
- **Selection:** made on validation only, then frozen by hash. The test was run **once**, behind a run-once guard.
- **Holdout:** the 2023+ holdout is still unscored.
- **Baseline:** every model is compared with persistence (last observed value), using paired bootstrap intervals.

## 4. Big Data component (PySpark / Spark SQL)

**Code:** `Code/bigdata/`. Run with PySpark 4.2.0 on JDK 21 in local mode (`local[8]`).

**ETL steps**
1. Read the three raw mandi CSVs (7,983,133 rows) with an **explicit schema**, after an exact header check. Malformed rows are counted; there were 0.
2. Parse dates. There were 0 unparseable dates.
3. Derive the July–June agricultural year.
4. Restrict to dates up to **2020-06-30**. This window ends before the test and holdout periods.
5. Compute data-quality counts. Values are counted, never repaired: duplicate-key rows, min > max price, zero modal price, and rows without an APY district.

**Spark SQL**
- **Q1:** district × agricultural-year aggregation: records, distinct markets, arrivals sum, exact median modal price, first and last date, duplicate-key rows.
- **Q2:** weekly state summary.
- **Q3:** top-10 districts by arrivals per crop and year, using a `RANK()` window.

**Parity:** Q1 was compared with the existing pandas output of Phase 4 (`mandi_apy_district_year.csv`) on **16,673 district-years**. The result was **0 mismatches** on every compared column and on the key set, with sums and medians held to a relative tolerance of 1e-9.

**MapReduce-style pattern:** Spark RDD `map` / `reduceByKey` (records and arrivals per crop × state) equals the Spark SQL `GROUP BY`. A word count over variety names illustrates the classic word-count problem. This is a Spark pattern in local mode, **not Hadoop MapReduce and not a cluster**.

**Observed runtime:** 108–116 s end to end on one machine (28 logical cores; `local[8]`). This is a local observation, not a cluster benchmark.

**Reproducibility:** two runs produced byte-identical output files. The run manifest records the input hashes and the tool versions.

## 5. Results

### 5.1 Prices (D-42)

| Crop | Weeks ahead | Approach selected on validation | One-time 2021–2022 test |
|---|---|---|---|
| Onion | 1 | conservative gradient boosting (with weather) | **−1.58%** MAE improvement vs persistence: 2021 −5.16%, 2022 +3.31% |
| all other 8 cells | 1, 2, 4 | persistence | — |

**Conclusion:** weekly mandi prices are highly persistent. The one learned model that passed validation did **not** beat persistence on the test years.

### 5.2 Arrivals (D-45)

- **Model:** conservative gradient boosting was selected for all 9 crop × horizon cells.
- **Test:** on the one-time 2021–2022 test it beat persistence in **all 18 cell-years**, by 2.3% to 13.5% lower log MAE. The gains are largest for Wheat and modest overall.
- **Caveat:** arrivals measure supply-side market activity, **not demand**.

### 5.3 Production context (D-46 – D-48)

**Contract `phase10-production-context-v1`**
- **Size:** 31,694 district-year rows (crop × district × decision year).
- **Timing:** APY year t − 2 informs decisions in year t, available from 1 July of the decision year. That two-year lag is a **policy assumption**, not a verified publication schedule.
- **Values:** kept as published. The one change: yield is null where production is null.
- **Comparability classes:** verified totals, "Whole Year" rows, single named seasons and ambiguous records are never merged.

**Quality flags (PQ-1 v1)**
- 9 active rules.
- 1 diagnostic rule (R4).
- 5 rules blocked until reference data exists: implausible area, implausible yield, area jump, boundary split, and the R4 row flag.
- 37 West Bengal and Gujarat Potato 1997-98 rows are marked `review` while a query to the data provider is pending. **No cause is asserted.**

**Windows:** design work used source years up to 2018-19. The reserved years 2019-20 to 2021-22 were built mechanically after the rules were frozen, and are shown as counts only.

## 6. Application

A read-only Streamlit dashboard (`Code/app/`; screenshots in `Documentation/Final/screenshots/`) has six tabs:
1. **Overview.**
2. **Prices:** observed values vs persistence vs model on validation, plus test metrics.
3. **Arrivals:** validation and test, by crop and horizon.
4. **Production context:** filters for comparability and quality class; reserved years as counts only.
5. **Big Data:** the Spark workflow, parity, quality checks, SQL, the MapReduce-style output and runtime.
6. **Limitations.**

The data layer enforces the data boundaries, and tests check them: no holdout, no reserved values, no file writes.

## 7. Verification and integrity

**Tests:** the full suite passes in the Spark/Streamlit environment: 279 passed, with 1 opt-in real-data test run separately. On the project interpreter, where Spark and Streamlit are absent, 268 pass and 3 skip. The suite includes:
- synthetic-fixture parity against Phase 4's own pandas code;
- real-data parity;
- an Streamlit `AppTest` smoke test of every tab.

**Integrity checks:**
- the 62 protected input hashes match;
- the frozen selections (D-42, D-45, Phase 10) verify by hash;
- run-once guards stop any repeat of the test evaluations.

## 8. Limitations

- **Forecasts:**
  - Price forecasting adds little beyond persistence.
  - The arrivals gains cover two test years, and the intervals do not capture nationwide shocks.
- **Production data:**
  - There is no verified district APY release history.
  - The input is a single 2023 data vintage.
  - Historical rows are relabelled to present-day geography.
- **Spark and Hadoop:**
  - The Spark results come from a single machine.
  - Hadoop / HDFS is not set up; that is pending instructor guidance.
- **Not built:** routing, optimisation and procurement recommendations. Transport, storage, capacity and demand data are not available.

## 9. Future work

1. Phase 11: market locations and route costs, once sourced distance and cost data exist.
2. Phase 12: an LP/MILP decision model with those inputs.
3. Phase 13: a rolling historical backtest.
4. Score the 2023+ holdout once, under its existing protocol.
5. A Hadoop / HDFS demonstration if the course requires it.

## 10. AI-assistance disclosure

[To be completed by the team, following the instructor's guidance on the course AI-use policy (handout p5).]

The facts to state: the code and documentation were developed with an AI coding assistant (Anthropic's Claude, through Claude Code), as recorded in the Git commit history. Add a description of each member's own role.
