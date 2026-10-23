# Demonstration script (about 10 minutes) and video plan

## Before the session (5 minutes)
- Set the environment for the PowerShell window: `$env:JAVA_HOME`, `$env:PYTHONDONTWRITEBYTECODE` (README_Setup.md §2).
- Start the dashboard: `<ENV>\venv\Scripts\streamlit.exe run Code\app\streamlit_app.py --server.headless true --browser.gatherUsageStats false`, then open `http://localhost:8501`.
- **Fallback if the live run fails:** the screenshots in `Documentation/Final/screenshots/` and the saved Spark outputs in `Processed_Data/bigdata/`.

## Live flow

| Time | Show | Say (one line each) |
|---|---|---|
| 0:00 | Overview tab | Problem, the three crops, the three heterogeneous sources (CSV, Excel, REST API), and what is and isn't built |
| 1:00 | Terminal: `python -B -m Code.bigdata.mandi_spark` (about 2 min; let it run while you talk) | PySpark reads the 8M raw rows with an explicit schema, then counts quality issues without repairing them |
| 1:30 | Big Data tab → Spark SQL Q1 expander | The district-year SQL query; the July–June agricultural year; the window ends before the test years |
| 2:30 | Big Data tab → parity table | Spark SQL equals the existing pandas output on 16,673 district-years: 0 mismatches |
| 3:00 | Big Data tab → MapReduce-style counts + word count | `map` / `reduceByKey` equals SQL. It is a Spark pattern, **not Hadoop** |
| 3:30 | Terminal output → runtime | About 110 s on one machine, `local[8]`; not a cluster benchmark |
| 4:00 | Price tab: Onion, h = 1, a series | Observed vs persistence vs model (validation). The **honest result**: persistence wins on test |
| 5:30 | Arrivals tab: Wheat, h = 4, test_2022 | Arrivals model beats persistence in all 18 test cell-years, modestly |
| 7:00 | Production tab: Potato, 1997-1998, Whole Year, include review | R13 warning; classes never merged; reserved years as counts only; the two-year lag is an assumption |
| 8:30 | Limitations tab | What is not built and why; Hadoop pending instructor guidance |
| 9:00 | Terminal: `pytest Code/tests/test_bigdata_spark.py Code/tests/test_app.py` | Tests prove parity, the data boundaries and read-only behaviour |
| 9:30 | Contribution matrix | Each member names their part, then live Q&A |

## Video plan (if required; handout p5, "if applicable")

- **Length and capture:** 6–8 minutes, screen capture at 1080p (Windows Game Bar `Win + Alt + R`, or OBS Studio, which is free).
- **Order:** follow the live flow above. Cut the Spark run to its start and its finished output, and show the runtime line.
- **Narration:** each member narrates their own component, which satisfies criterion C13 (individual contribution).
- **Export:** MP4, under the LMS size limit, named `CSE3712_<team>_demo.mp4`.
