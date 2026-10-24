# Big Data component and dashboard — implementation specification

**Status (2026-10-23): SPECIFICATION ONLY.** Nothing here is installed or implemented. Code is held until the project owner clarifies the course AI-use policy, and installation is held until the setup in §1 is approved.

**Not touched:** this work does not change any Phase 4–10 file, decision, freeze or evaluation boundary. All new code and outputs go to new locations: `Code/bigdata/`, `Code/app/` and `Processed_Data/bigdata/`.

**Course basis (handout `BDA_CSE 3712_ProjectBased.pdf`):**
- p2, CO2: PySpark and Spark SQL.
- p3, C6–C7: MapReduce and word count.
- p4: the experiential component, "Big data tools".
- p5, A3: focus "Big Data Tools, Hadoop and Pyspark"; Final Functional Application.

**Hadoop / HDFS:** excluded until the instructor clarifies whether the course requires it.
- **Resolved 2026-10-25 (D-54):** Hadoop / HDFS is not mandatory for this course project and is **outside the implementation scope**. It was not implemented, installed or benchmarked. The Big Data component as built is PySpark / Spark SQL in local mode over local files (§2 onward); PySpark lives only in the optional venv of §1, not in the default `requirements.txt`.

---

## 1. Isolated environment (awaiting approval)

`<ENV>` is a folder of your choice, for example `C:\Users\<you>\bda-env`. Everything lives outside OneDrive, so that about 1.5 GB is not synced, and outside the repository. No global PATH, Java or registry setting changes.

| Item | Source | Size | SHA-256 | Destination |
|---|---|---|---|---|
| Eclipse Temurin JDK 21.0.12.1+1 LTS (GPLv2 with Classpath Exception) | `https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip` | 205.1 MB zip, about 330 MB extracted | `f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e` | `<ENV>\jdk-21.0.12.1+1\` |
| Python venv, inheriting the existing Python 3.13.7 packages | `C:\Python313\python.exe -m venv --system-site-packages` | about 20 MB | — | `<ENV>\venv\` |
| pyspark 4.2.0 (Apache-2.0; requires Python ≥ 3.10; Spark 4.2 runs on Java 17/21/25) | PyPI, sdist only (built locally into a wheel) | 450.1 MB download, about 450 MB installed | `5ad689d53570ee1674193fd4f9bda065f0db3be9363a27d2a3406cc457b70b61` | venv `site-packages` |
| py4j 0.10.9.9 (pyspark dependency, BSD) | PyPI wheel | < 1 MB | (pip verifies) | venv |
| streamlit 1.57.0 (Apache-2.0) | PyPI wheel `streamlit-1.57.0-py3-none-any.whl` | 9.2 MB | `0d1d41972aeade5637dbb0e7f0eefa5312272f85304923d240a1b1f0475249c8` | venv |

**Streamlit dependencies not yet installed** (pip resolves them into the venv, about 20 MB in total; the exact list will be confirmed by a dry run): `altair` (plus `jsonschema`, `narwhals`, `jinja2` if absent), `blinker`, `cachetools`, `gitpython` (plus `gitdb`, `smmap`), `pydeck`, `toml`, `httptools`, `itsdangerous`. All other requirements are already installed at compatible versions.

**Build-time downloads:** pyspark has no wheel on PyPI, so pip builds one from the sdist. Its isolated build environment also downloads `setuptools` and `wheel`, about 3 MB.

**Commands, in order** (PowerShell, run from any folder):
```
# 1. JDK (download, verify, extract; no installer, no PATH change)
New-Item -ItemType Directory -Force <ENV> | Out-Null
Invoke-WebRequest -Uri "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip" -OutFile <ENV>\jdk21.zip
(Get-FileHash <ENV>\jdk21.zip -Algorithm SHA256).Hash   # must equal F9D6E191…8B4E
Expand-Archive <ENV>\jdk21.zip -DestinationPath <ENV>
Remove-Item <ENV>\jdk21.zip
# 2. venv
C:\Python313\python.exe -m venv --system-site-packages <ENV>\venv
# 3. dry run (downloads metadata/wheels to resolve only; installs nothing), then install
<ENV>\venv\Scripts\python.exe -m pip install --dry-run pyspark==4.2.0 streamlit==1.57.0
<ENV>\venv\Scripts\python.exe -m pip install --no-cache-dir pyspark==4.2.0 streamlit==1.57.0
# 4. smoke test (JAVA_HOME set for this process only)
$env:JAVA_HOME="<ENV>\jdk-21.0.12.1+1"; <ENV>\venv\Scripts\python.exe -c "from pyspark.sql import SparkSession as S; s=S.builder.master('local[2]').getOrCreate(); print(s.version, s.range(10).count()); s.stop()"
```

**What these change:**
- A new folder `<ENV>\`, about 1.2 GB.
- `--no-cache-dir` avoids a second 450 MB copy in the pip cache.
- Nothing in the repository, `C:\Python313`, `C:\Program Files\Java`, or the system and user environment variables. The global `java` stays JDK 24.

**Removal:** delete `<ENV>\`.

**Known Windows behaviour:**
- Spark prints "Did not find winutils.exe" (it has no Hadoop native binaries). Reading CSVs and running Spark SQL in local mode work without them; Spark's own file **writes** may fail.
- The design therefore never writes with Spark: results are collected to pandas, which writes them.
- Spark does not support JDK 24, so it is not used.

**Cost:** none. Local execution only; no cloud, hosting or paid service.

**Privacy:** Streamlit collects anonymous usage statistics by default. The app is launched with `--browser.gatherUsageStats false`.

---

## 2. PySpark / Spark SQL mandi ETL — `Code/bigdata/mandi_spark.py`

**Input** (read-only)
- `Dataset/India Commodity Wise Mandi Dataset/{Onion,Potato,Wheat}.csv` (about 8.0M rows, roughly 560 MB; one identical header across the three).
- `Processed_Data/integration/district_crosswalk.csv` (D-18).

The raw-file SHA-256 values are checked against `integration/audit/source_fingerprints.csv` before reading, reusing `Code/production/pipeline.verify_inputs`. The crosswalk check uses the documented `alias_basis` canonicalisation.

**Explicit schema:**
- `State Name`, `District Name`, `Market Name`, `Variety`, `Group`: string.
- `Arrivals (Tonnes)`, `Min Price (Rs./Quintal)`, `Max Price (Rs./Quintal)`, `Modal Price (Rs./Quintal)`: double.
- `Reported Date`: string.

Read with `header=true`, `enforceSchema=false` (the header must match the schema), and `mode=PERMISSIVE`. Malformed rows are counted, never dropped silently. A `crop` literal column is added per file.

**Transformations** (no value is repaired)
1. `reported_date = to_date(Reported Date, 'dd MMM yyyy')`; unparseable dates become null and are counted. This is the same format as Phase 4 (A-05: every date for these crops is `DD Mon YYYY`).
2. `apy_year_start = year(d) − (month(d) < 7)`, and `apy_year = concat(start, '-', start + 1)`. This is the Phase 4 `agri_year_start` rule (July–June).
3. **Window:** `reported_date ≤ 2020-06-30`, i.e. `apy_year ≤ 2019-2020`. This ends before the Phase 8/9 test period (2021–2022), the 2023+ holdout and the Phase 9 data cutoff (2020-12-27), and it is applied immediately after the read. The window is a constant, `PARITY_END`, and is asserted in the outputs.
4. Inner join with the crosswalk on (`crop`, `State Name` = `state`, `District Name` = `district`), keeping `apy_district IS NOT NULL`. This is equivalent to the Phase 4 left join followed by `apy_district.notna()`.

**Data-quality checks** (counts only, design and parity window; written to `quality_checks.csv`)

| Check | Condition |
|---|---|
| rows read | per crop |
| malformed rows | Spark corrupt-record count |
| unparseable or missing date | `reported_date IS NULL` |
| missing arrivals; zero arrivals | |
| zero or missing modal price | A-16: zero means "not reported" |
| min > max price | |
| duplicate record-key rows | rows whose (state, district, market, variety, group, date) occurs more than once |
| rows without an APY district | crosswalk unmatched or excluded |

Where Phase 4/5 recorded the same count (for example `integration/audit/duplicate_key_summary.csv`), the report shows both numbers side by side.

**Spark SQL** (temporary views `mandi` and `crosswalk`; the query text is kept in the module and shown in the dashboard)
- **Q1, district-year** (the parity target), grouped by `crop, apy_state, apy_district, apy_year`:
  - `COUNT(*)` → `mandi_records`;
  - `COUNT(DISTINCT market)` → `mandi_markets`;
  - `COALESCE(SUM(arrivals), 0)` → `mandi_arrivals_tonnes_sum` (pandas sums an all-null group to 0);
  - `percentile(modal, 0.5)` (exact) → `mandi_modal_price_median`;
  - `MIN(d)`, `MAX(d)` → first and last date.
- **Q2, weekly market summary** (shown in the dashboard): `date_trunc('week', d)` (Monday weeks, as D-38), with records, arrivals sum and median modal price per crop × state × market × week.
- **Q3, top districts by arrivals** per crop and agricultural year: a SQL window function, `RANK() OVER (PARTITION BY crop, apy_year ORDER BY arrivals DESC)`.

**Outputs** (new folder `Processed_Data/bigdata/`; pandas writes deterministic, sorted, LF CSVs)
- `district_year_spark.csv` (Q1)
- `weekly_market_spark.csv` (Q2)
- `top_districts_spark.csv` (Q3)
- `quality_checks.csv`
- `mapreduce_counts.csv` and `word_count.csv` (§4)
- `parity_report.csv` (§3)
- `run_manifest.csv`: Spark, Java and Python versions; input hashes; window; row counts; output hashes. No timestamps, so it is byte-reproducible.
- `run_log.csv`: UTC time, wall-clock seconds per stage, and `local[N]`. It records observed runtime and is not reproducible by design.

**Command** (project root):
```
$env:JAVA_HOME="<ENV>\jdk-21.0.12.1+1"; <ENV>\venv\Scripts\python.exe -B -m Code.bigdata.mandi_spark
```

**Configuration:**
- `master=local[*]`, `spark.sql.session.timeZone=UTC`, `spark.sql.shuffle.partitions=8`.
- `PYSPARK_PYTHON` is set to the venv interpreter inside the module.
- **Runtime claims** are local single-machine observations only, never cluster performance.

## 3. Spark / Pandas parity test (approved historical period)

**Reference:** `Processed_Data/integration/mandi_apy_district_year.csv`. This is the Phase 4 pandas aggregation `mandi_district_year()`, with content fingerprint `82411357e2d9…` recorded in `integration/audit/output_manifest.csv`. It is verified before use.

**Reference rows:** `link_status != 'apy_only'` and `apy_year ≤ 2019-2020`. That is 16,673 district-years (of 20,530 with mandi data).

**Comparison** on key (`crop, apy_state, apy_district, apy_year`):

| What | Rule |
|---|---|
| key sets | equal both ways |
| `mandi_records`, `mandi_markets`, `mandi_first_date`, `mandi_last_date` | exact |
| `mandi_arrivals_tonnes_sum`, `mandi_modal_price_median` | \|spark − pandas\| ≤ 1e-9 · max(1, \|pandas\|), because summation order differs |

**Report:** `parity_report.csv` gives one row per column: compared, equal, max difference, mismatching keys (first 10).

**Pass:** every count of mismatches is 0. Any mismatch is reported, never "fixed" by changing either side.

**Not compared:** `mandi_duplicate_key_rows`, `mandi_partial_year`, and the APY columns (the latter are joined from APY, not computed from mandi).

## 4. MapReduce-style pattern — `Code/bigdata/mapreduce_demo.py`

**Label:** "Spark RDD `map` / `reduceByKey` — a MapReduce-style processing pattern in Spark local mode. This is not Hadoop MapReduce and not a cluster." The label appears in the module docstring, the output and the dashboard.

1. **Counts:** `rdd.map(r → ((crop, state), (1, arrivals or 0))).reduceByKey(add pairs)` gives records and arrivals per crop × state. It is cross-checked against the Spark SQL `GROUP BY` and must be equal.
2. **Word count** (handout C7): `flatMap` over lower-cased `Variety` tokens, then `map(w → (w, 1))`, then `reduceByKey(+)`, sorted by count. It runs on the same windowed data.

## 5. Synthetic-fixture tests — `Code/tests/test_bigdata_spark.py`

`pytest.importorskip("pyspark")` means the existing suite under `C:\Python313` skips these tests, and the venv runs them. A session-scoped `local[1]` SparkSession is used. The fixture is about 30 handwritten rows in a temporary folder.

**The fixture includes:**
- dates on 30 June and 1 July (agricultural-year boundary);
- an unparseable date;
- a row after `PARITY_END`;
- missing arrivals;
- a group whose arrivals are all missing (sum must be 0);
- a zero modal price;
- min > max;
- an exact duplicate key and a conflicting duplicate key;
- a district without a crosswalk match;
- two markets in one district;
- names containing spaces.

| Test | Assertion |
|---|---|
| schema | output columns and types equal the spec; a CSV with a renamed header raises |
| agricultural year | the boundary dates map to 2018-2019 / 2019-2020 |
| window | no output date after `PARITY_END`; the later row is excluded |
| quality counts | each count equals the hand-computed value |
| **parity (synthetic)** | Spark Q1 equals Phase 4's own `mandi_district_year()` run on the same fixture, through the §3 comparator |
| all-null arrivals | sum = 0 in both |
| MapReduce | `reduceByKey` equals the Spark SQL `GROUP BY`; the word count equals the expected dictionary |
| determinism | two runs give byte-identical CSVs and manifest (run log excluded) |
| integrity | input hashes are unchanged after a run; nothing is written under `Code/modelling/dataset.PROTECTED_DIRS`; outputs only in the temporary or new folder |
| **real-data parity** (opt-in: `BDA_SPARK_REAL=1`) | 0 mismatches on the 16,673 reference rows |

## 6. Read-only Streamlit dashboard — `Code/app/`

> **Superseded 2026-10-24.** The Streamlit app (`Code/app/streamlit_app.py`) and its AppTests were removed; the React frontend (`frontend/`) over the FastAPI service (`Code/api/`) replaces it. `Code/app/data.py` is kept and still enforces the boundaries below. This section is kept as the historical spec.

**Data layer:** `Code/app/data.py` is pure pandas and testable without Streamlit. Every loader enforces its boundary.

**Pages:** `Code/app/streamlit_app.py` uses `st.tabs`, with `st.cache_data` on the loaders.

| Page | Source (read-only) | Shows | Boundary enforced by the loader |
|---|---|---|---|
| 1. Overview | `Master_Project_Context.md` facts; pipeline diagram (`st.graphviz_chart`, rendered in the browser) | problem, data sources, Phases 1–10 built, 11–14 not built | — |
| 2. Price forecasting | `phase08/validation_predictions.parquet` (filtered with pyarrow on crop, horizon and series); `phase08/model_validation_metrics.csv`; `phase08/test_results.csv` | per series: observed `y`, `persistence` and `yhat` (validation 2019–2020); validation and **one-time test** metrics vs persistence. The D-42 outcome is stated plainly: persistence everywhere except Onion h = 1 | `origin_date ≤ 2020-12-27` for predictions; test = metrics only (no Phase 8 test predictions exist); no 2023+ |
| 3. Arrivals forecasting | `phase09_models/candidate_predictions.parquet` (validation); `test_2021_2022/test_predictions.parquet`; `test_metrics.csv`; `candidate_metrics.csv` | crop / horizon / population filters; HGB vs persistence; improvements with intervals | periods ⊆ {val_2019, val_2020, test_2021, test_2022}; asserted |
| 4. Production context | `production_context/production_context_v1.csv` read **with a row filter at load**: `source_apy_year ≤ 2018-2019`; reserved counts from `output_manifest.csv` only | district / state production, area and yield; filters by `pq_class` and `annual_comparability` (classes never merged); R13 and lag warnings; for 2019-20 … 2021-22, **counts per `pq_class` plus a reserved-data notice, no values** | the loader returns no row with a source year > 2018-19 and no reserved value column; asserted |
| 5. Big Data | `Processed_Data/bigdata/*` | Spark workflow diagram, Q1–Q3 SQL text, results, quality checks, parity result (0 mismatches required), MapReduce-style label and counts, word count, observed runtime with the local-mode caveat | — |
| 6. Limitations | Phase 8–10 docs | the two-year lag is an assumption; blocked PQ-1 rules; arrivals are not demand; no optimiser exists; Hadoop status | — |

**What the dashboard never does:** write any file, train or refit, read the 2023+ holdout, or show reserved production values.

**Launch** (project root):
```
<ENV>\venv\Scripts\streamlit.exe run Code\app\streamlit_app.py --server.headless true --browser.gatherUsageStats false
```
Then open `http://localhost:8501`.

**Tests** (`Code/tests/test_app.py`; the data-layer tests run without Streamlit; the AppTest tests use `pytest.importorskip("streamlit")`):

| Test | Assertion |
|---|---|
| loaders | the expected columns load; filters return only the requested crop, horizon and series |
| reserved production | no returned row has a source year > 2018-19; reserved counts equal the output manifest |
| periods | prediction periods are within the allowed set; max date ≤ 2022-12-25 |
| key numbers | displayed improvement % equals `test_metrics.csv` / `test_results.csv` (recomputed from the source CSVs) |
| read-only | protected hashes are unchanged after all loaders run; the app source contains no `.to_csv(`, `.to_parquet(` or write-mode `open(` |
| app smoke | `streamlit.testing.v1.AppTest.from_file(...).run()` raises no exception on any tab |
| screenshots | Edge headless (`msedge --headless --screenshot`) against the running app, saved under `Outputs/Figures/app_*.png` |

## 7. Regression and integrity checks (after each component)

1. `C:\Python313\python.exe -B -m pytest -q -p no:cacheprovider Code/tests`: the existing 262 tests still pass, and the Spark and AppTest tests skip.
2. The venv runs `pytest Code/tests/test_bigdata_spark.py Code/tests/test_app.py`; all pass.
3. The integrity check passes: 62 protected hashes, D-42, D-45, AQ-1, and Phase 8/9 outputs unchanged vs HEAD.
4. Phase 10: `verify_freeze`, and the 19 output hashes are unchanged.
5. `git status` shows only the new paths (`Code/bigdata/`, `Code/app/`, the new tests, `Processed_Data/bigdata/`, this spec and the deliverables). The `EDA_Findings.pdf` deletion and the handout PDF stay untouched.

## 8. Order of work, once approved

| Step | Task | Done when |
|---|---|---|
| 0 | Environment §1 | the smoke test prints `4.2.0 10` |
| 1 | §2 + §3 + §5 | synthetic tests pass; real parity has 0 mismatches; runtime recorded |
| 2 | §4 | the MapReduce-style output equals SQL; the word count is written |
| 3 | §6 | data-layer and AppTest tests pass; screenshots captured |
| 4 | §7 | all checks green |
| 5 | Deliverables | report, slides, demo script, video plan, contribution matrix, setup README |
