"""
Agricultural market decision support — read-only dashboard (Final Functional Application; spec §6).
Run from the project root with the isolated environment:
    <venv>\\Scripts\\streamlit.exe run Code\\app\\streamlit_app.py --server.headless true --browser.gatherUsageStats false
It only reads frozen, validated outputs through Code/app/data.py. Nothing is trained, re-scored or written.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import os

os.chdir(PROJECT_ROOT)

import pandas as pd
import streamlit as st

from Code.app import data as d
from Code.bigdata import mandi_spark as ms
from Code.bigdata.mapreduce_demo import LABEL as MR_LABEL

st.set_page_config(page_title="Mandi Decision Support", layout="wide")
cache = st.cache_data(show_spinner=False)
price_series, price_predictions, price_metrics = cache(d.price_series), cache(d.price_predictions), cache(d.price_metrics)
arrivals_series, arrivals_predictions, arrivals_metrics = (cache(d.arrivals_series), cache(d.arrivals_predictions),
                                                           cache(d.arrivals_metrics))
production_design, production_reserved_counts, bigdata = (cache(d.production_design), cache(d.production_reserved_counts),
                                                          cache(d.bigdata))


def series_label(r) -> str:
    return f"{r.market} ({r.district}, {r.state}) — {r.variety}"


def pick_series(table: pd.DataFrame, key: str):
    labels = [series_label(r) for r in table.itertuples()]
    i = st.selectbox("Series (market — variety)", range(len(labels)), format_func=lambda j: labels[j], key=key)
    return tuple(table.iloc[i][d.SERIES])


st.title("Agricultural Market Decision Support — Onion, Potato, Wheat")
st.caption("CSE 3712 Big Data Analytics project · read-only view of frozen, validated outputs · "
           "historical observations, model predictions and descriptive context are labelled separately")

tabs = st.tabs(["Overview", "Price forecasting", "Arrivals forecasting", "Production context", "Big Data (Spark)",
                "Limitations"])

# ---------------------------------------------------------------- 1. overview
with tabs[0]:
    st.subheader("Problem")
    st.markdown("Traders choosing where and when to buy and sell agricultural produce need evidence on **prices**, "
                "**market arrivals** and **district production**. This project builds that evidence for Onion, Potato "
                "and Wheat from Indian open government data, with leakage-safe evaluation throughout.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Data sources**")
        st.markdown("- Mandi daily prices and arrivals: 325 commodity files, 4.5 GB; about 8.0M rows for the 3 crops\n"
                    "- APY district area / production / yield (DES, Ministry of Agriculture)\n"
                    "- Open-Meteo historical weather API (46 verified district locations)")
    with c2:
        st.markdown("**Built**: Phases 1–10 (data, cleaning, features, EDA, price and arrivals forecasting, "
                    "production context) and this Spark component. **Not built**: Phases 11–14 (routing, "
                    "optimisation, backtest) — their cost and capacity inputs are missing.")
    st.graphviz_chart("""digraph { rankdir=LR; node [shape=box, style=rounded];
        raw [label="Raw mandi CSVs\\nAPY · weather API"]; spark [label="PySpark / Spark SQL ETL\\n(parity-checked)"];
        p4 [label="Integration\\n(Phase 4)"]; p5 [label="Cleaning\\n(Phase 5)"]; p6 [label="Features\\n(Phase 6)"];
        p8 [label="Price forecasts\\n(Phase 8, D-42)"]; p9 [label="Arrivals forecasts\\n(Phase 9, D-45)"];
        p10 [label="Production context\\n(Phase 10, D-46–48)"]; app [label="This dashboard"];
        raw -> p4 -> p5 -> p6 -> p8; p6 -> p9; p4 -> p10; raw -> spark; spark -> p4 [style=dashed, label="parity"];
        p8 -> app; p9 -> app; p10 -> app; spark -> app }""")

# ---------------------------------------------------------------- 2. prices
with tabs[1]:
    st.subheader("Weekly median modal price (Rs/quintal)")
    st.info("Predictions shown are **validation** (2019–2020) only. The 2021–2022 test was run once and is shown as "
            "metrics; no forecast exists for 2023+ (reserved holdout).")
    c1, c2, c3 = st.columns(3)
    crop = c1.selectbox("Crop", d.CROPS, key="p_crop")
    h = c2.selectbox("Horizon (weeks ahead)", d.HORIZONS, key="p_h")
    config = c3.selectbox("Model inputs", ["no_weather", "weather"], key="p_cfg")
    ser = pick_series(price_series(crop, h), "p_series")
    pr = price_predictions(crop, h, ser, config)
    st.line_chart(pr.set_index("origin_date")[["observed", "persistence", "hgb_conservative"]])
    m = price_metrics()
    test = m["test"]
    sel = test[(test["crop"] == crop) & (test["horizon_weeks"] == h)]
    approach = sel["approach"].iloc[0]
    st.markdown(f"**Selected approach (D-42) for {crop}, h = {h}: `{approach}`.**")
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("Validation: conservative HGB vs persistence (MAE improvement %)")
        v = m["validation"]
        st.dataframe(v[(v["crop"] == crop) & (v["horizon_weeks"] == h)].round(2), hide_index=True)
    with t2:
        st.markdown("One-time 2021–2022 test of the selected approach")
        st.dataframe(sel.round(2), hide_index=True)
    st.warning("Honest result: for every cell except Onion h = 1, persistence was selected. For Onion h = 1 the learned "
               "model passed validation but did **worse** than persistence over the combined test period "
               f"({test[(test.crop == 'Onion') & (test.horizon_weeks == 1) & (test.period == 'test_combined')].rel_mae_improvement_pct.iloc[0]:+.2f}% MAE improvement).")

# ---------------------------------------------------------------- 3. arrivals
with tabs[2]:
    st.subheader("Median daily arrivals (tonnes per reported day) — a supply-side activity measure, not demand")
    c1, c2 = st.columns(2)
    crop = c1.selectbox("Crop", d.CROPS, key="a_crop")
    h = c2.selectbox("Horizon (weeks ahead)", d.HORIZONS, key="a_h")
    ser = pick_series(arrivals_series(crop, h), "a_series")
    ap = arrivals_predictions(crop, h, ser)
    period = st.radio("Period", ["test_2021", "test_2022", "val_2019", "val_2020"], horizontal=True, key="a_period")
    part = ap[ap["period"] == period].reset_index(drop=True)
    st.line_chart(part[["observed", "persistence", "hgb_conservative"]])
    st.caption("x-axis: forecast examples in stored order within the period (the stored predictions carry no date).")
    am = arrivals_metrics()
    t = am["test"]
    tt = t[(t["population"] == "primary") & (t["crop"] == crop)][["horizon_weeks", "period", "n", "log_mae",
                                                                  "persistence_log_mae", "rel_log_mae_improvement_pct"]]
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("Validation selection (D-45): % lower log MAE vs persistence")
        s = am["selection"]
        st.dataframe(s[s["crop"] == crop][["horizon_weeks", "candidate", "rel_2019_pct", "rel_2020_pct", "passes"]].round(2),
                     hide_index=True)
    with t2:
        st.markdown("One-time 2021–2022 test (primary population)")
        st.dataframe(tt.round(2), hide_index=True)
    st.success("Conservative HGB beat persistence in all 18 crop × horizon × test-year cells; gains are modest "
               "(about 2–13% lower log MAE).")

# ---------------------------------------------------------------- 4. production context
with tabs[3]:
    st.subheader("District production context (descriptive, not a forecast)")
    st.info("APY values are used as published, under `apy_lag2_policy_v1`: year t − 2 informs decisions in year t. "
            "That two-year lag is a **policy assumption**, not a verified publication schedule.")
    pdn = production_design()
    c1, c2, c3 = st.columns(3)
    crop = c1.selectbox("Crop", d.CROPS, key="c_crop")
    year = c2.selectbox("Source year (design window)", sorted(pdn["source_apy_year"].unique(), reverse=True), key="c_year")
    comp = c3.selectbox("Comparability class (never merged)", ["verified_total", "whole_year_row", "single_named_season"],
                        key="c_comp")
    classes = st.multiselect("Quality classes", ["ok", "annotated", "review"], default=["ok", "annotated"], key="c_pq")
    sub = pdn[(pdn["crop"] == crop) & (pdn["source_apy_year"] == year) & (pdn["annual_comparability"] == comp)
              & pdn["pq_class"].isin(classes)]
    year_rows = pdn[(pdn["crop"] == crop) & (pdn["source_apy_year"] == year)]
    if year_rows["pq_reasons"].fillna("").str.contains("provider_query_pending").any():   # regardless of the filters
        st.warning("R13: West Bengal / Gujarat Potato 1997-98 rows (class `review`) await a DES answer. They are kept "
                   "unchanged; no cause is asserted.")
    if sub.empty:
        st.info("No rows for this crop, year, comparability class and quality selection.")
    else:
        states = sub.groupby("apy_state", as_index=False)["production_tonnes"].sum().sort_values("production_tonnes",
                                                                                                 ascending=False)
        st.bar_chart(states.head(15).set_index("apy_state"))
        st.dataframe(sub[["apy_state", "apy_district", "production_tonnes", "area_ha", "yield_t_per_ha", "pq_class",
                          "pq_reasons", "decision_agri_year", "available_from"]].sort_values("production_tonnes",
                                                                                             ascending=False),
                     hide_index=True)
    st.markdown("**Reserved source years 2019-20 … 2021-22: counts only.** Their values exist in the frozen product "
                "for approved downstream protocols only and are not displayed here.")
    st.dataframe(production_reserved_counts(), hide_index=True)

# ---------------------------------------------------------------- 5. big data
with tabs[4]:
    st.subheader("PySpark / Spark SQL ETL over the raw mandi files")
    bd = bigdata()
    if "run_manifest" not in bd:
        st.error("No Spark run found. Run `python -B -m Code.bigdata.mandi_spark` with JAVA_HOME set.")
    else:
        man = bd["run_manifest"].set_index("name")["value"]
        log = bd["run_log"]
        last = log[log["stage"] == "total"].iloc[-1]
        par = bd["parity_report"]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Rows read (3 crops)", f"{int(bd['quality_checks'].query('check == \"rows_read_all_years\"')['value'].astype(int).sum()):,}")
        k2.metric("District-years compared", f"{int(par['rows_compared'].iloc[0]):,}")
        k3.metric("Parity mismatches", int(par["mismatches"].sum()))
        k4.metric("Last run (s)", f"{last['seconds']:.0f}", help=f"{last['master']} on one machine; not a cluster benchmark")
        st.graphviz_chart("""digraph { rankdir=LR; node [shape=box, style=rounded];
            a [label="3 CSVs\\nexplicit schema\\nheader check"]; b [label="parse date\\nJuly–June year\\nwindow ≤ 2020-06-30"];
            c [label="quality counts\\n(no repair)"]; d [label="Spark SQL\\nQ1 district-year\\nQ2 weekly · Q3 rank"];
            e [label="parity vs Phase 4\\npandas output"]; f [label="RDD map /\\nreduceByKey"];
            a -> b -> c; b -> d -> e; b -> f }""")
        st.markdown(f"Spark {man['spark']} · Java {man['java']} · Python {man['python']} · `{man['master']}` · "
                    f"{man['window']}. {man['note']}.")
        st.markdown("**Parity: Spark SQL Q1 vs the Phase 4 pandas aggregation**")
        st.dataframe(par, hide_index=True)
        st.markdown("**Data-quality checks** (counts only; nothing is repaired)")
        st.dataframe(bd["quality_checks"].pivot(index="check", columns="crop", values="value"))
        with st.expander("Spark SQL Q1 — district-year aggregation"):
            st.code(ms.Q1_DISTRICT_YEAR.strip(), language="sql")
        with st.expander("Spark SQL Q2 / Q3"):
            st.code(ms.Q2_WEEKLY_STATE.strip() + ";\n\n" + ms.Q3_TOP_DISTRICTS.strip(), language="sql")
        w = bd["weekly_state_spark"]
        crop = st.selectbox("Crop", d.CROPS, key="b_crop")
        st.markdown("Q2: weekly arrivals by state (top 5 states)")
        wc = w[w["crop"] == crop]
        top = wc.groupby("state")["arrivals_tonnes_sum"].sum().nlargest(5).index
        st.line_chart(wc[wc["state"].isin(top)].pivot_table(index="week_start", columns="state",
                                                            values="arrivals_tonnes_sum"))
        st.markdown("Q3: top districts by arrivals (window rank)")
        q3 = bd["top_districts_spark"]
        st.dataframe(q3[q3["crop"] == crop].sort_values(["apy_year", "arrivals_rank"], ascending=[False, True]).head(30),
                     hide_index=True)
        st.markdown(f"**{MR_LABEL}.**")
        c1, c2 = st.columns(2)
        c1.dataframe(bd["mapreduce_counts"][["crop", "state", "records", "arrivals_tonnes_sum", "matches_spark_sql"]],
                     hide_index=True)
        c2.bar_chart(bd["word_count"].head(15).set_index("word"))
        st.dataframe(log, hide_index=True)

# ---------------------------------------------------------------- 6. limitations
with tabs[5]:
    st.subheader("Limitations and data quality")
    st.markdown("""
- **Forecasts:** price models rarely beat persistence on the test years. Arrivals gains are real but modest.
  Arrivals measure market activity, **not demand**.
- **Reserved data:** the 2023+ holdout is unscored and never read. Reserved production years appear as counts only.
- **Production context:** the two-year APY lag is an assumption; there is no verified district release history.
  - The quality rules R4 (row flag), R5, R6, R7 and R8b are blocked until reference data exists.
  - West Bengal and Gujarat Potato 1997-98 await a data-provider answer.
  - "Whole Year" and single-season rows are not verified annual totals.
- **Spark:** a local-mode, single-machine run. Its runtime is not a cluster benchmark.
  - The MapReduce-style step is a Spark RDD pattern, not Hadoop.
  - Hadoop/HDFS is not set up; that is pending instructor guidance.
- **Not built:** routing, optimisation and procurement recommendations (Phases 11–14). Transport, storage, capacity and
  demand data are missing, so no sourcing plan is shown.
""")
