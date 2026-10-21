"""
One-time generator for Notebooks/Phase_07_EDA.ipynb.
Run via `python Code/utils/build_phase07_notebook.py` from the project root,
then execute with nbconvert.
"""

import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))


def code(text):
    cells.append(nbf.v4.new_code_cell(text))


md(
"""# Phase 7 — Exploratory Data Analysis

Describes price behaviour, market-arrival patterns, seasonality, weather/APY associations and data limitations for Onion, Potato and Wheat, and assembles the evidence for three decisions that must be made before modelling. Summary computations live in `Code/eda/analysis.py` and are written to `Processed_Data/eda/`; this notebook explains them and draws the figures. **No model is trained and nothing is forecast.**

## INDEX

1. [Objective, Scope and Rules](#1)
2. [Inputs, Column Roles and Analysis Samples](#2)
3. [Run the EDA Computations](#3)
4. [Price EDA](#4)
5. [Market-Arrivals EDA](#5)
6. [Price–Arrivals Association](#6)
7. [Weather Association](#7)
8. [APY Association](#8)
9. [Data Quality and Modelling Readiness](#9)
10. [Decision A — Forecast Horizon and Information Cutoff](#10)
11. [Decision B — Flagged Observations](#11)
12. [Decision C — Evaluation Split](#12)
13. [Validation](#13)
14. [Findings, Limitations and Phase 8 Handoff](#14)
""")

md("""<a id="1"></a>
## 1. Objective, Scope and Rules

- Columns are used by their **Phase 6 registry role** (identifier, target, predictor, eligibility_flag, audit_only) — the 85 columns are not all treated as predictors.
- Every statistic states its **sample**: `all_rows`, `price_present`, `usable_price`, `usable_price_excl_review`, `usable_arrivals`, `usable_arrivals_excl_review` (definitions in `sample_definitions.csv`).
- Crops are analysed **separately**; cross-crop comparisons use relative measures (seasonal indices, coefficients of variation), not raw rupee levels.
- **Prices are nominal Rs/quintal. No inflation adjustment is performed anywhere**; long-run comparisons of rupee levels mix real change with general inflation. Seasonal indices divide each price by its own series-year median, which removes the year's price level.
- Associations are **not causal** evidence. Arrivals measure market-supply activity, not consumer demand and not total production.
- Flagged and conflicting records are never silently dropped: their counts are reported, and their effect on conclusions is measured.""")

md("""<a id="2"></a>
## 2. Inputs, Column Roles and Analysis Samples""")

code(
"""import os, sys, subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "Notebooks" else Path.cwd()
os.chdir(PROJECT_ROOT)
sys.path.append(str(PROJECT_ROOT))
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_colwidth", 80)

from Code.eda import analysis as e
from Code.features import pipeline as f6
from Code.integration import pipeline as p4

CROPS = p4.load_selected_crops()
FIG = Path("Outputs/Figures")
registry = pd.read_csv(f6.AUDIT_DIR / "feature_registry.csv")
print("Column roles in the Phase 6 registry:")
print(registry["role"].value_counts().to_string())
pd.read_csv(f6.AUDIT_DIR / "row_counts.csv")"""
)

md("""<a id="3"></a>
## 3. Run the EDA Computations

Reads the three Phase 6 feature tables (fingerprinted before and after; never modified) and writes 15 summary tables to `Processed_Data/eda/`.""")

code(
"""import logging
logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
R = e.run_eda()
print("Run time (s):", R["seconds"])
R["sample_definitions"].pivot(index=["sample", "definition"], columns="crop", values="rows")"""
)

code(
"""SERIES_C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, MUTED, GRID = "#1f1f1e", "#6b6a64", "#e4e3dd"
plt.rcParams.update({"axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False})
COLOR = dict(zip(CROPS, SERIES_C))"""
)

md("""<a id="4"></a>
## 4. Price EDA

### 4a. Distribution (Rs/quintal, nominal) under three samples""")

code(
"""dist = R["distribution_summary"]
dist[dist["variable"] == f6.MODAL].drop(columns="variable").round(1)"""
)

md("""- Median modal prices (usable view, 2000–2024 pooled): Onion Rs 1,300, Potato Rs 850, Wheat Rs 1,580 per quintal.
- **Relative variability differs sharply**: coefficient of variation 0.79 (Onion), 0.76 (Potato), 0.31 (Wheat). Wheat — an MSP-influenced staple — is far more stable than the two perishable vegetables.
- The Phase 5 usable view removes the absurd maxima (e.g. Potato Rs 1.12 crore/quintal); dropping `review` rows as well changes no quantile up to p99 by more than Rs 50, but lowers the standard deviation (Onion 1,265 → 1,183; Potato 785 → 696). **Review rows affect variance-based statistics, not medians.**

### 4b. Long-run trend (nominal)""")

code(
"""y = R["yearly_profile"].query("variable == @f6.MODAL")
fig, ax = plt.subplots(figsize=(10, 4.2))
for crop in CROPS:
    d = y[(y["crop"] == crop) & y["year"].between(2002, 2023)]
    ax.plot(d["year"], d["median"], color=COLOR[crop], linewidth=2, label=crop)
    ax.fill_between(d["year"], d["p25"], d["p75"], color=COLOR[crop], alpha=0.15, linewidth=0)
ax.set_xlabel("Calendar year (2002-2023; partial years 2000-01 and 2024 omitted)")
ax.set_ylabel("Modal price, Rs/quintal (nominal)")
ax.set_title("Median modal price by year with interquartile band - usable_price sample, NOT inflation-adjusted",
             loc="left", color=INK, fontsize=11)
ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True); ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(FIG / "phase07_nominal_price_trend.png", dpi=150); plt.show()
y.pivot(index="year", columns="crop", values="median")"""
)

md("""Nominal median prices roughly tripled from the early 2000s to 2022–23 for Wheat (≈Rs 720 → 2,310) in a smooth, policy-like path, while Onion and Potato move in large irregular swings (e.g. Onion 2013, 2015, 2020–21; Potato 2014, 2020) on top of the upward drift. Because these are nominal rupees, part of the upward drift is general inflation; the figure should not be read as a real price increase. The composition of reporting markets also changes over time (Section 9), so yearly medians mix price change with coverage change.

### 4c. Seasonality (relative to each series' own year)""")

code(
"""s = R["seasonal_index"]
fig, axes = plt.subplots(2, 3, figsize=(13, 6.5), sharex=True)
months = np.arange(1, 13)
for j, crop in enumerate(CROPS):
    p = s[(s["crop"] == crop) & (s["variable"] == f6.MODAL) & (s["sample"] == "usable_price")]
    ax = axes[0, j]
    ax.fill_between(months, p["p25_rel"], p["p75_rel"], color=COLOR[crop], alpha=0.2, linewidth=0, label="IQR")
    ax.plot(months, p["median_rel"], color=COLOR[crop], linewidth=2, marker="o", markersize=4, label="median")
    ax.axhline(1, color=MUTED, linewidth=1, linestyle="--")
    ax.set_title(f"{crop}: price", loc="left", color=INK)
    a = s[(s["crop"] == crop) & (s["variable"] == f6.ARR)]
    ax2 = axes[1, j]
    ax2.bar(months, a["mean_rel_to_series_year_mean"], color=COLOR[crop])
    ax2.axhline(1, color=MUTED, linewidth=1, linestyle="--")
    ax2.set_title(f"{crop}: arrivals", loc="left", color=INK)
    ax2.set_xticks(months, [m[0] for m in e.MONTHS])
    for a_ in (ax, ax2):
        a_.yaxis.grid(True, color=GRID); a_.set_axisbelow(True)
axes[0, 0].set_ylabel("price / series-year median")
axes[1, 0].set_ylabel("arrivals / series-year mean")
axes[0, 0].legend(frameon=False, fontsize=8)
fig.suptitle("Seasonal pattern by calendar month (series-years with >= 20 observations; usable_price / usable_arrivals samples, 2000-2024)",
             x=0.01, ha="left", color=INK, fontsize=11)
fig.tight_layout(); fig.savefig(FIG / "phase07_seasonal_index_price_arrivals.png", dpi=150); plt.show()
s.pivot_table(index="month", columns=["crop", "variable", "sample"], values="median_rel").round(3)"""
)

md("""- **Onion**: prices are lowest in Apr–Jun (≈0.77–0.84 of the series-year median) and highest in Oct–Nov (≈1.31–1.33); arrivals are highest Mar–Jun (≈1.06–1.18 of the series-year mean). This is consistent with the large rabi-onion harvest reaching markets in spring, followed by depletion of stored stock before the kharif crop — but the data show co-movement only.
- **Potato**: prices lowest in Feb–Mar (≈0.75–0.78), highest Oct–Nov (≈1.09–1.13); arrivals highest Dec–Mar (≈1.14–1.18).
- **Wheat**: prices are almost flat across months (0.985–1.047), while arrivals spike in April (≈2.3× the series-year mean) and May (≈1.7×) — the procurement peak; this supports Phase 5's decision not to treat April arrival peaks as errors.
- Excluding `review` rows changes no monthly median by more than 0.002 (table above).""")

md("""### 4d. Markets, varieties and volatility""")

code(
"""v = R["variety_summary"]
display(v.groupby("crop").head(5)[["crop", "variety", "usable_price_rows", "share_of_usable_rows", "series",
                                    "median_modal", "p25_modal", "p75_modal"]].round(3))
se = R["series_summary"]
se[se["usable_price_rows"] >= 30].groupby("crop")[["cv_modal", "median_abs_pct_change", "reporting_density"]].describe(
    percentiles=[0.25, 0.5, 0.75]).round(3).T"""
)

md("""- "Other" is the largest variety label for every crop (≈49–52% of usable rows) — a generic source category, so variety is only partly informative; named varieties differ in median price (e.g. Wheat Dara Rs 1,730 vs Other Rs 1,515).
- Among series with ≥ 30 usable observations, the median within-series coefficient of variation is ≈0.51 (Onion), ≈0.40 (Potato), ≈0.16 (Wheat), and the median absolute change between consecutive observations is ≈3.2%, ≈1.4% and ≈0.8% — the same ordering as the pooled volatility.
- Reporting density (distinct reported days ÷ days between first and last report) has a median of only ≈0.30 / 0.33 / 0.19 for these series: most series report on a minority of calendar days.""")

md("""<a id="5"></a>
## 5. Market-Arrivals EDA""")

code(
"""display(dist[dist["variable"] == f6.ARR].drop(columns="variable").round(2))
ya = R["yearly_profile"].query("variable == @f6.ARR")
ya.pivot(index="year", columns="crop", values=["markets_active", "median"])"""
)

md("""- Arrivals are extremely skewed (pooled CV 4.7–25): the median market-day handles ≈6 t (Onion), 10 t (Potato) and 23 t (Wheat), while the top 1% exceed ≈1,150–3,300 t. Large values are concentrated in big terminal and procurement markets; Phase 5 left them in place unless they exceeded 100× the market's own past peak.
- Wheat's maximum (8.39 Mt in one market-day) is retained in the `usable_arrivals` sample because its market had insufficient prior history for the Phase 5 rule to judge it; it dominates Wheat's arrivals mean and standard deviation. **Arrivals analyses should use medians, logs or per-market scaling.**
- The number of reporting markets grows strongly until ≈2014 and dips in 2020–2021; yearly arrival *totals* therefore mostly track reporting coverage and are not a production trend.""")

md("""<a id="6"></a>
## 6. Price–Arrivals Association""")

code("""R["relationship_summary"].round(3)""")

md("""Within a series, same-day price and arrivals are **weakly negatively** associated for Onion and Potato (median Spearman ≈ −0.15 and −0.14; negative in ≈70% of series) and essentially unrelated for Wheat (−0.04). The association is modest and partly seasonal (both move with the harvest calendar), so it is not evidence of a demand curve or of arrivals causing prices. Price persistence is very strong: the within-series rank correlation between a price and the series' previous observation has a median of ≈0.95 for all crops.""")

md("""<a id="7"></a>
## 7. Weather Association (covered subset only)""")

code(
"""sp = R["split_evidence"]
print("Share of usable price rows with trailing weather features, by year:")
display(sp.pivot(index="year", columns="crop", values="share_rows_with_weather_features").round(3).T)
R["relationship_summary"][R["relationship_summary"]["relationship"].str.contains("wx_")].round(3)"""
)

md("""- Weather features exist for ≈20–30% of usable price rows in most years (up to 38% in the partial year 2001) and for **none after 2022-12-31** (Phase 3/4 collection window); they come from 46 high-volume districts only, so the covered subset is not a random sample of markets.
- On that subset, price relative to its trailing 90-day mean is positively associated with 30-day rainfall for Onion (median Spearman 0.35) and with 30-day temperature for Potato (0.41); Wheat shows essentially no association. **These coincide with the seasonal calendar** (monsoon months are also Onion's rising-price months), so they are likely seasonal confounding, not weather effects. Any weather-feature benefit must be judged against a calendar-only baseline in Phase 8.""")

md("""<a id="8"></a>
## 8. APY Association (district-year grain)""")

code(
"""ap = R["apy_district_year_association"]
fig, ax = plt.subplots(figsize=(10, 4))
for crop in CROPS:
    d = ap[ap["crop"] == crop]
    yrs = d["apy_year"].str[:4].astype(int)
    ax.plot(yrs, d["spearman_production_vs_mandi_arrivals"], color=COLOR[crop], linewidth=2, marker="o", markersize=3,
            label=f"{crop}: production vs mandi arrivals")
    ax.plot(yrs, d["spearman_production_vs_median_modal"], color=COLOR[crop], linewidth=1, linestyle="--",
            label=f"{crop}: production vs median modal price")
ax.axhline(0, color=MUTED, linewidth=1)
ax.set_xlabel("Agricultural year (start year, July-June)")
ax.set_ylabel("Spearman correlation across districts")
ax.set_title("APY district production vs same-year mandi activity (district-years with both sources, full mandi years)",
             loc="left", color=INK, fontsize=10)
ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True)
ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.18))
fig.tight_layout(); fig.savefig(FIG / "phase07_apy_district_association.png", dpi=150, bbox_inches="tight"); plt.show()
ap.groupby("crop")[["districts", "spearman_production_vs_mandi_arrivals", "spearman_production_vs_median_modal"]].median().round(3)"""
)

md("""- Across districts, higher APY production goes with higher mandi arrivals in the same agricultural year — strongly for Wheat (median Spearman ≈0.76), moderately for Potato (≈0.44) and weakly for Onion (≈0.23) — and with somewhat lower median prices (≈−0.33 to −0.36). These are cross-sectional associations: big producing districts host big markets and often lower farm-gate prices; they do not show that production changes prices over time.
- APY lag-2 features are missing for 51% (Onion), 34% (Potato) and 4% (Wheat) of rows (Phase 6), so APY-based features are realistic mainly for Wheat.""")

md("""<a id="9"></a>
## 9. Data Quality and Modelling Readiness""")

code(
"""q = R["quality_readiness"]
display(q[~q["metric"].str.startswith("missing %")].pivot(index="metric", columns="crop", values="value"))
c = R["conflict_distribution"]
print("Unresolved conflicts (Phase 5) by state (top) and year - kept visible, excluded from usable views:")
display(c.groupby(["crop", "state"])["conflict_rows"].sum().unstack(0).fillna(0).astype(int).sort_values("Potato", ascending=False).head(8))
c.groupby(["crop", "year"])["conflict_rows"].sum().unstack(0).fillna(0).astype(int).T"""
)

code(
"""se = R["series_summary"]
bins = [0, 1, 30, 100, 365, 1000, 10**7]
labels = ["0", "1-29", "30-99", "100-364", "365-999", ">=1000"]
tab = {}
for crop in CROPS:
    g = se[se["crop"] == crop]
    cat = pd.cut(g["usable_price_rows"], bins, right=False, labels=labels)
    tab[(crop, "series")] = cat.value_counts().reindex(labels)
    tab[(crop, "usable rows")] = g.groupby(cat, observed=False)["usable_price_rows"].sum().reindex(labels)
tab = pd.DataFrame(tab)
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
xx = np.arange(len(labels))
for i, crop in enumerate(CROPS):
    axes[0].bar(xx + (i - 1) * 0.27, tab[(crop, "series")], 0.25, color=COLOR[crop], label=crop)
    share = tab[(crop, "usable rows")] / tab[(crop, "usable rows")].sum() * 100
    axes[1].bar(xx + (i - 1) * 0.27, share, 0.25, color=COLOR[crop], label=crop)
for ax, yl, t in [(axes[0], "Number of series", "Series by length"),
                  (axes[1], "Share of usable price rows (%)", "Where the usable rows are")]:
    ax.set_xticks(xx, labels); ax.set_xlabel("Usable price observations per series (crop x market x variety)")
    ax.set_ylabel(yl); ax.set_title(t, loc="left", color=INK)
    ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True)
axes[0].legend(frameon=False)
fig.suptitle("History available per series - usable_price sample, 2000-2024", x=0.01, ha="left", color=INK)
fig.tight_layout(); fig.savefig(FIG / "phase07_series_history_coverage.png", dpi=150); plt.show()
tab"""
)

code(
"""pm = q[q["metric"].str.startswith("missing % (predictor)")].copy()
pm["feature"] = pm["metric"].str.replace("missing % (predictor) ", "", regex=False)
key = ["modal_prev_obs", "modal_lag_1d", "modal_lag_7d", "modal_roll7d_mean", "modal_roll30d_mean", "modal_roll90d_mean",
       "modal_roll30d_std", "arrivals_prev_obs", "arrivals_roll30d_mean", "wx_rain_sum_30d", "wx_temp_mean_mean_30d",
       "apy_production_tonnes_lag2"]
pm[pm["feature"].isin(key)].pivot(index="feature", columns="crop", values="value").loc[key]"""
)

md("""**Readiness findings** (denominator: all Phase 6 rows of the crop):
- 3,924 / 4,003 / 5,279 series; 30–40% have < 30 usable observations, but series with ≥ 365 usable observations (1,473 / 1,551 / 1,540) hold ≈90–93% of all usable price rows. Short series are numerous but carry little data.
- Targets: 1.1% / 1.2% / 0.6% of rows are not in `usable_modal_price`; < 0.01% are not in `usable_arrivals`.
- Unresolved conflicts: 68 / 164 / 106 rows, concentrated in Telangana, Madhya Pradesh and Punjab and in 2006 and 2010–2011; none after 2018.
- History features: previous-observation lags are almost always present (≈0.3–0.5% missing); exact calendar lags are missing 22–34%; weather 75–76%; APY lag-2 51% / 34% / 4%.

**Candidate modelling scope (evidence, not a final rule)**: series with ≥ 365 usable observations and active in the evaluation period cover most of the data; whether to also require regular reporting (e.g. a span of ≥ 2 years and density ≥ 0.5, which keeps only 491 / 592 / 335 series and 45% / 51% / 32% of usable rows) is a trade-off between regularity and coverage that Phase 8 must choose explicitly (see `Modelling_Readiness_Report.md`).""")

md("""<a id="10"></a>
## 10. Decision A — Forecast Horizon and Information Cutoff

Three different tasks:
1. **Next reported observation** — predict the series' next usable price, whenever it occurs. Phase 6 features (data strictly before the row's date) are valid as-is; the horizon is irregular (median gap 1 day, p90 3–4 days).
2. **Specific future calendar day** — predict the price on day o+h. The target exists only if the series reports exactly that day.
3. **Several days/weeks ahead** — predict the level over a future period from an origin o, using only information ≤ o.""")

code(
"""h = R["horizon_feasibility"]
w = R["weekly_horizon_feasibility"]
fig, ax = plt.subplots(figsize=(10, 4))
for crop in CROPS:
    d = h[h["crop"] == crop]
    ax.plot(d["horizon_days"], d["share_exact_day_observed"] * 100, color=COLOR[crop], marker="o", linewidth=2,
            label=f"{crop}: exact day o+h observed")
    ax.plot(d["horizon_days"], d["share_observed_within_pm3d"] * 100, color=COLOR[crop], marker="s", linewidth=1,
            linestyle="--", label=f"{crop}: within +-3 days of o+h")
    ww = w[w["crop"] == crop]
    ax.scatter(ww["horizon_weeks"] * 7, ww["share_target_week_observed"] * 100, color=COLOR[crop], marker="^", s=50,
               label=f"{crop}: target calendar week observed", zorder=3)
ax.set_xlabel("Horizon from a usable observation at origin o (days; weekly targets at 7, 14, 28)")
ax.set_ylabel("Share of origins with a usable target (%)")
ax.set_ylim(40, 101)
ax.set_title("How often a forecast target would actually exist - usable_price sample, 2000-2024", loc="left", color=INK)
ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True); ax.legend(frameon=False, fontsize=7, ncol=3)
fig.tight_layout(); fig.savefig(FIG / "phase07_horizon_feasibility.png", dpi=150); plt.show()
display(h.round(3)); w.round(3)"""
)

md("""**Evidence**: an exact target day o+h is observed only 55–78% of the time (30 days: 55% Wheat, 63% Onion, 66% Potato), whereas the target **calendar week** h weeks ahead holds at least one usable price 81–92% of the time. Exact-day targets would silently select easier, more regularly reported periods and markets.

**Proposed decision (D-38, for review)**: Phase 8's primary task = forecast the **weekly median usable modal price of a series for weeks h = 1, 2, 4 ahead** (≈7–28 days), from a forecast origin at the end of week W, using only information dated ≤ the origin date (Phase 6 features of the origin row or its week; any recomputation must keep the ≤-origin cutoff). Report "next reported observation" as a secondary, short-horizon baseline task. Do not use exact calendar-day targets. Phase 6 feature calculations stay unchanged.""")

md("""<a id="11"></a>
## 11. Decision B — Flagged Observations""")

code("""R["review_flag_effect"].round(3)""")

md("""**Evidence**: `review` rows are 0.86% of Onion usable prices (22,283 rows; reflecting genuine onion price spikes), 0.09% Potato and 0.02% Wheat. Including them leaves medians and p99 essentially unchanged but raises standard deviations (Onion +7%, Potato +13%). Suspected scale/entry errors (422 / 415 / 148 price rows; 75 / 62 / 53 arrivals rows) and the 338 unresolved conflicts are already outside the usable views.

**Proposed decision (D-39, for review)**: (1) train and evaluate only on `usable_modal_price` / `usable_arrivals` rows — i.e. exclude suspected scale/entry errors and unresolved conflicts from targets *and* history (already the Phase 6 history rule); (2) **retain `review` rows** in the primary experiments, because they are plausible extreme market events and the forecasting system must handle them; (3) run a sensitivity analysis excluding `review` targets and report both, especially for Onion; (4) never delete flagged rows — all flags and `source_row` stay in the data.""")

md("""<a id="12"></a>
## 12. Decision C — Evaluation Split""")

code(
"""sp = R["split_evidence"]
fig, ax = plt.subplots(figsize=(10, 4.2))
for crop in CROPS:
    d = sp[sp["crop"] == crop]
    ax.plot(d["year"], d["usable_price_rows"] / 1000, color=COLOR[crop], linewidth=2, marker="o", markersize=3, label=crop)
spans = [(2001.5, 2018.5, "train (expanding)", "#eeeeee"), (2018.5, 2020.5, "validation", "#dfe9f7"),
         (2020.5, 2022.5, "test", "#fbe3d6"), (2022.5, 2024.5, "no-weather holdout", "#e4f2ea")]
for a, b, lab, col in spans:
    ax.axvspan(a, b, color=col, zorder=0)
    ax.text((a + b) / 2, 205, lab.replace("no-weather holdout", "holdout"), ha="center", fontsize=8, color=INK)
ax.axvline(2022.99, color=INK, linestyle="--", linewidth=1)
ax.text(2023.05, 20, "weather ends\\n2022-12-31", fontsize=8, color=INK)
ax.set_ylim(0, 215)
ax.set_xlabel("Calendar year"); ax.set_ylabel("Usable price rows (thousands)")
ax.set_title("Usable price rows per year and the proposed chronological evaluation periods\\n"
             "(holdout = 2023-01-01 to 2024-02-02, for models without weather features)", loc="left", color=INK, fontsize=11)
ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True); ax.legend(frameon=False, loc="upper left")
fig.tight_layout(); fig.savefig(FIG / "phase07_split_evidence.png", dpi=150); plt.show()
sp.pivot(index="year", columns="crop", values=["usable_price_rows", "series_active", "series_with_earlier_history"])"""
)

md("""**Why not a random row split**: consecutive observations of a series are almost the same number (median within-series rank correlation with the previous observation ≈0.95). With a random split, a test row's neighbours — often the previous and next day of the same market — are in the training set, so a model can effectively interpolate and look far better than it would when forecasting the future. Rolling-window features would also straddle train and test.

**Evidence for a chronological design**: in 2021–2022, 87–97% of active series already had usable history in earlier years (`series_with_earlier_history`), so out-of-time testing does not mostly evaluate unseen series; weather features end on 2022-12-31; 2001 and 2024 are partial years; reporting dipped in 2020 (Wheat −27% rows).

**Proposed decision (D-40, for review)**: chronological, out-of-time evaluation with an expanding training window — train 2002–2018, validation 2019–2020 (for model/hyper-parameter choice), test 2021–2022 (weather and APY available; touched once), plus a 2023-01-01–2024-02-02 holdout for models that do not use weather features. Within that, use rolling forecast origins (e.g. monthly origins through the test period, each model trained only on data before the origin), leave a gap of at least the forecast horizon between the last training target and the first test origin, fit any scaler/encoder/imputer on training data only, and report metrics per crop, per horizon and for series with and without long history. Exact years must be confirmed in Phase 8 planning.""")

md("""<a id="13"></a>
## 13. Validation""")

code(
"""checks = {}
fp = R["input_fingerprints"]
checks["Phase 6 feature files unchanged during EDA (SHA-256)"] = bool(fp["unchanged"].all())
m6 = pd.read_csv(f6.AUDIT_DIR / "output_manifest.csv").set_index("file")
for crop in CROPS:
    df = pd.read_parquet(f6.FEATURE_DIR / f"features_{crop.lower()}.parquet")
    checks[f"{crop}: feature table content == Phase 6 manifest"] = (
        f6.frame_fingerprint(df) == m6.loc[f"features_{crop.lower()}.parquet", "content_sha256"])
    sd = R["sample_definitions"].query("crop == @crop").set_index("sample")["rows"]
    checks[f"{crop}: sample counts reproduce from the feature table"] = all(
        sd[k] == int(m.sum()) for k, m in e.masks(df).items())
    se_c = R["series_summary"].query("crop == @crop")
    checks[f"{crop}: series table covers every row once ({len(df):,})"] = int(se_c["rows"].sum()) == len(df)
    checks[f"{crop}: conflicts visible in EDA tables"] = (
        int(R["conflict_distribution"].query("crop == @crop")["conflict_rows"].sum())
        == int((df["dup_status"] == "conflict_unresolved").sum()))
    yr = R["yearly_profile"].query("crop == @crop and variable == @f6.MODAL")
    checks[f"{crop}: yearly usable rows sum to the usable sample"] = int(yr["rows"].sum()) == int(df["usable_modal_price"].sum())
    del df
s = R["seasonal_index"]
checks["Seasonal tables have exactly months 1-12 for every crop/variable/sample"] = bool(
    s.groupby(["crop", "variable", "sample"])["month"].apply(lambda m: sorted(m) == list(range(1, 13))).all())
for k, v in checks.items():
    print(("PASS" if v else "FAIL"), "-", k)
assert all(checks.values()), "Phase 7 validation failed"
print("\\nAll Phase 7 notebook validation checks passed.")"""
)

code(
"""tests = subprocess.run([sys.executable, "-m", "pytest", "Code/tests", "-q", "-p", "no:cacheprovider"],
                       capture_output=True, text=True)
print(tests.stdout[-3000:])
assert tests.returncode == 0, "Project test suite failed"
print("Full suite: Phases 4-7.")"""
)

md("""<a id="14"></a>
## 14. Findings, Limitations and Phase 8 Handoff

**Findings** are summarised in `Documentation/EDA_Findings.md`; data quality, candidate scope and the three proposed decisions in `Documentation/Modelling_Readiness_Report.md` and Decision Log D-38 – D-40.

**Limitations**: nominal prices only (no deflator in the project); reporting coverage changes over time, so pooled and yearly statistics mix price change with coverage change; weather associations are confounded with seasonality and cover a non-random 25% of rows ending in 2022; APY associations are cross-sectional; seasonal indices use calendar months for all regions; all results are associations, not causal effects.

**Phase 7 status: completed** (validation above). **Next**: Phase 8 planning — review and confirm D-38 – D-40 (target and horizon, flag policy, split years) before any model is trained.""")

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.13"},
}

out_path = "Notebooks/Phase_07_EDA.ipynb"
with open(out_path, "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print("Notebook written to", out_path, "with", len(cells), "cells")
