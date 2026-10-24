"""
Generator for the four read-only extension notebooks (candidate data and the final evaluation):
    Notebooks/Research_Extension_01_Candidate_Price_Data.ipynb
    Notebooks/Research_Extension_02_Candidate_Forecast_Experiments.ipynb
    Notebooks/Research_Extension_03_Final_Persistence_Test.ipynb
    Notebooks/Research_Extension_04_Conclusions_and_Project_Guide.ipynb
Run `python Code/utils/build_extension_notebooks.py` from the project root, then execute each with
`C:\\Python313\\python.exe Code/utils/run_notebook.py Notebooks/<name>.ipynb`.

Read-only: every number comes from saved summary CSV/JSON files under Processed_Data/candidates/. No parquet table,
network call, model fit, experiment run or file write happens; the D-52 test is never rerun and the 2023 holdout is
never read. "Extension" rather than "Phase 11+" because the roadmap reserves those phase numbers (D-49 undecided).
"""

from pathlib import Path

import nbformat as nbf

SETUP = """# Setup: locate the project root; read saved outputs only (no parquet, no network, no writes)
import hashlib, json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "Notebooks" else Path.cwd()
os.chdir(PROJECT_ROOT)
pd.set_option("display.width", 180); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 140)
plt.rcParams.update({"figure.dpi": 100, "axes.grid": True, "grid.alpha": 0.3})
C = Path("Processed_Data/candidates/datagov_prices")      # candidate data and experiments (not production)
EXP = C / "experiments"
CROPS = ["Onion", "Potato", "Wheat"]
COLORS = {"Onion": "#7b3294", "Potato": "#c2a5cf", "Wheat": "#e66101"}
print("Python", sys.version.split()[0])"""

CANDIDATE_NOTE = """> **Status of this material.** Everything here is a **candidate experiment** (`candidate-prices-v1.1`, D-50), kept separate from the production Phase 1–10 pipeline. Nothing in this notebook is a production model, and nothing here changes the dashboard."""


def build(name, cells):
    nb = nbf.v4.new_notebook()
    nb.cells = [nbf.v4.new_markdown_cell(t) if kind == "md" else nbf.v4.new_code_cell(t) for kind, t in cells]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nbf.write(nb, Path("Notebooks") / name)
    print("wrote", name)


# ---------------------------------------------------------------- E1
build("Research_Extension_01_Candidate_Price_Data.ipynb", [
    ("md", """# Extension 1 — Candidate Price Data (2024-02 → 2026-10)

**Question:** the original mandi files stop on 2024-02-02. Can recent, officially published prices extend the price series honestly, without mixing them into the frozen Phase 1–10 work?

| Section | Content |
|---|---|
| 1 | Why a candidate dataset, and its boundary rules (D-50) |
| 2 | Collection: the data.gov.in AGMARKNET feed, stages S1–S3 |
| 3 | Cleaning and build: from raw records to usable weekly targets |
| 4 | Market identity: why most market pairs were *not* merged |
| 5 | Coverage for forecasting, and limitations |

**Previous:** [Phase 7 — EDA](Phase_07_EDA.ipynb) · **Next:** [Extension 2 — Candidate Forecast Experiments](Research_Extension_02_Candidate_Forecast_Experiments.ipynb)

""" + CANDIDATE_NOTE),
    ("code", SETUP),
    ("md", """## 1. Boundary rules (D-50)

- **No data before 2024-02-03.** The 2023 rows belong to the reserved Phase 8 holdout and are never read as ordinary history.
- **Price only.** No arrivals or weather values are created for this period.
- **Grades:** FAQ-only is the primary design; FAQ + Local and pooled grades are sensitivity designs. Source grade labels are never edited.
- **Identities:** only 440 reviewed one-to-one market renames are merged; everything else stays a separate market.

The build contract is stored with the data:"""),
    ("code", """contract = json.loads((C / "dataset_v1_1/contract.json").read_text())
manifest = json.loads((C / "dataset_v1_1/build_manifest.json").read_text())
print("version:", manifest["version"], "| decision:", manifest["decision"], "| candidate start:", manifest["candidate_start"],
      "| R09u approved:", manifest["r09u_approved"])
print("record dates:", contract["inputs"]["date_range"])
pd.Series(contract["approvals"], name="recorded approval").to_frame()"""),
    ("md", """## 2. Collection

Prices were pulled from the public data.gov.in AGMARKNET resource, one crop-day at a time, in three approved stages. Each crop-day was fetched **twice** and accepted only if both fetches returned identical record sets whose count matched the API total. Raw responses are kept outside Git (`Dataset_Candidates/`, key redacted)."""),
    ("code", """stages = []
for f in sorted(C.glob("stage_S*_report_*.json")):
    r = json.loads(f.read_text())
    stages.append({"stage": r["stage"], "run": r["run"], "crop_days": r["crop_days_expected"], "api_calls": r["calls_this_run"],
                   "status": ", ".join(f"{k} {v}" for k, v in r["status_counts"].items()),
                   **{f"records_{k}": v for k, v in r["records_by_crop"].items()}, "accepted": r["accepted"]})
pd.DataFrame(stages)"""),
    ("code", """days = pd.read_csv(C / "crop_day_manifest.csv", parse_dates=["date"])
print(len(days), "crop-days,", days.status.value_counts().to_dict(), "|", days.date.min().date(), "→", days.date.max().date())
fig, ax = plt.subplots(figsize=(11, 3.5))
for crop, g in days.groupby("commodity"):
    w = g.set_index("date").api_total.resample("W").mean()
    ax.plot(w.index, w, label=crop, color=COLORS[crop])
ax.set(title="Records published per day (weekly mean of the API total)", ylabel="records per day"); ax.legend()
plt.show()"""),
    ("md", """## 3. From raw records to usable targets

Each stage applies a documented rule; values are flagged, not repaired. Excluded records are kept with their reason."""),
    ("code", """sc = pd.read_csv(C / "dataset_v1_1/stage_counts.csv")
sc["count"] = sc.records.fillna(sc.usable)
tbl = sc.pivot_table(index="stage", columns="crop", values="count", sort=False).astype(int)
tbl"""),
    ("code", """rep = json.loads((C / "dataset_v1_1/build_report.json").read_text())
ex = pd.Series(rep["exclusions_by_reason"]["price_anomaly"]).rename("records").rename_axis("crop|reason").reset_index()
ex[["crop", "reason"]] = ex["crop|reason"].str.split("|", expand=True)
ex.pivot_table(index="reason", columns="crop", values="records", fill_value=0).astype(int)"""),
    ("md", """**Reading the table.** `key_conflict` (the same market, day and grade reported with different prices) dominates for Wheat: those records are excluded from targets rather than averaged. The Madhya Pradesh Wheat *modal outside [min, max]* pattern began at the source in December 2023 (`Data_Source_Review.md` §6.2)."""),
    ("md", """## 4. Market identity

AGMARKNET renamed many markets when it relaunched. A rename was merged only after review; matching prices alone never establish identity."""),
    ("code", """m = pd.read_csv(C / "decisions_v1/mapping_decisions.csv", usecols=["decision"])
m.decision.value_counts().rename("market pairs").to_frame()"""),
    ("md", """## 5. Coverage for forecasting

The weekly model table has one row per series × origin week × horizon. A row is **evaluated** only if the series has enough usable history at the origin (`eligible_d41`). The split is by the Sunday of the target week."""),
    ("code", """cov = pd.read_csv(C / "experiment_design_v1_1/coverage_by_period.csv")
cov[(cov.design == "faq_only") & (cov.horizon == 1)].set_index(["crop", "period"])[
    ["rows", "markets", "states", "target_weeks", "top5_state_share_pct"]]"""),
    ("code", """cy = pd.read_csv(C / "dataset_v1_1/coverage_by_design_crop_year.csv")
p = cy[cy.design == "faq_only"].pivot(index="year", columns="crop", values="weekly_cells")
ax = p.plot.bar(figsize=(7, 3.5), color=[COLORS[c] for c in p.columns], rot=0,
                title="FAQ-only weekly price cells by year (2026 is a part year)")
ax.set_ylabel("weekly cells"); plt.show()"""),
    ("md", """## Limitations

- **Short history:** about 2.7 years, so seasonal baselines see roughly two seasons.
- **Concentration:** a few states hold most evaluated rows (Wheat: 5 states).
- **Identity:** 1,053 medium-confidence renames stay unmerged pending review, which splits some series.
- **No arrivals or weather** for this period; the candidate experiments are price-only (except the separately approved weather test in Extension 2)."""),
])

# ---------------------------------------------------------------- E2
build("Research_Extension_02_Candidate_Forecast_Experiments.ipynb", [
    ("md", """# Extension 2 — Candidate Forecast Experiments

**Question:** on the new 2024–2026 candidate data, does anything beat *persistence* (next week's price = this week's price)?

| Section | Content |
|---|---|
| 1 | Target, split and metrics (frozen protocol) |
| 2 | Baselines: persistence vs seasonal naive vs climatology |
| 3 | The pre-registered learned model, and why it failed |
| 4 | The weather experiment, its coverage, and why weather was not adopted |
| 5 | What this means |

All scores here are on the **2026 validation window** (target Sundays 2026-01-04 → 2026-06-28). The test window is covered in Extension 3.

**Previous:** [Extension 1](Research_Extension_01_Candidate_Price_Data.ipynb) · **Next:** [Extension 3 — Final Persistence Test](Research_Extension_03_Final_Persistence_Test.ipynb) · **Original-data counterpart:** [Phase 8](Phase_08_Price_Forecasting.ipynb)

""" + CANDIDATE_NOTE),
    ("code", SETUP),
    ("md", """## 1. Protocol (frozen before any score was seen)

- **Target:** the median modal price of a series in the target week, 1 (primary), 2 or 4 weeks after the origin week.
- **Split:** by the Sunday of the target week, so no training target falls inside an evaluated period.
- **Metrics:** MAE in Rs/quintal (primary), RMSE, MAPE (with an instability flag), median absolute percentage error.
- **Uncertainty:** markets are resampled with replacement (cluster bootstrap, 10,000 replicates, seed 20261022), because rows from one market are not independent."""),
    ("code", """proto = json.loads((C / "experiment_design_v1_1/exp_candidate_v1_protocol.json").read_text())
lf = hashlib.sha256((C / "experiment_design_v1_1/exp_candidate_v1_protocol.json").read_bytes().replace(b"\\r\\n", b"\\n")).hexdigest()
print("protocol SHA-256 (LF):", lf)
pd.DataFrame(proto["split_by_target_sunday"], index=["from", "to"]).T"""),
    ("md", """## 2. Baselines"""),
    ("code", """B = EXP / "exp_candidate_v1/baselines_phase8_quarterly"
base = pd.concat([pd.read_csv(B / f"faq_only_h{h}/by_crop.csv").assign(h=h) for h in (1, 2, 4)])
t = base.pivot_table(index=["Commodity", "h"], columns="model", values="mae").round(1)
t[["persistence", "seasonal_naive", "calendar_climatology"]]"""),
    ("code", """b1 = base[base.h == 1].pivot(index="Commodity", columns="model", values="mae")[["persistence", "seasonal_naive", "calendar_climatology"]]
ax = b1.plot.bar(figsize=(8, 3.5), rot=0, color=["#1a9850", "#fdae61", "#d73027"],
                 title="Validation MAE, FAQ-only, 1 week ahead (lower is better)")
ax.set_ylabel("MAE (Rs/quintal)"); plt.show()"""),
    ("md", """**Persistence wins by a wide margin.** Seasonal naive and climatology are roughly 4–12× worse: with ~2.7 years of history, last year's price says little about next week's. Persistence is the default forecast (D-51)."""),
    ("md", """## 3. The pre-registered learned model

One exploratory model was allowed: the Phase 8 conservative gradient boosting with a price-only weekly feature set, h = 1, FAQ-only. The rule fixed in advance: it must beat persistence in **both** validation quarters, with the 95% interval of skill above 0. Skill = 1 − MAE_model / MAE_persistence."""),
    ("code", """sel = pd.read_csv(EXP / "exp_candidate_v1/learned_hgb_conservative_faq_only_h1/run/selection.csv")
ci = lambda s: json.loads(s)
fig, ax = plt.subplots(figsize=(7, 3))
for i, (_, r) in enumerate(sel.iterrows()):
    for j, q in enumerate(["2026Q1", "2026Q2"]):
        lo, hi = ci(r[f"{q}_skill_ci95"]); y = i + (j - 0.5) * 0.25
        ax.errorbar(r[f"{q}_skill"], y, xerr=[[r[f"{q}_skill"] - lo], [hi - r[f"{q}_skill"]]], fmt="o", capsize=3,
                    color=["#4575b4", "#d73027"][j], label=q if i == 0 else None)
ax.axvline(0, color="k", lw=1); ax.set_yticks(range(len(sel)), sel.crop)
ax.set(xlabel="skill vs persistence (95% market-cluster CI)", title="Learned model: every interval is below 0"); ax.legend()
plt.show()
sel[["crop", "2026Q1_skill", "2026Q2_skill", "passes_preregistered_rule"]].round(3)"""),
    ("md", """**Why it failed.** Weekly prices are dominated by last week's level; the model has ~46 weeks of eligible targets and must learn the *change* from noisy weekly medians. Phase 8 saw the same pattern with far more history (its one selected model lost 1.58% on the test years). By the pre-registration, no other setting may be tried on this validation window."""),
    ("md", """## 4. The weather experiment

A second pre-registered experiment added Open-Meteo district weather (`exp-candidate-weather-v1`). Weather exists only for the verified district points, so it could cover only part of the market panel:"""),
    ("code", """rc = pd.read_csv(EXP / "exp_candidate_weather_v1/restricted_coverage.csv")
rc[["crop", "quarter", "eligible_rows", "weather_rows", "weather_row_pct", "weather_markets", "weather_states", "top_state", "top_state_share"]]"""),
    ("code", """acc = pd.read_csv(EXP / "exp_candidate_weather_v1/run/acceptance.csv")
rows = []
for _, r in acc.iterrows():
    for q in ("2026Q1", "2026Q2"):
        rows.append({"crop": r.crop, "quarter": q, "skill": r[f"{q}_skill"], "ci95": [round(x, 3) for x in ci(r[f"{q}_skill_ci95"])],
                     "ci_bonferroni": [round(x, 3) for x in ci(r[f"{q}_skill_ci_bonferroni"])], "pass": r[f"{q}_pass"]})
pd.DataFrame(rows).round(3)"""),
    ("md", """**Why weather was not adopted (D-51).**
- It failed the acceptance rule for every crop: Onion and Potato were clearly worse than persistence, and Wheat was indistinguishable from it (intervals straddle 0).
- Only about 15–26% of eligible rows had weather, from 17–29 market clusters, so even a positive result would have generalised poorly.
- It was the second model on the same validation window, so a multiple-comparison caveat applies (hence the Bonferroni column).
- Weather stays out of the candidate and production forecasting pipeline."""),
    ("md", """## 5. What this means

On recent data, **persistence is the honest default** for weekly mandi prices. Both learned attempts were pre-registered, scored once and recorded as failures; nothing was tuned afterwards. The remaining question was how large persistence's error is on unseen weeks, which is Extension 3."""),
])

# ---------------------------------------------------------------- E3
build("Research_Extension_03_Final_Persistence_Test.ipynb", [
    ("md", """# Extension 3 — Final Persistence Test (D-52, recorded in D-53)

**Question:** how large is the default persistence forecast's error on weeks nobody had looked at?

The candidate test window (target Sundays **2026-07-05 → 2026-10-18**) was opened **exactly once**, under decision D-52, for persistence only. This notebook **reads the saved results**; it never reruns the evaluation (a run-once lock refuses that), and it reads no test-window or holdout rows.

| Section | Content |
|---|---|
| 1 | Run evidence: lock, completion record, output hashes |
| 2 | Headline error by crop and horizon, with uncertainty |
| 3 | Grade-design sensitivity |
| 4 | Error by month, and the Onion 4-week September spike |
| 5 | States: wider uncertainty and leave-one-state-out |
| 6 | Coverage and exclusions |
| 7 | Validation vs test (descriptive only) |
| 8 | The reporting-only restriction |

**Previous:** [Extension 2](Research_Extension_02_Candidate_Forecast_Experiments.ipynb) · **Next:** [Extension 4 — Conclusions](Research_Extension_04_Conclusions_and_Project_Guide.ipynb)

""" + CANDIDATE_NOTE),
    ("code", SETUP),
    ("md", """## 1. Run evidence

The runner created `RUN_LOCK.json` before reading any test row and `RUN_COMPLETED.json` after writing the outputs. Here the chain is re-checked by hashing the saved files (read-only)."""),
    ("code", """D = EXP / "exp_candidate_v1/persistence_test_d52"
R = D / "run"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
lock, done, man = (json.loads((p).read_text()) for p in (D / "RUN_LOCK.json", D / "RUN_COMPLETED.json", R / "run_manifest.json"))
checks = {"completion record matches run manifest": done["run_manifest_sha256"] == sha(R / "run_manifest.json"),
          "run manifest matches freeze": man["freeze_manifest_sha256"] == sha(D / "freeze_manifest.json") == lock["freeze_manifest_sha256"],
          "all outputs match recorded hashes": all(sha(R / f) == h for f, h in man["outputs_sha256"].items())}
print("run:", man["utc_start"], "→", man["utc_end"], "| designs:", man["designs"], "| horizons:", man["horizons"])
print("note:", man["note"])
pd.Series(checks, name="verified").to_frame()"""),
    ("md", """## 2. Headline error (primary design: FAQ-only)

Two 95% intervals are shown for MAE: resampling **markets** (the protocol's interval) and resampling **states** (a robustness check). Few states means a wide state interval."""),
    ("code", """bc = pd.read_csv(R / "by_crop.csv")
fo = bc[bc.design == "faq_only"].set_index(["Commodity", "horizon"])
fo[["n", "markets", "states", "mae", "market_mae_ci95_lo", "market_mae_ci95_hi", "state_mae_ci95_lo", "state_mae_ci95_hi",
    "rmse", "mape_pct", "median_ape_pct", "mape_unstable"]].round(1)"""),
    ("code", """fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))
for ax, crop in zip(axes, CROPS):
    g = fo.loc[crop]
    ax.errorbar(g.index - 0.08, g.mae, yerr=[g.mae - g.market_mae_ci95_lo, g.market_mae_ci95_hi - g.mae], fmt="o", capsize=3, label="market CI")
    ax.errorbar(g.index + 0.08, g.mae, yerr=[g.mae - g.state_mae_ci95_lo, g.state_mae_ci95_hi - g.mae], fmt="s", capsize=3, label="state CI")
    ax.set(title=crop, xlabel="weeks ahead", xticks=[1, 2, 4], ylabel="MAE (Rs/quintal)")
axes[0].legend(); fig.suptitle("Persistence test error grows with horizon (FAQ-only, 95% intervals)"); plt.tight_layout(); plt.show()"""),
    ("md", """**Reading it.** One week ahead, persistence misses Potato and Wheat by about 30–40 Rs/quintal (1–4%), but Onion by about 230 (7.6%). By 4 weeks ahead the error is about 1.7× (Wheat) to 2.9× (Onion) the 1-week error. No cell triggered the MAPE instability flag."""),
    ("md", """## 3. Grade-design sensitivity (1 week ahead)"""),
    ("code", """bc[bc.horizon == 1].pivot(index="Commodity", columns="design", values="mae").round(1)[["faq_only", "faq_local", "pooled"]]"""),
    ("md", """Adding Local and other grades raises Onion's error (more, noisier series) and barely moves Wheat."""),
    ("md", """## 4. Error by month

The Thursday of the target week names its month. Months hold only 3–5 target weeks each."""),
    ("code", """bm = pd.read_csv(R / "by_crop_month.csv")
fig, axes = plt.subplots(1, 3, figsize=(12, 3.5), sharex=True)
for ax, crop in zip(axes, CROPS):
    for h, ls in zip((1, 2, 4), ("-", "--", ":")):
        g = bm[(bm.design == "faq_only") & (bm.horizon == h) & (bm.Commodity == crop)]
        ax.plot(g.month.str[5:], g.mae, ls, marker="o", label=f"h={h}", color=COLORS[crop])
    ax.set(title=crop, xlabel="month (2026)", ylabel="MAE (Rs/quintal)")
axes[0].legend(); fig.suptitle("FAQ-only test MAE by month"); plt.tight_layout(); plt.show()
bm[(bm.Commodity == "Onion") & (bm.horizon == 4)].pivot(index="month", columns="design", values="mae").round(1)"""),
    ("md", """**The Onion 4-week September spike.** Four-week-ahead Onion error in September (about 1,178 Rs/quintal in FAQ-only, MAPE ≈ 29%) is roughly double July–August, and it appears in every grade design. It rests on 4 target weeks, so it describes this season, not a general rule; its cause is **not** established here."""),
    ("md", """## 5. States"""),
    ("code", """bs = pd.read_csv(R / "by_crop_state.csv")
bs[(bs.design == "faq_only") & (bs.horizon == 1) & (bs.Commodity == "Wheat")][["state", "n", "markets", "mae", "market_mae_ci95_lo", "market_mae_ci95_hi"]].round(1)"""),
    ("code", """lo = pd.read_csv(R / "leave_one_state_out.csv")
lo[(lo.design == "faq_only") & (lo.horizon == 1)].groupby("Commodity").agg(
    states=("left_out_state", "size"), mae_all_states=("mae_all_states", "first"), min_without_one=("mae", "min"), max_without_one=("mae", "max")).round(1)"""),
    ("md", """Wheat's evaluated rows come from only **5 states**, dominated by Uttar Pradesh (low error) and Madhya Pradesh (high error). Dropping one of them moves Wheat MAE between about 29 and 57, which is why the state interval is so much wider than the market interval. Some state cells rest on 1–2 markets and are anecdotal."""),
    ("md", """## 6. Coverage and exclusions"""),
    ("code", """cv = pd.read_csv(R / "coverage.csv")
print(pd.read_csv(R / "exclusions.csv").exclusion.unique())
cv[cv.design == "faq_only"].set_index(["Commodity", "horizon"])[
    ["test_rows", "excluded_rows", "evaluated_rows", "markets", "states", "target_weeks", "first_target_week", "last_target_week"]]"""),
    ("md", """- Every cell covers all **16 target weeks**.
- The only exclusion reason is *not eligible at origin* (too little usable history).
- **Limitation:** a week with no observed target price never enters the model table, so it cannot appear as an exclusion. All coverage is conditional on an observed target."""),
    ("md", """## 7. Validation vs test (descriptive only)"""),
    ("code", """val = pd.read_csv(EXP / "exp_candidate_v1/baselines_phase8_quarterly/faq_only_h1/persistence_all_eligible_rows.csv")
v = val.pivot(index="Commodity", columns="quarter", values="mae")
v["test (Jul–Oct)"] = fo.xs(1, level="horizon").mae
v.round(1)"""),
    ("md", """Onion's test error is more than twice its validation error; Potato's is lower; Wheat's is similar. The periods differ in season, rows and markets, so this is a **description, not evidence that forecasting got worse**."""),
    ("md", """## 8. Reporting-only restriction

The test window is now **consumed**. These results must not be used to tune, compare or select models, features, thresholds or populations (D-52 item 10). Any future learned price or arrivals model needs a fresh evaluation period with data after 2026-10-20."""),
])

# ---------------------------------------------------------------- E4
build("Research_Extension_04_Conclusions_and_Project_Guide.ipynb", [
    ("md", """# Extension 4 — Conclusions and Project Guide

## 1. How to read this project

| # | Story step | Notebook(s) |
|---|---|---|
| 1 | Problem, objectives, decision-support motivation | [Demonstration](Overview_00_Project_Demonstration.ipynb), [Phase 1](Phase_01_Project_and_Data_Understanding.ipynb) |
| 2 | Data sources, collection, cleaning, quality, limitations | [Phase 2](Phase_02_Crop_Feasibility_Audit_and_Selection.ipynb), [Phase 3](Phase_03_Weather_Data_Collection.ipynb), [Phase 4](Phase_04_Data_Integration.ipynb), [Phase 5](Phase_05_Data_Cleaning.ipynb), [Phase 6](Phase_06_Feature_Engineering.ipynb), [Extension 1](Research_Extension_01_Candidate_Price_Data.ipynb) |
| 3 | Exploratory analysis | [Phase 7](Phase_07_EDA.ipynb) |
| 4 | Targets, evaluation method, persistence baselines | [Phase 8](Phase_08_Price_Forecasting.ipynb), [Extension 2 §1–2](Research_Extension_02_Candidate_Forecast_Experiments.ipynb) |
| 5 | Learned models and why they did not beat persistence | [Phase 8](Phase_08_Price_Forecasting.ipynb), [Extension 2 §3](Research_Extension_02_Candidate_Forecast_Experiments.ipynb); arrivals: [Phase 9](Phase_09_Arrivals_Model_Experiments.ipynb) |
| 6 | Weather experiment and why weather was not adopted | [Extension 2 §4](Research_Extension_02_Candidate_Forecast_Experiments.ipynb) |
| 7 | Final persistence test (D-52) and its uncertainty | [Extension 3](Research_Extension_03_Final_Persistence_Test.ipynb) |
| 8 | Conclusions, usefulness, limitations, future work | this notebook; production context: [Phase 10](Phase_10_Production_Context.ipynb) |

**Production vs candidate.** Phases 1–10 are the production pipeline behind the application. Extensions 1–3 are a separately versioned **candidate** experiment on 2024–2026 data; none of it is a production model."""),
    ("code", SETUP),
    ("md", """## 2. The evidence in one table

Price forecasting, one week ahead, MAE relative to persistence (negative skill = worse than persistence):"""),
    ("code", """learned = pd.read_csv(EXP / "exp_candidate_v1/learned_hgb_conservative_faq_only_h1/run/by_crop.csv")
weather = pd.read_csv(EXP / "exp_candidate_weather_v1/run/by_crop.csv")
test = pd.read_csv(EXP / "exp_candidate_v1/persistence_test_d52/run/by_crop.csv")
summary = pd.DataFrame({
    "learned model skill (validation)": learned[learned.model == "learned"].set_index("Commodity").skill_vs_persistence,
    "price+weather skill (validation, weather subset)": weather[weather.model == "price_weather"].set_index("Commodity").skill_vs_persistence,
    "persistence test MAE (Rs/q)": test[(test.design == "faq_only") & (test.horizon == 1)].set_index("Commodity").mae,
    "persistence test MAPE %": test[(test.design == "faq_only") & (test.horizon == 1)].set_index("Commodity").mape_pct})
summary.round({"learned model skill (validation)": 3, "price+weather skill (validation, weather subset)": 3,
               "persistence test MAE (Rs/q)": 1, "persistence test MAPE %": 1})"""),
    ("md", """## 3. Conclusions

1. **Prices are highly persistent.** On both the original data (Phase 8, 2021–2022 test) and the 2024–2026 candidate data, no learned model beat "next week = this week" in a pre-registered, one-time test.
2. **Arrivals are different.** The Phase 9 learned arrivals model beat persistence in all 18 test cell-years (by 2.3–13.5% lower log MAE). Arrivals measure supply activity, not demand.
3. **Weather did not help** price forecasting on the subset where it exists, and it is not used.
4. **Honest uncertainty matters.** The persistence test error is small for Wheat and Potato (1.5–3.5% MAPE one week ahead) and larger for Onion (7.6%, rising to 21% at four weeks), with wider uncertainty across states than across markets.

## 4. Practical usefulness

- A trader can treat this week's mandi price as next week's expectation, and use the Extension 3 error bands (by crop, horizon and month) to size the risk, especially for Onion in late summer.
- The application shows prices, arrivals, production context, road routes and mapped warehouses side by side, with every data boundary enforced.
- The pipeline shows how to evaluate forecasts without fooling oneself: frozen protocols, run-once tests, cluster-robust intervals and recorded negative results.

## 5. Limitations

- Candidate data covers only ~2.7 years, price only, concentrated in a few states (Wheat: 5).
- The persistence test covers 16 weeks of one season; weeks without observed target prices are absent.
- The 2023 holdout is still unscored. Routing has no transport cost, and warehouses have no verified capacity or tariffs.
- Spark runs on one machine (local mode), not a cluster.

## 6. Future work

1. **Lawful market-level arrivals** for the candidate period: the DMI request is drafted but not sent; CEDA terms are only partly verified.
2. **A fresh evaluation period** (data after 2026-10-20) for any new price or arrivals model, with a new pre-registration.
3. Score the reserved 2023 holdout once, under its existing protocol, if approved.
4. Transport costs and verified warehouse data, then the planned LP/MILP decision model."""),
])
