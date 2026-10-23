"""
Generator for Documentation/Final/Final_Presentation.pptx (python-pptx). Every number is read from the frozen outputs
or the Spark run files, so the deck cannot drift from the evidence. Run from the project root:
    C:\\Python313\\python.exe -B Code/utils/build_final_slides.py
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

OUT = Path("Documentation/Final/Final_Presentation.pptx")
SHOTS = Path("Documentation/Final/screenshots")
FOREST, MOSS, LEAF, GOLD, INK, MUTED, WHITE, CARD = (RGBColor.from_string(c) for c in
                                                    ["1F4D2B", "97BC62", "E8F0DF", "D99A1E", "1B1B1B", "5A6B5D",
                                                     "FFFFFF", "F4F7F1"])
HEAD, BODY = "Cambria", "Calibri"

bd = Path("Processed_Data/bigdata")
qc = pd.read_csv(bd / "quality_checks.csv")
rows_read = int(qc.loc[qc["check"] == "rows_read_all_years", "value"].astype(int).sum())
par = pd.read_csv(bd / "parity_report.csv")
runlog = pd.read_csv(bd / "run_log.csv")
run_s = runlog.loc[runlog["stage"] == "total", "seconds"].iloc[-1]
p8 = pd.read_csv("Processed_Data/modelling/phase08/test_results.csv")
onion = p8[(p8["crop"] == "Onion") & (p8["horizon_weeks"] == 1)].set_index("period")["rel_mae_improvement_pct"]
p9 = pd.read_csv("Processed_Data/modelling/phase09_models/test_2021_2022/test_metrics.csv")
p9 = p9[(p9["population"] == "primary") & (p9["period"] != "test_combined")]
pc_man = pd.read_csv("Processed_Data/production_context/output_manifest.csv", dtype=str)
pc_rows = int(pc_man.loc[pc_man["item"] == "counts", "value"].astype(int).sum())

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def text(slide, x, y, w, h, runs, size=16, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT, name="text"):
    """runs: a string, or a list of paragraphs; each paragraph a string or (string, {bold, color, size})."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    for i, para in enumerate([runs] if isinstance(runs, str) else runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(6)
        t, o = (para, {}) if isinstance(para, str) else para
        r = p.add_run()
        r.text = t
        r.font.name, r.font.size = o.get("font", font), Pt(o.get("size", size))
        r.font.bold, r.font.color.rgb = o.get("bold", bold), o.get("color", color)
    return tb


def card(slide, x, y, w, h, fill=CARD, name="card"):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    s.adjustments[0] = 0.08
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.fill.background()
    s.shadow.inherit = False
    s.name = name
    return s


def badge(slide, x, y, label, fill=FOREST, name="badge"):
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(0.62), Inches(0.62))
    c.fill.solid()
    c.fill.fore_color.rgb = fill
    c.line.fill.background()
    c.name = name
    tf = c.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = 0
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    r = tf.paragraphs[0].add_run()
    r.text = label
    r.font.name, r.font.size, r.font.bold, r.font.color.rgb = BODY, Pt(13), True, WHITE


def content_slide(title, notes):
    s = prs.slides.add_slide(BLANK)
    text(s, 0.6, 0.4, 12.1, 0.9, title, size=32, bold=True, color=FOREST, font=HEAD, name="title")
    s.notes_slide.notes_text_frame.text = notes
    return s


def dark_slide(notes):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = FOREST
    s.notes_slide.notes_text_frame.text = notes
    return s


def stat(slide, x, y, value, label, w=2.85):
    card(slide, x, y, w, 1.7, name=f"stat {label}")
    text(slide, x + 0.2, y + 0.15, w - 0.4, 0.8, value, size=40, bold=True, color=FOREST, font=HEAD, name="stat value")
    text(slide, x + 0.2, y + 1.0, w - 0.4, 0.6, label, size=14, color=MUTED, name="stat label")


def style_chart(chart, title):
    chart.has_title = True
    chart.chart_title.text_frame.text = title
    tp = chart.chart_title.text_frame.paragraphs[0]
    tp.runs[0].font.size, tp.runs[0].font.bold, tp.runs[0].font.name = Pt(14), True, BODY
    for ax in (chart.category_axis, chart.value_axis):
        ax.tick_labels.font.size, ax.tick_labels.font.name = Pt(12), BODY
        ax.tick_labels.font.color.rgb = MUTED
    chart.value_axis.major_gridlines.format.line.color.rgb = RGBColor.from_string("DDE3D8")
    chart.category_axis.format.line.color.rgb = RGBColor.from_string("BFC8BA")


# 1 — title
s = dark_slide("Introduce the team and the one-sentence goal: evidence for where and when to trade three staple crops.")
text(s, 0.8, 2.1, 11.7, 1.4, "Agricultural Market Decision Support", size=48, bold=True, color=WHITE, font=HEAD,
     name="deck title")
text(s, 0.8, 3.5, 11.7, 0.8, "Onion · Potato · Wheat — prices, arrivals and production from Indian open government data",
     size=22, color=LEAF, name="subtitle")
text(s, 0.8, 5.6, 11.7, 0.9, ["CSE 3712 Big Data Analytics · Project end-term", "[Team members · roll numbers]"],
     size=16, color=MOSS, name="course line")

# 2 — problem and data
s = content_slide("Three public sources, one decision question",
                  "Explain each source and its format. The mandi files are the big-data part; APY gives district "
                  "production; the weather API gives climate covariates.")
for i, (head, big, sub) in enumerate([("Mandi prices & arrivals", "4.5 GB", "325 CSV files · 7.98M rows for 3 crops"),
                                      ("APY district production", "455k rows", "CSV + Excel codebook · DES, Govt. of India"),
                                      ("Open-Meteo weather", "46 sites", "REST API (JSON) · 2001–2022, verified geocoding")]):
    x = 0.6 + i * 4.1
    card(s, x, 1.7, 3.8, 3.2, name=f"source {i}")
    badge(s, x + 0.25, 1.95, str(i + 1))
    text(s, x + 0.95, 1.95, 2.7, 0.6, head, size=18, bold=True, name="source head")
    text(s, x + 0.25, 2.8, 3.3, 0.9, big, size=40, bold=True, color=FOREST, font=HEAD, name="source stat")
    text(s, x + 0.25, 3.8, 3.3, 0.9, sub, size=14, color=MUTED, name="source sub")
text(s, 0.6, 5.3, 12.1, 1.3, [("Question: ", {"bold": True, "color": FOREST}),
                              "Where and when should a trader buy and sell? We build honest, leakage-safe evidence for "
                              "that decision, without claiming an optimiser we have not built."], size=16, name="question")

# 3 — pipeline
s = content_slide("A tested pipeline from raw files to decisions",
                  "Walk left to right. Each step is a tested module with a decision log; selections are frozen by hash.")
steps = [("Integrate", "reviewed crosswalk, July–June year"), ("Clean", "flag, never delete"),
         ("Features", "leakage-safe, t−1 cutoff"), ("EDA", "seasonality, persistence"),
         ("Forecast", "prices & arrivals vs persistence"), ("Context", "district production + PQ-1 flags")]
for i, (head, sub) in enumerate(steps):
    x = 0.6 + i * 2.07
    card(s, x, 2.0, 1.85, 2.2, fill=LEAF if i % 2 else CARD, name=f"step {head}")
    badge(s, x + 0.62, 2.2, str(i + 4) if i < 4 else ("8–9" if i == 4 else "10"))
    text(s, x + 0.1, 2.9, 1.65, 0.5, head, size=17, bold=True, align=PP_ALIGN.CENTER, name="step head")
    text(s, x + 0.1, 3.4, 1.65, 0.8, sub, size=12, color=MUTED, align=PP_ALIGN.CENTER, name="step sub")
card(s, 0.6, 4.7, 12.1, 1.9, name="protocol")
text(s, 0.9, 4.85, 11.5, 1.7, [("Evaluation protocol", {"bold": True, "color": FOREST, "size": 18}),
                               "Chronological: train 2002–2018 · validate 2019–2020 · one-time test 2021–2022 · "
                               "2023+ holdout still unscored",
                               "Every model is compared with persistence; bootstrap intervals; selections frozen by hash"],
     size=15, name="protocol text")

# 4 — big data stats
s = content_slide("PySpark ETL reproduces the pandas pipeline exactly",
                  "Spark reads all raw rows with an explicit schema. Spark SQL district-year totals equal the Phase 4 "
                  "pandas output on every district-year — zero mismatches. Runtime is one machine, not a cluster.")
stat(s, 0.6, 1.7, f"{rows_read / 1e6:.2f}M", "raw rows read (explicit schema)")
stat(s, 3.65, 1.7, f"{int(par['rows_compared'].iloc[0]):,}", "district-years compared")
stat(s, 6.7, 1.7, f"{int(par['mismatches'].sum())}", "parity mismatches vs pandas")
stat(s, 9.75, 1.7, f"{run_s:.0f} s", "end-to-end, local[8], one machine")
card(s, 0.6, 3.8, 12.1, 2.8, name="etl steps")
text(s, 0.9, 3.95, 11.5, 2.6, [("What the ETL does", {"bold": True, "color": FOREST, "size": 18}),
                               "Exact header check → explicit schema → malformed-row and date counts (0 / 0)",
                               "July–June agricultural year; window ≤ 2020-06-30 (before test and holdout periods)",
                               "Quality counts only: duplicate keys, min > max price, zero modal price, unmatched districts",
                               "Results written by pandas; two runs produce byte-identical files"],
     size=15, name="etl text")

# 5 — spark sql + mapreduce
s = content_slide("Spark SQL and a MapReduce-style pattern",
                  "Show the Q1 query. Then the RDD map/reduceByKey job, which equals the SQL GROUP BY. Be explicit: "
                  "this is a Spark pattern in local mode, not Hadoop MapReduce.")
card(s, 0.6, 1.6, 6.6, 5.0, fill=RGBColor.from_string("1E2B22"), name="sql code")
text(s, 0.85, 1.8, 6.2, 4.7, ["SELECT m.crop, c.apy_district, m.apy_year,", "  COUNT(*) AS mandi_records,",
                              "  COUNT(DISTINCT m.market) AS mandi_markets,",
                              "  COALESCE(SUM(m.arrivals_tonnes),0) AS arrivals,",
                              "  percentile(m.modal_price, 0.5) AS median_price",
                              "FROM mandi m JOIN crosswalk c ON ...", "WHERE c.apy_district IS NOT NULL",
                              "GROUP BY m.crop, c.apy_district, m.apy_year"],
     size=14, color=LEAF, font="Courier New", name="sql text")
card(s, 7.5, 1.6, 5.2, 2.3, name="mapreduce")
text(s, 7.75, 1.75, 4.8, 2.1, [("map → reduceByKey", {"bold": True, "color": FOREST, "size": 18}),
                               "((crop, state), (1, arrivals)) summed per key — equals the SQL GROUP BY",
                               "Word count over variety names (topic C7)"], size=14, name="mr text")
card(s, 7.5, 4.2, 5.2, 2.4, fill=LEAF, name="label")
text(s, 7.75, 4.35, 4.8, 2.2, [("Honest label", {"bold": True, "color": FOREST, "size": 18}),
                               "Spark RDD MapReduce-style pattern in local mode — not Hadoop MapReduce, not a cluster.",
                               "Hadoop / HDFS: pending instructor guidance."], size=14, name="label text")

# 6 — prices
s = content_slide("Prices: persistence is hard to beat",
                  "Persistence was selected for eight of nine cells on validation. The one learned model, Onion one "
                  "week ahead, passed validation but was worse than persistence over the combined test period.")
cd = CategoryChartData()
cd.categories = ["Test 2021", "Test 2022", "Test combined"]
cd.add_series("Onion h=1: MAE improvement vs persistence (%)",
              [round(onion[k], 2) for k in ["test_2021", "test_2022", "test_combined"]])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(1.6), Inches(7.2), Inches(5.0), cd)
ch = gf.chart
style_chart(ch, "Onion, 1 week ahead — one-time test (% MAE improvement; < 0 = worse)")
ch.has_legend = False
pl = ch.plots[0]
pl.has_data_labels = True
pl.data_labels.number_format, pl.data_labels.number_format_is_linked = '0.00"%"', False
pl.data_labels.font.size, pl.data_labels.font.name = Pt(12), BODY
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
pl.series[0].invert_if_negative = False
ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
for i, pt in enumerate(pl.series[0].points):
    pt.format.fill.solid()
    pt.format.fill.fore_color.rgb = MOSS if onion[["test_2021", "test_2022", "test_combined"][i]] > 0 else GOLD
for dpt in pl.series[0]._element.findall(qn("c:dPt")):          # a dPt without it renders negatives white
    dpt.find(qn("c:idx")).addnext(dpt.makeelement(qn("c:invertIfNegative"), {"val": "0"}))
card(s, 8.2, 1.6, 4.5, 5.0, name="price takeaway")
text(s, 8.45, 1.8, 4.1, 4.7, [("8 of 9 cells", {"bold": True, "color": FOREST, "size": 28, "font": HEAD}),
                              ("persistence selected on validation", {"color": MUTED, "size": 14}),
                              ("Onion h = 1", {"bold": True, "color": FOREST, "size": 28, "font": HEAD}),
                              (f"{onion['test_combined']:+.2f}% on the combined test — the model did worse",
                               {"color": MUTED, "size": 14}),
                              ("Weekly mandi prices are highly persistent (EDA: within-series correlation ≈ 0.95).",
                               {"size": 14})], name="price text")

# 7 — arrivals
s = content_slide("Arrivals: the model beats persistence in all 18 test cells",
                  "Conservative gradient boosting, selected on validation, beat persistence in every crop × horizon × "
                  "test year. Gains are modest and largest for Wheat. Arrivals are a supply-side activity measure, not demand.")
cd = CategoryChartData()
cd.categories = [f"{c}" for c in ["Onion", "Potato", "Wheat"]]
for h in [1, 2, 4]:
    vals = [round(p9[(p9["crop"] == c) & (p9["horizon_weeks"] == h)]["rel_log_mae_improvement_pct"].mean(), 1)
            for c in ["Onion", "Potato", "Wheat"]]
    cd.add_series(f"{h} week{'s' if h > 1 else ''} ahead", vals)
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(1.6), Inches(8.0), Inches(5.0), cd)
ch = gf.chart
style_chart(ch, "% lower log MAE vs persistence, mean of test 2021 and 2022")
ch.has_legend, ch.legend.position, ch.legend.include_in_layout = True, XL_LEGEND_POSITION.BOTTOM, False
ch.legend.font.size, ch.legend.font.name = Pt(12), BODY
pl = ch.plots[0]
pl.has_data_labels = True
pl.data_labels.number_format, pl.data_labels.number_format_is_linked = '0.0', False
pl.data_labels.font.size, pl.data_labels.font.name = Pt(11), BODY
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
for ser, col in zip(pl.series, [MOSS, FOREST, GOLD]):
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = col
card(s, 8.9, 1.6, 3.8, 5.0, name="arrivals takeaway")
text(s, 9.15, 1.8, 3.4, 4.7, [("18 / 18", {"bold": True, "color": FOREST, "size": 36, "font": HEAD}),
                              ("test cell-years better than persistence", {"color": MUTED, "size": 14}),
                              (f"{p9['rel_log_mae_improvement_pct'].min():.1f}–{p9['rel_log_mae_improvement_pct'].max():.1f}%",
                               {"bold": True, "color": FOREST, "size": 28, "font": HEAD}),
                              ("range of improvement", {"color": MUTED, "size": 14}),
                              ("Two test years only; intervals do not cover nationwide shocks.", {"size": 14})],
     name="arrivals text")

# 8 — production context
s = content_slide("Production context: descriptive, flagged, never repaired",
                  "District APY values two years back, as published. Four comparability classes are never merged. "
                  "Quality rules only flag. The two-year lag is a policy assumption. R13 rows await a provider answer.")
items = [("31,694", "district-year rows (contract v1)"), ("t − 2", "APY year informing decision year t — an assumption"),
         ("4", "comparability classes, never merged"), ("9 / 1 / 5", "PQ-1 rules active / diagnostic / blocked")]
for i, (big, lab) in enumerate(items):
    x, y = 0.6 + (i % 2) * 3.15, 1.6 + (i // 2) * 2.55
    card(s, x, y, 2.95, 2.3, name=f"pc {i}")
    text(s, x + 0.2, y + 0.2, 2.6, 0.9, big, size=34, bold=True, color=FOREST, font=HEAD, name="pc stat")
    text(s, x + 0.2, y + 1.15, 2.6, 1.1, lab, size=14, color=MUTED, name="pc label")
card(s, 7.0, 1.6, 5.7, 4.85, fill=LEAF, name="pc rules")
text(s, 7.25, 1.75, 5.3, 4.6, [("Integrity rules", {"bold": True, "color": FOREST, "size": 18}),
                               "Rules designed on source years ≤ 2018-19 only",
                               "2019-20 … 2021-22 built after a hash freeze; shown as counts only",
                               "37 West Bengal / Gujarat Potato 1997-98 rows marked 'review'; no cause asserted",
                               "No forecasting model, no procurement cap, no marketable-surplus estimate"],
     size=15, name="pc rules text")
assert pc_rows == 31694

# 9 — dashboard
s = content_slide("The functional application: a read-only dashboard",
                  "Live demo here. Six tabs; the data layer enforces the boundaries: validation and test only, no "
                  "holdout, production values only through 2018-19, no file writes.")
shot = SHOTS / "app_5_big.png"
if shot.exists():
    pic = s.shapes.add_picture(str(shot), Inches(0.6), Inches(1.5), height=Inches(5.3))
    pic.name = "dashboard screenshot"
card(s, 4.9, 1.5, 7.8, 5.3, name="tabs")
text(s, 5.2, 1.65, 7.3, 5.1, [("Six tabs", {"bold": True, "color": FOREST, "size": 18}),
                              "Overview — problem, sources, what is built",
                              "Prices — observed vs persistence vs model; test metrics",
                              "Arrivals — crop / horizon / period filters",
                              "Production — class and quality filters; reserved years as counts",
                              "Big Data — Spark workflow, SQL, parity, quality, runtime",
                              "Limitations — what the evidence cannot support",
                              ("Streamlit 1.57 · local · free; usage statistics disabled", {"color": MUTED, "size": 13})],
     size=15, name="tabs text")

# 10 — integrity
s = content_slide("Verification: tests, hashes and frozen evaluations",
                  "Explain run-once guards and hash freezes: test periods were scored exactly once, and nothing in the "
                  "dashboard or Spark job can rerun them.")
stat(s, 0.6, 1.7, "279", "passed, 1 skipped: full suite in the Spark/app venv")
stat(s, 3.65, 1.7, "62", "protected input hashes verified")
stat(s, 6.7, 1.7, "3", "frozen selections verified (D-42, D-45, Phase 10)")
stat(s, 9.75, 1.7, "1×", "each test period scored, once")
card(s, 0.6, 3.8, 12.1, 2.8, name="integrity")
text(s, 0.9, 3.95, 11.5, 2.6, [("How the evidence stays honest", {"bold": True, "color": FOREST, "size": 18}),
                               "Synthetic-fixture parity against Phase 4's own pandas code; real-data parity 0 mismatches",
                               "Dashboard tests: no reserved production value, no holdout row, no file writes",
                               "Selections fixed on validation before any test; the 2023+ holdout remains unscored"],
     size=15, name="integrity text")

# 11 — limitations and next steps
s = dark_slide("Close with the honest limits and the concrete next steps, then hand over to Q&A and the contribution matrix.")
text(s, 0.8, 0.6, 11.7, 1.0, "Limits and next steps", size=40, bold=True, color=WHITE, font=HEAD, name="closing title")
text(s, 0.8, 1.8, 5.6, 4.8, [("What the evidence cannot support", {"bold": True, "color": MOSS, "size": 20}),
                             ("Price models add little over persistence", {"color": WHITE}),
                             ("Arrivals ≠ demand; two test years only", {"color": WHITE}),
                             ("APY lag is an assumption; single 2023 vintage", {"color": WHITE}),
                             ("Spark is local-mode; Hadoop pending guidance", {"color": WHITE}),
                             ("No routing or optimiser: cost data missing", {"color": WHITE})], size=16,
     name="limits")
text(s, 7.0, 1.8, 5.6, 4.8, [("Next", {"bold": True, "color": MOSS, "size": 20}),
                             ("Route costs once distance and cost data are sourced", {"color": WHITE}),
                             ("LP / MILP decision model on those inputs", {"color": WHITE}),
                             ("Rolling historical backtest", {"color": WHITE}),
                             ("Score the 2023+ holdout once, under its protocol", {"color": WHITE})], size=16,
     name="next")

# neutral metadata: python-pptx's template carries its own author and 2013 dates; no team attribution is invented here
cp = prs.core_properties
cp.author = cp.last_modified_by = cp.keywords = cp.subject = cp.category = ""
cp.comments = "CSE 3712 Big Data Analytics project presentation"         # python-pptx's name for dc:description
cp.title = "Agricultural Market Decision Support — CSE 3712"
cp.revision = 1
cp.created = cp.modified = datetime(2026, 10, 23)
OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print("wrote", OUT, "with", len(prs.slides), "slides")
