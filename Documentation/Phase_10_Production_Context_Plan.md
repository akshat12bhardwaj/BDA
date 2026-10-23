# Phase 10 Plan — District Production Context (proposal)

**Status (revision 3, 2026-10-23): D-46, D-47 and D-48 ACCEPTED by the project owner on 2026-10-23** (accepted forms in `Decision_Log.md`; R13 Option 1). **D-49 remains PROPOSED — NOT ACCEPTED**, so phase names and the roadmap are unchanged. **v1 implemented on 2026-10-23** (§17). Nothing here changes D-01 – D-45 or any Phase 4–9 file.

*Original status (revision 1–2):* [PROPOSAL for review, 2026-10-23; PROPOSED — NOT APPROVED; nothing implemented]. No Phase 10 code, outputs or model exist. Every decision below is a recommendation awaiting the project owner.

**Revision 2 (2026-10-23): decision resolution.** Follows the project owner's stated direction:
- §6 resolves every PQ-1 rule as *specified* (evidence-backed, no unsupported number), *review-only*, or *blocked*. No numerical threshold is active.
- The Wheat Rabi exception is withdrawn.
- §14 gives exact proposed decision entries D-46 … D-49 (**not** added to `Decision_Log.md`).
- §15 is a **draft, unsent** DES enquiry.
- §16 reviews the audit scripts.

Revision 2 was **PROPOSED — NOT APPROVED**.

**Revision 3 (2026-10-23): owner acceptance.**
- D-46, D-47 and D-48 were accepted in the forms recorded in `Decision_Log.md`. §14 keeps the proposal text as history.
- D-48 clarifications: R8a is computed per crop and state; R10 compares against the most recent earlier source year with a row for the same crop, state and district.
- R13 Option 1: all annual rows of (West Bengal, Potato, 1997-98) and (Gujarat, Potato, 1997-98).
- D-47 adds the publication-timing caveat: the lag-2 rule is not shown to be conservative for source years ≥ 2019-20.
- D-49 is not accepted.

**State this plan was written against:** branch `main`, HEAD `b726575` (2 commits ahead of `origin/main`, unpushed); the only uncommitted change is the pending deletion of `Documentation/EDA_Findings.pdf`.

**Audit scripts** (read-only; kept outside the repository, re-runnable from the project root with `C:\Python313\python.exe -B`): an APY audit, and a hit-count of candidate quality rules. Every number in §2 comes from them or from files named beside it.

---

## 1. Executive recommendation

1. **Build Option A**, a descriptive, leakage-safe district production context (`phase10-production-context-v1`). **Do not build a production-forecasting model (Option B)** in this phase (§4).
2. **Information rule:** APY year *Y* may be used from 1 July of year *Y* + 2, i.e. at decision agricultural year *t* only `source_apy_year = t − 2`. This is the existing D-36 lag. It remains a **policy assumption**: no district-level release history could be verified (§7).
3. **Quality:** a versioned rule set **PQ-1 v1** that only **flags and annotates**. It never repairs, clips, imputes or deletes. Of its 13 rule codes (R8 split into R8a / R8b; revision 2, §6):
   - 8 are specified, with exact conditions and no unsupported number;
   - 2 are review-only markers;
   - 4 are blocked pending evidence (R5, R6, R7, R8b), and the 1% cut-off of R4 is not activated.
4. **Reserved years:** design and threshold work uses APY years **≤ 2018-19 only**. APY 2019-20 … 2021-22 are built mechanically, with frozen rules, for test and holdout-era decisions. APY **2022-23 is excluded from v1**: no decision inside the data range needs it (§8).
5. **Numbering:** keep the roadmap numbering, and rename Phase 10 from "Supply Prediction" to "District Production Context" (§9).
6. **Two significant source anomalies need a data-provider query before use:**
   - **West Bengal Potato 1997-98:** the district areas sum to 2.2× the state's total geographic area.
   - **Gujarat Potato 1997-98:** yields of 0.004–0.08 t/ha.

## 2. Current-state audit and reproducible APY findings

### 2.1 Sources inspected (read-only)

| Item | Location | Notes |
|---|---|---|
| Raw APY | `Dataset/crop-wise-area-production-yield.csv` | 16 columns; for Onion/Potato/Wheat 41,835 rows (14,822 / 14,108 / 12,905); `id` unique |
| Codebook | `Dataset/Crop_Wise_Area_Production_Yield_codebook.xlsx` | units, extraction page, retrieval and update dates (§3) |
| Season table | `Processed_Data/integration/apy_season.csv` (Phase 4) | 41,835 rows = the raw rows for the three crops |
| Annual table | `Processed_Data/integration/apy_annual.csv` (Phase 4, D-20) | 33,011 district-years, 1997-98 … 2022-23 |
| Link table | `Processed_Data/integration/mandi_apy_district_year.csv` (D-19) | `link_status`: mandi_and_apy / mandi_only / apy_only |
| Crosswalk | `Processed_Data/integration/district_crosswalk.csv` (D-18) | 1,474 rows; mandi district → APY district via a reviewed alias table; no fuzzy matching |
| Lag-2 features | `Processed_Data/features/features_<crop>.parquet`, `apy_*_lag2` (D-36) | missing on 51% / 34% / 4% of Onion / Potato / Wheat rows (documented in D-36 / Roadmap) |

**Inspection boundary used here:** values were inspected for `apy_year ≤ 2018-19` only (§8). For 2019-20 onwards, only row counts and unit labels were read.

**Disclosure:** the previous session's summary profile included aggregate statistics over years ≤ 2020-21 (quantiles, missing shares and zero counts). No threshold in this plan is derived from those years.

### 2.2 Findings (design window 1997-98 … 2018-19; 34,010 season rows)

| # | Finding | Status | Method / source rows |
|---|---|---|---|
| F1 | **Units are uniform:** every row is `Hectare / Tonnes / Tonnes/Hectare` (all years; labels only) | reproduced | group-by on `area_unit, production_unit, yield_unit` |
| F2 | **No duplicate or conflicting records** on (year, state, district, crop, season); `id` unique | reproduced | duplicated-key check |
| F3 | **Reported yield is internally consistent:** of 33,908 rows with area > 0, 11 differ from production ÷ area by > 1% and none by > 10% | reproduced | \|yield − production/area\| ÷ (production/area) |
| F4 | **Missing production is encoded with `yield = 0`:** 102 rows (Onion 52, Potato 24, Wheat 26), all with area > 0 and yield exactly 0 | reproduced | `production.isna()` → `yield` value counts |
| F5 | **Zero production with positive area:** 12 rows (5 / 4 / 3), area 1–34 ha, mostly Haryana / Rajasthan / Tamil Nadu 2001-02 and 2002-03 (e.g. ids 57470, 57177, 57372, 80463) | reproduced; cause unknown | `production == 0` |
| F6 | **West Bengal Potato 1997-98:** the 18 district rows sum to 19,616,403 ha and 19,732,232 t. The 1998-99 state sum is 318,199 ha (61.65× smaller). 17 of 18 rows have yield < 3 t/ha, against 17–27 t/ha for the same districts in 1998-99 … 2001-02. Examples: ids 10186 Murshidabad (4,314,164 ha), 10215 Nadia, 10154 Malda. **No other state × crop has a 1997-98 / 1998-99 area ratio above 1.43.** | reproduced; **physically impossible as hectares** (state geographic area ≈ 8.88 M ha, S9). Cause **unverified**: not asserted to be a unit error. | state sums by year; per-district rows |
| F7 | **Gujarat Potato 1997-98:** yields of 0.004–0.08 t/ha on areas up to 134,000 ha (Bharuch: 706 t on 134,000 ha; also Valsad, Surendranagar, Amreli, Surat, Rajkot …) | reproduced; cause unverified (new finding) | yield ÷ national crop-year median ≤ 0.1 |
| F8 | **Implausibly high yields:** Onion Srikakulam (Andhra Pradesh) Kharif 2017-18 at 4,070 t/ha (id 327626; 2 ha, 8,140 t) and 2018-19 at 2,611 t/ha (id 348187); Karnal 2008-09 at 2,150 t/ha (id 171180). Andhra Pradesh Onion has 11 rows above 60 t/ha in 2017-18 and 2018-19. Potato Panipat 2002-03 at 213.8 t/ha (id 72200). The season-row 99.9th percentiles are 74.8 (Onion), 44.7 (Potato) and 5.5 (Wheat) t/ha. | reproduced; plausibility needs reference yields (§6) | top-n by yield; quantiles |
| F9 | **"Single-season" annual values are mostly `Whole Year` for Onion and Potato** (79.8% / 67.7%) but `Rabi` for Wheat. Named single seasons that may be partial: Onion Rabi 1,053, Kharif 170, Summer 15, Autumn 1; Potato Rabi 1,693, Winter 480, Kharif 308, Summer 2. | reproduced | `apy_annual.seasons_reported` where `annual_method == single_season` |
| F10 | **Reporting method changes over time** within 184 of 560 Onion, 179 of 581 Potato and 19 of 603 Wheat districts (total_row ↔ single_season) | reproduced | `nunique(annual_method)` per district |
| F11 | **Ambiguous district-years:** 18 Potato rows with several seasons but no Total (Meghalaya 1997-98/1998-99 Rabi + Whole Year; Kheda, Dharmapuri, Dindigul and Erode 1998-99 Kharif + Whole Year), left missing by D-20 | reproduced | `annual_method == ambiguous_multi_season_no_total` |
| F12 | **The Total row equals the sum of seasons** in 3,034 of 3,037 groups (> 1% differences in 3) | reproduced (confirms D-20) | Total vs sum of non-Total |
| F13 | **District identity is consistent within the file:** `district_code` ↔ `district_name` is 1:1 within each state | reproduced | name/code cardinality |
| F14 | **District counts grow** from 448 (1997-98) to 644 (2018-19); 230 of 678 district names first appear after 1997-98 (Telangana 25, Chhattisgarh 21, Karnataka 18, Gujarat 14, Kerala 14 …) | reproduced | distinct names per year |
| F15 | **Current state names are applied to historical rows:** "Telangana" districts appear from 1997-98, although Telangana was formed on 2 June 2014 (S8). Telangana's district count jumps from 9 (2015-16) to 29 (2016-17). | reproduced; implies the source re-labels history by present geography. The 2016 reorganisation date is **unverified**. | per-state district counts |
| F16 | **History length per district** (years with production, of 22): median 17 Onion, 18 Potato, 22 Wheat; minimum 1 | reproduced | `nunique(apy_year)` per district |
| F17 | **The latest years are present in the file:** rows for 2021-22 and 2022-23 exist (Onion 724 / 670, Potato 660 / 608, Wheat 562 / 563); values not inspected | counts only | — |

## 3. Evidence and provenance register (accessed 2026-10-23)

**Fetch limits:** primary government pages could not be fetched from this environment (`desagri.gov.in`: TLS certificate error; `pib.gov.in` and `indiadataportal.com`: HTTP 403). Claims marked "search result" come from search-engine extracts of those pages and **must be confirmed by opening the page** before they are relied on.

| ID | Source | Supports | Strength |
|---|---|---|---|
| S1 | Local codebook, sheet `Metadata Information` | Publisher: DES, Ministry of Agriculture & Farmers Welfare. Extraction page: `https://data.desagri.gov.in/website/crops-apy-report-web`. Data last updated 14-12-2023; retrieval 26-02-2026; district granularity; yearly; units ha / t / t/ha | in-project document (verified locally) |
| S2 | `https://data.desagri.gov.in/website/crops-apy-report-web` | the official extraction page | **not fetched** (TLS error) |
| S3 | India Data Portal, *Crop Wise Area Production Yield* — `https://ckandev.indiadataportal.com/dataset/area-production-yield-apy` | Licence listed as Open Data Commons Attribution; caveat that some crop names map to identical crop codes; the same metadata layout as S1, so the local file was **probably obtained via this mirror** | search result; mirror, not the publisher |
| S4 | DES Agricultural Statistics Division — `https://desagri.gov.in/divisions-cell/agricultural-statistics-division/` | Four Advance Estimates + a Final Estimate per **July–June agricultural year** (supports A-13); national final estimates normally follow months after the year ends | search result |
| S5 | DES RTI reply, 28 June 2021 — `https://desagri.gov.in/wp-content/uploads/2021/06/RTI-reply-Gorle-Syamsundar-Rao-28-June-2021.pdf` | DES compiles district-wise APY from State Agricultural Statistics Authorities; "compilation … for the remaining years … in progress" (district data can lag national estimates) | search result |
| S6 | PIB, *Final estimates of production of major crops released for the year 2022-23* — `https://pib.gov.in/PressReleseDetailm.aspx?PRID=1968931` | national 2022-23 final estimates (field crops, incl. Wheat) released 18 Oct 2023 | search result |
| S7 | PIB, *Final Estimates of 2022-23 and First Advance Estimates of 2023-24 of Area and Production of Horticultural Crops* — `https://pib.gov.in/PressReleseDetailm.aspx?PRID=2012191`; reported 7–8 March 2024 (Business Standard via PressReader 2024-03-08; global-agriculture.com) | **national horticulture (Onion, Potato) 2022-23 finals came out ~March 2024**, after the local file's 14-12-2023 update | search result + secondary press |
| S8 | Andhra Pradesh Reorganisation Act, 2014 (No. 6 of 2014) — `https://lddashboard.legislative.gov.in/sites/default/files/A2014-6.pdf`; appointed day notified by S.O. 655(E), 4 March 2014 | Telangana formed with effect from 2 June 2014, comprising ten listed districts | primary legal text (via search) |
| S9 | West Bengal geographic area 88,752 km² — SLBC West Bengal state profile `https://slbcbengal.pnb.bank.in/StateProfile_31032020.asp`; Wikipedia *West Bengal* | the denominator for F6 (≈ 8.875 M ha) | secondary; **Census of India figure still needed** |
| S10 | Local Government Directory — `https://lgdirectory.gov.in` (Ministry of Panchayati Raj) | the official district-code registry tracking bifurcations | **not consulted**; needed for boundary rules |

**Classification of the key claims:**

| Claim | Class |
|---|---|
| Units ha / t / t/ha; DES publisher; extraction page; 14-12-2023 update | verified (S1, local) |
| The APY year is the July–June agricultural year | supported by an official description (S4, to be opened); remains A-13 |
| District areas of WB Potato 1997-98 exceed the state's land area | reproduced locally + secondary area figure (S9) |
| WB / Gujarat Potato 1997-98 are unit or entry errors | **hypothesis, unverified**; data-provider question |
| District APY for year Y is available by 1 July of Y + 2 | **policy assumption**; not verified (§7) |
| 2022-23 Onion / Potato district values in the file are final | **open question**: they predate the national horticulture finals (S7) |
| The 2016-17 Telangana district increase is a reorganisation | hypothesis; needs a state gazette or LGD |
| Crop calendars, marketable-surplus ratios, procurement windows, district boundary mappings | **no evidence gathered; not assumed** |

**Questions for the data provider (DES / SASA):**
1. Units and correctness of West Bengal and Gujarat Potato 1997-98.
2. The release history of district APY by year, and whether earlier years were revised (vintages).
3. Whether 2022-23 horticulture district values are final.
4. Whether historical rows are re-labelled to present-day states and districts.
5. The meaning of "Whole Year" for seasonal crops.

## 4. Option A versus Option B

| Criterion | A: descriptive context | B: production forecasting |
|---|---|---|
| Observations | uses every district-year as published | ≤ 22 annual points per district in the design window (median 17 / 18 / 22); a training target for 2019+ would sit in reserved years |
| Effective horizon | none: reports t − 2 as known | forecasting year t from ≤ t − 2 is a **2–3-year-ahead** forecast |
| Boundary changes | flagged; the value is kept as published | splits truncate or shrink parent series (F14, F15), creating artificial target drops |
| Reporting consistency | `annual_comparability` exposes method changes (F9, F10) | the target definition changes within 184 / 179 Onion / Potato districts |
| Quality anomalies | flagged and kept | errors in targets (F6–F8) would be learned unless thresholds are settled first |
| Publication and revision | one rule, documented | the same rule plus vintage risk on targets |
| Downstream value | enough for a slow-moving sourcing prior (§10) | a better annual number does not give marketable surplus or weekly supply, which is what Phase 12 lacks |
| Precedent | — | Phase 8: learned price models rarely beat persistence on test (D-42) |
| Cost and risk | low; mirrors AQ-1 / Phase 4 conventions | needs its own protocol, split and approval (as D-44) |

**Recommendation:** A. B may be reconsidered later under its own protocol, if a downstream consumer shows that a 2–3-year-ahead district forecast changes a decision.

## 5. Proposed data contract `phase10-production-context-v1`

**Grain:** one row per (crop, apy_state, apy_district, decision_agri_year) for which an APY district-year exists in `apy_annual.csv` at `source_apy_year = decision_agri_year − 2`.

**Scope:**
- **No row** means APY reported nothing for that district-year; it is never filled.
- `decision_agri_year` runs from 1999-2000 to 2023-24, the last agricultural year with mandi data (data end Feb 2024).
- Rows with source years 2019-20 … 2021-22 are built only under §8.

| Field | Definition | Source | Unit | Missing policy | Allowed values | Available from | Downstream use |
|---|---|---|---|---|---|---|---|
| `crop` | selected crop | apy_annual | — | never missing | Onion, Potato, Wheat | — | key |
| `apy_state`, `apy_district` | APY (DES) names, as published | apy_annual | — | never missing | APY names | — | key; join via the D-18 crosswalk |
| `apy_district_code` | APY's own district code (renamed from the proposed `district_code` so it is not mistaken for an LGD/Census code; 1:1 with the name, F13) | apy_annual `district_code` | — | null if absent in APY | integer | — | audit; future LGD link |
| `decision_agri_year` | July–June year in which the context is used (A-13) | derived | `YYYY-YYYY` | never | 1999-2000 … 2023-24 | — | key; join to mandi `apy_year` |
| `source_apy_year` | the APY year the values describe | `decision_agri_year − 2` | `YYYY-YYYY` | never | 1997-98 … 2021-22 | — | audit |
| `available_from` | the first date the values may be used: 1 July of `decision_agri_year`'s start year | the §7 policy | date | never | — | itself | leakage check |
| `information_rule` | identifier of the availability policy | constant | — | never | `apy_lag2_policy_v1` | — | audit |
| `production_tonnes` | annual production as published (Total row, or the single season row) | apy_annual | t | null if missing in APY or ambiguous (D-20) | ≥ 0 | `available_from` | context; prior for sourcing |
| `area_ha` | annual area as published | apy_annual | ha | as above | > 0 | `available_from` | context |
| `yield_t_per_ha` | the published yield; **null when production is null** (F4: the source encodes such yields as 0) | apy_annual | t/ha | null if production is null | ≥ 0 | `available_from` | context |
| `annual_method` | the D-20 method | apy_annual | — | never | total_row, single_season, ambiguous_multi_season_no_total | — | interpretation |
| `seasons_reported` | the source seasons in the district-year | apy_annual | — | never | pipe-joined season names | — | interpretation |
| `annual_comparability` | **new:** how far the value can be read as a full-year figure | derived from the two fields above | — | never | `verified_total` (Total row); `whole_year_row` (single "Whole Year" row); `single_named_season` (only Rabi / Kharif / …; may be partial); `ambiguous` | — | consumers must not compare classes as equals |
| `pq_class` | the overall PQ-1 outcome | PQ-1 | — | never | `ok`, `annotated`, `review`, `unusable` | `available_from` | filter |
| `pq_reasons` | the triggered rule codes | PQ-1 | — | empty string if none | pipe-joined codes (§6) | as above | audit |
| `pq_version`, `contract_version` | versions | constants | — | never | `pq1-v1`, `phase10-production-context-v1` | — | audit |

**Not per row:** the input SHA-256 values (raw APY, `apy_season.csv`, `apy_annual.csv`, the crosswalk) go in a manifest beside the output, as in AQ-1.

**Trailing summary — defined, but recommended to be deferred to v1.1:**
- **Definition:** `production_tonnes_median_3y` is the median of `production_tonnes` over source years t − 2, t − 3 and t − 4.
- **Rows used:** only rows with `pq_class ∈ {ok, annotated}`, the same `annual_comparability` class, and no boundary marker. At least 2 values are required; otherwise null.
- **Why defer:** without the boundary rule (PQ-1 R8, blocked) a split district's median mixes pre- and post-split areas.

## 6. Quality-rule specification PQ-1 v1 (flags only; source values preserved)

**Resolution categories (revision 2):**
- **Specified:** an exact, reproducible condition with no unsupported numerical threshold.
- **Review-only:** a conservative marker that sends a value to `review` without excluding it.
- **Blocked:** not active until the named evidence exists. A blocked rule produces no flag in v1 and is listed in the manifest as inactive.

| Code | Detects | Exact condition | Evidence | Action | False positives / negatives | Resolution |
|---|---|---|---|---|---|---|
| R1 `missing_value` | missing production or area; ambiguous multi-season | `production_tonnes` null, or `area_ha` null, or `annual_method == ambiguous_multi_season_no_total` | F4, F11, D-20 | `unusable` (the value is null; nothing to use) | none | **specified** |
| R2 `yield_zero_encodes_missing` | a published yield of 0 alongside missing production | production null and source yield == 0 | F4 (102 / 102 rows) | annotate; the contract yield is null | none observed | **specified** |
| R3 `zero_production` | production == 0 with area > 0 | exact equality | F5 (12 rows) | `review`; never excluded (crop failure or placeholder; cause unknown) | true crop failures go to review: intended | **review-only** |
| R4 `yield_inconsistent` | published yield ≠ production ÷ area | **no row-level cut-off.** The manifest reports, per crop, the count and maximum of \|yield − production/area\| ÷ (production/area) | F3 (max < 10%; 11 rows > 1%) | diagnostic only (no row flag) | — | **specified as a diagnostic**; the row flag is **blocked** until a tolerance is justified (the 1% of revision 1 was data-derived, so it is withdrawn) |
| R5 `implausible_area` | physically impossible area | district crop area > the district's official geographic area; state sum > the state's | F6, S9 | `unusable` once active | none if the reference is correct | **blocked:** needs a versioned official geographic-area table (Census of India / LGD) |
| R6 `implausible_yield` | yield outside a plausible range | not defined. The revision 1 candidate (10× / 0.1× of the national crop-year median) is **withdrawn**. Its design-window hit counts (high 2 / 1 / 0; low 120 / 172 / 32) show the low side is noisy. | F6–F8 | `review` once active | — | **blocked:** needs reference maximum and minimum yields from an agronomic or official source |
| R7 `area_jump` | an abrupt change vs the district's own history | not defined. The revision 1 candidate is withdrawn: its reference is contaminated by earlier anomalies (WB 1999-2000 is flagged because 1997-98 is wrong) and tiny districts trip it. | candidate output | annotate once active | — | **blocked:** needs a robust reference design and a justified ratio |
| R8a `first_reported_after_state_start` | a district name absent in the state's first APY year | the district's first source year > its state's first source year (computed only over years ≤ the row's source year) | F14 | annotate | the source re-labels history by present geography (F15), so this is **not** proof of a boundary change | **specified** |
| R8b `boundary_split` | a parent / child district split | mapping from LGD / gazette history | F15, S8, S10 | annotate | — | **blocked:** needs LGD district history or state gazettes |
| R9 `single_season_annual` | an annual value backed by one named season | `annual_comparability == single_named_season` (**all crops, Wheat included**) | F9 | annotate; never presented as a verified annual total | genuine single-season crops are annotated too: intended, until a sourced crop calendar exists | **specified** (the Wheat Rabi exception is withdrawn) |
| R10 `method_change` | the comparability class changes vs the previous source year | class(source year) ≠ class(previous source year of the same district) | F10 | annotate | none | **specified** |
| R11 `unit_label` | unit labels other than Hectare / Tonnes / Tonnes/Hectare | exact string comparison | F1 (0 hits), S1 | `unusable` | none | **specified** (guard) |
| R12 `duplicate_conflict` | duplicate (year, state, district, crop, season) | exact key duplication | F2 (0 hits) | `unusable` | none | **specified** (guard) |
| R13 `provider_query_pending` | WB and Gujarat Potato 1997-98 rows | **accepted (D-48, Option 1):** every annual row with crop Potato, source year 1997-98 and state West Bengal or Gujarat. *Proposed (rev. 2, superseded):* an explicit `id` list fixed from F6 / F7. | F6, F7 | `review` until DES answers; no exclusion, no cause asserted (mirrors the Phase 9 U3 marker) | — | **review-only** |

**How the rules combine into `pq_class` (v1):**
- `unusable` if R1, R11 or R12 is triggered;
- else `review` if R3 or R13 is triggered;
- else `annotated` if R2, R8a, R9 or R10 is triggered;
- else `ok`.

Blocked rules (R4 row flag, R5, R6, R7, R8b) take no part until a later PQ-1 version activates them by decision.

**Comparability is never merged:** `verified_total`, `whole_year_row` and `single_named_season` stay separate classes in every output and summary. A consumer that wants "annual production" must state which classes it accepts.

**Reproducibility:**
- Each rule is a pure function of `apy_annual` / `apy_season` rows with source year ≤ the row's own source year.
- R8a and R10 look backward only. **No active rule looks forward.**
- v1 has no numerical thresholds. Any later threshold must live in a versioned provenance CSV, as AQ-1 does, with its source.

## 7. Temporal availability and leakage policy

- **Existing decisions:**
  - D-19 / A-13: the July–June agricultural year.
  - D-36: APY enters features at lag 2.
  - A-19: "about 6 months" after year end, based on **one observation**: the 14-12-2023 update containing 2022-23.
- **New evidence:**
  - National field-crop finals for 2022-23 appeared on 18 Oct 2023 (S6).
  - National horticulture finals for Onion and Potato appeared around March 2024 (S7), after the local file's update. The local 2022-23 Onion/Potato district values may therefore be provisional.
  - S5 indicates that district compilation can lag.
  - **No district-level release history was found.**
- **Proposed rule (`apy_lag2_policy_v1`, a policy assumption):** APY year *Y* is available from **1 July of *Y* + 2** (≥ 12 months after *Y* ends), so decision year *t* uses `source_apy_year = t − 2` only.
  - It never uses t − 1, even when a value exists.
  - It never backfills an earlier decision with a later year.
  - The label `source_apy_year` (what is described) is kept separate from `available_from` (when it is usable).
- **Known residual risk — vintages:** the file is one 2023 vintage. Earlier years may have been revised after first release, so backtests use revised, not first-published, values. Archival vintages would remove this risk; none are available. The risk will be stated in every result.
- **Checks:** every row satisfies `source_apy_year == decision_agri_year − 2` and `available_from ≤` any decision date that uses it. Phase 10 tests assert both.

## 8. Reserved-year recommendation

Under the §7 rule:

| Decision period | Uses source APY years |
|---|---|
| Validation decisions, 2019–2020 (`Phase_09_Integration_Plan.md` §5) | ≤ 2018-19 |
| Test-era decisions, 2021–2022 | 2018-19 … 2020-21 |
| Holdout-era decisions, 2023 – Feb 2024 | 2020-21, 2021-22 |
| No decision in the data range | 2022-23 |

**Recommendation** (consistent with D-40, and with how D-45 applied AQ-1 v1 unchanged to test rows):
1. **Design window = source years ≤ 2018-19.** All rule design, threshold choice and inspection happen here.
2. **Reserve 2019-20, 2020-21 and 2021-22** from Phase 10 development:
   - After PQ-1 is frozen by hash, these rows are built mechanically.
   - Only counts per `pq_class` are reported.
   - Values are read only by approved test or holdout protocols downstream.
3. **Exclude 2022-23 from v1:** it is unneeded, and its finality is in doubt (S7).
4. **The Phase 6 `apy_*_lag2` features are unaffected.** They already exist and were used under D-42 / D-45. Nothing is changed.

**Approval needed:** this does not alter any existing boundary. It adds a Phase 10-specific one.

## 9. Phase numbering and dependency proposal

**Recommendation: option (a) of `Phase_09_Integration_Plan.md`.** Keep the roadmap numbering, and treat the Integration Plan as the cross-phase interface specification. No files are renamed by this plan.

| Phase | Name (proposed) | Depends on | Status |
|---|---|---|---|
| 10 | **District Production Context** (was "Supply Prediction") | Phase 4 APY tables, D-18 crosswalk | this proposal |
| P (parallel, research only) | Cost and constraint evidence register: transport Rs/t-km, mandi fees, storage cost and capacity, spoilage, procurement windows | none (no code) | not started; blocks Phase 12 |
| 11 | Market Locations and Route Costs (nodes, distances, shortest paths) | 46 verified points (D-16), sourced distances or disclosed haversine, register P | not started |
| 12 | Decision Model (LP first, then MILP) | Phases 8, 9, 10, 11 and P | not started |
| 13 | Historical Rolling Backtest (roadmap "Dynamic Feedback", re-scoped) | 12; D-40 periods | not started |
| 14 | Final Evaluation and Demonstration (notebook first, then dashboard) | 13 | the demo notebook exists for Phases 1–9 only |

## 10. Downstream Phase 11 / 12 integration requirements

| Phase 10 output | Possible consumer | Allowed use | Not allowed |
|---|---|---|---|
| `production_tonnes`, `area_ha` (t − 2) | Phase 12 sourcing | rank or shortlist source districts; a slow prior | treating it as marketable surplus, weekly supply or market-level supply |
| a production-based cap | Phase 12 constraint | only with a **sourced share** or an explicitly approved assumption | inventing a share |
| `pq_class`, `annual_comparability` | Phases 12 and 13 | filters; sensitivity analysis (with and without `review` rows) | silent exclusion |
| `apy_state`, `apy_district` | Phase 11 nodes | join to mandi markets only via the D-18 crosswalk; coordinates only from the D-16 verified set | guessed coordinates or fuzzy joins |

| Blocking input (not in the data) | Needed by | Status |
|---|---|---|
| Market or district coordinates beyond the 46 verified points | 11 | missing; D-16 rule |
| Road distances / route network | 11 | missing; haversine only with disclosure |
| Transport cost (Rs/t-km), loading | 11, 12 | missing; register P |
| Mandi fees and commission | 12 | missing; state-specific sources needed |
| Storage cost, capacity, spoilage per week | 12 | missing |
| Marketable-surplus ratio | 12 | missing |
| Crop calendars / harvest windows; Wheat MSP procurement windows | 12, 13 | missing |
| Demand | 12 | **not in any dataset** (A-02); arrivals are not demand |

## 11. Test and acceptance plan (for the eventual implementation)

**Tests** (`Code/tests/test_phase10_production_context.py`; synthetic fixtures plus real-file guards):
1. Inputs are hashed and equal their recorded fingerprints (`cleaning_audit` / `features_audit` records for `apy_annual.csv`); inputs are unchanged after the run.
2. `source_apy_year == decision_agri_year − 2` for every row; no `source_apy_year` > 2021-22; no 2022-23 row.
3. `available_from` equals 1 July of the decision year's start; a decision dated before it cannot join (synthetic).
4. Keys are unique; row count = the eligible `apy_annual` rows; values are equal to source (no repair, clip or impute), except the documented R2 null.
5. Each rule fires on a synthetic positive and not on a negative. Rule outputs do not change when **later** years change (no look-ahead).
6. `pq_class` precedence; R9 applies to every crop (no Wheat exception); blocked rules produce no flag; the R13 id list matches F6/F7 exactly.
7. Reserved rows are built only after the PQ-1 freeze verifies, and the build log records counts only.
8. Nothing is written into `PROTECTED_DIRS` (`dataset.py`); the output directory is new.
9. The notebook contract: no reads of reserved values, no absolute paths, executes with Python 3.13 (mirrors `test_notebooks.py`).

**Acceptance:**
- All existing 242 tests still pass.
- The D-42 / D-45 freezes verify.
- The 62 recorded input hashes are unchanged.
- The manifest is reproducible byte-for-byte on a rerun.

## 12. Risks, unresolved questions and decisions requiring owner approval

| # | Decision | Recommendation |
|---|---|---|
| Q1 | Option A vs B | A (§4) |
| Q2 | Phase numbering | option (a); rename Phase 10 (§9) |
| Q3 | Information rule `apy_lag2_policy_v1` | adopt as a labelled policy assumption (§7) |
| Q4 | Design window ≤ 2018-19; reserve 2019-20 … 2021-22; exclude 2022-23 | adopt (§8) |
| Q5 | The R6 / R7 conventions (10× / 0.1×) or external references | **resolved (rev. 2):** withdrawn; R6 / R7 blocked pending reference evidence |
| Q6 | R5 reference (Census / LGD geographic areas) | source it; R5 stays blocked until then |
| Q7 | Send provider queries (§3) | the draft is in §15; **sending is the owner's decision**; until answered, R13 `review` |
| Q8 | The R9 exception for Wheat Rabi | **resolved (rev. 2):** withdrawn; R9 annotates all crops until a sourced crop calendar exists |
| Q9 | The field rename `district_code` → `apy_district_code` | adopt |
| Q10 | Defer the trailing summary to v1.1 | adopt |

**Main risks:**
- Revised values (vintages).
- Boundary splits (F14, F15).
- Single-season figures read as annual.
- Primary web sources not yet opened (§3).
- **Production context will not by itself make Phase 12 feasible:** every cost and capacity input is still missing.

## 13. Implementation steps after approval

1. On the owner's instruction, add the §14 entries **D-46 … D-49** to `Decision_Log.md` in the form the owner approves, and mark each ACCEPTED only as the owner states.
2. Collect the R5 reference and any R6 reference with an evidence register (source, version, access date); record the provider answers if received.
3. Implement `Code/production/pipeline.py:run_production_context()` with the following properties:
   - It reads `apy_annual.csv`, `apy_season.csv` and the raw APY `id`s.
   - It hashes the inputs before and after.
   - It writes to a new `Processed_Data/production_context/`: `production_context_v1.csv`, `pq1_provenance.csv` and `output_manifest.csv`.
   - It follows the phase-pipeline convention (`Code/<phase>/pipeline.py`, as in Phases 4–6).
4. Write the §11 tests with synthetic fixtures; build and inspect the design window (source ≤ 2018-19) only.
5. Freeze PQ-1 and the contract by hash (as D-42 / D-45). Then build the reserved source years once, mechanically, with the counts-only log.
6. Add `Code/utils/build_phase10_notebook.py` and `Notebooks/Phase_10_Production_Context.ipynb` (read-only over outputs, design window only); run them with `Code/utils/run_notebook.py`.
7. Update `Master_Project_Context.md`, `Data_Lineage.md`, `Future_Work_Roadmap.md` (Phase 10 renamed) and `Assumptions.md` (the lag policy wording replacing or annotating A-19).
8. Run the full test suite and the integrity checks, then present for review. Commit only on instruction.

## 14. Proposed decision entries for owner review (NOT in `Decision_Log.md`)

The entries follow the log's existing format (D-43 … D-45). They are written here only. Each heading reads PROPOSED until the owner states otherwise; this plan does not add them to the log.

**Roadmap consistency (checked for D-49):**

| Phase | `Future_Work_Roadmap.md` | `Master_Project_Context.md` §2 table | Conflict |
|---|---|---|---|
| 10 | "Supply Prediction", XGBoost | "Supply Prediction" | **name and scope** (D-46 / D-49) |
| 11 | "Logistics / Dijkstra"; routes and costs | same | none (name broadened) |
| 12 | "MILP Optimization" (PuLP / OR-Tools, not installed) | same | none on order; the tooling choice stays open (Integration Plan §7) |
| 13 | "Dynamic Feedback", defined as a rolling historical simulation | same | name only; the scope already matches backtesting |
| 14 | "Final End-to-End Evaluation" (demonstration content) | same | none |

The roadmap's header also still says Phase 9 "has started" and is stale. That is outside this decision, and to be fixed when the roadmap is next edited.

---

### D-46 — [ACCEPTED 2026-10-23 by the project owner; proposal text below kept as history] Phase 10 scope: descriptive district production context, contract `phase10-production-context-v1`
**Proposal**:
- **Scope:** Phase 10 builds a **descriptive**, leakage-safe district production context from APY (Option A). **No production-forecasting model** (Option B) is built or authorised.
- **Contract:** `phase10-production-context-v1` as `Phase_10_Production_Context_Plan.md` §5, including:
  - `available_from` and `information_rule` (D-47);
  - `annual_comparability` ∈ {`verified_total`, `whole_year_row`, `single_named_season`, `ambiguous`};
  - `apy_district_code`, the APY code kept as published and not an LGD/Census code;
  - `pq_class` / `pq_reasons` (D-48).
- **Grain:** one row per (crop, APY state, APY district, decision agricultural year) where the source district-year exists. A missing row means "not reported" and is never filled.
- **Values:** as published in `apy_annual.csv`. Nothing is repaired, clipped, imputed or deleted, except one documented change: a yield is set to null when production is null (source encoding, plan F4).
- **Comparability:** a verified annual total, a "Whole Year" row and a single named season are kept as distinct classes and never merged.
- **Deferred to v1.1:** the trailing 3-year summary, pending the boundary evidence for R8b.

**Evidence**: plan §2 (F1–F17) and §4.
- At most 22 annual points per district in the design window (median 17 / 18 / 22).
- A 2–3-year effective forecast horizon under D-47.
- Boundary re-labelling and splits (F14, F15).
- The reporting method changes in 184 / 179 / 19 districts.

**Alternatives considered**: Option B (forecasting): rejected for now, because the data are too few and non-stationary, the targets contain unresolved anomalies, and no downstream need for it has been shown.
**Status**: proposed 2026-10-23; **accepted 2026-10-23 by the project owner.** The accepted form is in `Decision_Log.md` D-46. It adds that no production-based procurement cap or marketable-surplus estimate is authorised.
**Phase**: 10.

### D-47 — [ACCEPTED 2026-10-23 by the project owner; proposal text below kept as history] APY information availability and the Phase 10 design / reserved windows
**Proposal**:
- **Availability rule (`apy_lag2_policy_v1`, a policy assumption, not a verified release guarantee):**
  - APY year Y1–Y2 (1 July Y1 – 30 June Y2) may be used from **1 July of Y2 + 1**.
  - So decision agricultural year t uses `source_apy_year = t − 2` only; never t − 1, and never a later year to backfill an earlier decision.
  - Example: 2018-19 values become usable from 1 July 2020, i.e. in decision year 2020-21.
  - This restates D-36's lag with an explicit date. D-36 and A-19 are otherwise unchanged.
- **Design window:** all rule design, inspection and any future threshold choice use source years **≤ 2018-19** only.
- **Reserved:** source years **2019-20, 2020-21 and 2021-22**.
  - They are built once, mechanically, after PQ-1 and the contract are frozen by hash.
  - Only counts per `pq_class` are reported.
  - Their values are read only by downstream protocols that are themselves approved.
- **Excluded from v1:** source year **2022-23**. No decision up to the end of the data (Feb 2024) needs it, and its finality is uncertain.
- **Unchanged:** this adds a Phase 10 boundary. It does not change D-40, D-42, D-45 or the Phase 6 `apy_*_lag2` features.

**Evidence**: A-19 (one observed release); national finals for 2022-23, 18 Oct 2023 (field crops) and about March 2024 (horticulture) (plan S6, S7); district compilation can lag (S5). No district-level release history was found.
**Residual risk**: the file is one 2023 vintage, so revised values are used for earlier years. Every result states this.
**Alternatives considered**: lag 1 (rejected: not available for much of each year, D-36); release-date-specific availability (not possible without a release history).
**Status**: proposed 2026-10-23; **accepted 2026-10-23 by the project owner.** The accepted form is in `Decision_Log.md` D-47. It adds the publication-timing caveat and the disclosure of the earlier exploratory profile.
**Phase**: 10.

### D-48 — [ACCEPTED 2026-10-23 by the project owner, with R13 Option 1; proposal text below kept as history] PQ-1 v1 production quality rules (flags only; no numerical thresholds active)
**Proposal**:
- Adopt PQ-1 v1 as in `Phase_10_Production_Context_Plan.md` §6, revision 2:
  - **specified:** R1, R2, R4 (manifest diagnostic only), R8a, R9 (all crops), R10, R11, R12;
  - **review-only:** R3 (zero production), R13 (WB and Gujarat Potato 1997-98, pending DES);
  - **blocked, inactive in v1:** the R4 row flag, R5 (needs official geographic areas), R6 (needs reference yields), R7 (needs a robust reference design), R8b (needs LGD / gazette split history).
- **`pq_class` precedence:** `unusable` (R1, R11, R12) > `review` (R3, R13) > `annotated` (R2, R8a, R9, R10) > `ok`.
- **Activating a blocked rule** requires a new decision citing its evidence, and a new PQ version.

**Evidence**: plan §2 F1–F15, from the design window only; candidate hit counts (revision 1) are kept as the record of why thresholds were withdrawn.
**Alternatives considered**: the AQ-1 10× / 0.1× unit-factor convention for R6 / R7 (withdrawn: unsupported for APY, noisy on small districts, contaminated references).
**Status**: proposed 2026-10-23; **accepted 2026-10-23 by the project owner.** The accepted form is in `Decision_Log.md` D-48. It adds the clarifications for R8a (per crop and state) and R10 (most recent earlier source year with a row for the same crop, state and district), and R13 Option 1 (all annual rows of West Bengal and Gujarat Potato 1997-98).
**Phase**: 10.

### D-49 — [PROPOSED 2026-10-23; NOT ACCEPTED] Phase numbering and names for Phases 10–14
**Proposal**:
- Keep the roadmap numbering; this is option (a) of `Phase_09_Integration_Plan.md`.
- **Rename:**
  - Phase 10 "Supply Prediction" → **District Production Context**.
  - Phase 11 → **Market Locations and Route Costs**.
  - Phase 12 → **Decision Model (LP, then MILP)**.
  - Phase 13 "Dynamic Feedback" → **Historical Rolling Backtest** (same scope as the roadmap's definition).
  - Phase 14 → **Final Evaluation and Demonstration**.
- **Research track P** (cost and constraint evidence: transport, fees, storage, spoilage, capacities, procurement windows) runs in parallel, with no code, and blocks Phase 12.
- **Files:** no files are renamed. `Future_Work_Roadmap.md` and the `Master_Project_Context.md` table are updated only after acceptance.

**Evidence**: the roadmap consistency table above; Integration Plan §6–7.
**Alternatives considered**: option (b), inserting an integration phase and renumbering (rejected: it renumbers existing references for no gain).
**Status**: proposed 2026-10-23; awaiting the project owner.
**Phase**: 10–14 (planning).

## 15. Draft enquiry to DES (DRAFT — NOT SENT)

**Sending is the owner's decision.**
- **Recipient:** to be confirmed from the official contact page of `desagri.gov.in` (Agricultural Statistics / district APY). No address is assumed here.
- **Sender details:** to be completed by the owner.

> **Subject:** Query on district-wise Crop Area, Production and Yield (APY) data — Potato 1997-98 (West Bengal, Gujarat), release history and revisions
>
> Dear Sir/Madam,
>
> We are using the district-wise Crop Wise Area Production Yield dataset (extraction page `https://data.desagri.gov.in/website/crops-apy-report-web`; our copy is marked "Data Last Updated 14-12-2023") in an academic project. Could you please help with the following?
>
> 1. **West Bengal, Potato, 1997-98 (season "Whole Year"):** the district areas sum to about 19.6 million hectares (e.g. Murshidabad 4,314,164 ha with 3,773,700 t; Nadia 4,100,237 ha; Malda 2,880,154 ha). In 1998-99 the state total is about 0.32 million ha. Are the 1997-98 area and production values in different units, or are they otherwise to be read differently?
> 2. **Gujarat, Potato, 1997-98:** several districts show yields of about 0.004–0.08 t/ha (e.g. Bharuch: 134,000 ha, 706 t). Are these values correct, and in the stated units?
> 3. **Release history:** for each agricultural year, when were district-level figures first published? Are earlier years revised in later releases, and are earlier releases (vintages) available?
> 4. **2022-23 horticultural crops (Onion, Potato):** are the district values in the 14-12-2023 release final, or provisional pending the horticulture final estimates?
> 5. **Geography:** are historical rows re-labelled to present-day state and district names? For example, Telangana districts appear for years before 2014. Is a mapping of district splits available?
> 6. **Seasons:** for a district with a single "Whole Year" row, does that row represent the full agricultural-year total?
>
> Thank you for your assistance.

## 16. Audit scripts: review and preservation recommendation

The scripts live in the session scratchpad (outside the repository; temporary). They were reviewed, not re-executed for this revision.

| Script | Purpose | Assessment | Recommendation |
|---|---|---|---|
| `apy_audit.py` | F1–F16 | Correct, but it loads all years before filtering; prints row counts for reserved years; has one pandas reindex warning (`both[r["area"] > 0]`); no input-hash check; output only to stdout | **Preserve after hardening**, as `Code/production/apy_audit.py` when Phase 10 is approved |
| `apy_candidate_rules.py` | R6 / R7 hit counts | Exploratory thresholds now withdrawn | **Do not preserve as code.** Its counts are recorded in §6 and D-48 as the reason for withdrawal. |
| `profile_apy.py` | first profile (previous session) | Computed value statistics through **2020-21**, outside the D-47 design window | **Do not preserve** (disclosed in §2.1) |
| `integrity.py` | protected-hash, D-42 / D-45 freeze, run-guard and git checks | Useful and read-only. It calls `arrivals_final.preflight()` (checks only, never runs the test). It hard-codes "17 baseline files" and depends on `git`. | Optionally preserve as `Code/utils/verify_integrity.py` under a separate, small approval; not part of Phase 10 |

**Safe reproducibility approach for `apy_audit.py`:**
1. Check the inputs' SHA-256 values against their recorded fingerprints before reading:
   - raw APY: `integration/audit/source_fingerprints.csv`;
   - `apy_annual.csv`: `features_audit/input_fingerprints.csv`.
2. Filter to `year ≤ 2018-19` immediately after load, and assert it.
3. Report reserved years only as row counts.
4. Write deterministic CSVs to the new `Processed_Data/production_context/audit/`, never into `PROTECTED_DIRS`.
5. Give it a pytest that runs it on a synthetic fixture and asserts that no reserved value reaches any output.
6. Run it with `C:\Python313\python.exe -B` from the project root.

## 17. Implementation record (v1, 2026-10-23)

Implemented under D-46 – D-48 as accepted. D-49 is still not accepted, so the roadmap and phase names are unchanged.

- **Code:**
  - `Code/production/pipeline.py`: contract, PQ-1 v1, input verification, freeze, and the stages `design` / `freeze` / `build`.
  - `Code/production/apy_audit.py`: the hardened audit of §16.
  - `Code/tests/test_phase10_production_context.py`.
  - `Code/utils/build_phase10_notebook.py`, which generates `Notebooks/Phase_10_Production_Context.ipynb` (read-only).
- **Outputs** in `Processed_Data/production_context/`:
  - `production_context_v1.csv`: 31,694 rows, of which 27,531 are design-window and 4,163 reserved.
  - `pq1_provenance.csv`, `output_manifest.csv`, `pq1_freeze_manifest.csv`, `build_log.csv`.
  - `design/`, and `audit/` (13 tables + manifest).
  - Lineage and reproduction steps: `Data_Lineage.md`, Phase 10 section.
- **Order followed:**
  1. Inputs verified.
  2. Audit and design build (source ≤ 2018-19) inspected.
  3. PQ-1 and the contract frozen by hash (once).
  4. Reserved years built mechanically, with counts only.
  5. Rebuild confirmed byte-identical.
- **R4 diagnostic** (design window, annual grain): Onion 7,898 rows, maximum 1.0%; Potato 8,862 rows, 6.9%; Wheat 10,659 rows, 1.05%. No flag.
- **Crosswalk verification:** a documented CSV round-trip canonicalisation of `alias_basis` only. Neither the file nor the record was modified (`Data_Lineage.md`).
- **Differences from earlier sections:**
  - §11's notebook test lives in the Phase 10 test file.
  - The audit drops the withdrawn 1% / 10% / 0.1×-median cuts.
  - The comparability-class changes (297 / 341 / 69 districts) count four classes, while F10's 184 / 179 / 19 counted the two D-20 methods.
- **Not done:** the R5 and R6 references; the provider answers (the DES enquiry is unsent); v1.1 (trailing summary, R8b).
