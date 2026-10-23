# Phase 9 — Market-Activity (Arrivals) Modelling: problem definition and baseline protocol

**Status: [PROTOCOL written 2026-10-22, before any Phase 9 code or results].** Scope is roadmap Phase 9 (`Future_Work_Roadmap.md`). Results are added in §9 after the baseline run. **Arrivals are a supply-side measure of market activity, not demand** (A-02); no output is ever labelled "demand".

## 1. Data audit (read-only; Phase 6 feature tables, which keep the Phase 5 flags)

**Coverage and quality** (Onion / Potato / Wheat):

| Item | Onion | Potato | Wheat |
|---|---|---|---|
| Rows | 2,623,671 | 2,764,417 | 2,593,279 |
| Arrivals value missing (NaN) | 0 | 0 | 0 |
| `usable_arrivals` | 99.995% | 99.992% | 99.994% |
| Not usable (entry error suspected + unresolved conflicts) | 143 (75 + 68) | 226 (62 + 164) | 159 (53 + 106) |
| `review` (kept usable) | 399 | 399 | 484 |
| `insufficient_history` (Phase 5 rule not applicable; kept usable) | 30,409 | 29,208 | 43,707 |
| Genuine zero arrivals (usable) | 9 | 3 | 14 |
| Duplicate usable (series, date) | 0 | 0 | 0 |
| Usable daily arrivals p50 / p90 / p99 (tonnes) | 5.9 / 134 / 1,752 | 10 / 140 / 1,154 | 23 / 310 / 3,316 |
| Series with ≥ 365 usable arrival dates over the full history (reporting only) | 1,481 | 1,564 | 1,552 |
| Rows with usable arrivals but no usable price | 27,983 | 32,982 | 14,155 |

**Source semantics:**
- The raw mandi files carry `Arrivals (Tonnes)` on every record. Onion, for example, has 0 blanks and 9 explicit zeros in 2,624,379 rows.
- **A day without a record therefore means "not reported", not "zero arrivals".** Closures, holidays and non-reporting cannot be told apart in the data, so days without a record are never filled with 0.

**Reporting frequency** varies widely. Share of series-weeks by number of reporting days:

| Days reported | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| Onion | 13.8% | 12.0% | 10.0% | 11.8% | 16.7% | 23.4% | 12.3% |
| Potato | 11.6% | 9.9% | 8.7% | 11.3% | 16.8% | 25.7% | 16.0% |
| Wheat | 16.6% | 12.2% | 11.5% | 14.4% | 19.0% | 22.7% | 3.6% |

**Implausible magnitudes remain usable** (a data-quality finding; Phase 5 is protected and is not changed here):
- Phase 5 (D-30) flags a value only against the market's previous 365-day **peak**. Markets whose earlier values were already inflated pass, and `insufficient_history` rows are not checked.
- **Example:** Wheat, Faridkot, 2002-12-13: 8,389,090 t in one day, against a trailing 90-day median of 461,393 t that is itself implausible.
- **Scale:** usable rows above 100× their own trailing 90-day median number 1,004 / 895 / 8,422 (Onion / Potato / Wheat). This is a descriptive screen only, not a flag.
- **Revisions:** none. The source has no revision field, and conflicting duplicates have identical arrivals (D-26).

**Units:** tonnes per reported day. Price forecasts use Rs/quintal; 1 tonne = 10 quintals.

## 2. Target

- **Target:** the **weekly median of usable daily arrivals (tonnes per reported day)** for series s in week W + h. Weeks run Monday–Sunday, the same as Phase 8.
- **Why a median per reported day, not a weekly sum:**
  - A sum mixes market volume with how many days a market happened to report, which varies from 1 to 7 days per week.
  - A median resists the unflagged unit errors in §1.
  - It mirrors the Phase 8 price target, so price and arrivals forecasts share one key and one week convention.
- **Downstream use:** consumers who need a weekly volume must multiply by an assumed number of trading days and say so. Nothing here estimates trading days.
- **Missing target:** a week with no usable arrivals record has **no example**, because a gap is not zero. Genuine zero reports stay zero.
- **Review rows:** usable `review` rows stay in targets, as in Phase 8 (D-39). No review-sensitivity variant is run at the baseline stage.

## 3. Origin, horizons, series, eligibility

- **Origin:** the end of Sunday of week W. Horizons are h = 1, 2 and 4 weeks. Series key: (crop, state, district, market, variety), as in D-33.
- **Origins exist only** for series-weeks with at least one usable arrivals record in week W.
- **Eligibility**, mirroring D-41 for arrivals and counting **usable arrival dates**:
  - **Evaluation:** at least 365 distinct usable arrival dates on or before the origin (`eligible_at_origin`).
  - **Training** for anything fitted at refit date T: series that reached 365 dates by T (`eligible_from_origin` ≤ T).
  - The full-history count is reporting only.
- **Status:** this is a **proposed** Phase 9 rule. It needs a decision entry before it is treated as accepted.

## 4. Information available at the origin

- **Allowed:** usable arrivals rows dated ≤ origin, through:
  - origin-week aggregates: median and number of reporting days
  - earlier weekly medians of the same series, used by seasonal naive
  - calendar fields of the target week
- **Not allowed:** target-week rows and anything dated after the origin.
- Phase 6 arrivals features (`arrivals_*`, which use data before the anchor date) are allowed for later learned models; baselines do not use them.

## 5. Periods (consistent with D-40)

| Period | Target-week Sundays | Use in this phase |
|---|---|---|
| Train | 2002-01-06 – 2018-12-30 | fitting learned seasonal quantities |
| Validation 2019 / 2020 | 2019-01-06 – 2020-12-27 | baseline comparison, years reported separately and combined |
| Test | 2021-01-03 – 2022-12-25 | **reserved; not scored in this phase** |
| Holdout | 2023-01-01 → | **reserved; not accessed** |

**Hard separation:**
- The builder **truncates its input at 2020-12-27** (the last validation target Sunday) before anything is computed, so no 2021+ row is ever read into a Phase 9 dataset in this phase.
- Refits are quarterly: the latest quarterly refit on or before each origin, and training targets end on or before the refit date (§B.7 of the Phase 8 plan).

## 6. Baselines (nothing learned except where stated)

1. **Persistence:** the origin-week median.
2. **Seasonal naive:** the series' weekly median 52 weeks before the target week, where one exists. Its coverage is reported.
3. **Calendar-adjusted persistence:** origin-week median × exp(m), where m is the median of log((target + 1) / (origin + 1)) over refit-eligible training examples, per crop × horizon × target month. It is fitted at each quarterly refit on training data only; log1p is used because zero arrivals exist.

No other model is fitted at this stage.

## 7. Metrics and segments

**Metrics:**
- **Primary: log MAE** = mean |log(1 + forecast) − log(1 + actual)|. It is scale-free and robust to the unflagged unit errors.
- MAE (tonnes/day)
- median absolute error (tonnes/day)
- WAPE = Σ|e| / Σ actual (%)
- skill vs persistence on log MAE, on identical rows

MAPE is not used, because actual arrivals can be 0.

**Reporting:** by crop × horizon × 2019 / 2020 / combined, and by segment:
- reporting days in the origin week: 1–2, 3–5, 6–7
- origin-week median volume: < 10, 10–100, ≥ 100 t/day

## 8. Alignment and output

- Arrivals forecasts use the **same key and week fields** as `phase8-forecast-v1` (crop, state, district, market, variety, origin_date, horizon_weeks; Monday–Sunday target weeks). They join row-for-row on that key and stay a separate component.
- The contract is `phase9-arrivals-forecast-v1` (`Arrivals_Forecast_Contract.md`).
- Until a Phase 9 selection decision exists, its approach is **provisional persistence**, and it is labelled as such.

## 9. Results: validation 2019–2020 only (2026-10-22)

**Run:** `Code/modelling/arrivals.py:run_arrivals_baselines()`. Outputs are in `Processed_Data/modelling/phase09/`:
- `arrivals_baseline_metrics.csv`, `arrivals_refit_log.csv`
- `arrivals_dataset_manifest.csv`, `arrivals_sample_counts.csv`, `arrivals_eligibility_summary.csv`
- `arrivals_input_fingerprints.csv`, `arrivals_provenance.csv`

**Checks:**
- The input was truncated at 2020-12-27, and the largest target Sunday in any dataset is ≤ 2020-12-27.
- The test period was not scored and the holdout was not accessed.
- Input hashes were unchanged and match the Phase 7 record.
- Runtime 21 s.

**Population:**
- Series with usable arrivals up to the cutoff: 3,598 / 3,669 / 4,984 (Onion / Potato / Wheat).
- Series arrivals-eligible by 2018-12-30: 1,182 / 1,215 / 1,307. By 2020-12-27: 1,330 / 1,390 / 1,433.
- Origin-eligible validation examples: about 52k–57k per crop × horizon. At h = 1: 2019 / 2020 = 28,616 / 26,539 (Onion), 29,892 / 25,750 (Potato), 31,862 / 25,309 (Wheat).

**Log MAE** (primary metric), 2019 / 2020:

| Crop | h | Persistence | Calendar-adjusted persistence (skill) | Seasonal naive (skill) |
|---|---|---|---|---|
| Onion | 1 | 0.203 / 0.209 | identical (0.000 / 0.000) | 0.417 / 0.487 (−1.11 / −1.36) |
| Onion | 2 | 0.237 / 0.247 | identical | 0.415 / 0.486 (−0.80 / −0.99) |
| Onion | 4 | 0.282 / 0.309 | 0.282 / 0.310 (−0.000 / −0.002) | 0.412 / 0.483 (−0.50 / −0.57) |
| Potato | 1 | 0.152 / 0.178 | identical | 0.386 / 0.514 (−1.58 / −1.91) |
| Potato | 2 | 0.178 / 0.217 | 0.178 / 0.217 (−0.001 / −0.000) | 0.386 / 0.514 (−1.19 / −1.37) |
| Potato | 4 | 0.216 / 0.270 | 0.218 / 0.269 (−0.007 / +0.003) | 0.385 / 0.515 (−0.79 / −0.90) |
| Wheat | 1 | 0.394 / 0.392 | 0.391 / 0.390 (+0.006 / +0.004) | 0.726 / 0.797 (−0.88 / −1.06) |
| Wheat | 2 | 0.485 / 0.481 | 0.477 / 0.477 (+0.016 / +0.009) | 0.724 / 0.796 (−0.51 / −0.66) |
| Wheat | 4 | 0.626 / 0.615 | 0.596 / 0.605 (+0.048 / +0.017) | 0.723 / 0.793 (−0.17 / −0.29) |

**Other metrics, persistence, 2019–2020 combined** (MAE / median absolute error in t/day, WAPE):

| Crop | h = 1 | h = 4 |
|---|---|---|
| Onion | 26.8 / 0.60, 31.0% | 40.8 / 1.00, 47.3% |
| Potato | 11.3 / 0.85, 21.1% | 17.9 / 1.05, 33.3% |
| Wheat | 50.8 / 4.95, 43.2% | 84.8 / 7.65, 81.2% |

The large gap between MAE and median absolute error shows how far a few large markets and extreme values dominate the tonnes-based metrics.

**Segments** (persistence log MAE, combined, h = 1):

| Crop | Reporting days in origin week: 1–2 / 3–5 / 6–7 | Volume: < 10 / 10–100 / ≥ 100 t/day |
|---|---|---|
| Onion | 0.294 / 0.221 / 0.162 | 0.151 / 0.255 / 0.380 |
| Potato | 0.226 / 0.169 / 0.146 | 0.131 / 0.193 / 0.222 |
| Wheat | 0.492 / 0.394 / 0.342 | 0.380 / 0.385 / 0.436 |

Sparse reporting and high-volume markets are the hardest.

**Findings:**
1. **Persistence is the benchmark for arrivals too.** Seasonal naive is far worse in every cell. Its coverage is 86–91%, and arrival levels shift from year to year.
2. **Calendar-adjusted persistence equals persistence for Onion and Potato.** The training median monthly log change is 0: a typical series' weekly median is unchanged from one week to the next.
3. **Wheat gains a little.** The calendar adjustment helps in both years, growing with horizon (+4.8% / +1.7% at h = 4). This matches the April procurement surge, and it is the only signal any baseline found. No uncertainty interval has been computed.
4. **Arrivals are noisier than prices.** Wheat log MAE of 0.39–0.62 means typical errors of about 50–85% in level. Tonne-based totals carry large errors, and the unflagged magnitude errors in §1 inflate MAE and WAPE.

**Not done in this phase:**
- no learned models;
- no bootstrap intervals;
- no selection decision (the output contract keeps provisional persistence);
- test and holdout untouched.

**Proposed next step for review:** decide whether to (a) accept persistence for arrivals, with Wheat calendar adjustment as a candidate needing interval evidence, and (b) open a Phase 5 follow-up decision on the unflagged arrivals magnitudes before any learned arrivals model. The proposed decision entry is **D-43 [PROPOSED]** in `Decision_Log.md`.

## 10. Baseline uncertainty: calendar-adjusted persistence vs persistence (validation only)

**Method:** `arrivals.bootstrap_log_mae()`, output `arrivals_bootstrap.csv`.
- A paired cluster bootstrap on identical validation rows, using the primary metric (log MAE).
- **Whole series** are resampled, so a series' repeated weekly rows stay together. Market clustering is the sensitivity check.
- Same settings as Phase 8 §K: 10,000 replicates, seed 20261022, percentile 95% intervals, 2019 and 2020 resampled separately.
- Predictions were regenerated in memory. The regenerated baseline files were byte-identical to the saved ones.
- **Positive = calendar adjustment better.**

**Wheat** (series clusters; market clusters give the same verdicts):

| h | 2019: log-MAE improvement [95% CI], relative % (series, rows) | 2020 |
|---|---|---|
| 1 | +0.0022 [+0.0016, +0.0028], +0.56% (862 series, 31,862 rows) | +0.0017 [+0.0011, +0.0023], +0.43% (862, 25,309) |
| 2 | +0.0079 [+0.0062, +0.0095], +1.62% (854, 31,442) | +0.0045 [+0.0028, +0.0061], +0.93% (851, 24,448) |
| 4 | +0.0302 [+0.0254, +0.0347], +4.82% (838, 30,901) | +0.0105 [+0.0061, +0.0151], +1.71% (836, 23,662) |

**Wheat by origin quarter** (h = 4, relative %, `arrivals_wheat_quarterly_stability.csv`):

| 2018Q4 | 2019Q1 | 2019Q2 | 2019Q3 | 2019Q4 | 2020Q1 | 2020Q2 | 2020Q3 | 2020Q4 |
|---|---|---|---|---|---|---|---|---|
| +2.5 | +6.4 | +7.5 | −0.1 | +2.1 | −1.0 | +4.4 | +0.9 | +0.7 |

The gain comes from forecasting the run-up to and start of the procurement season (January–June origins). It was negative in 2020Q1, the lockdown run-up.

**Onion and Potato:** changes are at most ±0.7%. They are sometimes significantly worse, for example Potato h = 4 in 2019 at −0.71% [−0.91, −0.52], and better only once (Potato h = 4 in 2020, +0.27%). There is no useful signal.

**What this establishes:**
- **Within each validation year**, the Wheat improvement is distinguishable from zero across series in both years, at every horizon.
- **It is small:** only h = 4 in 2019 exceeds the 2% practical minimum used in Phase 8 §L.2; h = 4 in 2020 is +1.7%.
- **It is not established across years or market regimes.** Series-level resampling does **not** capture nationwide shocks: procurement policy, MSP announcements and the 2020 lockdown hit all Wheat series together, so the intervals overstate certainty about future years. The quarterly pattern shows the gain depends on the seasonal context. It remains **exploratory** (D-43).

## 11. Arrivals data-quality audit and proposed flagging policy AQ-1

`Code/modelling/arrivals_quality.py` is read-only, with outputs `arrivals_quality_*.csv`. It reads rows dated ≤ 2020-12-27 only. Phase 5 outputs and behaviour are unchanged, and nothing is deleted or overwritten.

### 11.1 Root cause in Phase 5 (R12 / D-30; `Code/cleaning/pipeline.py:trailing_market_arrivals`)

The reference is the **maximum** of the same **market's** arrivals (all varieties, all rows) over the previous 365 days. A value is flagged only at ≥ 10× that maximum (`review`) or ≥ 100× (`entry_error_suspected`), and only with at least 10 earlier observations. Four weaknesses follow:
1. **Self-masking.** A single earlier error becomes the maximum for a year, so later errors of similar size pass.
2. **Lenient threshold.** Anything up to 10× the year's peak passes as `none`.
3. **No check without history.** Rows with fewer than 10 earlier observations (`insufficient_history`: 30,409 / 29,208 / 43,707 rows) are never checked. The Faridkot 8,389,090 t record is the series' first and is unchecked.
4. **No low-side check.** Implausibly *small* values are never flagged.

### 11.2 The proposed screen AQ-1

**Reference:** robust and per series. `prev_ref` is the median of the series' previous 13 reported weekly medians (at least 4); `next_ref` is the median of the next 4 (at least 2). The row's own week is excluded from both.

**Thresholds:** 10 and 100, the unit-factor reasoning of D-29/D-30. They are **not** a physical capacity bound; no evidence supports a universal maximum.

**Classes:**

| Class | Rule |
|---|---|
| `likely_unit_error` | ≥ 100× the earlier level and not sustained afterwards |
| `likely_unit_error_low` | ≤ 1/100 of the earlier level and not sustained afterwards |
| `likely_unit_error_forward_only` | no history, but ≥ 100× or ≤ 1/100 of the following weeks |
| `isolated_spike` | 10–100×, reverting; review |
| `sustained_shift` | ≥ 10× and it persists; possibly genuine |
| `unscreenable` | too little history and no forward signal |
| `ok` | otherwise |

**Context columns (descriptive):** `unit_factor_signature` (a ratio within 0.15 log10 of a power of ten) and `tiny_value` (≤ 0.1 t).

### 11.3 Extent (usable rows dated ≤ 2020-12-27)

| Class | Onion | Potato | Wheat |
|---|---|---|---|
| Usable rows | 2,041,623 | 2,175,348 | 2,119,360 |
| `likely_unit_error` | 435 | 447 | 1,276 |
| `likely_unit_error_low` | 1,267 | 550 | 3,585 |
| `likely_unit_error_forward_only` | 147 | 123 | 635 |
| **All likely errors** | **1,849 (0.09%)** | **1,120 (0.05%)** | **5,496 (0.26%)** |
| Of these, Phase 5 level `none` / `review` / `insufficient_history` | 1,644 / 79 / 126 | 904 / 80 / 136 | 4,857 / 97 / 542 |
| `isolated_spike` | 3,998 | 4,145 | 13,845 |
| `sustained_shift` | 17,414 | 14,636 | 93,849 |
| `unscreenable` | 35,000 | 39,218 | 45,363 |

**Patterns:**
- **Unit-factor signature:** 31–48% of high- and low-side likely errors carry one (for example ×1000 or ×1/1000). Forward-only rows have no earlier ratio, so they cannot carry one.
- **Rate by reporting frequency:** the likely-error rate is highest when a series reports only 1–2 days that week. Per 10k rows, for 1–2 / 3–5 / 6–7 reporting days: Onion 18.1 / 9.8 / 6.8; Potato 15.2 / 5.8 / 3.4; Wheat 51.1 / 18.5 / 28.0.
- **A 2019–2020 reporting artefact:** Wheat likely errors rise from 157–286 a year (2014–2018) to 1,321 (2019) and 943 (2020); Onion from 50–124 to 305 and 176. These are almost all **low-side placeholder-like values**. In 2019–2020 Wheat, 0.01 t appears 809 times and 0.1 t 508 times, against a typical level of about 96 t/day, and Madhya Pradesh accounts for 1,977 of 2,113 rows. The pattern resembles the zero-price placeholders of D-27, but the source cannot confirm it.
- **Genuine extremes are likely among the flags:**
  - Wheat `sustained_shift` (93,849 rows) is concentrated in March–May, the procurement surge against an off-season reference. It is **not** an error class.
  - Wheat high-side `likely_unit_error` rows also peak in April–May (536 + 365 of 1,276); all three likely-error classes together give 1,141 + 878 of 5,496. Some are probably genuine short procurement bursts at small markets.
- **States:** high-side likely errors are concentrated in Haryana, Madhya Pradesh and Punjab (Wheat); Madhya Pradesh, Punjab and Uttar Pradesh (Onion); Punjab, Uttar Pradesh and Bihar (Potato).
- **Effect on Phase 9 validation:** examples whose origin or target week contains a likely error are 0.53% (Onion), 0.24% (Potato) and 2.6–2.7% (Wheat). Weekly medians and log metrics limit, but do not remove, their effect.

### 11.4 Proposed policy (for a separate decision; NOT applied)

1. **Keep Phase 5 unchanged.** Add AQ-1 as an **additional, versioned flag column** in a new derived table, never by editing Phase 4–7 outputs.
2. **Exclude from usable arrivals targets and history:** `likely_unit_error`, `likely_unit_error_low` and `likely_unit_error_forward_only`.
3. **Keep, with a review flag:** `isolated_spike`. Keep `sustained_shift`.
4. **For Wheat, review rather than exclude** high-side likely errors in March–May unless they carry a unit-factor signature, to protect genuine procurement bursts.
5. **Treat `tiny_value` placeholders** (≤ 0.1 t among a normal level) as their own sub-class for a source check with the data provider. Until then, handle them by rule 2.
6. **Leakage:** `next_ref` looks up to 4 weeks ahead. A modelling pipeline may use a row's AQ-1 class only once those 4 weeks are before the origin. Otherwise use the backward-only part (`r_prev`) or leave the row unflagged.
7. **Report every Phase 9 result with and without AQ-1 exclusions** before any learned arrivals model.

**Trade-offs:**
- **Removed:** about 0.05–0.26% of usable rows. That is a small loss of data, but it removes the values that dominate tonne-based errors.
- **False positives:** these are likely in seasonal markets (procurement bursts, harvest-time spikes), which is why rules 3 and 4 exist.
- **False negatives:** these remain for errors that persist for more than 4 weeks (a series reporting in the wrong unit for months shows as `sustained_shift`) and for unscreenable rows without a forward signal.
- **The thresholds are conventions**, set by unit factors, not by measured capacity.

**Status update (§12):** AQ-1 is implemented as the separate derived table **AQ-1 v1**. Using it in a primary modelling population still needs approval.

**Tests:** `Code/tests/test_phase09_arrivals_quality.py` covers known spike, dip, start-of-series, sustained and placeholder cases. It also checks that the reference is not inflated by an earlier error (unlike R12), that the input is never modified, and that the cutoff is respected.

## 12. Accepted protocol (D-43) and AQ-1 v1 as a derived, leakage-safe policy (2026-10-22)

### 12.1 Protocol

**D-43 is accepted** by the project owner, without change (`Decision_Log.md`; the original proposal text is kept). It fixes:
- the weekly-median-per-reported-day target;
- Monday–Sunday weeks with a Sunday origin, and h = 1, 2 and 4;
- training on targets up to 2018, with 2019 and 2020 validated separately;
- eligibility of ≥ 365 Phase 5-usable arrival dates (at the origin for evaluation, at the refit date for training);
- missing days count as not reported, never as zero; a target week with no usable record yields no example;
- persistence as the primary baseline;
- reserved test (2021–2022) and holdout (2023+) periods.

**Why:** the target is robust to the unflagged magnitude errors and does not mix volume with reporting frequency. The design mirrors the Phase 8 price protocol, so the two outputs join one-to-one.

### 12.2 AQ-1 v1, as implemented

`Code/modelling/arrivals_quality.py:screen` and `Code/modelling/arrivals_aq1.py`.

**Definitions** (unchanged from §11.2): references are the median of the series' previous 13 reported weekly medians (at least 4) and of the next 4 (at least 2). Ratios are compared with thresholds of 10× and 100×, which come from unit factors and are not a physical bound. The classes are as in §11.2.

**Derived table:**
- Files: `Processed_Data/modelling/phase09/aq1/aq1_flags_v1_<crop>.parquet`. These are local and git-ignored.
- One row per usable arrivals record dated ≤ 2020-12-27, with:
  - Phase 5 `arrivals_extreme_level` copied unchanged
  - references, ratios and `aq1_class`
  - `aq1_available_from`
  - `unit_factor_signature`, `tiny_value`, `high_side`, `march_to_may`
  - `provider_query_pending` (§14)
  - `aq1_version`
- **Provenance** (tracked): `aq1/aq1_flags_v1_manifest.csv` records rows, class counts, the content hash and the file SHA-256. `arrivals_aq1_provenance.csv` records the input SHA-256 values (equal to the Phase 7 record), thresholds, cutoff and variants.
- Raw arrivals and Phase 5 outputs are never modified; tests check this.

**Leakage safety:**
- **Availability date:** each row carries `aq1_available_from`, the Sunday of the 4th following reported week. If fewer than 4 follow before the cutoff, it is the cutoff, because the class then depends on data being absent up to the cutoff. A test checks that a row's class does not change when data after that date changes.
- **Targets** (ground truth) are cleaned retrospectively: excluded rows leave the target week's median, and a fully excluded target week yields no example.
- **Calendar-factor training at refit r** uses a cleaned training target only if every excluded row in that week has `aq1_available_from` ≤ r; otherwise it uses the original value. Tested.
- **Origin inputs** (the origin-week median, i.e. the persistence forecast) and **eligibility** stay on the Phase 5 view.
  - An origin-week row's class needs at least 2 later reported weeks, so it is never available at the origin.
  - Start-of-series (`forward_only`) flags rely entirely on later weeks; they are subject to the same availability rule and are never knowable at their own origin (tested).
- **Consequence:** AQ-1 cannot change any forecast or forecast input in this design. It changes only the measured truth and the training data.

**False-positive risks** (documented, not resolved):
- Genuine short procurement bursts in small Wheat markets (March–May), and harvest-time spikes in Onion and Potato.
- Low-level series where a small value is normal: 685 of the 2,162 Madhya Pradesh tiny Wheat values are class `ok` for this reason.

**False negatives:** errors that persist for more than 4 reported weeks (they appear as `sustained_shift`), and rows that are unscreenable and have no forward signal.

### 12.3 Class counts (rows ≤ 2020-12-27)

| | Onion | Potato | Wheat |
|---|---|---|---|
| Rows | 2,041,623 | 2,175,348 | 2,119,360 |
| `likely_unit_error` / `_low` / `_forward_only` | 435 / 1,267 / 147 | 447 / 550 / 123 | 1,276 / 3,585 / 635 |
| `isolated_spike` | 3,998 | 4,145 | 13,845 |
| `sustained_shift` | 17,414 | 14,636 | 93,849 |
| `unscreenable` | 35,000 | 39,218 | 45,363 |
| `provider_query_pending` | 1,185 | 737 | 2,162 |

## 13. Baselines: original vs AQ-1 populations (validation only)

**Outputs:** `arrivals_aq1_baseline_metrics.csv`, `arrivals_aq1_population_changes.csv`, `arrivals_aq1_bootstrap.csv` and `arrivals_aq1_practical_check.csv`. The original Phase 9 outputs (17 CSVs) were checked byte-identical afterwards.

**Variants:**

| Variant | Exclusions |
|---|---|
| `original` | none; identical to §9, by test |
| `aq1_likely` | all three likely-error classes (the policy core) |
| `aq1_likely_and_spikes` | also isolated spikes (sensitivity) |
| `aq1_wheat_marmay_review_except_unitsig` | Wheat only: March–May high-side likely errors kept unless they carry a unit-factor signature |
| `aq1_wheat_marmay_review_all` | Wheat only: all March–May high-side likely errors kept |

Spikes and lasting shifts are review-only (kept) in every variant except `aq1_likely_and_spikes`.

**Coverage** (`aq1_likely`, h = 1; 2019 / 2020):

| Crop | Examples dropped (target week fully excluded) | Target value changed | Series |
|---|---|---|---|
| Onion | 6 / 10 of 28,616 / 26,539 | 99 / 67 | 796 / 789 → 796 / 788 |
| Potato | 0 / 4 | 33 / 21 | unchanged except 1 |
| Wheat | 15 / 39 of 31,862 / 25,309 | 606 / 425 | unchanged |

Across all variants the largest drop is 136 Wheat examples (`aq1_likely_and_spikes`, combined).

**Persistence log MAE**, original → `aq1_likely` (2019 / 2020):

| Crop | h = 1 | h = 4 |
|---|---|---|
| Onion | 0.2033 → 0.2020 / 0.2089 → 0.2079 | 0.2817 → 0.2807 / 0.3095 → 0.3077 |
| Potato | 0.1515 → 0.1514 / 0.1780 → 0.1782 | 0.2160 → 0.2157 / 0.2700 → 0.2694 |
| Wheat | 0.3936 → 0.3880 / 0.3920 → 0.3868 | 0.6260 → 0.6213 / 0.6153 → 0.6076 |

**What AQ-1 changes:**
- Error falls by about 0.6% (Onion) and 1.2–1.5% (Wheat), with no meaningful change for Potato.
- On common rows, essentially all of the change comes from cleaner targets, not from dropped examples. For Wheat h = 1, 2019: 0.3925 on the original targets vs 0.3880 on cleaned targets.
- The Wheat March–May variants differ from `aq1_likely` by at most 0.0005.
- Treating spikes as errors moves Wheat 2020 at h = 1 and h = 2 slightly *up* (0.3884 and 0.4753, against 0.3868 and 0.4749 for `aq1_likely`). That supports keeping spikes review-only.

**Calendar-adjusted persistence vs persistence** (identical rows within each variant; paired series bootstrap, 10,000 replicates):

| Wheat h | `original` 2019 / 2020 | `aq1_likely` 2019 / 2020 |
|---|---|---|
| 1 | +0.56% [+0.41, +0.71] / +0.43% [+0.29, +0.58] | +0.56% [+0.40, +0.71] / +0.43% [+0.28, +0.58] |
| 2 | +1.62% [+1.29, +1.93] / +0.93% [+0.60, +1.24] | +1.63% [+1.30, +1.94] / +0.93% [+0.60, +1.25] |
| 4 | +4.82% [+4.14, +5.46] / +1.71% [+1.01, +2.41] | +4.83% [+4.14, +5.47] / +1.73% [+1.01, +2.42] |

- The other Wheat variants are within 0.05 percentage points of these.
- Onion and Potato stay within ±0.7%, as in §10.
- **Practical check** (`arrivals_aq1_practical_check.csv`): no crop × horizon meets *both* the interval criterion (above 0 in both years, both clusterings) and the pre-specified **2% practical gain in both years**, in any variant. Wheat meets the interval criterion at every horizon but reaches ≥ 2% only at h = 4 in 2019.
- **Statistical vs practical significance:** the improvement is detectable within each year, but it is too small to count as practically important under the pre-specified rule.
- Cluster resampling does not capture nationwide shocks (procurement policy, MSP, the 2020 lockdown), so the intervals overstate certainty about other years.

**Wheat calendar adjustment status:** **exploratory, unchanged.** It does not meet the practical criterion, with or without AQ-1.

## 14. Madhya Pradesh placeholder-like values (investigation; nothing asserted, nothing removed)

Outputs: `arrivals_mp_placeholder_*.csv`.

**Wheat, Madhya Pradesh, 2019–2020, values ≤ 0.1 t:**
- **Volume:** 2,162 rows across 96 markets, 109 series and 37 districts, about 2.5% of MP Wheat rows in those years.
- **Values:** 0.01 t (971), 0.1 t (932), 0.05 t (193), 0.02 t (43), 0.03 t and 0.04 t (7 each).
- **Prices:** every one of these rows carries a usable modal price, for example Rs 1,700–2,100/q.
- **Days of the week:** concentrated on **Sundays (761) and Saturdays (464)**, against 137–212 on weekdays.
- **Onset:** MP had 11–188 such values a year in 2002–2018, then 1,073 in 2019 and 1,089 in 2020. Other states ranged from 16 to 1,364 a year (2002–2020), with no jump in 2019.
- **Most affected series:** Nalkehda, Shajapur, Other (192 of 618 rows); Ratlam, Lok-1 (186 of 530); Berachha, Shajapur (131 of 295, a low-level series with median 1.7 t); Badod (120); Jaora (119).
- **AQ-1 classes:** 1,475 `likely_unit_error_low`, 685 `ok` (in low-level series), 1 `forward_only`, 1 `unscreenable`.
- **The same marker applies to Onion (1,185) and Potato (737) in MP, 2019–2020.**

**Representative rows** (public mandi names; t = tonnes):

| Date | Market | Arrivals | Previous level | Following level | Modal price |
|---|---|---|---|---|---|
| 2019-03-21 | A lot (Ratlam) | 0.05 t | 71 t | 5,288 t | Rs 1,720 |
| 2019-07-14 | Ambaha (Morena) | 0.10 t | 20.6 t | 57.4 t | Rs 1,700 |
| 2019-09-08 | Aron (Guna) | 0.01 t | 91.5 t | 39.9 t | Rs 1,840 |
| 2019-03-22 | Badnagar (Ujjain) | 0.10 t | 35.3 t | 719 t | Rs 1,874 |

**Status:**
- **Kept and marked** (`provider_query_pending`) in the AQ-1 v1 table. The rows already in a likely-error class are excluded only in the AQ-1 variants; the marker itself excludes nothing.
- **Not asserted to be wrong.** The weekend concentration fits placeholders for non-trading days or minimum-lot reporting, but only the source can confirm this.

**Draft query for the data provider (not sent):**

> Subject: Clarification on very small daily arrivals values — Madhya Pradesh mandis, 2019–2020
>
> We use the commodity-wise mandi dataset (wheat, onion, potato). For Madhya Pradesh in 2019–2020 we see many daily records with arrivals of exactly 0.01, 0.05 or 0.1 tonnes (for example Wheat at Nalkehda, Ratlam, Berachha, Badod and Jaora). These records carry normal modal prices, and the same markets usually report tens to hundreds of tonnes. They occur mainly on Saturdays and Sundays, and they rise from under 200 a year before 2019 to over 1,000 a year in 2019 and 2020.
>
> Could you tell us whether these values are (a) actual arrivals, (b) a unit-conversion issue (for example quintals or kilograms recorded as tonnes), (c) a placeholder or minimum value entered on days without trading or reporting, or (d) another reporting artefact, such as a change in the data-entry system in 2019? If there is documentation of the units or entry rules for the `Arrivals (Tonnes)` field over this period, we would be grateful for a reference.

## 15. Remaining risks and approvals needed before learned arrivals modelling

1. **AQ-1 v1 as the primary population:** approve, amend or reject. The evidence shows a small gain and no effect on baseline rankings.
2. **Spikes:** confirm they stay review-only. `aq1_likely_and_spikes` slightly hurts Wheat 2020 at h = 1 and h = 2.
3. **Wheat March–May exception:** it makes no measurable difference. Keep it for genuine bursts, or simplify by dropping it.
4. **Madhya Pradesh query:** send the draft (only by a person), and decide how `provider_query_pending` rows are handled until an answer arrives.
5. **Wheat calendar adjustment:** confirm it stays exploratory. It fails the 2% practical criterion.
6. **Before any learned arrivals model:** pre-specify candidate models, their features (Phase 6 `arrivals_*` history, calendar, price context) and a selection rule like Phase 8 §L.2, before fitting. **Done as a proposal:** `Phase_09_Model_Protocol.md` (D-44 PROPOSED). The notebook `Notebooks/Phase_09_Arrivals_Model_Experiments.ipynb` runs everything except fitting until it is approved.
7. **Remaining risks:**
   - unflagged errors that persist longer than 4 weeks;
   - closures that cannot be told apart from non-reporting;
   - two validation years;
   - nationwide shocks not captured by the intervals.

## 16. D-45 selection, freeze and the one-time 2021–2022 arrivals test (2026-10-23)

**Selection.** D-44 validation produced the D-45 proposal. The project owner **accepted D-45 as written on 2026-10-23**: conservative HGB for Onion, Potato and Wheat × h = 1, 2 and 4.

**Freeze.** The manifest is `Processed_Data/modelling/phase09_models/test_2021_2022/arrivals_freeze_manifest.csv` (`phase9-arrivals-test-v1`, 46 entries). It records SHA-256 values for:
- 10 code files: `arrivals*.py`, `dataset.py`, `baselines.py`, `uncertainty.py`, and the Phase 6 and Phase 4 pipelines;
- the protocol document and the feature registry;
- the AQ-1 manifest and flag files;
- the experiment config and every validation output (selection table, metrics, bootstraps, predictions);
- the D-44 and D-45 decision sections, as text with normalised line endings;
- the three feature inputs, which equal the Phase 7 record;
- the nine selected settings, the feature list, the populations and the refit rule.

It was verified by a separate process before the test, and again after it. The manifest's own file hash (`d9d71db7…`) is recorded in the run log, not inside the manifest, so there is no circularity.

**Validation behaviour unchanged by the test-period parameters.** Re-fitting Potato h = 1 reproduced all 55,638 saved validation predictions exactly.

**Run-once guard** (`arrivals_final.preflight` / `run_test`). The test is allowed only if:
- D-45 is ACCEPTED and the D-44 gate holds;
- the freeze verifies;
- the window equals the D-40 test period and stays out of the holdout;
- no attempt is recorded in the persistent `run_log.csv` and no results exist.

A failure is logged as `failed` and blocks retries until reviewed. This is tested on synthetic data, including an unaccepted decision, a bad hash, a wrong window, a repeat run and a failed run.

**The run:**
- **Log:** `started` 2026-10-22T20:39:23Z, then `completed` at 20:48:08Z (2026-10-23 IST); 524 s; 1,648,535 prediction rows across the three populations. A second attempt is refused.
- **Access audit** (`test_access_audit.csv`):
  - rows were read through a parquet filter `reported_date ≤ 2022-12-25`;
  - **0 rows after 2022-12-25 were loaded**;
  - scored target weeks ran from 2021-01-03 to 2022-12-25;
  - **the 2023+ holdout was not accessed.**
- **Protocol:** quarterly expanding refits as in validation. AQ-1 v1 rules were applied unchanged to rows ≤ 2022-12-25 to clean test targets, and training targets were cleaned only once a flag was knowable.

**Results** (primary population AQ-1; % lower log MAE than persistence on identical rows; 95% series-cluster CI). Market clusters give the same verdicts.

| Crop | h | 2021 | 2022 |
|---|---|---|---|
| Onion | 1 | +3.38 [+2.23, +4.52] | +6.34 [+5.23, +7.39] |
| Onion | 2 | +3.85 [+2.77, +4.91] | +5.81 [+4.75, +6.87] |
| Onion | 4 | +4.11 [+2.94, +5.23] | +4.57 [+3.32, +5.75] |
| Potato | 1 | +3.19 [+1.96, +4.40] | +4.12 [+2.99, +5.24] |
| Potato | 2 | +2.96 [+1.79, +4.07] | +4.23 [+3.03, +5.40] |
| Potato | 4 | +4.49 [+3.27, +5.67] | +2.34 [+0.99, +3.63] |
| Wheat | 1 | +5.83 [+4.79, +6.87] | +9.00 [+7.97, +10.00] |
| Wheat | 2 | +6.10 [+4.85, +7.31] | +10.84 [+9.78, +11.89] |
| Wheat | 4 | +8.10 [+6.57, +9.56] | +13.49 [+12.18, +14.73] |

**What the results show:**
- All 18 cell-years have intervals above zero, and all reach the 2% practical minimum. The smallest is Potato h = 4 in 2022, at +2.34%.
- **Original population and all-flagged-MP exclusion (U3):** the same verdicts in all 18 cell-years, and the populations differ by at most 0.62 percentage points.
- **Tonnes per day:** in a few cells the absolute error barely changes. For example, Onion h = 2 in 2021 has MAE 32.38 against 32.38 t/day, even though log MAE improves.

**How to read this:**
- Unlike the Phase 8 price model, the arrivals gains held on two unseen years.
- The intervals are within-year and do not capture nationwide shocks.
- The `provider_query_pending` marker covers 2019–2020 only, so it affects training targets, not test targets.
- The 2023+ holdout stays reserved.
- **The selection is unchanged by these results** (D-45).
