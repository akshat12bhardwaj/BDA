# EDA Findings — Phase 7

**Status: [COMPLETED].** Source: `Notebooks/Phase_07_EDA.ipynb`, computed by `Code/eda/analysis.py` into `Processed_Data/eda/` (15 tables) from the Phase 6 feature tables. Figures are in `Outputs/Figures/phase07_*.png`.

**How to read these findings**
- **Prices are nominal Rs/quintal, with no inflation adjustment.** Seasonal patterns are measured relative to each series' own year (price ÷ that series-year's median), so they are not distorted by long-run inflation.
- **A series is crop × market × variety.** Each statistic states its sample; definitions are in `sample_definitions.csv`.
- **Everything here is association, not causation.** Arrivals measure market-supply activity. They are not consumer demand and not total production.

## Onion

- **Level and spread:** the usable-view median is Rs 1,300/qtl (p05–p95: 420–4,000). Pooled CV is 0.79. The median series has CV 0.51 and a 3.2% median absolute change between consecutive observations. It is the most volatile crop.
- **Seasonality:** prices are lowest in April–June (0.77–0.84 of the series-year median) and highest in October–November (1.31–1.33). Arrivals are highest in March–June (1.06–1.18 of the series-year mean). The price trough coincides with the spring arrival peak.
- **Trend:** nominal yearly medians rise with large irregular swings (spikes in 2013, 2015 and 2020–21).
- **Flags:** 22,283 usable rows (0.86%) are price `review` rows, the most of any crop, reflecting genuine spikes. They leave medians unchanged but raise the standard deviation by about 7%.
- **Price vs arrivals:** within series, same-day price and arrivals have a median Spearman of −0.15, negative in 71% of series.
- **Weather (covered subset):** price relative to its trailing 90-day mean rises with 30-day rainfall (median Spearman 0.35). This is likely seasonal confounding, because monsoon months are also rising-price months.
- **APY:** across districts, production vs same-year arrivals is only weakly associated (median Spearman 0.23). APY lag-2 values are missing for 51% of rows.

## Potato

- **Level and spread:** median Rs 850/qtl (p05–p95: 300–2,500). Pooled CV is 0.76; the median series has CV 0.40 and a 1.4% median absolute change.
- **Seasonality:** prices are lowest in February–March (0.75–0.78) and highest in October–November (1.09–1.13). Arrivals are highest December–March (1.14–1.18).
- **Trend:** nominal medians swing strongly (peaks in 2014 and 2020).
- **Flags:** review rows are 0.09% of the usable view, but excluding them lowers the standard deviation by about 13%.
- **Price vs arrivals:** median Spearman −0.14, negative in 70% of series.
- **Weather (covered subset):** a positive association with 30-day temperature (0.41), again aligned with the seasonal calendar.
- **APY:** production vs arrivals median Spearman 0.44. APY lag-2 values are missing for 34% of rows.

## Wheat

- **Level and spread:** median Rs 1,580/qtl (p05–p95: 800–2,400). Pooled CV is 0.31; the median series has CV 0.16 and a 0.8% median absolute change. It is by far the most stable crop.
- **Trend:** nominal medians rise smoothly from about Rs 720 (2002) to Rs 2,310 (2023), consistent with a policy-influenced, MSP-linked staple.
- **Seasonality:** prices are almost flat across months (0.985–1.047). Arrivals spike in April (2.27× the series-year mean) and May (1.69×) — the procurement peak. This supports Phase 5's decision to keep April peaks.
- **Arrivals extremes:** the 8,389,090 t maximum (Faridkot, 2002-12-13) remains in the usable-arrivals view because its market had too little history for the Phase 5 rule (`insufficient_history`). Wheat arrival means and standard deviations should not be used without robust scaling.
- **Price vs arrivals:** essentially unrelated within series (median −0.04).
- **Weather:** no meaningful association on the covered subset.
- **APY:** production vs arrivals across districts is strong (median Spearman 0.76). APY lag-2 values are missing for only 4% of rows.

## Cross-crop findings

- **Prices are highly persistent:** the within-series rank correlation with the previous observation is about 0.95 for all crops.
- **Reporting is irregular but dense:** the median gap is 1 day and the p90 is 3–4 days, but the median reporting density is only 0.19–0.33 of calendar days per series.
- **Variety labels are coarse:** "Other" covers 49–52% of usable rows for every crop. Named varieties differ in price level (e.g. Wheat Dara Rs 1,730 vs Other Rs 1,515).
- **Coverage changes over time:** reporting markets grow until about 2014 and dip in 2020–21. Pooled and yearly statistics therefore mix price change with coverage change.
- **APY production vs median mandi price** is negative across districts (≈ −0.33 to −0.36 for each crop): big producing districts tend to have lower prices. This is a cross-sectional association only.

## Limitations

- **No deflator exists in the project**, so all levels are nominal.
- **Weather coverage is a non-random subset:** 46 high-volume districts, about 25% of rows, ending 2022-12-31.
- **Seasonal indices use calendar months nationally**, so regional calendars are averaged together.
- **All relationships are descriptive and non-causal.**
