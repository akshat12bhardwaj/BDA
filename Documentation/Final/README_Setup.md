# Setup and run guide

This runs locally on Windows with no paid service. Everything below is run from the project root (the folder that contains `Code/`).

## 1. Requirements

| Component | Version | Used for | Licence |
|---|---|---|---|
| Python | 3.13 (`C:\Python313\python.exe`) | the whole pipeline and tests | PSF |
| pandas, numpy, scikit-learn, pyarrow, matplotlib | already installed | Phases 1–10 | BSD / Apache |
| Isolated venv (`--system-site-packages`) | created outside the repo | adds PySpark and Streamlit only | — |
| Eclipse Temurin JDK | 21 LTS (portable zip) | Spark (needs Java 17, 21 or 25) | GPLv2 with Classpath Exception |
| PySpark | 4.2.0 | Big Data component | Apache-2.0 |
| Streamlit | 1.57.0 | dashboard | Apache-2.0 |

The raw data (`Dataset/`, about 4.5 GB) and the `*.parquet` tables are not stored in Git. Copy `Dataset/` in, then rebuild with the phase pipelines (Phase 4 → 6) if needed.

## 2. One-time environment (no global PATH or Java change)

Replace `<ENV>` with a folder outside OneDrive and outside the repository, for example `C:\Users\<you>\bda-env`.

```powershell
# JDK 21 (verify SHA-256 F9D6E191AB098C0D416E7D588A24420A8621CD2F4720DAB2459B8B7B2D2D8B4E)
Invoke-WebRequest -Uri "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip" -OutFile <ENV>\jdk21.zip
(Get-FileHash <ENV>\jdk21.zip -Algorithm SHA256).Hash
Expand-Archive <ENV>\jdk21.zip -DestinationPath <ENV>; Remove-Item <ENV>\jdk21.zip
# venv with PySpark and Streamlit
C:\Python313\python.exe -m venv --system-site-packages <ENV>\venv
<ENV>\venv\Scripts\python.exe -m pip install --no-cache-dir pyspark==4.2.0 streamlit==1.57.0
```

In each new PowerShell window, set these for that process only:

```powershell
$env:JAVA_HOME = "<ENV>\jdk-21.0.12.1+1"
$env:PYTHONDONTWRITEBYTECODE = "1"
```

To remove the environment, delete `<ENV>`.

## 3. Run

| What | Command | Observed |
|---|---|---|
| Spark smoke test | `<ENV>\venv\Scripts\python.exe -c "from pyspark.sql import SparkSession as S; s=S.builder.master('local[2]').getOrCreate(); print(s.version, s.range(10).count()); s.stop()"` | `4.2.0 10` |
| Spark ETL + parity | `<ENV>\venv\Scripts\python.exe -B -m Code.bigdata.mandi_spark` | about 110 s on `local[8]`; parity 0 mismatches on 16,673 district-years |
| Dashboard | `<ENV>\venv\Scripts\streamlit.exe run Code\app\streamlit_app.py --server.headless true --browser.gatherUsageStats false` | open `http://localhost:8501` |
| Phase 10 rebuild | `C:\Python313\python.exe -B -m Code.production.pipeline build` | byte-identical outputs |

**Spark on Windows:** the warning "Did not find winutils.exe" is expected. The ETL never writes with Spark (pandas writes the results), so it is harmless.

## 4. Tests

```powershell
# existing suite (project Python; the Spark and Streamlit smoke tests skip here)
C:\Python313\python.exe -B -m pytest -q -p no:cacheprovider Code/tests
# new components (venv; JAVA_HOME set)
<ENV>\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider Code/tests/test_bigdata_spark.py Code/tests/test_app.py
# optional real-data parity (about 2 minutes)
$env:BDA_SPARK_REAL = "1"; <ENV>\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider Code/tests/test_bigdata_spark.py -k real
```

Results on 2026-10-23:
- Project Python: **268 passed, 2 skipped**.
- venv: **36 passed, 1 skipped** (the opt-in real-data test).
- Real-data parity: **1 passed**.

## 5. Where things are

| Path | Contents |
|---|---|
| `Code/bigdata/` | `mandi_spark.py` (ETL, Spark SQL Q1–Q3), `parity.py`, `mapreduce_demo.py` |
| `Processed_Data/bigdata/` | Spark outputs, `parity_report.csv`, `run_manifest.csv`, `run_log.csv` |
| `Code/app/` | `data.py` (read-only loaders with the data-boundary checks), `streamlit_app.py` |
| `Documentation/Final/` | report, slides, demo script, contribution matrix, checklist, screenshots |
