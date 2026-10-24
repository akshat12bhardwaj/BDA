# Data Source Review: Audit, Replacement Candidates and Migration Plan

**Status (2026-10-24): evidence gathered, nothing approved.**
- No production dataset, frozen output, model or dashboard file was changed.
- Raw candidate samples are in the git-ignored folder `Dataset_Candidates/`.
- Small validation outputs are in `Processed_Data/candidates/`.
- The scripts are in `Code/candidates/`. Each one is read-only and takes its paths as arguments.

**Evidence labels** used in this document:
- **[V] verified:** measured here, or read from an official response.
- **[A] assumption:** believed but not proven.
- **[U] unresolved:** needs a decision or access we do not have.

## Contents
1. Existing data quality audit
2. Replacement research and source comparison
3. Replacement decision matrix
4. Download and provenance manifest
5. Validation report
6. Proposed migration plan
7. New training and testing experiment plan
8. Remaining risks, licensing issues and data gaps

---

## 1. Existing Data Quality Audit

Produced by `Code/candidates/audit_existing.py`. Outputs are in `Processed_Data/candidates/existing_audit/`.

**Headline [V].** Field-level missingness in the current data is low. The weaknesses are coverage, freshness, reporting density and provenance.

### 1.1 Mandi prices and arrivals

Source: `Dataset/India Commodity Wise Mandi Dataset/{Onion,Potato,Wheat}.csv`. Its upstream source and download location were never recorded (Master Context §4.1). §5.1 shows it is a copy of the AGMARKNET feed served by data.gov.in.

The data is used by both the dashboard and the models:
- Phases 4–9 use it.
- The Spark ETL uses it.
- The `/api/markets/*` and outlook endpoints read Spark and Phase 8/9 outputs that derive from it.

| Metric [V] | Onion | Potato | Wheat |
|---|---|---|---|
| Raw rows (10 columns) | 2,624,379 | 2,764,987 | 2,593,767 |
| Date range | 2000-10-19 → **2024-02-02** | 2000-10-19 → **2024-02-02** | 2001-03-16 → **2024-02-01** |
| States / districts / markets / varieties | 32 / 512 / 1,732 / 25 | 33 / 505 / 1,624 / 22 | 28 / 457 / 1,988 / 71 |
| Modal price unusable (zero or missing) | 1.07% | 1.20% | 0.55% |
| Min / max price null after zero→missing | 4.86% / 4.58% | 4.90% / 4.60% | 4.94% / 4.72% |
| Arrivals unusable | 0.005% | 0.008% | 0.006% |
| Conflicting duplicate rows (kept, flagged) | 68 | 164 | 106 |
| Price scale error suspected / review | 422 / 22,330 | 415 / 2,339 | 148 / 471 |
| Arrivals entry error suspected | 75 | 62 | 53 |
| Rows with same-day weather | 25.3% | 23.6% | 25.2% |
| Rows with an APY district | 95.9% | 95.5% | 97.9% |
| Median market reporting density (days reported ÷ days in its span; markets with span ≥ 1 year) | 0.33 | 0.38 | **0.14** |
| Markets reporting on < 25% of days | 622 of 1,479 | 510 of 1,424 | 1,091 of 1,810 |

**Missingness by year [V]** (`mandi_by_year.csv`):
- Unusable modal price peaks in 2006–2011 (Onion 4.76%, Potato 5.06% and Wheat 1.62%, each in 2008).
- It falls below 0.1% from 2016.
- 2024 holds only January: 17,028 / 17,548 / 9,805 rows.

**Location gaps [V]** (`mandi_by_state.csv`):
- Assam Wheat reports about 300 rows a year in 2017–2019, then none from 2020.
- The number of reporting states falls in 2020 (Wheat 17 → 14, Onion 28 → 22), consistent with COVID-period reporting gaps.

**Known issues already handled by earlier phases [V]:**
- zero-price placeholders (Phase 5, R-rules);
- unresolvable conflicting duplicates (A-18);
- Madhya Pradesh arrivals placeholders of 0.01 / 0.05 / 0.1 t in 2019–2020 (Phase 9, AQ-1).

**Suitability.** The data is suitable for its purpose through 2022 and covers the 2023 holdout. It is **unsuitable for anything after 2024-02-02**, because it is stale by 32 months. Wheat's low reporting density reflects seasonal trading (procurement peaks), not missing data.

### 1.2 Weather

Source: Open-Meteo archive, assembled as `Processed_Data/integration/weather_daily_panel.parquet`. It is used by Phase 4/6 features, the weather configuration in Phase 8, and `/api/locations/{id}/climate`.

| Metric [V] | Value |
|---|---|
| Rows / locations | 369,610 / 46 district points |
| Dates | 2001-01-01 → **2022-12-31** |
| Nulls (7 variables) | 0.000% |
| Duplicate keys / Tmax < Tmin / negative rain / Tmax > 50 °C | 0 / 0 / 0 / 0 |

**Suitability:**
- The panel is complete internally, but its coverage is narrow. It reaches only about a quarter of mandi rows, and it ends before the 2023 holdout, which is why the holdout is "no-weather" by design.
- **[A]** Open-Meteo is ERA5 reanalysis, a modelled product, not station observations. §5.3 measures how it compares with IMD.

### 1.3 Agricultural production (APY)

Source: `Dataset/crop-wise-area-production-yield.csv`, from DES via data.desagri.gov.in, last updated 14-12-2023 per its codebook. It is used by Phase 4/6 features, the Phase 10 production context and `/api/production`.

| Metric [V] | Onion | Potato | Wheat |
|---|---|---|---|
| Rows / states / districts | 14,822 / 25 / 581 | 14,108 / 28 / 615 | 12,905 / 31 / 642 |
| Years | 1997-98 → 2022-23 (26) | same | same |
| Production null / zero | 0.36% / 0.04% | 0.19% / 0.07% | 0.22% / 0.02% |
| Duplicate (year, state, district, season) keys | 0 | 0 | 0 |
| Units | ha, t, t/ha | same | same |

**Suitability:** good. Two limits:
- **District coverage varies by year** (Onion: 194 to 471 districts, `apy_by_year.csv`).
- The latest year is 2022-23.

Phase 10 already reserves source years 2019-20 and later.

### 1.4 Other inputs

- **Agri Market Dataset.csv** (39,060 rows): Maharashtra only, 5 commodities. Phase 4 showed it is identical to mandi values (96.6% match), so it is a consistency check only.
- **final_data.csv** (4,151 rows, 0 nulls, unique market codes): a lookup table.

Both are **Retain as is**. Neither is a modelling input.

### 1.5 Boundaries that must not move [V]

- **Price model (Phase 8, D-40/D-42)** (`split_definition.csv`):
  - train: target Sundays 2002-01-06 → 2018-12-30;
  - validation: 2019 and 2020;
  - test: 2021–2022, run once;
  - holdout: from 2023-01-01, no weather, unscored.
- **Arrivals (Phase 9, D-45):** frozen by hash; tested once on 2021–2022.
- **Phase 10:** source years ≤ 2018-19 are the design window; 2019-20 → 2021-22 are reserved.
- **Dashboard limits:** `Code/app/data.py` enforces price origins ≤ 2020-12-27, no 2023+ data and no reserved production values.

---

## 2. Replacement Research and Source Comparison

Ranked by fit to this project. "Access verified" means real records were retrieved, not just a landing page viewed.

| # | Candidate (provider) | Landing page → endpoint | Coverage | Fields / granularity | Licence and access | Access verified |
|---|---|---|---|---|---|---|
| A1 | **Variety-wise Daily Market Prices** (DMI, MoA&FW, AGMARKNET via data.gov.in) | [data.gov.in resource](https://www.data.gov.in/resource/variety-wise-daily-market-prices-data-commodity) → `api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24` | All India; probed 2003 → **2026-10-20**; updated daily (API `updated_date` 2026-10-22); totals: Onion 3,402,994, Potato 3,470,113, Wheat 3,539,548 records | State, District, Market, Commodity, Commodity_Code, Variety, **Grade**, Min/Max/Modal price, Arrival_Date. **No arrivals quantity** | Portal-level GODL-India **[A]**; the public sample key returns **10 records per call**; a personal key is free on registration, but its limit is **[U]** | **Yes**: 261 calls, record-level match (§5.1) |
| A2 | **Agmarknet 2.0** (DMI/NIC) | [agmarknet.gov.in](https://agmarknet.gov.in) → undocumented `api.agmarknet.gov.in/v1/daily-price-arrival/*` | Per its own filter metadata: price from 2021-01-01, arrivals from 2021-01-01 (commodity level), price + arrivals together only from **2025-11-07** (go-live); one-year window per request; 4,176 markets, 751 districts | Price and arrivals, market IDs | No published API, licence or terms **[U]** | Filter metadata only. Reports were not pulled, deliberately |
| A3 | Current Daily Price (MoA&FW, data.gov.in) | [data.gov.in resource](https://data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi) → resource `9ef84268-…` | Current day **[A]** (from its title; history depth not probed) | Same price fields, no arrivals | As A1 | Schema only |
| A4 | APMC arrivals and prices (Agmarknet mirror on India Data Portal) | [IDP package](https://ckandev.indiadataportal.com/dataset/apmc-arrivals-and-prices) | Not determinable | — | "License not specified"; CKAN lists one resource with no URL | **No**: no downloadable file |
| W1 | **IMD gridded** daily rainfall 0.25° (1901–2024) and Tmax/Tmin 1° (IMD Pune) | [IMD Pune gridded data](https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html) → POST `rainfall.php` / `maxtemp.php` with a year | India land; the year list runs to 2025; gauge-based observations | Rain mm/day on a 135×129 grid; temperature on 31×31 | No licence stated on the page; cite Pai et al. 2014 (MAUSAM); redistribution **[U]** | **Yes**: 2022 rain (25.4 MB) and Tmax (1.4 MB); file sizes equal grid × 365 × 4 bytes exactly |
| W2 | Open-Meteo archive (current source) | [open-meteo.com](https://open-meteo.com/en/docs/historical-weather-api) | 1940 → about 5 days ago; ERA5 / ERA5-Land reanalysis | 7 variables in use | **CC BY 4.0, with a link required next to displayed data** ([licence](https://open-meteo.com/en/licence)); free tier is non-commercial **[A]** | Yes (Phase 3) |
| W3 | NASA POWER (NASA LaRC, MERRA-2) | [power.larc.nasa.gov](https://power.larc.nasa.gov) → `/api/temporal/daily/point` | Global, 1981 → near present | T2M, T2M_MAX/MIN, PRECTOTCORR, RH2M, WS2M on a 0.5°×0.625° cell | NASA open data, no key | **Yes**: 3 points, 2015–2022 |
| P1 | **UPAg district crop-wise APY** (DES via UPAg, on India Data Portal) | [IDP package](https://ckandev.indiadataportal.com/dataset/area-production-yield-apy) → resource `6f70d961-…` | 2013-14 → **2024-25**; field crops only | Area, production, yield; **no unit columns** | Open Data Commons Attribution (IDP package) | **Yes**: full file, 16.9 MB |
| P2 | DES crop-wise APY, re-mirrored 2026-03-02 | Same package → resource `f980409d-…`; origin [data.desagri.gov.in](https://data.desagri.gov.in/website/crops-apy-report-web) | 1997-98 → 2022-23 | Same 16 columns as ours | Same | **Yes**: full file, 56.2 MB |

**Not investigated in depth [U]:**
- **NHB horticulture statistics:** state-level Onion/Potato, likely 2023-24+.
- **ICRISAT District Level Database:** registration required; ends about 2017.
- **Crop calendars:** DES/IMD crop weather calendars.
- **Soil and irrigation layers.**

None of these has a stated purpose in the current models. Section 8 says when they would matter.

**Not considered credible as a primary source:** dataful.in and IndiaStat. They are third-party compilations of the same official data, often paywalled.

---

## 3. Replacement Decision Matrix

| Dataset | Decision | Evidence |
|---|---|---|
| Mandi prices 2001 → 2024-02 (current) | **Retain** | The official API holds the same records: 35/35 sampled market-days have identical modal prices, and daily counts differ by −7 to +31 rows. Replacing it adds no quality and would break Phase 4–10 hashes. |
| A1 data.gov.in prices, **2024-02-03 → present** | **Supplement**, pending approval and a personal key | It is the only verified official source of current prices. Before use it needs two things: (i) a market-name crosswalk, because only 3.4% of 2026 Onion records match existing market names; and (ii) deterministic, deduplicated paging (§5.1). |
| A1 as a **replacement** for history | **Reject** | No arrivals field. For overlapping years it duplicates what we already hold. |
| Mandi arrivals (current) | **Retain** (sole source) | No verified public source offers arrivals history before 2021 at market level. Agmarknet 2.0 offers arrivals only from 2021-01-01, through an undocumented backend. |
| A2 Agmarknet 2.0 backend | **Reject for bulk use; ask DMI** | Undocumented and without terms. It would be the only route to arrivals after 2024-02. |
| A3 current daily price | **Reject** | Current-day snapshot; A1 already covers it. |
| A4 IDP arrivals mirror | **Reject** | No downloadable file; no licence. |
| Weather: Open-Meteo (current) | **Retain**, and extend to 2026 for the same 46 points if a new test window is approved | It agrees with IMD gauge rainfall better than NASA POWER does (monthly r 0.95–0.98). It runs about 1.2–2.0 °C cooler than IMD on Tmax: a bias to document, not a reason to switch. |
| W1 IMD gridded rainfall | **Supplement** (rainfall only), conditional | Observation-based and India-specific. It could extend rainfall to every mandi district, but that needs district boundaries the project lacks (the routing market nodes have 0 coordinates by design), and its redistribution terms are unconfirmed. |
| W1 IMD 1° temperature | **Reject** | The 1° (~110 km) cells are coarser than the current district points. |
| W3 NASA POWER | **Reject** | Measurably worse against IMD: Nashik 2022 rain **2,331 mm vs IMD 1,332 mm**, monthly r 0.89–0.97. The cell is coarse. |
| APY (current) | **Retain** | The 2026-03 DES re-mirror is **content-identical**: 41,835 of 41,835 Onion/Potato/Wheat rows match, 0 production revisions, no new years. |
| P1 UPAg APY | **Supplement, Wheat only** | Adds Wheat 2023-24 (539 district rows) and 2024-25 (531). Units verified against DES on 5,188 overlapping rows: area ratio 1.000, production 1.000, yield ×1000 (kg/ha), 99.7% within 1%. Contains no Onion or Potato. |
| P2 DES re-mirror | **Reject** (redundant) | Identical content. |

---

## 4. Download and Provenance Manifest

- **Machine-readable manifest:** `Processed_Data/candidates/provenance_manifest.csv`. It has 270 files, each with path, provider, endpoint, licence, access method, retrieval date, bytes, SHA-256 and transformations ("none").
- **Retrieval date:** 2026-10-24 IST.

| Folder (`Dataset_Candidates/`) | Contents | Size |
|---|---|---|
| `datagov_variety_prices/2026-10-24/` | 262 raw JSON API responses: 69 validation calls (30 day counts, 36 record lookups, 3 post-2024 days) and 192 continuity pages (Onion, full days 2024-01-17, 2025-06-18 and 2026-10-20), plus one schema probe | < 1 MB |
| `agmarknet2/2026-10-24/` | `daily-price-arrival_filters.json` (filter and date-range metadata) | 0.5 MB |
| `nasa_power/2026-10-24/` | Nashik, Ludhiana and Agra daily, 2015–2022 (CSV) | 0.4 MB |
| `imd_gridded/2026-10-24/` | `rain_2022.grd` (0.25°), `tmax_2022.grd` (1°) | 26.8 MB |
| `apy_idp/2026-10-24/` | `des_apy_idp_20260302.csv`, `upag_apy_idp_20261012.csv` | 73.2 MB |

**Rules followed:**
- Raw files are stored byte-for-byte as received and are never edited.
- Derived tables live only in `Processed_Data/candidates/`.
- `Dataset/` is untouched, and `Dataset_Candidates/` is git-ignored.

**Access notes:**
- The data.gov.in API rejects an encoded `/` (`%2F`) in date filters.
- It stalls on the `Python-urllib` user agent, so the scripts call `curl`.

---

## 5. Validation Report

### 5.1 A1 data.gov.in prices against the existing mandi data

Scripts: `validate_datagov.py`, `identifier_continuity.py`. Outputs: `Processed_Data/candidates/datagov/`.

**Schema [V]:**
- All fields arrive as strings in the older records.
- In 2026 records, `Commodity_Code` and the prices arrive as numbers.
- Dates are `dd/mm/yyyy`.
- Units are not stated. The values match our Rs./quintal exactly, so the unit is Rs./quintal **[V by equality]**.

**Daily record counts** (`daily_count_comparison.csv`, 10 dates × 3 crops) [V]:
- API minus ours ranges from **−7 to +31 rows a day**, or −1.6% to +12.5%.
- The largest gaps are Wheat 2010–2016 (+25 to +29) and Onion/Potato 2016-01-15 (+30/+31).
- Possible cause **[A]:** later back-filled records or a grade split. Not resolved.

**Record-level match** (`record_match_sample.csv`; 36 market-days stratified across 2008/2014/2019/2023) [V]:
- 35 of 36 market-days were found in the API.
- In all 35, the modal price for the same variety is **identical**.
- The one miss: Wheat, Nanggaon, Maharashtra, 2019-12-12.
- Every sampled record has grade `FAQ`.

**Conclusion [V]:** the existing dataset is a copy of this feed. There is nothing to "repair" in it with A1.

**Identifier continuity**, Onion full days (`Onion_continuity.json`) [V]:

| Day | Records (API total) | Market names found in existing data | Varieties found | Grades |
|---|---|---|---|---|
| 2024-01-17 | 556 | **98.6%** | 100% | FAQ only |
| 2025-06-18 | 829 | **76.7%** (new Tamil Nadu *Uzhavar Sandhai* farmer markets) | 99.4% | FAQ / Local / Non-FAQ |
| 2026-10-20 | 530 | **3.4%**; 41.3% after stripping a trailing " APMC" | 95.8% | 10 labels |

- Agmarknet 2.0 renamed markets at go-live (e.g. *Sonepat* → *Sonepat APMC*, *Indore* → *Indore APMC*).
- It also brought in a grade taxonomy.
- Composition shifted too: 829 records on a June 2025 day against about 550 a year earlier.
- Naively appending post-2024 data would therefore create **new, short series** rather than continuing existing ones.

**Paging defect [V]** (diagnosed and avoided in §5.5):
- Offset paging with `limit=10` returned **15–17% duplicate rows**: 87/556, 139/829 and 95/530.
- Fewer distinct records than `total` were retrieved, so some records were never returned.
- The fix found: one call per partition with no offset, accepted only when `count == total == distinct`.

**Plausibility [V]:** modal prices on 2026-10-20 run from 190 to 13,000 Rs./q for Onion. The existing R-rules (zero placeholder, scale error) apply unchanged.

### 5.2 Agmarknet 2.0 metadata [V]

From `daily-price-arrival_filters.json`:
- `price.from_date` 2021-01-01; `arrival.from_date` 2021-01-01; `both.from_date` **2025-11-07**; `to_date` 2026-10-23.
- `allowed_year_range` = 1.
- Note 100005: "arrival quantities at the commodity level for all dates."

No report data was requested.

### 5.3 Weather: Open-Meteo vs NASA POWER vs IMD, 2022, three points

Script: `compare_weather.py`. Output: `Processed_Data/candidates/weather_comparison_2022.csv`.

All three sources have 0 missing days at all points [V].

| Point | Rain 2022, mm: Open-Meteo / NASA / **IMD** | Monthly rain r vs IMD: OM / NASA | Mean Tmax °C: OM / NASA / **IMD** | Daily Tmax MAE vs IMD: OM / NASA |
|---|---|---|---|---|
| Nashik | 1,136 / **2,331** / 1,332 | 0.969 / 0.930 | 30.2 / 30.6 / 32.2 | 2.41 / 2.68 |
| Ludhiana | 873 / 1,000 / 834 | 0.976 / 0.970 | 29.8 / 31.7 / 31.3 | 1.69 / 1.54 |
| Agra | 819 / 776 / 997 | 0.951 / 0.888 | 31.4 / 33.2 / 32.6 | 1.50 / 1.67 |

**Interpretation:**
- Daily rain correlation is modest for every source (0.53–0.80), as expected for point vs grid comparisons. The weekly and monthly aggregates the models use agree well.
- **[A]** IMD temperature is a 1° cell average, so part of the Tmax gap is spatial support, not error.
- Three points and one year is a sample, not a national validation.

### 5.4 APY candidates

Script: `compare_apy.py`. Output: `Processed_Data/candidates/apy_comparison.json`.

**DES re-mirror [V]:**
- Same 455,359 rows and same columns.
- Outer join on (year, state, district, crop, season): 41,835 rows matched for the three crops, 0 left-only, 0 right-only, **0 production revisions**.
- The file SHA-256 differs from ours only through formatting.

**UPAg [V]:**
- Years 2013-14 → 2024-25.
- Onion 0 rows, Potato 0 rows, Wheat 6,321 rows (628 districts; Rabi 6,209 / Summer 94 / Kharif 18).
- Null area 0%; null production and yield 0.17%.
- Against DES Wheat (5,188 matched rows, 2013-14 → 2022-23): medians are area 1.000, production 1.000 and yield ×1000. So the units are **ha, t and kg/ha**.
- 99.7% of production values agree within 1%.

### 5.5 Personal-key pagination diagnosis and a single-call extraction method (2026-10-24)

**Run 1, offset paging** (`datagov_key_check.py`; log `Processed_Data/candidates/datagov_key_check/20261023T232047Z.json`):
- Personal key; Onion, 17/01/2024; 100-record pages.
- Result: 556 rows, but only 408 distinct.
- The repeated page at offset 300 differed.
- Verdict: unreliable.

**Diagnosis [V]**, made offline from that run's saved responses:
1. **The source is not duplicated.** The run's first call (`limit=1000`) returned all 556 records, every one distinct.
2. **The record key is not the cause.** There were 0 conflicting keys, duplicates were whole-record identical, and the paged union is a strict subset of the one-call set.
3. **The cause is unstable server ordering under offset paging.**
   - Pages at offsets 0, 100 and 500 equal the matching slices of the single response.
   - Pages at offsets 200–400 do not: page 300 overlaps earlier pages by 84 records.
   - A repeat request for offset 300 shared **0** records with the first one.
   - So 148 records were returned twice and 148 never.
4. **Ordering is undocumented.** The data.gov.in API page renders its parameter list client-side. The only mention of `sort` found is a third-party R client (`ogdindiar`) for a legacy endpoint, so sorting was **not** tested and is not relied on.

**Method tested: one call per partition, no offset** (`datagov_partition_check.py`):
- Each call uses `limit=5000`, `offset=0` and no sort.
- A partition is accepted only if count = total = distinct records **and** total < limit.
- Log: `Processed_Data/candidates/datagov_partition_check/20261023T232646Z.json`. Raw responses, key redacted: `Dataset_Candidates/datagov_partition_check/20261023T232646Z/`.
- 53 calls, all HTTP 200.

| Experiment [V] | Filters | Result |
|---|---|---|
| X0 cap | Commodity=Onion (3,403,719 rows) | 5,000 returned for `limit=5000`, so a single call holds at least 5,000 records. The largest commodity-day seen is 829. |
| X1 repeat ×3 | Commodity + date (Onion 17/01/2024) | 556 / 556 / 556, all distinct, **identical sets** |
| X2 state partition | Commodity + State + date; 32 states (23 non-empty), taken from the coarse set **plus** every state in our Onion history, so a state missing from the coarse call would still be queried | Union = 556 = coarse set; partition totals sum to 556; 0 missing, 0 extra, 0 overlap |
| X3 market partition | Commodity + State + Market + date; Madhya Pradesh, 11 markets (several varieties per market, including the range-flagged records) | Union = 17 = the state set; 0 missing, 0 extra, 0 overlap |
| X4 other crops and days, ×2 each | Potato 17/01/2024 (550), Wheat 17/01/2024 (387), Onion 18/06/2025 (829) | Every call complete and distinct; repeats identical |
| Agreement with existing data, 2024-01-17 (state + market + variety) | Onion / Potato / Wheat | 538 / 530 / 357 matched pairs, **100% identical modal price** |

**Unmatched records [V]:** 18 API-only and 16 ours-only Onion records. Nearly all are **market renames the API applies retroactively** to 2024 dates, with identical prices:
- Aurangabad → Chattrapati Sambhajinagar;
- Osmanabad → Dharashiv;
- Kota (FV) → Kota (F&V);
- Alwar(FV) → Alwar (F&V).

A few, such as Morbi and Hingna, have no counterpart and may be later back-fills **[A]**. So the market crosswalk (M2) is needed even for dates inside the existing data.

**Modal-price range anomalies [V].** On Onion 17/01/2024 there are 5 records, not 4. The paged run missed one.

| State | District | Market | Variety | Min | Max | Modal |
|---|---|---|---|---|---|---|
| Madhya Pradesh | Ratlam | Sailana | Medium | 1,000 | 1,253 | 890 |
| Madhya Pradesh | Ratlam | Sailana | Nasik | 1,180 | 1,665 | 890 |
| Madhya Pradesh | Indore | Indore | Other | 722 | 1,616 | 114 |
| Madhya Pradesh | Indore | Indore | White | 1,388 | 1,388 | 114 |
| Madhya Pradesh | Shajapur | Sajapur | Onion | 559 | 1,275 | 100 |

- All five are byte-identical in the existing cleaned data (`source_row` 168005, 168003, 131990, 131988, 97323), where Phase 5 already flags them as `modal_outside_range`.
- They are therefore **source values, not parsing errors**. The prices arrive as clean numeric strings.
- Potato has 2 and Wheat 18 on the same day.
- The harness now reports them as `source_flags` and no longer treats them as malformed responses. No values are altered or dropped; the Phase 5 rules handle them downstream.

**Remaining uncertainty [U]:**
- Only 4 commodity-days on 2 dates were tested.
- Completeness is shown against the API's own totals and by independent partitions agreeing. No independent ground truth exists for dates after 2024-02.
- Throttling and rate limits over thousands of calls are unknown.
- Commodity-day totals for 2024-02 → 2026-10 are assumed below 5,000; the acceptance rule enforces this per call.

### 5.6 Authorised extraction pilot (2026-10-24): passed

**Inputs and outputs:**
- Script: `Code/candidates/datagov_pilot.py`. Tests: `Code/tests/test_datagov_pilot.py`.
- Log: `Processed_Data/candidates/datagov_pilot/20261023T233559Z.json`, plus `_crop_days.csv`.
- Raw responses, key redacted: `Dataset_Candidates/datagov_pilot/20261023T233559Z/` (17 MB).

**Method:**
- One call per crop-day: `limit=5000`, `offset=0`, no sort.
- Record identity is the canonical JSON of all returned fields (sorted keys), so no comparison depends on row order.
- A response is accepted only if count = API total = distinct records and total < 5,000.
- Retries: at most 3 attempts (waits of 5 s and 15 s), on transport failure, HTTP 5xx or a non-JSON body.
- The run stops at once on HTTP 401/403/429 or a rate-limit or key message.
- Hard budget: 160 calls.

**Date selection (deterministic; `select_dates`):**
- 10 crop-days per crop, all between 2024-02-03 and 2026-10-20.
- 8 are evenly spread and staggered by crop. They cover every weekday, including Saturdays and Sundays.
- 2 are high-volume days per crop, chosen from evidence: the largest API total seen (Onion 2025-06-18), and the peak months and weekdays in our 2022–2023 data (Potato in February, Wheat in April, Mondays).

| Crop | Dates (spread …; high-volume) | API totals |
|---|---|---|
| Onion | 2024-02-03, 2024-06-23, 2024-11-12, 2025-04-02, 2025-08-22, 2026-01-10, 2026-06-01, 2026-10-20; 2024-06-17, 2025-06-18 | 575, 455, 786, 830, 819, 481, 739, 530; 420, 829 |
| Potato | 2024-02-04, 2024-06-22, 2024-11-11, 2025-04-01, 2025-08-21, 2026-01-09, 2026-05-31, 2026-10-19; 2025-02-17, 2026-02-16 | 354, 612, 727, 721, 704, 579, 467, 625; 845, 592 |
| Wheat | 2024-02-05, 2024-06-21, 2024-11-10, 2025-03-31, 2025-08-20, 2026-01-08, 2026-05-30, 2026-10-18; 2024-04-15, 2025-04-21 | 390, 668, 150, 419, 774, 645, **1,158**, 342; 797, 1,145 |

**Results [V]:**

| Check | Result |
|---|---|
| Calls | **136 of 160**, all HTTP 200, 0 retries, 0 rate-limit or access responses |
| Duration and size per request | 0.32–2.51 s (median 0.72 s); largest response 470 KB |
| Crop-days passed | **30 / 30**: every fetch had count = total = distinct, 0 duplicates, 0 malformed records |
| Repeated fetches | 30 / 30 identical record sets |
| Records | 19,178 per fetch set (min 150, max 1,158; all below the 5,000 limit) |
| State partitions | Onion 2025-06-18: 29 states queried, 22 non-empty, 829 = 829. Potato 2026-02-16: 30 queried, 25 non-empty, 592 = 592. Wheat 2025-04-21: 17 queried, 14 non-empty, 1,145 = 1,145. All with 0 missing, 0 extra and 0 overlap; partition totals sum exactly to the coarse total |
| Source flags (modal outside [min, max]) | Onion 6, Potato 2, Wheat 161 |

**About the Wheat source flags.** Wheat's 161 are concentrated in Madhya Pradesh (for example, 83 of 84 on 2024-04-15), with modal prices both below the minimum and above the maximum. That is the pattern Phase 5 already flags in the existing data. No flags appear on any pilot day from 2024-11 onward. Why is not established **[U]**: it could be a validation rule introduced at the Agmarknet 2.0 go-live, or chance.

**What the pilot does and does not show:**
- It shows the single-call method is **repeatable** and **internally consistent** on 30 crop-days spread over the window and on 3 high-volume partitions.
- It does **not** prove completeness for every date. The API's own totals are not independent evidence.
- After 2024-02 there is no external reference to check against. The only independent check, 100% modal agreement with the existing data, is limited to dates ≤ 2024-02-02 (§5.5).

---

## 6. Proposed Migration Plan (requires approval; nothing below has been executed)

**Expected impact.** The overlapping history will **not** change. The gains are:
1. prices from 2024-02-03 to the present, for a genuinely unseen evaluation window;
2. Wheat production context for two more years;
3. optionally, observed rainfall for more districts.

Arrivals after 2024-02 stay unavailable unless DMI grants access.

| Step | Action | Writes to | Gate |
|---|---|---|---|
| M0 | Decide the questions in §8 (U1–U5); register a personal data.gov.in key | — | **User** |
| M1 | Bulk pull A1 for Onion/Potato/Wheat, 2024-02-03 → 2026-10-23 (994 days), **one call per commodity-day, no offset paging** (§5.5): 2,982 calls, or 5,964 if every day is fetched twice | `Dataset_Candidates/datagov_variety_prices/<date>/` (raw JSON) | Per call: count = total = distinct and total < limit; the two fetches of a day must be set-equal; manifest hashes |
| M2 | Market crosswalk, old → new names: exact → suffix rule → reviewed aliases, in the same style as `Code/integration/district_aliases.csv` | `Processed_Data/v2/market_crosswalk.csv` | Manual review of every non-exact match; unmatched markets become new series, never force-matched |
| M3 | Normalise to the Phase 4 canonical schema (`arrivals_tonnes` = NaN, `grade` kept as an extra column); apply Phase 5 rules R01–R14 by calling the existing `run_cleaning` logic on the new rows only | `Processed_Data/v2/mandi_prices_2024plus_<crop>.parquet` | Row reconciliation (raw = clean + removed), as in Phase 5 |
| M4 | (Optional) Open-Meteo for the same 46 points, 2023-01-01 → cut-off | `Processed_Data/v2/weather/` | Same validator (`Code/weather/validator.py`) |
| M5 | UPAg Wheat 2023-24 / 2024-25, with yield converted kg/ha → t/ha | `Processed_Data/v2/upag_wheat_apy.csv` | Unit assertion against DES on the overlap |
| M6 | Write a v2 data manifest (inputs, hashes, counts, coverage) | `Processed_Data/v2/manifest.csv` | — |

Phase 4–10 outputs, frozen manifests and `Dataset/` are read-only throughout.

### 6.1 Staged plan for M1 (proposed after the §5.6 pilot; **not authorised**)

**Window:** 2024-02-03 → 2026-10-20, which is 991 days × 3 crops = 2,973 crop-days.

| Stage | Scope | Calls | Checkpoint before the next stage |
|---|---|---|---|
| S1 | 2024-02-03 → 2024-04-30 (88 days; includes the Wheat procurement peak), every crop-day fetched **twice** + 1 state partition (~30) | ≈ 560 | 100% pass; repeat sets identical; daily totals plotted for gaps or zero days; user approval |
| S2 | 2024-05-01 → 2025-11-06 (the pre-go-live remainder, 555 days), twice | ≈ 3,510 | As S1, per quarter, with 1 state partition per quarter (~30 each) |
| S3 | 2025-11-07 → 2026-10-20 (post-go-live, 348 days), twice | ≈ 2,210 | As S1, plus a look at the grade and market-name mix |
| **Total** | 2,973 crop-days × 2 fetches + about 9 partitions | **≈ 6,220** | — |

A lighter option is one fetch per crop-day plus a 10% repeat sample: about 3,540 calls. Decide after S1, from S1's evidence.

**Restartability:**
- **Manifest:** one row per crop-day: commodity, date, API total, record-set SHA-256 (sorted canonical records), status and calls.
- **Restart:** skips crop-days already marked `pass`.
- **Raw files:** named by crop and date, written to a temporary file then renamed, so an interrupted run never leaves a half-written file.
- **Budget:** a hard call budget per stage. The run stops at once on 401/403/429 or a rate-limit message, with no unbounded retries.
- **Zero-record days:** a crop-day returning 0 records counts as a valid response, but it is listed for review against neighbouring days. It could be a holiday or an outage.
- **Safety:** nothing is merged into `Processed_Data` outside `candidates/` until migration steps M2–M3 are approved.

**Implementation:** `Code/candidates/datagov_extract.py`, with tests in `Code/tests/test_datagov_extract.py`.
- **Approval gate:** only stages listed in `STAGES` can run, and **S1 is the only stage listed**.
- **S1 budget:** 600 calls = 528 fetches + 1 state partition (Wheat 2024-04-15, the in-window peak; about 30 calls) + headroom for transient retries.
- **Raw files:** `Dataset_Candidates/datagov_prices/raw/<crop>/<date>_f{1,2}.json`, written atomically.
- **Records** in `Processed_Data/candidates/datagov_prices/`:
  - `crop_day_manifest.csv`: one row per crop-day, holding the parameters, API total, returned and distinct counts, content SHA-256, retrieval time, status and source flags;
  - `requests.csv`: every attempt, with HTTP code, duration, bytes and outcome;
  - `stage_<S>_report_<run>.json`: the stage summary.
- **Resume:** a crop-day is reused only if it is `pass`, its parameters match, and both raw files re-hash to the manifest's content hash.
- **Failures:** a crop-day that fails validation stops the run and stays visible as `fail`. It becomes `blocked`, needing a manual decision, after 3 failed runs.
- **Zero-record days:** recorded as `zero_review`, and they hold back stage acceptance until reviewed.

### 6.2 Stage S1 result (run `20261023T234936Z`, 2026-10-24): **accepted; S2 not authorised**

**Inputs and outputs:**
- Report: `Processed_Data/candidates/datagov_prices/stage_S1_report_20261023T234936Z.json`.
- Manifest: `crop_day_manifest.csv` (264 rows). Request log: `requests.csv` (545 rows).
- Raw data: 106 MB under `Dataset_Candidates/datagov_prices/` (git-ignored, key redacted; a scan for the key found no copies).

**Results [V]:**

| Check | Result |
|---|---|
| Period | 2024-02-03 → 2024-04-30, 88 days × 3 crops = 264 crop-days; the manifest covers the period exactly |
| Calls | **545 of 600**, all HTTP 200, 0 retries, 0 rate-limit or access responses; 0.34–3.0 s per call (median 0.89) |
| Crop-days | **264 / 264 pass**: both fetches with count = total = distinct, identical sets, 0 malformed records, 0 zero-record days |
| Records (one fetch) | Onion 44,821 · Potato 45,657 · Wheat 43,473 = **133,951**. Per day: Onion 185–636, Potato 214–625, Wheat 62–923. The lowest days are Sunday 2024-03-24 and Monday 2024-03-25 (Holi). All far below the 5,000 limit |
| Coverage | Markets (state, market): Onion 877, Potato 850, Wheat 1,118. States: 27 / 26 / 14 |
| Grades | FAQ 133,948, Medium 2, Large 1 (still the pre-relaunch taxonomy) |
| State partition | Wheat 2024-04-15: 17 states queried, 12 non-empty, 797 = 797, 0 missing, 0 extra, 0 overlap |
| Protected data | Phase 8 D-42, Phase 9 D-45 and Phase 10 PQ-1 freezes verify; 55 / 55 raw fingerprints unchanged; 573 protected files byte-identical before and after |
| Overlap with existing data | **None by construction**: S1 starts the day after our data ends (2024-02-02). The overlap evidence is §5.5 (2024-01-17: 100% modal agreement) |

**Source anomaly: Madhya Pradesh Wheat [V; cause U].**
- Modal outside [min, max] in S1: Wheat 3,329 (7.7%, of which Madhya Pradesh 3,313), Onion 286 (Madhya Pradesh 216), Potato 120 (Madhya Pradesh 64).
- In our existing data, Madhya Pradesh Wheat has **0.0% such records every month from 2022 to 2023-11**, then 4.8% (2023-12), 21.7% (2024-01) and 22.6% (2024-02).
- So the change began at the source in December 2023. It is not seasonal and not an extraction artefact.
- Flagged Wheat modals fall both below the minimum (1,468) and above the maximum (1,861), with a median deviation of 3.2% of the maximum.
- The pilot saw none from 2024-11 onward.
- Records are kept unaltered and flagged. The policy is now defined in §6.4.

### 6.3 Stage S2 result (run `20261024T005524Z`, 2026-10-24): **accepted; S3 not authorised**

**Inputs and outputs:**
- Report: `stage_S2_report_20261024T005524Z.json`.
- Manifest: now 1,929 rows (S1 + S2). Request log: `requests.csv` (S2: 3,515 rows).
- Raw data: `Dataset_Candidates/datagov_prices/` holds 983 MB for S1 + S2.

**Pre-run checks [V]:**
- The S2 definition is checked against its approved count (555 days × 3 = 1,665 crop-days) before any request.
- S3 is not in `STAGES`, and the runner refuses it.
- The freezes and all 573 protected-file hashes verified before the run.

**Results [V]:**

| Check | Result |
|---|---|
| Period and crops | 2024-05-01 → 2025-11-06 for Onion, Potato and Wheat; the manifest covers the period exactly (555 dates × 3) |
| Calls | **3,515 of 3,600**: 3,509 HTTP 200 plus **6 transport timeouts** (HTTP 0, about 21 s each), each recovered on its second attempt; 0 rate-limit or access responses; median 0.93 s, 99th percentile 2.7 s, max 57 s |
| Crop-days | **1,665 / 1,665 pass**: count = total = distinct on both fetches, identical sets, 0 malformed records, 0 zero-record days, 0 failed or blocked |
| Records (one fetch) | Onion 398,601 · Potato 374,101 · Wheat 333,351 = **1,106,053**. Per day: Onion 240–1,657, Potato 249–1,372, Wheat 70–1,466 |
| State partitions (7 of 7 exact; 0 missing, extra or overlapping) | Onion 2024-06-12: 616 · Potato 2024-08-14: 665 · Wheat 2024-11-13: 690 · Onion 2025-02-12: 742 · Wheat 2025-04-16: 1,241 · Potato 2025-08-13: 713 · Onion 2025-10-15: 850 |
| S1 evidence | All 546 S1 raw and report files byte-identical; the 264 S1 manifest rows and 545 S1 request rows are unchanged |
| Protected data | Freezes verify; 55 / 55 raw fingerprints unchanged; 573 protected files identical before and after |
| API key | A scan of all saved outputs found no copies |

**Investigated: unexpectedly large days, 2025-11-01 → 11-06 [V].**
- The five largest crop-days all fall here. For example, Onion 2025-11-03 has 1,657 records against a median of 765.
- The cause is **double reporting during the Agmarknet 2.0 cut-over, six days before the documented 2025-11-07 go-live.**
  - The same market is published under its old name and as "<name> APMC".
  - On 2025-11-03 there are 797 / 545 / 734 such pairs (Onion / Potato / Wheat, matched on state, base name, variety and grade), with 98.8–100% identical modal prices.
  - By 2025-11-06 old names have almost disappeared (3 / 3 / 1 pairs). No "APMC"-suffixed names exist before 2025-11-01.
- The records are distinct by identity, so the extraction kept them faithfully. They must be resolved by the market crosswalk (M2) **before** weekly targets are built, never by name similarity alone.

**Small days:** Wheat Sundays and holidays (70–104 records). These are expected and are not zero-record days.

### 6.4 Price-anomaly policy for the new feed (`candidate-price-policy-v1`)

**Implementation:** `Code/candidates/price_policy.py`, with tests in `Code/tests/test_price_policy.py`.
- **Input:** only crop-days marked `pass`.
- **Output:** `Processed_Data/candidates/datagov_prices/analytical_v1/`, containing the parquet tables (git-ignored, regenerable), `anomaly_rates_by_crop_state_month.csv`, `policy_effect_by_crop*.csv` and `policy_summary.json`.
- No frozen output is read for writing or changed.

**Rules, aligned with Phase 5 (`Code/cleaning/pipeline.py`):**
- **Phase 5 helper reused:** the `value_status` function.
- **Source fields:** all source fields are kept as the strings received. Parsed prices use the Phase 5 column names.
- **R04:** a zero, negative or non-finite price becomes missing in the parsed copy only.
- **R03:** the same key (state, district, market, commodity, variety, grade, date) with different values sets `key_conflict`.
- **R07:** min > max sets `min_gt_max`.
- **R08:** modal outside [min, max] sets `modal_outside_range`.
- **Flag columns:** `price_anomaly` records the reason: `modal_missing` > `key_conflict` > `min_gt_max` > `modal_outside_range` > `none`.
- **Exclusion:** only `usable_modal_price` (reason `none`) may feed forecasting targets. No record is deleted or corrected.
- **Not yet applied:** R09 (scale error against a trailing reference), until the M3 market history exists.

**Reconciliation [V].** In S1 the raw "modal outside range" counts (Onion 286, Potato 120, Wheat 3,329) exceed R08's counts (216 / 64 / 3,313). Every one of the 70 / 56 / 16 extra records has **max price = 0**, a "not reported" placeholder. That becomes missing under R04, exactly as in Phase 5.

**Result on S1 + S2 [V]:** 1,929 crop-days, 1,240,004 records, 2024-02-03 → 2025-11-06.

| Crop | Records | Usable after the policy | Excluded | of which key_conflict / modal_outside_range / min_gt_max | Markets kept | Weekly market×variety cells lost |
|---|---|---|---|---|---|---|
| Onion | 443,422 | 437,431 | 5,991 (1.4%) | 5,421 / 566 / 4 | 2,228 of 2,228 | 0.29% |
| Potato | 419,758 | 418,527 | 1,231 (0.3%) | 1,156 / 74 / 1 | 2,067 of 2,067 | 0.04% |
| Wheat | 376,824 | 344,890 | **31,934 (8.5%)** | 25,573 / 6,361 / 0 | 2,089 of 2,089 | 1.91% |

Excluded records are concentrated in **Madhya Pradesh**. There, 4.2% of weekly cells are lost for Wheat and for Onion, and 1.4% for Potato. Two source patterns follow each other [V]:
1. **Out-of-range modals:** Madhya Pradesh Wheat at about 19% from 2024-02 to 2024-06, 7.2% in 2024-07, then 0.0% from 2024-08 onward.
2. **Two versions per key:** 97% of Wheat conflicts are in Madhya Pradesh; 12,670 of 12,747 keys have exactly 2 versions, appearing every month from 2024-05. Version modals differ by a median of 0.3% (90th percentile 5.4%) for Wheat and 3.8% (71%) for Onion.

The source has no lot or session field to choose between versions, which is assumption A-18. Phase 5's R03 is therefore followed, but at a far larger scale than in the historical data (106 Wheat conflict rows in Phase 5).

**Decision for M3 [U]:** whether to keep excluding Madhya Pradesh versioned records or use a documented rule such as the median of versions. That rule would change the Phase 5 alignment, so it needs approval. **Decided 2026-10-24:** keep excluding them; the median rule is a sensitivity experiment only (§6.7).

**Policy re-applied to S1 + S2 + S3 [V]:** 2,973 crop-days, 1,990,311 records, 2024-02-03 → 2026-10-20.

| Crop | Records | Usable | Excluded | key_conflict / modal_outside_range / min_gt_max | Weekly cells lost |
|---|---|---|---|---|---|
| Onion | 683,604 | 673,263 | 10,341 (1.5%) | 9,766 / 571 / 4 | 0.22% |
| Potato | 647,268 | 644,180 | 3,088 (0.5%) | 3,007 / 80 / 1 | 0.05% |
| Wheat | 659,439 | 600,587 | 58,852 (8.9%) | 52,488 / 6,364 / 0 | 1.19% |

### 6.5 Stage S3 result (run `20261024T065011Z`, 2026-10-24): **accepted; acquisition complete**

**Pre-run checks [V]:**
- The S3 definition matches the approved count: 348 days × 3 = 1,044 crop-days.
- A test asserts that S1, S2 and S3 are contiguous and non-overlapping, covering 2024-02-03 → 2026-10-20 exactly once.
- The freezes and all 573 protected hashes verified, and all 4,058 S1/S2 evidence files were hashed beforehand.

**Results [V]:**

| Check | Result |
|---|---|
| Period | 2025-11-07 → 2026-10-20; the manifest covers 348 dates × 3 crops exactly. The full manifest now holds **2,973 crop-days, all `pass`** |
| Calls | **2,250 of 2,300** |
| Transient failures | **34 retries**: 33 transport timeouts (about 21 s each; one at 180 s) and 1 HTTP 504. All recovered within the bounded policy; one request needed 3 attempts |
| Rate limits and access | 0 rate-limit or access responses. Latency median 1.59 s, against 0.93 s in S2 |
| Crop-days | **1,044 / 1,044 pass**: count = total = distinct on both fetches, identical sets, 0 malformed records, 0 zero-record days |
| Records (one fetch) | Onion 240,182 · Potato 227,510 · Wheat 282,615 = **750,307** |
| Per-day range | Onion 334–986, Potato 263–926, Wheat 61–1,748. The largest days are Wheat 2026-04-17 → 04-29 (procurement peak); the smallest are Wheat Sundays and holidays (61 on 2026-02-15) |
| State partitions (5 / 5 exact; 0 missing, extra or overlapping) | Wheat 2025-12-10: 653 · Onion 2026-02-11: 679 · Wheat 2026-04-15: 1,715 · Potato 2026-08-12: 801 · Onion 2026-10-14: 782 |
| S1 / S2 evidence | 4,058 files byte-identical; the 1,929 S1/S2 manifest rows are unchanged, with none re-fetched; the S1/S2 request rows (545 / 3,515) are intact |
| Protected data | Freezes verify; 55 / 55 raw fingerprints unchanged; 573 protected files identical |
| API key | A scan of saved outputs found no copies |
| Disk | Raw data 1.6 GB for S1–S3; 97 GB free |

**All stages together:** 6,310 calls; 1,990,311 records per fetch set; 2024-02-03 → 2026-10-20.

### 6.6 Portal cut-over and proposed market mapping (`market_mapping.py`, **proposal only; nothing merged**)

**Code and outputs:**
- Code: `Code/candidates/market_mapping.py`. Tests: `Code/tests/test_market_mapping.py`.
- Outputs in `Processed_Data/candidates/datagov_prices/market_mapping/`:
  - `market_mapping_proposed.csv`: one row per source (state, district, market), with first and last seen, records, crops, grades, era, `canonical_market_id`, `mapping_type`, `effective_from`, evidence JSON, confidence and `review_status`;
  - `ambiguous_candidates.csv`;
  - `grades_by_month.csv`;
  - `mapping_summary.json`.

**Method:**
- A name rule (case and punctuation folded, trailing " APMC" removed) only **generates** candidate pairs inside one state.
- A pair needs independent evidence:
  - the same district;
  - strictly one-to-one;
  - succession: the old name stops by 2025-11-20 and the new one starts on or after 2025-10-18;
  - co-reported records on the same date, crop, variety and grade, with identical modal prices.
- **Confidence:**
  - high = all four, with ≥ 5 co-reported records and ≥ 95% identical;
  - medium = the first three without strong co-reporting;
  - low = anything else, never mapped.
- No row is `approved`. Canonical identity = the pre-relaunch (state, district, market), so post-relaunch series continue the historical ones.

**Inventory [V]:** 5,266 source identities.
- 906 are pre-relaunch only, 1,426 report under the same name throughout, and 2,934 are post-relaunch.
- There are 2,193 candidate pairs:

| Confidence | Pairs | Notes |
|---|---|---|
| high (`proposed`) | 535 | For example: Mapusa → Mapusa APMC (10 co-reported, 100% identical); Sheohar → Sheohar APMC |
| medium (`proposed_needs_review`) | 1,053 | 500 with no co-reported record, 553 with only 1–4. Plausible successions, but the evidence is thin |
| low (`ambiguous_not_mapped`) | 605 | 440 not one-to-one, 187 with a different district, 170 with no succession (they overlap) |
| post-relaunch names with **no** candidate | 798 | For example Ayodhya APMC, Prayagraj APMC, Bengaluru APMC, Roorkee APMC. These look like renames beyond the suffix rule (likely Faizabad, Allahabad, Bangalore); manual review needed |

**Ambiguities to review [V]:**
1. **District reorganisations.** The new portal assigns many markets to newly created districts: for example Pendraroad from Bilaspur to Gourela Pendra Marwahi, Gandai and Kheragarh to Khairagarh Chhuikhadan Gandai, and Baramkela to Sarangarh Bilaigarh. Mapping these needs a district crosswalk (for example LGD codes), not names.
2. **Persistent dual reporting after go-live.** In 165 of the 170 no-succession pairs, the old name keeps publishing alongside the "APMC" name. That is **11,869 co-reported records with 100% identical modal prices**, concentrated in **2026-03 (8,949) and 2026-04 (2,605)**. Examples: Tamil Nadu Uzhavar Sandhai markets, and Ramkrishanpur(Howrah) → Ramkrishanpur(Howrah) APMC. This is a second double-reporting episode, separate from the cut-over window, and needs its own de-duplication rule.
3. **Names differing only in punctuation**, such as AJattihalli versus A.Jattihalli (Uzhavar Sandhai). These are listed, not mapped.

**Cut-over double reporting (2025-11-01 → 11-06) [V].** Under the high and medium mappings, **6,118 usable records** are exact duplicates of a record under the other name (same crop, variety, grade, date and prices):

| Date | 11-01 | 11-02 | 11-03 | 11-04 | 11-05 | 11-06 |
|---|---|---|---|---|---|---|
| Duplicate records | 1,506 | 885 | 1,757 | 1,445 | 518 | 7 |

These must be de-duplicated after mapping, never left as two series or two records in one weekly median.

**Effect on weekly aggregation [V].** Usable records only, at the D-33 grain (crop, state, district, market, variety; weekly median):

| Measure | Source names | With proposed high and medium mappings |
|---|---|---|
| Series | 17,530 | 13,620 (3,910 fragments re-joined) |
| Weekly cells, whole period | 433,791 | 430,328 |
| Weekly cells, cut-over weeks (2025-10-27 → 11-09) | 10,186 | 6,723 (−34%) |

Without mapping, almost every market active across the relaunch becomes two short series: one ending 2025-11-06, one starting 2025-11-01.

**Grade changes [V]:**
- Up to 2024-12, only FAQ appears in this sample of months.
- Local and Non-FAQ appear from 2025-01.
- After the relaunch, Grade A/B/C, Grade Range-1/2/3, Large, Medium and Small appear. In 2026-02: FAQ 21,224, Local 14,472, Non-FAQ 4,367, Medium 3,268, Grade A 1,249 and others.
- Market-variety-days with **more than one grade**: 0% to 2024-12, 5–7.5% in 2025-02 → 2025-10, and 2–4% after the relaunch.
- The D-33 series key has **no grade**, so these grades would be pooled into one weekly median.

**Decision needed [U]:**
- pool grades as the historical pipeline does, since grade was almost always FAQ there; or
- restrict targets to one grade (FAQ); or
- add grade to the series key.

**Not done:** no weekly table was built from these mappings and no record was merged. Final weekly figures wait for mapping approval.

### 6.7 Sensitivity experiment design: exclusion versus median of conflicting versions (**design only, not applied**)

- **Primary policy (unchanged):** `candidate-price-policy-v1`. Records with `key_conflict` are excluded from targets.
- **Alternative (sensitivity arm only):** for each conflicting key (state, district, market, crop, variety, grade, date), use the **median modal price of its versions** as one observation.
  - This applies only if every version is otherwise valid: no `modal_outside_range` and no `min_gt_max`.
  - It is flagged `derived_median_of_versions` and never written into the primary analytical tables.
- **Size [V, descriptive]:**
  - Wheat: 52,488 conflicting records in 26,039 keys (Madhya Pradesh 23,870) would add 26,039 observations, but only **+475 weekly cells (+0.3%)**, because most affected market-weeks already have other usable days.
  - Onion: 4,844 keys, +98 cells. Potato: 1,502 keys, +36 cells.
- **Protocol:**
  - The same splits, horizons, features and models as the main price-only experiment.
  - Both arms are fitted and scored on **identical evaluation target rows**: the intersection of cells valid under both arms. Each arm's own extra cells are reported separately.
  - Metrics: MAE and RMSE by crop × horizon, and for Madhya Pradesh against the other states.
  - A paired series-cluster bootstrap of the MAE difference.
  - Decision rule: switch to the median policy only if it does not worsen out-of-sample error on the shared rows and the Madhya Pradesh subgroup shows no bias shift.
  - The test period is used once, after both arms are frozen on validation.
- **Status:** not run. It depends on mapping approval and on the price-only experiment configuration (§7).

### 6.8 Market-identity review (2026-10-24; `identity-rule-v1`; **nothing applied to a final weekly table**)

**Code and outputs:**
- Code: `Code/candidates/identity_review.py`. Tests: `Code/tests/test_identity_review.py` (8 tests).
- Outputs in `Processed_Data/candidates/datagov_prices/identity_review_v1/`:
  - `high_confidence_validation.csv` (all 535 pairs, one row each, with evidence and outcome);
  - `medium_review_sample.csv` and `medium_sample_strata.csv`;
  - `dedup_log.csv`;
  - `faq_coverage_by_crop_year.csv`;
  - `identity_review_summary.json`.

**Task 1: validation of all 535 high-confidence pairs.** Each pair was checked individually.

*Hard checks (any failure means `rejected`):*
1. No many-to-one collision across all high and medium proposals.
2. The old name reports nothing after 2025-11-20.
3. Same-day **min, max and modal** each ≥ 95% identical.
4. Price level: the median modal for the first 28 days of the new name over the last 28 pre-cut-over days of the old name, same crop, lies in [0.5, 2].
5. At least one shared variety.

*Required evidence (any missing means `unresolved`):*
- the same district;
- ≥ 5 same-day records;
- the new name present in the Agmarknet 2.0 official market list, with the same district.

| Outcome | Pairs | Evidence |
|---|---|---|
| `accepted_rule_v1` | **440** | All checks pass. Same-day records: median 8, minimum 5. Min, max and modal agreement **100%** for every accepted pair. All 440 match the Agmarknet 2.0 market list with the same district; 428 also match the legacy `final_data.csv` market list |
| `unresolved` | **81** | The new name is not in the Agmarknet 2.0 market list (44 in Kerala, 15 Maharashtra, 5 Uttar Pradesh, 5 Madhya Pradesh, 12 others). The portal list names markets differently from the data.gov.in feed (for example "Aroor Market" against "Aroor APMC"), so the list cannot confirm them without a further name rule. A state alias Keralam → Kerala was added for lookup only |
| `rejected` | **14** | Price-level discontinuity. Two kinds: (a) **unit scale**: Samana APMC Onion about 34–42 against Samana about 1,500 (looks like Rs/kg); Mapusa APMC includes values such as 13.5 among normal values of about 1,600; (b) a **level drop for Madhya Pradesh Onion** (Mandsaur, Ratlam, Sehore, Ujjain and others; ratio 0.16–0.44) while the same markets' Wheat holds at about 0.96 |

"Accepted" means accepted by a recorded rule, **not approved**. Human sign-off is still required.

**Task 2: stratified medium-confidence sample.**
- **Strata:** 65 cells of state class (the 8 states with ≥ 50 medium pairs, plus "other_states") × overlap bucket (0, 1–2, 3–4 same-day records) × crop relevance (Onion, Potato, Wheat, multi).
- **Rule:** per stratum, max(2, round(0.10 × N)), capped at N. A seeded permutation (**seed 20261024**) is drawn over rows sorted by identity, so the result depends only on the data and the seed.
- **Sample: 160 of 1,053.**
  - Evidence: 89 have same-day price evidence, 71 rest on name and dates only.
  - Overlap: 0 records (71), 1–2 (46), 3–4 (43).
  - Crop relevance: Wheat 67, multi 61, Onion 19, Potato 13.
  - States: 19.
- **District reorganisation stratum:** empty, because medium requires the same district by construction. The reorganisation cases are the 187 low-confidence pairs (§6.6), handled in Task 3.
- **Review file:** gives old and new identities, dates, crops, varieties, grades, the last 3 old and first 3 new usable prices per shared crop-variety, and blank `reviewer_decision`, `reviewer`, `review_date` and `review_notes` columns.
- The other 893 medium pairs **stay unresolved**, whatever the sample shows.

**Task 3: official identifiers [V].**
- **Legacy Agmarknet market codes do not survive the relaunch.**
  - `final_data.csv` has 4,151 markets with `Market_code`; the Agmarknet 2.0 filter metadata has 4,176 markets with `id` and `district_id`.
  - Of the 3,062 code values present in both, only 39 name the same market. Example: legacy 570 = Amalner (Maharashtra), Agmarknet 2.0 id 570 = "APMC Achalpur".
  - So no official identifier links old and new names. Each list gives only its own portal's district assignment, which is used above as corroboration.
- **LGD district codes:**
  - Source: Local Government Directory, Ministry of Panchayati Raj; the [India Data Portal mirror](https://ckandev.indiadataportal.com/dataset/lgd-codes) (ODC-By, file dated 2023-10-20; the official site [lgdirectory.gov.in](https://lgdirectory.gov.in/) responds).
  - Content: 765 districts with LGD, Census 2001 and Census 2011 codes. It confirms the new Chhattisgarh districts behind the ambiguous pairs: Gaurella Pendra Marwahi (734), Khairgarh Chhuikhadan Gandai (759), Manendragarh Chirimiri Bharatpur (760), Sarangarh Bilaigarh (763), all with Census 2011 code 0.
  - **Limitation:** it carries **no parent-district or change history**, so it cannot show which market moved where.
  - The feed spells these districts differently ("Gourela …", "Khairagarh …").
  - Saved under `Dataset_Candidates/lgd_idp/2026-10-24/`.
- **Not found:** an official Agmarknet market master with stable codes across the relaunch, or an Agmarknet-to-LGD crosswalk.
- **Research mapping:** CEDA Ashoka maps Agmarknet markets to Census 2011 districts ([README](https://agmarknet.ceda.ashoka.edu.in/README.html)). It is a research product and was unreachable from this machine.
- **Conclusion:** district-reorganisation pairs **stay separate identities** (unresolved) until an official parent-child record or DMI confirmation is obtained.

**Task 4: duplicate and cut-over audit [V].**
- **De-duplication applies only across the 440 accepted identities.**
  - Key: canonical market, crop, variety, grade and date.
  - Equivalence fields: min, max and modal (numeric).
  - Tie-break: the record under the canonical (old) name, then the smallest `source_id`, then the smallest `record_ref` (a SHA-256 of the 11 source fields). It is independent of row order (tested).
  - The log has one row per group: all record references, source names, the retained reference, the rule and the reason.
- **Results:**
  - 3,889 groups. **3,873 records are removed from the analytical view** (flagged, not deleted): 917 / 654 / 1,034 / 916 / 345 / 7 on 2025-11-01 → 11-06.
  - **16 groups (48 records)** have differing values and become `identity_conflict`, all excluded from targets. Examples: Damoh Wheat Non-FAQ 2025-11-03; Indore Onion Non-FAQ 2025-11-01.
- **Not de-duplicated:**
  - March–April 2026 dual reporting (§6.6): its identities are not established.
  - The 2,245 cut-over duplicates under medium identities (6,118 − 3,873) stay as separate series pending review.
  - If the 158 one-to-one dual-reporting pairs were established, 12,304 records would be removed, and weekly cells would fall from 433,791 to 431,168 (the parallel series collapse). This is unresolved and **not applied**.
- **Unit-scale records [V].** Usable modals under 100 Rs/q occur both before (Onion 1,813, Potato 1,568) and after the relaunch (Onion 484, Potato 502, Wheat 5). They are concentrated in a few markets (Rania APMC, Patti APMC, Samana APMC), about 0.1–0.4% of records. A scale-error rule (Phase 5 R09 analogue) is therefore **required** before targets (§6.9).

**Task 5: grade policy [V].**
- **All grades are preserved.** De-duplication never crosses grades (tested).
- **FAQ coverage collapses after 2024:**

| Crop | FAQ share of usable records, 2024 / 2025 / 2026 | FAQ markets 2026 (of all markets) |
|---|---|---|
| Onion | 85.6% / 58.6% / **33.9%** | 698 of 1,767 |
| Potato | 87.0% / 65.4% / **40.8%** | 693 of 1,611 |
| Wheat | 99.9% / 76.4% / 70.7% | 1,246 of 1,753 |

- **Markets leaving FAQ.** Among markets mostly FAQ before the relaunch and active after it, **110 of 352 Onion, 106 of 353 Potato and 59 of 299 Wheat markets stop being mostly FAQ** after it.
- **Price evidence.** Same market, variety and day, the median price ratio to FAQ is: **Local 1.000** (473 pairs), Medium 1.000 (114), Grade A 1.000 (34), Non-FAQ 0.959 (51,194).
- **Interpretation.** "Local" behaves like a relabelled FAQ, but that is evidence for review, not a rule; it is **not pooled**.

**Series designs** (usable, de-duplicated records; key = crop, canonical market, variety [, grade]):

| Design | Onion: series / weekly cells / series < 8 weeks | Potato | Wheat |
|---|---|---|---|
| Pooled all grades (D-33 equivalent) | 4,019 / 140,225 / 1,169 | 3,986 / 131,519 / 1,263 | 7,943 / 160,070 / 4,049 |
| **FAQ-only (proposed primary)** | 2,555 / **89,572** / 856 | 2,442 / 87,676 / 830 | 7,103 / 138,514 / 3,712 |
| Grade-aware | 5,929 / 146,905 / 2,558 | 5,751 / 137,060 / 2,606 | 10,438 / 177,511 / 5,748 |

- **FAQ-only** keeps the historical target definition (the pre-2024 data are almost all FAQ). But it loses **36% of Onion and 33% of Potato weekly cells** against pooling, concentrated in 2025–2026. About 30% of continuing Onion and Potato markets drop out after the relaunch: a comparability break in **coverage**, not in price level.
- **Grade-aware** avoids pooling but fragments heavily: about 43–55% of series are shorter than 8 weeks.

### 6.9 Proposed versioned analytical dataset contract: `candidate-prices-v1` (**specification only; not built**)

**Location:** `Processed_Data/candidates/datagov_prices/dataset_v1/`. It is separate from production, and the Phase 4–10 outputs and `Dataset/` are never written.

| Step | Input → output | Rule | Provenance kept |
|---|---|---|---|
| 1. Raw | Manifest `pass` crop-days → raw records | First fetch per crop-day; record identity = canonical JSON | Raw file path, crop-day content SHA-256, `retrieved_utc`, `record_ref` |
| 2. Anomaly flags | → `price_anomaly`, `usable_modal_price` | `candidate-price-policy-v1` (§6.4: R03, R04, R07, R08) | All 11 source fields as strings; parsed copies |
| 3. Scale check | → `price_scale_flag` | **New, required:** Phase 5 R09 analogue (modal against a trailing crop-national median; ≥ the Phase 5 scale ratio means `scale_error_suspected`, excluded). Thresholds fixed on data ≤ 2024-04-30 (S1) only | Ratio and reference stored |
| 4. Identity | → `canonical_id`, `source_id`, `identity_status` | Only human-approved mappings (initially at most the 440 `accepted_rule_v1` after sign-off). Everything else keeps its own `source_id` as `canonical_id`, with `identity_status` set to `unresolved` or `own` | Mapping row, evidence JSON, rule version |
| 5. Exact duplicates | → `dedup_status`, `dedup_group` | §6.8 Task 4: exact equality of min, max and modal under an approved identity; deterministic tie-break; conflicts set to `identity_conflict` and excluded | `dedup_log.csv` |
| 6. Grade selection | → `target_subset` | Primary: `Grade == FAQ`. Secondary: pooled all grades and grade-aware, reported separately. Grades are never merged silently | `Grade` as published |
| 7. Weekly aggregation | → `weekly_<design>_<crop>.parquet` | Key (crop, canonical_id, variety[, grade], week Mon–Sun); target = median of `usable_for_target` modals; counts of records, days and grades per cell | Contributing `record_ref` count and the first and last date per cell |
| 8. Model-ready | → origins and targets | As D-38/D-40: origin ≤ cut-off, h = 1/2/4 weeks, features from data ≤ origin only. Transformations are fitted on the training window. Price-only (no arrivals or weather after 2024-02) | Experiment config and manifest (§7) |

**Coverage reporting** for every step, by crop × state × month:
- records and usable records;
- each exclusion reason;
- markets and series;
- weekly cells;
- the share of cells from unresolved identities.

**Unresolved identities** stay as their own series and are reported separately. They are never joined to a history.

**Decisions required before building:**
1. Sign-off of the 440 `accepted_rule_v1` pairs, and a decision on the 14 rejected and 81 unresolved.
2. Completion of the 160-pair medium review (`reviewer_decision`).
3. The March–April 2026 dual-reporting rule.
4. Primary grade design: FAQ-only, which loses about a third of 2025–26 Onion and Potato cells, against an evidence-based FAQ + Local equivalence or a pooled design.
5. Scale-check (step 3) thresholds.
6. The 2023 holdout question (U3).

### 6.10 Recorded decisions, open questions and the build contract (2026-10-24; **build not started**)

**Code and outputs:**
- Code: `Code/candidates/candidate_decisions.py`. Tests: `Code/tests/test_candidate_decisions.py` (6 tests).
- Outputs in `Processed_Data/candidates/datagov_prices/decisions_v1/`:
  - `mapping_decisions.csv`;
  - `medium_review_worksheet.csv`;
  - `grade_experiments.csv`;
  - `decisions_summary.json`;
  - `candidate_prices_v1_contract.json`.

**1. Mapping decisions (recorded).** Mapping version `candidate-market-map-v1`.

| Decision | Pairs | Scope |
|---|---|---|
| `approved_candidate_experiment` | 440 | `accepted_rule_v1` pairs only. Approved by the project owner on 2026-10-24 **for `candidate-prices-v1` only, not production**. Evidence retained per row |
| `separate_rejected` | 14 | Own identities |
| `separate_unresolved` | 81 | Own identities |
| `separate_pending_review` | 1,053 | Medium pairs, including the 160 sampled; own identities until reviewed individually |
| `separate_not_mapped` | 605 | Low pairs |

The approved set is asserted one-to-one in code. No identity is inferred from matching prices.

**2. Medium review worksheet:**
- **Reproducibility:** the 160-row sample was re-drawn from the scored pairs with seed 20261024 and is **identical** to the saved sample.
- **File:** `medium_review_worksheet.csv` has columns `review_id` (MR001–MR160), the old and new identities, dates, record counts, crops, the same-day overlap and identical share, evidence type, stratum, varieties, grades and price evidence.
- **Columns left blank** for a person: `decision` (ACCEPT / REJECT / UNSURE) and `reason_code` (same_market_renamed / different_market / price_evidence_conflicts / district_question / insufficient_evidence), plus reviewer, date and notes.

**How results may be used:**
- Only reviewed pairs marked ACCEPT become approved, individually.
- For the 893 unreviewed pairs, the sample only estimates the error rate per stratum. For example, 0 rejections among k reviewed gives a 95% upper bound of about 3/k.
- That estimate can direct where to review next. **It never approves unreviewed pairs.**

**3. Duplicate policy (recorded):**
- The existing exact-duplicate handling and its provenance are kept (§6.8, Task 4).
- March–April 2026 dual reporting stays unresolved.
- Values are never averaged, and records are never de-duplicated across grades (tested).

**4. Grade designs (three separate candidate experiments; grade always a column).**

These figures use only usable records after de-duplication under the 440 approved pairs and the scale rule. Grade labels are never changed.

| Design | Crop | Series | Markets | Weekly cells 2024 / 2025 / 2026 | Pre-relaunch series continuing after it |
|---|---|---|---|---|---|
| FAQ-only | Onion | 2,552 | 1,587 | 39,282 / 33,377 / 17,776 | 301 of 1,479 (20.4%) |
| FAQ-only | Potato | 2,440 | 1,547 | 36,998 / 33,224 / 18,351 | 297 of 1,349 (22.0%) |
| FAQ-only | Wheat | 7,102 | 2,461 | 44,004 / 45,309 / 50,216 | 608 of 2,959 (20.5%) |
| FAQ + Local | Onion | 3,661 | 2,455 | 43,603 / 47,642 / 36,066 | 507 of 1,740 (29.1%) |
| FAQ + Local | Potato | 3,629 | 2,245 | 40,947 / 42,840 / 34,754 | 356 of 1,600 (22.2%) |
| FAQ + Local | Wheat | 7,431 | 2,683 | 44,087 / 46,228 / 55,500 | 628 of 2,968 (21.2%) |
| Pooled | Onion | 4,017 | 2,615 | 43,603 / 52,571 / 45,219 | 558 of 1,767 (31.6%) |
| Pooled | Potato | 3,983 | 2,404 | 40,950 / 47,790 / 43,911 | 401 of 1,626 (24.7%) |
| Pooled | Wheat | 7,942 | 2,908 | 44,087 / 53,258 / 63,905 | 670 of 3,095 (21.6%) |

**Interpretation [V]:**
- **Continuity through the relaunch is low in every design (20–32%).** The main cause is identity, not grade: only 440 old→new pairs are approved, so most series still break at the relaunch.
- Grade choice moves 2026 coverage a lot. FAQ-only keeps 39% (Onion) and 42% (Potato) of pooled 2026 cells.

**FAQ against Local: evidence, not proof [V]:**
- Of 473 same market, variety and day pairs, **only 32.1% are exactly equal** (median absolute difference 0.38%), and 359 of the pairs are in Uttar Pradesh.
- Dominant-grade transitions across the relaunch: FAQ→FAQ 729 markets, Local→Local 295, FAQ→Medium 88, **FAQ→Local 83**, FAQ→Non-FAQ 48, FAQ→Grade A 28.
- So "Local" is **not** shown to be a relabelled FAQ. It is close in price where both are reported, but most switching markets go to other grades.

**5. Scale-error rule (designed on S1 only; thresholds fixed, not tuned):**
- **R09 is kept exactly as Phase 5** (`Code/cleaning/pipeline.py`):
  - the reference is the crop's national daily median modal, trailing 30 days (past and same day);
  - ratio = max over min, max and modal of max(p/ref, ref/p);
  - ≥ 10 is `review` (kept usable); ≥ 50 is `scale_error_suspected` (excluded).
- **New R09u, `unit_scale_suspected` (excluded):** modal ≤ ref/10 **and** 100 × modal inside [ref/3, 3 × ref].
  - The 1/10 is R09's own review threshold.
  - The band [1/3, 3] holds 98.7% (Onion), 95.6% (Potato) and 100% (Wheat) of ordinary S1 modals.
- **Why it was proposed (S1):** low Potato modals sit at a *modal-only* median ratio of 48.8, below R09's 50. Values of 11–31 Rs/q (for example Dewas, Ujjain, Shimoga) look like Rs/kg entries.
  - **Correction (2026-10-24, §6.11):** R09 takes the maximum ratio over min, max **and** modal. Measured with that rule, **61 of the 62 S1 records R09u flags are already excluded by R09**, so in S1 R09u adds just 1 record.
  - Across S1–S3 the fixed rule would add about 594 Onion and 1,184 Potato exclusions beyond R09, nearly all after S1.
- **S1 counts:**
  - R09 review: Onion 477, Potato 79, Wheat 23.
  - R09 scale error: Onion 54, Potato 9, Wheat 14.
  - R09u: Onion 53, Potato 9, Wheat 0.
- **Fixed rule applied to all of S1–S3 (not tuned on it):**
  - R09 scale error: Onion 1,777, Potato 693, Wheat 335.
  - R09u: Onion 2,039, Potato 1,579, Wheat 4.
- **False-positive risks:**
  1. A genuine distress price near ref/10 whose ×100 falls in the band. This is implausible for these crops (it means below about 1.7 Rs/kg), but possible in a glut.
  2. The reference is national, so a remote high-cost market (for example the Nagaland Potato around 11,600) can reach R09 `review`. Review rows stay usable.
  3. Kerala Pothencode (about 10× the reference) stays `review` and usable. A ×10 unit hypothesis is not evidenced and is **not** added.
- Flagged records are kept with their values. Only `usable_for_target` changes.
- **Usable for targets after all rules:** Onion 669,546, Potato 640,940, Wheat 599,349.

**6. U3: the 2023 holdout as input history (unresolved; the build stays blocked) [V].**
- **What the records say:**
  - D-40 (Decision_Log) defines 2023-01-01 → 2024-02-02 as a no-weather holdout.
  - D-42 and D-45 say the 2023+ holdout "stays reserved".
  - Phase 8 §P pre-specifies one run-once evaluation (persistence, plus the Onion h = 1 no-weather HGB) on target Sundays 2023-01-01 → 2024-01-28, "only after … the project owner approves running it".
  - Phase 8 code refuses test and holdout periods.
- **What they do not say:** none states whether **another** experiment may read 2023 as input history (lags, training targets).
- **§P's own precedent:** its refits train on the 2021–2022 test targets, which by then have been evaluated. That suggests a reserved period becomes ordinary history only **after** its evaluation.
- **Conflict:** a price-only experiment from 2024-02 needs about a year of lag history at its first origins. That history is 2023, the reserved holdout.
- **Not assumed.** `assert_no_holdout_inputs` makes the candidate build refuse any input before 2024-02-03 (tested).
- **Options for the owner:**
  - **(a) Run the §P holdout evaluation first** (as pre-specified, run-once). 2023 then becomes ordinary history for later experiments. This is the recommended default, and it follows §P's own precedent.
  - **(b)** Start the candidate experiment from 2024-02-03 with no earlier history. Lags warm up inside 2024, and the first evaluable origins move to about 2025-02.
  - **(c)** Explicitly authorise 2023 as input-only. This is a new decision entry, and it weakens the holdout's independence.

**7. Contract `candidate-prices-v1`:** `decisions_v1/candidate_prices_v1_contract.json`, together with §6.9:
- **Inputs:** manifest-`pass` raw first fetches, 2024-02-03 → 2026-10-20, with no earlier history until U3 is decided.
- **Mapping:** `candidate-market-map-v1`, applying the 440 approved pairs.
- **Anomaly rules:** R03, R04, R07, R08, R09 (unchanged) and R09u.
- **Duplicates:** as in point 3.
- **Grade designs:** `faq_only`, `faq_local` and `pooled`. The primary design is undecided.
- **Weekly key:** (crop, canonical_id, variety[, grade], Mon–Sun week). The target is the median of `usable_for_target` modals. Each cell carries `n_records`, `n_days`, grades and its first and last dates.
- **Coverage reports:** by crop × state × month.
- **Leakage checks:** no input before the start; features ≤ origin; transformations fitted on the training window; thresholds fixed on S1; no production or holdout file opened for writing.

### 6.11 Pre-build blocker check (2026-10-24): **build NOT authorised; stopped before any weekly table**

**U3: unresolved [V].** The evidence:

| Question | Finding | Reference |
|---|---|---|
| What was 2023 reserved for? | One out-of-time check, in a third market regime and without weather, of persistence and of D-42's learned cell (Onion h = 1, no-weather HGB). "It cannot change D-42." | `Phase_08_Modelling_Plan.md` §P (lines 628–663); D-40 (Decision_Log line 271 ff.) |
| Has it been run? | **No.** No `holdout_results.csv`, no holdout freeze manifest and no run-once guard file exist in the repository. D-42: "The 2023+ no-weather holdout is **not** evaluated and stays reserved." D-45: "The 2023+ holdout stays reserved." No later decision entry (the log ends at D-48) mentions it | Decision_Log lines 341 and 414; repository search |
| Does the protocol allow 2023 as later training input? | **Not explicitly.** §P allows its own refits to train on the evaluated 2021–2022 test targets. That is a precedent, not a rule for 2023, and it is silent on other experiments using reserved data | §P "Refits" |
| Effect of reuse | Reading 2023 inputs in a new experiment does not change the frozen D-42/D-45 artefacts (they are verified by hash). But data that a still-pending, pre-registered evaluation depends on would then shape a new experiment's design and validation, which weakens §P's "independent" check. Model selection in the new experiment would be informed by the holdout period | — |

**Conclusion:** the protocol is ambiguous. **The guard is kept** (`CANDIDATE_START = 2024-02-03`, `assert_no_holdout_inputs`), and the build waits for a decision.

**Decision records verified in the files:**
- **Recorded:**
  - 440 approved mapping pairs (`mapping_decisions.csv`; one-to-one asserted; candidate scope);
  - 14 rejected, 81 unresolved and 605 low kept separate;
  - March–April 2026 dual reporting kept separate;
  - **primary grade design FAQ-only**, with FAQ + Local and pooled as sensitivity experiments (recorded from the 2026-10-24 instruction).
- **Not recorded:**
  - **medium review**: 0 of 160 worksheet decisions; all 1,053 medium pairs stay separate, which does not block the build;
  - **R09u**: present only as a proposal. `R09U_APPROVED = False`, so R09u is computed for evidence but excludes nothing (tested).

**R09u evidence** (`decisions_v1/r09u_s1_evidence.csv`, S1 only): 62 records.
- Onion 53: 44 at Kochas (Balthari), Bihar; 8 at Shimoga.
- Potato 9: 7 at Shimoga; 1 each at Dewas and Ujjain.
- 61 are already excluded by R09 (`scale_error_suspected`); 1 is R09 `review`.
- With R09u inactive, usable-for-target counts are Onion 670,140, Potato 642,124 and Wheat 599,349.

**Approval checklist** (`decisions_v1/approval_checklist.csv`):

| # | Approval | Status | Options | Recommended default |
|---|---|---|---|---|
| 1 | **U3: 2023 as input history** | pending, **blocks the build** | (a) approve and run the §P holdout evaluation first, then decide separately whether 2023 may become history; (b) build from 2024-02-03 with no earlier history (first evaluable origins about 2025-02); (c) a new decision entry allowing 2023 as input only | (b) for this candidate build, which needs no reserved data; (a) separately if a 2023 history is wanted later |
| 2 | **R09u activation** | pending, **blocks the build** | approve as designed; reject (R09 only); or revise | Approve: in S1 it adds 1 exclusion; across S1–S3 it removes about 1,800 likely Rs/kg Onion and Potato values that R09 keeps |
| 3 | Medium review (160 rows) | pending, does not block | fill in the worksheet | Can follow the build; unreviewed pairs stay separate |
| 4 | Primary grade design | recorded | — | — |
| 5 | Mapping (440) | recorded | — | — |
| 6 | Dual reporting kept separate | recorded | — | — |

**To record an approval:**
- **U3:** add a decision entry (for example D-49b or D-50) stating the boundary.
- **R09u:** a decision entry plus `R09U_APPROVED = True`, made by or for the owner.

The build stays blocked until items 1 and 2 are recorded.

### 6.12 `candidate-prices-v1` build (D-50, 2026-10-24): **built and validated; not merged; no model trained**

**Decision record:** D-50 (Decision_Log) records all six items. `candidate_prices_v1_contract.json` cites D-50 for each approval.

**Code and outputs:**
- Code: `Code/candidates/build_candidate_prices.py`. Tests: `Code/tests/test_build_candidate_prices.py` (8 tests).
- Outputs in `Processed_Data/candidates/datagov_prices/dataset_v1/`:
  - `records_<crop>.parquet`: every record with `record_ref`, its provenance and its flags;
  - `weekly_<design>.parquet` and `model_table_<design>.parquet`;
  - `dedup_log.csv`;
  - `stage_counts.csv`;
  - `coverage_by_design_crop_year.csv`;
  - `build_report.json`;
  - `build_manifest.json` (input and output hashes).
- The parquet files (121 MB) are git-ignored and regenerable.

**Invariants [V]:**
- **Reproducible:** two full runs produced **byte-identical outputs** (all 9 files' SHA-256 equal).
- **Traceable:** 25 / 25 sampled weekly cells were recomputed exactly (median, `n_records`, `cell_refs_sha`) from the records table.
- **Date guard:** the first record is 2024-02-03, with no earlier row read. Weekly cells cover complete Monday–Sunday weeks 2024-02-05 → 2026-10-12 (Phase 8 `week_start`). Partial-week records are kept but not aggregated: Onion 2,009, Potato 2,136, Wheat 1,379.
- **R09u:** disabled. Flagged for evidence only: Onion 2,039, Potato 1,579, Wheat 4; none excluded.
- **Grades and identities:** grade labels unchanged; 440 approved one-to-one mappings (asserted); no 2023 holdout read; price-only (asserted).

**Incident and fix:**
- Appending D-50 first broke the **Phase 10 PQ-1 freeze check**. D-48 was the last entry, and the freeze hashes each decision up to the next `### ` heading, so the extra blank line before D-50 changed D-48's hashed text.
- Fixed by removing that blank line, so D-46 to D-48 are byte-identical to HEAD under the freeze's own extraction rule. No protected data or check was changed.
- Added `test_new_decision_entries_keep_the_phase8_to_10_freezes_valid`, which verifies all three freezes on the real artefacts.

**Record counts by stage [V]:**

| Stage | Onion | Potato | Wheat |
|---|---|---|---|
| 1 Raw (manifest `pass`, first fetch) | 683,604 | 647,268 | 659,439 |
| 2 After anomaly policy (usable) | 673,263 | 644,180 | 600,587 |
| 3 After R09 (scale errors excluded; review kept) | 671,550 (−1,777 scale; 12,590 review kept) | 643,552 (−693; 3,229) | 600,400 (−335; 245) |
| 4–5 After approved identities and exact duplicates | 670,140 (−1,407 duplicates, −9 conflicts) | 642,124 (−1,428, −0) | 599,349 (−1,038, −39) |
| 6 FAQ-only, complete weeks | 398,070 | 414,103 | 480,876 |
| 6 FAQ + Local | 594,114 | 567,096 | 503,908 |
| 6 Pooled | 668,146 | 640,014 | 598,016 |

**Anomaly exclusions in total:**
- key_conflict: Onion 9,766, Potato 3,007, Wheat 52,488;
- modal_outside_range: 571 / 80 / 6,364;
- min_gt_max: 4 / 1 / 0;
- R09 scale error: 1,777 / 693 / 335.

**Identities [V]:** 5,266 source identities.

| Status | Identities | Records | Usable records |
|---|---|---|---|
| Approved mapping (old + new names) | 880 | 782,892 | 748,743 |
| Own (never a candidate pair) | 1,138 | 166,625 | 164,490 |
| Pending review (medium) | 2,106 | 551,376 | 520,843 |
| Not mapped (low) | 952 | 345,293 | 341,349 |
| Unresolved | 162 | 111,308 | 110,086 |
| Rejected | 28 | 32,817 | 26,102 |

So about 60% of usable records sit in identities whose history across the relaunch is **not** joined.

**Weekly coverage (cells / series / markets) [V]:**

| Design | Crop | 2024 | 2025 | 2026 (to 10-18) |
|---|---|---|---|---|
| **FAQ-only (primary)** | Onion | 38,792 / 1,315 / 1,005 | 32,675 / 1,767 / 1,266 | 17,215 / 1,100 / 697 |
| | Potato | 36,481 / 1,189 / 954 | 32,549 / 1,747 / 1,255 | 17,700 / 1,084 / 692 |
| | Wheat | 43,810 / 2,443 / 1,307 | 44,606 / 3,160 / 1,710 | 49,166 / 4,583 / 1,246 |
| FAQ + Local | Onion | 43,264 / 1,566 / 1,254 | 46,799 / 2,374 / 1,754 | 34,873 / 2,158 / 1,537 |
| | Potato | 40,615 / 1,429 / 1,190 | 42,048 / 2,201 / 1,639 | 33,610 / 2,104 / 1,382 |
| | Wheat | 43,895 / 2,452 / 1,309 | 45,529 / 3,253 / 1,772 | 54,316 / 4,949 / 1,523 |
| Pooled | Onion | 43,264 / 1,566 / 1,254 | 51,753 / 2,589 / 1,845 | 43,692 / 2,549 / 1,766 |
| | Potato | 40,618 / 1,432 / 1,190 | 47,028 / 2,397 / 1,733 | 42,426 / 2,511 / 1,610 |
| | Wheat | 43,895 / 2,452 / 1,309 | 52,566 / 3,610 / 1,890 | 62,551 / 5,373 / 1,752 |

**Missing weeks [V]:**
- Every one of the 141 complete weeks has cells in every design and crop.
- Per series (FAQ-only): median observed weeks are Onion 23, Potato 23.5, Wheat 7.
- Median missing share within a series' span: 4.9% / 2.9% / 18.4% (90th percentile 75–83%).
- Series with a gap of 4 weeks or more: 931 / 845 / 3,110. Series shorter than 8 weeks: 854 / 830 / 3,716.
- Wheat's short, gappy series reflect its seasonal trading.

**Continuity across the relaunch [V]** (pre-relaunch series that continue after it):

| Design | Onion | Potato | Wheat |
|---|---|---|---|
| FAQ-only | 289 of 1,473 (19.6%) | 292 of 1,346 (21.7%) | 606 of 2,956 (20.5%) |
| FAQ + Local | 496 of 1,735 (28.6%) | 352 of 1,597 (22.0%) | 625 of 2,965 (21.1%) |
| Pooled | 549 of 1,763 (31.1%) | 398 of 1,624 (24.5%) | 667 of 3,092 (21.6%) |

The dominant cause is unjoined identities: only 440 old→new pairs are approved.

**Model tables (price-only; origin week W; targets at W + 1, 2 or 4):**
- Features: `y_origin`, `lag1`, `lag2`, `lag4`, `lag52` (exact weeks), `n_weeks_history`, `n_usable_dates_to_origin`, `weeks_since_prev_obs`, `eligible_d41`.
- Rows (FAQ-only, h = 1): Onion 80,219, Potato 79,307, Wheat 111,932.
- **Rows eligible under D-41** (≥ 365 usable dates by the origin): 13,221 / 13,821 / 10,953. The first eligible origin is 2025-02-03 (Wheat 2025-02-10). That is about 89 weeks of eligible origins, because no pre-2024-02-03 history is used (D-50).
- No split is assigned. Splits belong to the experiment configuration, which is not approved.

**Limits on comparison with the old dataset:**
1. **No overlapping period.** The old data end 2024-02-02 and the candidate data begin 2024-02-03, so errors cannot be compared on the same weeks.
2. **Price-only.** There are no arrivals or weather after 2024-02, so the D-42 configurations that use weather cannot be reproduced.
3. **D-41 eligibility starts in 2025-02.** About 89 weeks of eligible origins against 2002–2022 before; the populations differ, so the numbers are not comparable.
4. **Market identity is partly reconciled.** About 60% of usable records are in unjoined identities, and series continuity is 20–31%.
5. **Grade mix changes after the relaunch.** FAQ-only coverage falls in 2026, and pooled mixes grades that the old data (almost all FAQ) never mixed.
6. **Source anomalies.** Madhya Pradesh conflicting versions (excluded), the unapproved R09u unit-scale candidates (kept as usable), and the March–April 2026 dual reporting (separate series).

---

## 7.1 Candidate dataset audit and proposed forecast experiment `exp-candidate-v1` (2026-10-24; **specification only; nothing trained**)

**Code and outputs:**
- Code: `Code/candidates/experiment_design.py`. Tests: `Code/tests/test_experiment_design.py`.
- Outputs in `Processed_Data/candidates/datagov_prices/experiment_design_v1/`: `audit_and_design.json` and `coverage_by_period.csv`.
- No split is written into any dataset. The proposed split is used only to count coverage.

### 7.1.1 Audit of `candidate-prices-v1` [V]

| Check | Result |
|---|---|
| Output hashes against `build_manifest.json` | all 9 match |
| Provenance | the content SHA-256 of all 2,973 crop-days matches the extraction manifest |
| Date range | records 2024-02-03 → 2026-10-20; weekly cells 2024-02-05 → 2026-10-12 (complete weeks); **no input before 2024-02-03** |
| 2023 holdout | the build code contains no path literal to `Dataset/` or to any Phase 4–10 output; the inputs are the crop-day manifest and the mapping decisions only |
| Exclusions | 0 records unusable without a documented reason; 0 usable despite a reason; **0 excluded by R09u alone** (disabled) |
| Duplicates | 3,889 groups, 0 spanning grades; 3,873 removals = the log total |
| Grades | FAQ-only contains only `FAQ`; FAQ + Local only `FAQ` and `Local`; labels unchanged |
| Weekly key | unique per (crop, canonical market, variety, week) in all designs |
| Targets | every model-table row has target = origin + h weeks exactly; the tables equal a fresh rebuild from the weekly tables (lags are exact-week cells at W − k, k ≥ 1) |
| `record_ref` | unique **among usable records**. Not unique overall: see finding A2 |

**Findings:**
- **A1. D-41 counting deviation.**
  - The build counts usable dates only inside complete weeks, so the partial first week (2024-02-03/04) is missed: at most 2 dates per series.
  - Under the exact D-41 rule (all usable dates ≤ origin), **244 FAQ-only h = 1 rows would become eligible**: 236 train, 6 validation, 2 test (264 for FAQ + Local; 290 for pooled).
  - A sample of 40 origins per design agreed on eligibility in every case, but the deviation is real.
  - **Proposed fix (needs approval):** a v1.1 build counting all usable dates from 2024-02-03.
- **A2. Type-variant duplicates at the cut-over.**
  - On 2025-11-01 → 11-05 the feed published 21 Tripura Potato records twice: once with string values and once with numbers.
  - They are distinct by canonical JSON, so the extraction kept both. The text-based policy then labelled the pairs `key_conflict`. All 42 records are excluded; no weekly value or `cell_refs_sha` is affected.
  - **They are exact duplicates, not conflicts.** A v1.1 policy could value-normalise before R03 and recover 21 records. Needs approval.

### 7.1.2 Effective sample sizes [V]

The figures below are D-41-eligible, h = 1, FAQ-only (primary), under the proposed split. **Rows are not independent:** consecutive weeks of a series are strongly autocorrelated, and series within a market or state share shocks.

| Crop | Period | Rows | Series | Markets | States | Target weeks | Top-5 state share | Approved-mapping row share |
|---|---|---|---|---|---|---|---|---|
| Onion | train | 10,199 | 417 | 398 | 18 | 46 | 81% | 72% |
| Onion | validation | 1,974 | 134 | 129 | 10 | 26 | 83% | 100% |
| Onion | **test** | **1,048** | **76** | **72** | **8** | **16** | 89% | 100% |
| Potato | validation | 2,079 | 152 | 149 | 12 | 26 | 87% | 98% |
| Potato | **test** | **1,137** | **84** | **82** | **11** | **16** | 88% | 97% |
| Wheat | validation | 3,327 | 187 | 177 | 5 | 26 | 100% | 100% |
| Wheat | **test** | **2,589** | **195** | **177** | **5** | **16** | 100% | 100% |

- **Every evaluable row is in a series that existed before the relaunch, and in validation and test 97–100% are approved-mapping identities.** A renamed market reaches 365 usable dates by 2026 only if its mapping is approved. The evaluation population is therefore the **reconciled subset of markets, not a random sample**. Results generalise to those markets only.
- **Wheat is evaluable in 5 states only.**
- FAQ + Local and pooled reach more Onion series (test: 246 and 293), most of them not approved mappings: own names continuing across the relaunch. Full table: `coverage_by_period.csv`.
- **Horizons:** coverage for h = 2 and h = 4 is nearly the same as for h = 1 (for example Onion test 1,034 and 1,022). But consecutive origins share target weeks for h > 1, so their effective sample is smaller than the row count.

### 7.1.3 Proposed specification

- **Data:**
  - `candidate-prices-v1` (D-50). Primary design FAQ-only; FAQ + Local and pooled are separate sensitivity experiments, never pooled into the primary result.
  - Price-only.
  - Population: D-41 at the origin for evaluation, and at the refit date for training (D-41 clarification 2).
- **Horizons:** h = 1 primary. h = 2 and h = 4 are secondary and always reported with their effective sample sizes.
- **Split** (fixed by calendar before any model result exists; periods by **target-week Sunday**, Phase 8 rule B.7):

| Period | Target Sundays | Use |
|---|---|---|
| Train | ≤ 2025-12-28 (eligible from 2025-02 because there is no pre-2024-02-03 history) | fitting, expanding window |
| Validation | 2026-01-04 → 2026-06-28 (26 weeks) | model and setting choice; reported per quarter as well as combined |
| Test | 2026-07-05 → 2026-10-18 (16 weeks) | **once**, after a freeze manifest and a run-once guard, as in Phase 8 |

- **Refits:** the first Sunday of each quarter (2026-01-04, 04-05, 07-05, 10-04). Each refit trains only on targets ending ≤ the refit date, which purges overlap. Preprocessing is fitted inside each refit.
- **Baselines (Phase 8 definitions):**
  1. **persistence**, the origin-week median (primary);
  2. **seasonal naive**, the series' weekly median 52 weeks **before the target week**. This must be read from the weekly table at W + h − 52, not from `lag52`, which is relative to the origin;
  3. **calendar climatology**, the median training target for the target month, crop level, refitted with the model.
- **Learned model, exploratory only.** At most one: the Phase 8 `hgb_conservative` settings, **unchanged and not re-tuned**, on the price-only features, trained on this dataset. The frozen D-42 artefacts are never reused or altered. With only about 46 training weeks it is not expected to be reliable, and **the primary result is the baseline comparison**.
- **Metrics (Phase 8):**
  - MAE (primary) and RMSE in Rs/quintal; MAPE (%; every target is > 0 after R04);
  - skill against persistence, 1 − MAE / MAE_persistence, on **identical rows**;
  - all by crop × horizon × period, with each validation quarter separate.
- **Uncertainty:**
  - a paired cluster bootstrap with **market (canonical_id) clusters**, 10,000 replicates, seed 20261022 (Phase 8 §K);
  - a state-cluster bootstrap and a leave-one-state-out check as robustness, given 5–11 states.
- **Coverage reporting:** series, markets, states, target weeks and missing-week behaviour per period. Continuing against post-relaunch series. Results for approved-mapping markets against own-name markets.
- **Leakage controls:**
  - target-Sunday assignment and refit purge;
  - features dated ≤ origin (verified A-audit);
  - thresholds fixed (Phase 5 R09; no R09u in the primary);
  - no validation-driven re-tuning of data rules;
  - the test is used once;
  - the 2023 holdout and any data before 2024-02-03 are never read (D-50 guard).
- **Comparison with frozen Phase 8:**
  - Absolute MAE or MAPE are **not** compared across datasets (different periods, market mix, grades and features).
  - The only comparable quantity is **skill against persistence within each dataset**, reported next to Phase 8's validation (2019, 2020) and test (2021–2022) skills as context, with the differences listed in §6.12 point 6.
  - D-42's weather model cannot run (no weather after 2022).

### 7.1.4 Conflicts with the Phase 8 protocol (flagged)

1. **Validation length.** Phase 8 validated on two full calendar years, reported separately. Here validation is half a year and test about 4 months, so **neither contains a full seasonal cycle**.
2. **Seasonal mismatch.** The Wheat procurement peak (April–May) falls only in validation; the test (July–October) has none. Onion and Potato seasonal lows and highs are also split unevenly.
3. **Training length.** About 46 eligible target weeks, against 17 years in Phase 8. Learned-model results are exploratory only.
4. **Regime change inside training.** The relaunch (2025-11) falls within the training window, and validation and test are entirely after it.
5. **Population.** D-41 eligibility starts in 2025-02 under D-50, and the eligible set is the reconciled subset of markets (§7.1.2).
6. **Phase 8 also had a next-reported-observation baseline.** It needs daily data at the origin, not the weekly table. Omitted unless requested.

### 7.1.5 Sensitivity analyses (descriptive; primary data unchanged) [V]

- **R09u** (disabled; R09u-excluded weekly tables computed in memory only):

| Design | Flagged usable records | Weekly cells lost | Cells whose median changes |
|---|---|---|---|
| FAQ-only | Onion 13, Potato 7 | 4 / 2 | 7 / 1 (median relative change 24%) |
| FAQ + Local | Onion 576, Potato 1,180 | 159 / 187 | 10 / 14 |
| Pooled | Onion 594, Potato 1,184 | 160 / 190 | 14 / 14 |

  - Concentrated in **Tamil Nadu Potato markets** (Thiruvarur, Thammampati, Mannarkudi, Thuraiyur, Lalgudi, Cuddalore, Chidambaram: 20 records each) and **Samana APMC** Onion (23).
  - **Proposal:**
    1. A person other than the rule's author reviews every S1 flag (62) and a stratified sample of later flags (for example 5 per top market and 30 random), against neighbouring days and other markets, labelling each likely Rs/kg, genuine or unclear.
    2. Only then, run an "R09u-excluded" sensitivity arm for FAQ + Local and pooled, scored on rows shared with the primary.
- **Wheat conflicts:**
  - 52,488 records, 91.7% in Madhya Pradesh.
  - In FAQ-only they touch 13,139 weekly cells; **12,593 still have other usable records** and 546 are lost entirely (**0.4%** of 137,582 usable cells). Pooled: 473 lost (0.3%).
  - The median-of-versions alternative (§6.7) can therefore change coverage only marginally. Its value is in **target composition** in Madhya Pradesh. It stays a sensitivity arm.
- **Grade designs:**
  - Continuity across the relaunch is 19.6–21.7% (FAQ-only), 21.1–28.6% (FAQ + Local) and 21.6–31.1% (pooled) (§6.12).
  - Pooled raises evaluable Onion test series from 76 to 293, but mostly through own-name markets and Local or other grades.
- **Reliability of post-relaunch evaluation:**
  - Every evaluable test row comes from a continuing series.
  - Test h = 1 rests on **72 / 82 / 177 markets in 8 / 11 / 5 states over 16 target weeks**.
  - Market-cluster confidence intervals will be wide. State concentration (top 5 states = 88–100% of rows) means a single state can dominate.
  - Recommendation: report state-level results and leave-one-state-out checks, and treat any skill difference within its cluster-bootstrap interval as inconclusive.

### 7.1.6 Approvals needed before execution
1. The split, the refit dates and the baseline set as above (or amended).
2. Whether to apply the **A1 (D-41 count)** and **A2 (type-variant duplicates)** fixes as `candidate-prices-v1.1` before running. Recommended: yes. Both are mechanical and change at most 244–290 eligible rows and 21 records.
3. Whether the exploratory learned model is in scope.
4. The R09u independent review (§7.1.5) before any R09u sensitivity arm.
5. Whether the Wheat median-of-versions sensitivity arm (§6.7) runs.
6. Who performs the freeze and authorises the single test run.

## 7.2 `candidate-prices-v1.1` and the frozen experiment protocol (2026-10-24; **nothing trained, no result inspected**)

### 7.2.1 Changes from v1

v1 stays the frozen reference. **Rebuilding v1 now (`--version v1`, into a scratch folder) reproduces all 9 v1 outputs byte for byte**, and the v1 files themselves are unchanged.

**Code:**
- `build_candidate_prices.py`: a `VERSIONS` table; v1 has every change off.
- `price_policy.py`: `dedup_type_variants`, off by default; `load_accepted` now keeps `raw_index` and `raw_value_types`.
- `experiment_design.py`: the audit rebuilds with each dataset's own recorded D-41 rule.

**Outputs:**
- `dataset_v1_1/`, holding `contract.json` and `build_manifest.json` with `changes_from_v1`.
- `experiment_design_v1_1/`.

| Change | Rule | Verified effect |
|---|---|---|
| **A1. D-41 count** | `n_usable_dates_to_origin` counts **every** usable date ≤ origin, including the partial first week 2024-02-03/04, which v1 skipped. Weekly cells still use complete weeks only. The 365-date threshold is unchanged | FAQ-only h = 1: **244 rows newly eligible (236 train, 6 validation, 2 test) — exactly as predicted**; FAQ + Local 264 (254 / 8 / 2); pooled 290 (280 / 10 / 0). 0 rows lost eligibility. The audit sample now matches the exact D-41 count in 40 / 40 origins per design (v1: 18–33 / 40) |
| **A2. Type-variant duplicates** | Records identical in all 11 source fields as text are `type_variant_duplicate`. The **string-typed copy is kept** (then the lower raw position), the numeric copy is excluded, **before** R03 | **Verified on the raw JSON:** all 21 pairs (20 Potato, 1 Onion; all Tripura; 2025-11-01 → 11-05) are exactly two records, identical in every field as text and differing only in JSON value type. **No pair had a substantive difference.** Result: 21 records recovered as usable (Onion +1, Potato +20); `key_conflict` 65,261 → 65,219; 21 numeric copies excluded with the new reason; no value changed |

**Combined effect, v1 → v1.1:**
- Records are unchanged: 683,604 / 647,268 / 659,439.
- Usable-for-target: Onion 670,140 → 670,141; Potato 642,124 → 642,144; Wheat 599,349 (unchanged).
- Weekly cells: +4 (FAQ-only), +4 (FAQ + Local), +5 (pooled).
- Model-table rows: +11 / +11 / +16.
- A2 also lifted 3 FAQ-only training rows over the D-41 threshold (pooled: 3 train + 1 validation), so the newly eligible totals are 247 / 267 / 294.

**Revalidation [V]:**
- Two v1.1 builds are byte-identical.
- 45 / 45 weekly cells (3 crops × 3 designs × 5) were recomputed exactly from records: median, `n_records`, `cell_refs_sha`.
- Model tables equal a fresh rebuild under the v1.1 rule.
- Targets are exactly h weeks after origin; lags are exact-week cells before the origin.
- No input before 2024-02-03, and no protected path literal in the build code.
- 0 exclusions without a documented reason; 0 removed by R09u.
- Duplicate groups never span grades; grade subsets contain only their labels.
- 3,873 duplicate removals match the log; 440 one-to-one mappings.
- `record_ref` is unique among usable records.
- All freezes, 55 raw fingerprints and 573 protected files are unchanged.

### 7.2.2 Frozen experiment protocol (`exp_candidate_v1_protocol.json`, SHA-256 `a6b1240c4c4f80da…`; status: specified, not executed)

**As proposed in §7.1.3, unchanged:**
- **Split by target-week Sunday:** train ≤ 2025-12-28; validation 2026-01-04 → 06-28; test 2026-07-05 → 10-18.
- **Refits:** 2026-01-04, 04-05, 07-05, 10-04.
- **Horizons:** h = 1 primary; h = 2 and 4 secondary.
- **Designs:** FAQ-only primary; FAQ + Local and pooled as sensitivity experiments.
- **Baselines:** persistence, seasonal naive (52 weeks before the **target** week), calendar climatology.
- **Metrics:** MAE (primary), RMSE, MAPE, and skill against persistence on identical rows.
- **Uncertainty:** a market-cluster paired bootstrap (10,000 replicates, seed 20261022), with state-cluster and leave-one-state-out diagnostics.

**Reconciliation with Phase 8:**

| Phase 8 element | Here | Status |
|---|---|---|
| Period = target-week Sunday; training targets ≤ refit date (B.7, D-40) | same | aligned |
| Quarterly expanding refits; preprocessing per refit | same | aligned |
| D-41 at origin (evaluation) / at refit (training) | same; count now exact (A1) | aligned |
| Baselines: persistence, seasonal naive, calendar climatology | same definitions | aligned |
| Next-reported-observation baseline | omitted (needs daily origin data) | **conflict 6, needs a decision** |
| MAE / RMSE / MAPE / skill on identical rows | same | aligned |
| Paired bootstrap, seed 20261022 | same seed; **market clusters** (Phase 8 used series and market) | aligned in spirit; state diagnostics added |
| Validation 2 calendar years, reported per year | half-year, reported per quarter | **conflict 1** |
| Selection: beat persistence in both validation years | analogue: both validation quarters (learned model only) | **needs approval** |
| Train 2002–2018 | about 46 eligible target weeks (2025-02 → 2025-12) | **conflict 3** |
| Weather / APY features | none (price-only) | expected difference |

The other documented limitations are unchanged (§7.1.4):
- the short evaluation span (validation 26 weeks, test 16 weeks), with no full seasonal year;
- the Wheat procurement peak falling only in validation;
- market concentration (Wheat in 5 states; the top 5 states are 82–100% of rows);
- the relaunch inside the training window;
- the evaluable population being the reconciled subset.

**No date, metric or setting was changed silently.** The conflicts above are presented for decision, not resolved by me.

### 7.2.3 Learned model plan (prepared; not executed)

The plan is in the protocol under `learned_model`. The settings are read from the frozen Phase 8 code (`LEARNERS['hgb_conservative']`), not copied by hand.

**Reusable unchanged:**
- HistGradientBoosting: max_iter 200, learning_rate 0.05, max_leaf_nodes 15, min_samples_leaf 1000, l2 10, no early stopping, random_state 0;
- one model per crop × horizon;
- target log(y_target / y_origin), with price features scaled by y_origin;
- the D-41 training population at the refit date;
- quarterly refits.

**Needs approval:**
1. **The feature set.** Phase 8's features are daily-level and do not exist in the weekly table. The proposal is the lag1, lag2, lag4 and lag52 ratios to y_origin, plus weeks_since_prev_obs, n_weeks_history and the target-month sin/cos. This is a **new** feature set.
2. **The selection rule** (both validation quarters).
3. **The scope** (h = 1, FAQ-only only).

**Never:** reuse or alter the D-42/D-45 artefacts; tune on the test window.

### 7.2.4 Independent sensitivity reviews

**R09u review pack** (read-only; `review_packs/r09u_v1/`):
- `r09u_flagged_records.csv`: **3,622 flagged records**. Each carries its `record_ref`, raw file path, crop-day `content_sha256`, crop, state, district, market, variety, grade, date, min, max and modal, R09 level, usable status, the same market's median modal within ±7 days, and 100 × modal over that median.
- `r09u_review_sample.csv`: **138 records**, seed 20261022: all 62 from S1, 46 from the top-10 markets (5 each), and 30 random.
- `reviewer_label` (likely_rs_per_kg / genuine / unclear), `reviewer`, `review_date` and `notes` are **blank**.
- R09u stays disabled, with 0 reviewed.

**Wheat median-of-versions** (§6.7): **deferred, not activated**. No conflicting records are averaged, and the primary dataset is unchanged. The descriptive size remains 546 FAQ-only cells (0.4%).

### 7.2.5 Approval checklist (`experiment_design_v1_1/approval_checklist.csv`)

| Item | Status |
|---|---|
| v1.1 validation | **passed** (above) |
| Split and refit schedule | proposed in the frozen protocol; pending approval |
| Baselines and metrics | proposed; pending approval (including whether the next-reported-observation baseline is dropped) |
| Learned model scope | plan prepared; feature set, selection rule and scope pending |
| R09u independent review | pack prepared; 0 reviewed; R09u disabled |
| Wheat median-of-versions | deferred (not activated) |
| Test freeze and one-time test run | approver: project owner (to be named); not authorised |

## 7.3 Baseline run preflight (2026-10-24): **stopped before running; one protocol gap needs a decision**

**Runner and tests:**
- Runner: `Code/candidates/baselines_candidate.py`, with persistence, seasonal naive and calendar climatology; validation only; no learned model.
- Tests: `Code/tests/test_baselines_candidate.py` (6 tests, synthetic data).
- **No baseline has been run** and no validation or test metric exists.

**Approved decisions taken as given:**
- the target-week split and quarterly refits;
- FAQ-only h = 1 first;
- the three baselines;
- the two validation quarters as the selection periods (a documented adaptation, not equivalent seasonal evidence);
- the next-reported-observation baseline omitted;
- no learned model;
- the 2023 holdout reserved;
- R09u disabled; Wheat median-of-versions not activated.

**Preflight results [V]:**

| Check | Result |
|---|---|
| Protocol hash | **Content matches the approved `a6b1240c4c4f80da…`.** The file on disk hashes to `00966959…` only because it was written with CRLF line endings (text mode on Windows). The approved hash is of the canonical LF text. With line endings normalised, the file, the protocol regenerated from current code and the recorded hash are identical. The runner verifies the LF-normalised hash; the frozen file is not rewritten |
| D-50 | all six approvals recorded in the v1.1 contract; R09u disabled; start 2024-02-03 |
| v1.1 dataset | manifest version `candidate-prices-v1.1`; all output hashes match (manifest SHA-256 `4a04140d…`) |
| Boundaries | train ≤ 2025-12-28; validation 2026-01-04 → 06-28 (Q1 to 03-29, Q2 from 04-05); test 2026-07-05 → 10-18 (`check_split` passes) |
| Test-window guard | model rows and weekly cells are read with a parquet filter `week ≤ 2026-06-22` (the last validation target week), then asserted. On the real files the guarded maximum is 2026-06-22. Verified by reading **date columns only**: no price or label was loaded |
| 2023 holdout | the runner opens only `dataset_v1_1` and the protocol file; it has no path literal to `Dataset/` or to any Phase 4–10 output, and v1.1 holds no row before 2024-02-03 |
| **Refit coverage** | **FAILS under the approved list** (below) |

**The protocol gap: refits before the first approved refit date.**
- The protocol lists refits 2026-01-04, 04-05, 07-05 and 10-04.
- Under the Phase 8 rule (`refit_date_for`: each origin uses the latest refit on or before it), the first validation origins come before 2026-01-04, and **Phase 8's own function raises** "an origin precedes the first scheduled refit":

| Horizon | Validation origin weeks before 2026-01-04 | Eligible rows affected |
|---|---|---|
| h = 1 | 1 (origin Sunday 2025-12-28) | 348 |
| h = 2 | 2 | 681 |
| h = 4 | 4 | 1,164 |

- **Only calendar climatology is affected.** Persistence and seasonal naive have no fitted state. But scoring on identical rows ties all three baselines to the same choice.
- Phase 8 used `refit_schedule()`, **the first Sunday of every quarter**. Its first 2019 validation origins used the 2018-10-07 refit (`model_refit_log.csv`), so the approved list is a subset of the Phase 8 schedule.

**Options for the owner:**

| Option | Effect |
|---|---|
| **(a) `phase8_quarterly` (recommended)** | Use the Phase 8 schedule, adding refit **2025-10-05** for those origins (training targets ≤ 2025-10-05). This is identical to how Phase 8 handled its first validation weeks. Nothing after the origin is used |
| (b) `approved_list` + drop rows | Score validation only from origin 2026-01-04. Loses the first validation week for h = 1 (348 rows), so Q1 has 12 instead of 13 target weeks |
| (c) Add 2025-12-28 (train end) as an extra refit | Not a Phase 8 cadence; a new rule |

The runner implements (a) and (b) as `--refit-rule phase8_quarterly | approved_list`. Option (b) currently stops at the guard; it would need an explicit drop-rows switch.

**MAPE handling (decided in code, not silently redefined):**
- Every target is a weekly median of usable modals, and usable modals are > 0 after R04. The runner refuses any non-positive target.
- Because R09u is disabled, a few targets may be very small (likely Rs/kg values). The runner therefore reports, per crop:
  - the count of targets < 100 Rs/q;
  - median APE beside MAPE;
  - the share of total APE contributed by the top 1% of rows.
- MAPE is flagged as unstable where that share is large.

## 7.4 Baseline results, `exp-candidate-v1` (2026-10-24; validation only; **test window not opened; no learned model**)

**Decision:** the owner approved refit option (a), `phase8_quarterly`.

**Run:** `python -m Code.candidates.baselines_candidate --refit-rule phase8_quarterly`. Outputs in `Processed_Data/candidates/datagov_prices/experiments/exp_candidate_v1/baselines_phase8_quarterly/<design>_h<h>/`:
- `by_crop.csv`, `by_crop_quarter.csv`, `by_crop_state.csv`;
- `bootstrap.csv`, `leave_one_state_out.csv`;
- `persistence_all_eligible_rows.csv`;
- `run_manifest.json` (protocol hash, dataset manifest hash, code hashes, refits, seed and output hashes);
- `run_index.json`.

**Fix before the run [V].** Calendar climatology first trained only on rows labelled "train". Phase 8 refits are expanding windows over **all** targets ended by the refit date, so the 2026-04-05 refit must also include Q1 validation targets. That is now fixed and tested (`test_climatology_refit_is_an_expanding_window_over_all_targets_ended_by_the_refit`). This was not a leak, because only targets ended by the refit were ever used, but it was a deviation from the protocol.

**Pre-run checks [V]:**
- Protocol LF hash `a6b1240c…`; D-50 approvals; v1.1 output hashes; R09u off.
- Guarded reads: 0 test rows loaded; the latest target week loaded is 2026-06-22.
- Every forecast uses the latest quarterly refit on or before its origin Sunday.
- **Refits used:** 2025-10-05, 2026-01-04 and 2026-04-05. For FAQ-only h = 1 they cover 348, 3,337 and 3,701 rows; across all horizons and designs 2,193 to 19,525 rows each.

**Reproducibility [V]:** two complete runs (9 design × horizon combinations, 64 files) are **byte-identical**.

**Identical rows:** all three baselines are scored on the same rows. Rows without a seasonal-naive value (no target-week cell 52 weeks earlier) are excluded from the comparison: 77–170 per crop × design × horizon. Persistence on all eligible rows is reported separately.

**Primary: FAQ-only, h = 1 (validation 2026-01-04 → 06-28; 26 target weeks)**

| Crop | Rows (Q1 / Q2) | Markets | States | Persistence MAE / RMSE / MAPE / median APE | Seasonal naive MAE, skill [95% CI] | Climatology MAE, skill [95% CI] |
|---|---|---|---|---|---|---|
| Onion | 1,889 (988 / 901) | 128 | 10 | 95.6 / 158.7 / 7.12% / 3.85% | 578.0, **−5.04** [−5.99, −4.27] | 600.4, **−5.28** [−6.22, −4.47] |
| Potato | 1,948 (993 / 955) | 148 | 12 | 49.2 / 98.9 / 5.83% / 2.56% | 485.3, **−8.87** [−10.63, −7.44] | 577.3, **−10.74** [−12.88, −8.98] |
| Wheat | 3,240 (1,254 / 1,986) | 176 | 5 | 36.6 / 70.8 / 1.50% / 0.54% | 203.0, **−4.54** [−5.15, −3.99] | 163.5, **−3.46** [−3.97, −3.02] |

Skill = 1 − MAE / MAE_persistence. The 95% intervals come from the paired market-cluster bootstrap (10,000 replicates, seed 20261022).

**Every quarter, horizon and design agrees [V]:**
- **Persistence is best everywhere.**
- Skills: seasonal naive −1.3 to −10.0; climatology −1.3 to −16.2.
- Every bootstrap interval excludes 0, and every leave-one-state-out skill is negative.
- The deficit narrows with horizon (FAQ-only Onion: seasonal naive −5.04 at h = 1, −3.05 at h = 2, −1.51 at h = 4).

| Design | h | Onion: rows / persistence MAPE / seasonal naive skill | Potato | Wheat |
|---|---|---|---|---|
| FAQ-only | 2 | 1,857 / 10.36% / −3.05 | 1,901 / 9.78% / −4.92 | 3,127 / 2.12% / −2.82 |
| FAQ-only | 4 | 1,805 / 16.02% / −1.51 | 1,829 / 18.06% / −2.26 | 2,931 / 3.13% / −1.52 |
| FAQ + Local | 1 | 4,740 / 5.29% / −5.15 | 2,361 / 6.16% / −8.28 | 3,470 / 1.51% / −4.64 |
| Pooled | 1 | 5,940 / 5.72% / −4.81 | 3,560 / 6.69% / −6.91 | 4,170 / 1.55% / −4.56 |

The full per-quarter tables are in each `by_crop_quarter.csv`.

**Diagnostics [V]:**
- **MAPE instability** (top 1% of rows ≥ 20% of total APE, a threshold fixed before the run):
  - flagged only for **Onion Q1 calendar climatology** (21–25%, in FAQ-only and FAQ + Local, all horizons);
  - that cell has 2 targets below 100 Rs/q, probably Rs/kg entries left in because R09u is disabled;
  - persistence MAPE is never flagged (top-1% share 7–11%).
- **Concentration** (FAQ-only h = 1): the largest state is West Bengal for Onion (29.6%) and Potato (33.3%), and **Uttar Pradesh for Wheat (59.3%)**. The top 5 states hold 84% / 88% / **100%**.
  - Leave-one-state-out skill ranges are narrow and all negative, so no single state drives the ranking.
  - Absolute MAE levels, though, are dominated by those states.
- **Quarter effects:** seasonal naive is much worse in Q1 than Q2 for Onion (−7.76 vs −2.33) and Wheat (−7.74 vs −2.13). This reflects 2025→2026 year-on-year level shifts. With only one year of lag history, seasonal naive measures a single year's change.

**Comparison with Phase 8 (context only, not comparable):**
- Phase 8 also found "persistence beats seasonal naive everywhere, by a wide margin" (2019–2020).
- The candidate persistence MAPE (h = 1: 7.1% / 5.8% / 1.5%) is not compared with Phase 8's absolute values: different years, markets, grades, and a weekly target built from a different population.

**Limitations:**
- 26 validation weeks (half a year).
- Wheat in 5 states.
- The evaluable population is the reconciled subset of markets.
- Seasonal naive rests on one year of history.
- Climatology is fitted on about 9 months of eligible targets.
- No test evaluation.

**Recommendation on the exploratory learned model:**
- **Weakly warranted, narrowly scoped.** The baselines only confirm that persistence is the benchmark to beat; they say nothing about whether a learned model can do better.
- Phase 8's conservative HGB beat persistence in validation (Onion h = 1) but was **1.58% worse in the 2021–2022 test**, with 17 years of training. Here there are about 46 training weeks.
- The prior that a model beats persistence robustly is therefore low, and gains of the size that matter (a few percent of a 36–96 Rs/q MAE) are smaller than the market-cluster uncertainty is likely to resolve.
- If it is run: FAQ-only, h = 1 only, with the price-only feature set approved first. The pre-registered success criterion is "skill > 0 in **both** validation quarters, with the market-cluster 95% interval excluding 0". Otherwise persistence stays the decision default and the test window remains unopened.

## 7.5 Pre-registered exploratory learned model (2026-10-24): **FAILED the pre-registered rule for every crop**

**Scope and code:**
- Scope: one model (owner authorisation): FAQ-only, h = 1, price-only, the frozen Phase 8 `hgb_conservative` estimator unchanged. Validation only.
- Code: `Code/candidates/learned_candidate.py`. Tests: `Code/tests/test_learned_candidate.py` (5 tests, synthetic data).
- Outputs: `experiments/exp_candidate_v1/learned_hgb_conservative_faq_only_h1/`, holding `learned_preregistration.json` and `run/`.

**Pre-registration before any training [V]:**
- `--register` wrote `learned_preregistration.json`, SHA-256 **`03df2c4d1b20…`**, once.
- It records the features, target, training rule, selection rule, seed and replicates, and the hashes of:
  - the protocol (`a6b1240c…`) and the v1.1 manifest (`4a04140d…`);
  - `learned_candidate.py`, `baselines_candidate.py`, `experiment_design.py`;
  - `Code/modelling/models.py` (`42e7026b…`, **identical to the D-42 freeze manifest**, so the estimator code is the frozen one);
  - `Code/modelling/dataset.py`.
- `--run <sha>` refuses unless the file and every recorded hash still match. It then repeats the baseline guards (protocol, D-50, v1.1 hashes, test-window parquet filter, refit coverage).
- **Not done:** no alternative feature set was tried, no setting was changed, and the rule was not altered after results.

**Estimator, unchanged** (read from `LEARNERS['hgb_conservative']`): max_iter 200, learning_rate 0.05, max_leaf_nodes 15, min_samples_leaf 1000, l2_regularization 10, early_stopping False, random_state 0.
- One model per crop, refitted at 2025-10-05, 2026-01-04 and 2026-04-05.
- Target: log(y_target / y_origin), with prediction y_origin × exp(output) (Phase 8 `log_ratio`).

**Pre-registered features.** Each is computed only from model-table columns built from weeks ≤ the origin week. NaN is kept, never imputed, because HGB handles it natively.

| Feature | Calculation | Missing when |
|---|---|---|
| `log_y_origin` | log of the origin-week median | never |
| `r_lag1`, `r_lag2`, `r_lag4` | weekly median 1, 2 or 4 weeks before the origin week ÷ y_origin | that week has no cell |
| `r_lag52` | weekly median 52 weeks before the origin week ÷ y_origin | no cell (all series before 2025-02) |
| `weeks_since_prev_obs` | weeks since the series' previous observed week | first week of a series |
| `log1p_n_weeks_history` | log1p(observed weeks up to and including the origin) | never |
| `month_sin`, `month_cos` | sin/cos(2π(month − 1)/12), month of the origin week's Thursday (Phase 8 convention) | never |

**Training rule (Phase 8 `training_examples`, eligible_by_refit):**
- At refit T, train on every example whose target Sunday ≤ T and whose series reached D-41 eligibility at an origin Sunday ≤ T, including that series' earlier weeks.
- Asserted at runtime: no training target after the refit.
- Training rows per refit: Onion 33,302 / 37,152 / 38,921; Potato 34,895 / 39,390 / 40,918; Wheat 18,796 / 24,179 / 27,041. Of these, 69–82% are earlier, not-yet-eligible weeks, as the Phase 8 rule allows.

**Pre-registered selection rule, applied unchanged:** for each crop, MAE(learned) < MAE(persistence) in 2026Q1 **and** in 2026Q2, **and** the market-clustered 95% CI of skill is entirely above 0 in each quarter. Identical eligible rows; 10,000 replicates; seed 20261022.

**Results** (validation; identical eligible rows; persistence MAE differs slightly from §7.4, which dropped rows without a seasonal-naive value):

| Crop | Quarter | Rows | Markets / states | MAE learned vs persistence | Skill [95% market-cluster CI] | Pass |
|---|---|---|---|---|---|---|
| Onion | Q1 | 1,038 | 120 / 10 | 140.4 vs 94.7 | **−0.48** [−0.59, −0.39] | no |
| Onion | Q2 | 938 | 82 / 10 | 123.7 vs 99.7 | **−0.24** [−0.32, −0.18] | no |
| Potato | Q1 | 1,069 | 142 / 11 | 66.0 vs 57.7 | **−0.14** [−0.23, −0.07] | no |
| Potato | Q2 | 1,010 | 91 / 12 | 48.1 vs 41.1 | **−0.17** [−0.23, −0.12] | no |
| Wheat | Q1 | 1,292 | 154 / 5 | 46.9 vs 41.5 | **−0.13** [−0.17, −0.10] | no |
| Wheat | Q2 | 2,039 | 173 / 5 | 36.5 vs 34.2 | **−0.07** [−0.11, −0.03] | no |

**Outcome: `passes_preregistered_rule` = False for Onion, Potato and Wheat.** Every interval lies entirely **below** 0.

**Diagnostics [V]:**
- Combined skill: Onion −0.36, Potato −0.15, Wheat −0.10. Leave-one-state-out ranges are all negative: Onion −0.41 to −0.29, Potato −0.18 to −0.11, Wheat −0.15 to −0.04.
- **RMSE is slightly lower than persistence in some cells** (Wheat Q2 65.9 vs 69.6; Potato Q1 102.8 vs 103.7) while MAE and median APE are worse: Wheat median APE 0.73% vs 0.41%. The model damps large moves but adds error on the typical small ones. This is a diagnostic, not a criterion.
- MAPE was never flagged unstable (top 1% of rows carry 6.4–11.3% of APE). Onion has 2 targets under 100 Rs/q.

**Reproducibility [V]:** two runs from the same registration produced byte-identical outputs (9 files, including the prediction parquet).

**Conclusion:**
- The single pre-registered learned model is **not eligible for further consideration**, and persistence remains the default.
- This matches Phase 8's own experience: its conservative HGB was 1.58% worse than persistence in the 2021–2022 test, with far more history. Here it has about 46 weeks of eligible targets and price-only features.
- By the pre-registration, no other feature set or setting may now be tried on this validation window.
- The test window stays closed. No test configuration is frozen.

## 7.6 D-52 persistence-only test result (2026-10-24): **reporting only; the candidate test window is now consumed**

**Record:** D-53 (full tables, month and state findings). Authorisation, freeze and guard: D-52.

**Run [V]:**
- Executed exactly once, 2026-10-24 14:37:24 → 14:37:30 UTC, under the D-52 freeze (`3298a555…`) and the run-once guard.
- Outputs: `experiments/exp_candidate_v1/persistence_test_d52/run/`. The completion record, run manifest and output hashes are consistent.
- Persistence only. Nothing trained, tuned or selected. No input before 2024-02-03; the 2023 holdout was not accessed.

**Primary result, `faq_only` h = 1** (Rs/quintal; 95% market-cluster interval):

| Crop | Rows | Markets / states | MAE [95% CI] | RMSE | MAPE % | Median APE % |
|---|---|---|---|---|---|---|
| Onion | 1,048 | 72 / 8 | 231.3 [216.1, 247.7] | 374.3 | 7.6 | 4.3 |
| Potato | 1,137 | 82 / 11 | 32.0 [24.8, 40.6] | 78.9 | 3.5 | 1.1 |
| Wheat | 2,591 | 177 / 5 | 40.7 [34.6, 48.4] | 87.5 | 1.5 | 0.8 |

**Caveats:**
- **Few independent units:** 16 target weeks in all, and Wheat comes from 5 states. The state-cluster intervals are much wider (Wheat [27.3, 60.4]).
- **Onion h = 4 September:** the error spikes (1,178.4 in `faq_only`, on 4 target weeks).
- **Missing weeks:** weeks without an observed target price are absent from the model table, so they cannot appear as exclusions.
- **Validation comparison:** descriptive only (Onion 94.7 / 99.7 on validation against 231.3 on test), not evidence of a causal change.
- **Use:** results must not be used for model selection on this window. Future models need data after 2026-10-20.

---

## 8. Weather and arrivals extension audit (2026-10-24; **no integration, no training table, no model**)

**Code and outputs:**
- Code: `Code/candidates/weather_extension.py` (`audit`, `fetch`, `validate`, `coverage`). Tests: `Code/tests/test_weather_extension.py` (4 tests).
- Reports: `Processed_Data/candidates/weather_v1/`.
- Raw responses: `Dataset_Candidates/openmeteo_ext/2026-10-24/{ext,refetch_2022}/` (JSON bytes plus `manifest.csv`, git-ignored).
- IMD grids: `Dataset_Candidates/imd_gridded/2026-10-24/`.
- **Not touched:** `Code/weather/collector.py` was not used, because its cache is the original raw folder. The original panel and raw files are unchanged (protected-hash check).

### 8.1 Existing weather data [V]

- **Source:** the Open-Meteo Historical Weather (ERA5 / ERA5-Land reanalysis) archive API, key-less (`Code/weather/config.py`).
- **Variables, daily, `Asia/Kolkata`:** `temperature_2m_mean/max/min` (°C), `rain_sum` (mm), `relative_humidity_2m_mean` (%), `wind_speed_10m_mean` (km/h), `et0_fao_evapotranspiration` (mm).
- **Locations:** `locations.csv` lists all 46 district points with latitude, longitude, geocoder name and id, admin-1 and admin-2, and resolution status.
  - 35 `phase3_verified`, 10 `phase4_resolved_alias` (for example Bhatinda → Bathinda, Palakad → Palakkad, Coochbehar → Cooch Behar), 1 `phase3_rejected_corrected` (Ferozpur; the Phase 3 point was 159 km off, and `Punjab_Ferozpur.csv` is superseded by `_corrected`).
  - No point is a district boundary or centroid. Each is the geocoder's principal town (A-10).
- **Panel** (`weather_daily_panel.parquet`): 369,610 rows = 46 × 8,035 days, 2001-01-01 → 2022-12-31; **0 missing dates, 0 duplicate dates, 0 null values**.
- **Linkage to mandi data:** Phase 4 joins by **exact state + district** (`weather_match`), with no proxy or nearest-district match.
- **Use elsewhere:**
  - Phase 6 `wx_*` features: t − 1 and trailing 7/30/90-day windows, strictly before t, NaN outside 2001–2022 or without a location;
  - Phase 8 `weather` configuration (D-42 Onion h = 1 weather HGB);
  - the dashboard `/api/locations/{id}/climate` (Open-Meteo CC BY 4.0 link added in §7.1).
- **Coverage of the new price data** (exact state + district; all 46 district names appear verbatim in v1.1):
  - usable candidate records: Onion 21.2%, Potato 17.6%, Wheat 24.4% (FAQ-only 26.0% / 21.2% / 25.2%);
  - **evaluable validation rows (FAQ-only, h = 1, D-41): 22.8% / 17.6% / 20.1%, in only 25 / 20 / 29 markets**.

### 8.2 Extension candidate (fetched, not integrated) [V]

**What was fetched:**
- Open-Meteo archive (historical reanalysis, **not forecasts**), the same 46 points and 7 variables.
- **2024-02-03 → 2026-10-20** (D-50: nothing earlier): 46 / 46 fetched, 991 days each, 0 null values.
- Units are identical to the original.
- The manifest records the request parameters, retrieval UTC, response SHA-256, grid latitude, longitude and elevation, units and null counts. 3.2 MB.

**Terms:**
- Open-Meteo data are **CC BY 4.0**, and a link must sit next to displayed data (§2).
- The free API is for non-commercial use (an academic project qualifies); usage limits were respected with pacing and a 429 back-off.
- ERA5 has a delay of about 5 days. Data near the end of the window may come from preliminary (ERA5T) fields and can be revised.

**Source stability: important.** A **re-fetch of 2022** for the same points does **not** reproduce the original panel (`refetch_2022_vs_original.csv`; 16,790 rows):

| Variable | Identical | Max abs diff | Mean abs diff |
|---|---|---|---|
| temperature_2m_mean, relative_humidity_2m_mean, wind_speed_10m_mean | 100% | 0 | 0 |
| rain_sum | 96.2% | 25.6 mm | 0.06 mm |
| temperature_2m_max | 87.4% | 0.9 °C | 0.02 °C |
| et0_fao_evapotranspiration | 84.2% | 0.22 mm | 0.004 mm |
| temperature_2m_min | **51.2%** | **2.5 °C** | 0.07 °C |

Open-Meteo has revised archived values since Phase 3. **The original panel and the extension are therefore different archive vintages.** Any combined series must either be re-fetched in full as one vintage, or carry an explicit vintage-break flag. Never splice them silently.

### 8.3 Validation against IMD gridded data [V]

**Reference:**
- IMD Pune gridded **analyses** (gauge-based interpolation, not station observations): rainfall 0.25° (2022, 2024, 2025), Tmax and Tmin 1° (2022, 2024, 2025).
- All files are exact-size; 2024 has 366 days.
- IMD's page text still says rainfall covers "1901–2024", so **2025 may be provisional**.

**Comparison:**
- Nearest IMD cell for **all 46 points** (`imd_validation.csv`), for the original 2022 and the extension 2024-02-03 → 2025-12-31.
- Overall and by IMD season (winter Jan–Feb; pre-monsoon Mar–May; monsoon Jun–Sep; post-monsoon Oct–Dec).
- **All 46 points have a valid IMD cell, so none is unvalidated.** This is **46 points, not national validation.**

| Period | Variable | Median bias | Median MAE | Median daily r (range) | Median monthly r (range) |
|---|---|---|---|---|---|
| Original 2022 | rain | +0.12 mm/day | 3.20 | 0.52 (0.25–0.81) | 0.94 (0.72–1.00) |
| Original 2022 | Tmax | **−0.83 °C** | 1.50 | 0.98 | 1.00 |
| Original 2022 | Tmin | +0.75 °C | 1.29 | 0.98 | 1.00 |
| Extension 2024–25 | rain | +0.26 mm/day | 3.35 | 0.53 (0.34–0.68) | 0.92 (0.77–0.98) |
| Extension 2024–25 | Tmax | **−0.49 °C** | 1.52 | 0.97 | 0.99 |
| Extension 2024–25 | Tmin | +0.75 °C | 1.18 | 0.98 | 0.99 |

- **The known Tmax discrepancy is confirmed:** Open-Meteo runs cooler than IMD, by about 0.5–0.8 °C at the median, and is warmer on Tmin by about 0.75 °C.
- **By location:**
  - **8 points have |Tmax bias| > 2 °C**: Buldhana −3.1, Malappuram +3.0, Jalandhar +2.6, Palakad +2.6, Hoshiarpur +2.3 and others.
  - **5 have |Tmin bias| > 2 °C**: Malappuram +3.8 with monthly r 0.66, Palakad +2.7, and Punjab points about +2.2.
  - Kerala and Punjab dominate. IMD's 1° (about 110 km) cells mix coast, ghats and plain, so part of this is spatial support, not error.
- **Rain:**
  - Monthly agreement is good (median r 0.92). **Daily agreement is weak** (median 0.53; pre-monsoon 0.26).
  - Annual totals: Open-Meteo / IMD median 1.07, range 0.65–1.94.
  - 6 points have monthly r < 0.85.
- **By season (extension):** Tmin bias is largest in winter and post-monsoon (+1.1 to +1.2 °C); rain MAE is largest in the monsoon (8.1 mm/day).

**Implication:** weekly or monthly weather aggregates are defensible; **daily rain is not** a reliable point measure. Tmax and Tmin need a per-location bias note. No source value is corrected.

### 8.4 Arrivals [V unless marked]

**Existing arrivals** (old mandi dataset, Phase 5/9):
- Tonnes; Onion / Potato / Wheat **2000-10 / 2000-10 / 2001-03 → 2024-02-02**; 1,732 / 1,623 / 1,987 markets; 99.99% `usable_arrivals`.
- **Quality issues already documented:**
  - tiny values ≤ 0.1 t: 54,629 / 36,936 / 23,338 rows;
  - Madhya Pradesh 2019–2020 placeholders (0.01 / 0.05 / 0.1 t; 2,162 rows, 96 markets; Phase 9 AQ-1 `likely_unit_error_low`);
  - entry errors 75 / 62 / 53;
  - conflicting duplicate rows 68 / 164 / 106.
- **No arrivals exist after 2024-02-02 in any source the project holds.**

**Sources for 2024-02 onward:**

| Source | Arrivals? | Access | Assessment |
|---|---|---|---|
| data.gov.in variety-wise prices (resource used for candidate prices) | **No** (no quantity field) | Documented API, personal key | Cannot supply arrivals |
| data.gov.in "Current Daily Price" | **No** | Documented API | Cannot supply arrivals |
| data.gov.in "Crop-wise All India Mandi Arrivals of top ten crops 2016-17 → 2020-21" | annual, all-India | Documented | **Wrong grain** (annual, national) and period. [A] from search; not downloaded |
| Agmarknet 2.0 backend (`api.agmarknet.gov.in/v1/daily-price-arrival/*`) | **Yes**, from 2021-01-01, "at the commodity level", one-year windows (filter metadata, §5.2) | **Undocumented; no published terms** | **Do not bulk-download.** Best technical candidate; needs written permission or documented API access from DMI. Its market ids would also help identity matching |
| eNAM (enam.gov.in) | traded quantity [A] | The site returns a JavaScript application shell for every path; no documented download or API found | Not usable without documented access; eNAM covers a subset of mandis only |
| CEDA Agri Market Data (Ashoka University) | says daily arrivals since 2001, downloadable [A] | **Unreachable** from this machine (connection refused, twice); licence and terms unverified | A research mirror, possibly useful for the historical overlap; verify terms before use |

**Recommended source and matching strategy:**
1. Request documented access from DMI/Agmarknet for daily market-level arrivals from 2024-02 (or 2021), including **market ids**.
2. Match by market id. Where ids are unavailable, match by the approved candidate identity (`candidate-market-map-v1`) and **exact** date, crop, variety and grade. Never by price similarity.
3. Validate units (tonnes vs quintals), tiny placeholder values and duplicates with the Phase 9 AQ-1 rules before any use.

**Limitation:** the Agmarknet 2.0 arrivals note says "commodity level". Variety- or grade-level arrivals may not exist, which would limit any arrivals feature to the market × crop × day grain.

### 8.5 Leakage-safe feature plan (design only; nothing built or trained)

**Experiments** (to be evaluated like §7.3–7.5, on identical rows, without assuming any gain):

| # | Experiment | Inputs | Evaluable rows |
|---|---|---|---|
| E1 | Persistence (price history only) | y_origin | all FAQ-only h = 1 eligible rows (baseline, §7.4) |
| E2 | Price + validated weather | E1 + weather features below | **only the 46 weather districts** (validation FAQ-only h = 1: 22.8% / 17.6% / 20.1% of rows; 25 / 20 / 29 markets). E1 is re-scored on exactly these rows |
| E3 | Price + arrivals | E1 + arrivals features | **blocked**: no arrivals after 2024-02-02 until §8.4 step 1 succeeds |
| E4 | Weather + arrivals | both | only where both cover the market-week; blocked with E3 |

**Proposed features** (origin = the end of week W; "available" means known before the origin):

| Feature | Source and join | Temporal definition | Availability | Missing data | Leakage risk |
|---|---|---|---|---|---|
| `wx_rain_sum_7d`, `wx_rain_sum_28d` | Open-Meteo archive, single vintage; exact state + district of the canonical market | sum over the 7 / 28 days ending the day **before** the origin Sunday | Observed history. A **real-time** system would see only about 5-day-delayed ERA5/ERA5T, so a production version must lag by about 5 days | NaN if no location or any missing day; never zero-filled | Low if lagged. **Vintage risk:** re-fetching revises past values, so freeze one vintage per experiment |
| `wx_tmax_mean_7d`, `wx_tmin_mean_7d` | same | mean over the 7 days before the origin | same | same | Same, plus a per-location IMD bias (§8.3), reported not corrected |
| `wx_rain_anom_28d` | same, with climatology from **training years only** (2024-02 → refit date) | 28-day sum minus the training-period mean for those calendar days | Climatology refitted per refit | NaN without enough history | Medium: fitting climatology on later data leaks; refit-only fitting is required |
| (excluded) daily rain, same-day weather | — | — | — | — | Daily rain fails validation (§8.3); same-day values are not known at the origin |
| (excluded) weather **forecasts** | — | — | Historical forecasts are not in the archive API | — | Using observed future weather as a "forecast" is look-ahead leakage; would need an archived-forecast source |
| `arr_sum_w`, `arr_sum_w-1`, `arr_ratio_4w` (E3/E4) | Agmarknet arrivals (once permitted); market id or approved identity; crop | sum in weeks W and W−1; ratio to the trailing 4-week mean | Arrivals are published with the day's report; same-week values are available by the origin Sunday **only if** reported by then (needs verification) | NaN; AQ-1 flags excluded | Medium: late or revised reports; unit errors |

### 8.6 Recommended sequence and approvals

**Sequence:**
1. **Approve the weather vintage policy.** Either re-fetch 2024-02-03 → 2026-10-20 as one frozen vintage, which is done (this fetch), or, if older history is ever needed, re-fetch it from the same vintage too. Never splice with the 2001–2022 panel.
2. Approve E2 scope: FAQ-only h = 1, weather districts only, the features above, pre-registered like §7.5, on the same validation window.
   - **Caveat:** E2 would be a *new* model on the validation window that already scored the failed price-only model. It answers a different question (does weather help on the weather subset?), but the multiple-comparison risk must be acknowledged.
3. Request DMI/Agmarknet arrivals access (documented API or permission). Do not use the undocumented backend for bulk pulls.
4. Only after access, run an arrivals audit (units, AQ-1 rules, market ids) and then E3/E4.

**Approvals needed:**
- (a) the vintage policy;
- (b) E2 scope and the multiple-comparison caveat;
- (c) whether to approach DMI for arrivals access, and who does it;
- (d) whether to verify CEDA's terms for historical arrivals;
- (e) any use of IMD 2025 (possibly provisional) beyond validation.

### 8.7 Weather-version policy: reconstruction result (2026-10-24) [V]

**What is known about the original panel:**
- It was requested with `Code/weather/config.py` settings: archive URL, the 7 daily variables, `timezone=Asia/Kolkata`, 2001-01-01 → 2022-12-31, coordinates from `weather_location_resolution.csv`, no `models` parameter.
- **Its retrieval times were never recorded.** `retrieved_at_utc` is empty in `weather_collection_manifest.csv`, and the raw CSVs store parsed values, not response bytes. Their file dates (2026-09-18, and 2026-10-16 for the Phase 4 additions) are cache writes only.
- **Open-Meteo exposes no data-version field.** The response headers and JSON carry none (checked), so a vintage can only be identified by **retrieval date plus content hash**. The original panel's vintage cannot be recovered.

**Candidate reconstruction:**
- Command: `python -m Code.candidates.weather_extension reconstruct`, into `Dataset_Candidates/openmeteo_ext/2026-10-24/reconstruct_2001_2022/`.
- Same documented settings and coordinates. The original panel and the extension are unchanged.
- The first run stopped after 20 of 46 locations when the server returned a non-JSON body. The fetch now treats that as transient, with bounded back-off.
- The manifest records request times for 26 locations. For the other 20 it records **file write times**, labelled as such, because the interrupted run never wrote its manifest.
- Retrieval span: 2026-10-24 12:26 → 13:09 UTC.

| Check | Result |
|---|---|
| Completeness | 46 locations × 8,035 days = 369,610 rows; **0 missing dates, 0 duplicate dates, 0 null values** |
| Units and variables | identical to the extension (°C, mm, %, km/h, mm), same 7 variables |
| Location | **all 46 points return the same grid cell as the original** (the latitude and longitude kept in the original raw CSVs) |
| Same-day reproducibility | 3 fixed locations re-fetched for both windows: **daily values, grid, units and elevation identical**. Raw bytes differ only by `generationtime_ms`, which changes on every response, so a byte comparison is not a valid test |
| Agreement with the original panel (`reconstruction_vs_original_by_year.csv`) | mean temperature, humidity and wind **100%** every year. **Tmin 51–63%** identical (max difference 4.2 °C), **Tmax 83–89%** (0.9 °C), rain 96–97% (32.3 mm), ET0 83–85% (0.22 mm), **in every year 2001–2022**, with a step in 2017 (Tmax agreement up, Tmin down) |

**Interpretation [A]:** the differences cover the whole history and only the derived daily extremes, rainfall and ET0. Means, humidity and wind are untouched. That points to a change in how Open-Meteo derives these daily aggregates, not to new observations. Open-Meteo has not been asked to confirm this.

**Policy (recommended; adopt as the version-break rule):**
1. **A weather vintage = retrieval date + manifest SHA-256.** Any re-fetch is a new vintage; matching request parameters do not make two fetches the same vintage.
2. **Never splice vintages** within one dataset or experiment.
   - The **original Phase 3/4 panel stays the frozen production input** (Phase 6 `wx_*`, Phase 8 weather configuration, dashboard climate).
   - The **2026-10-24 vintage** (reconstruction 2001–2022 + extension 2024-02-03 → 2026-10-20, retrieved the same day with identical settings, same grid cells, reproducible within the day) is the **candidate vintage**.
3. The candidate experiments need only the extension (D-50 start 2024-02-03; climatology from training-window weather only). The reconstruction is evidence and a fallback; it is not an experiment input.
4. **Limitation:** "consistent" here means one retrieval day, identical settings and same-day reproducibility. It does not mean a versioned dataset with a guaranteed model mixture, which the API does not expose.

### 8.8 IMD provisional-data policy

- **IMD gridded data are validation-only.** They are never a model feature, never a training input, and never a correction of another source. `FORBIDDEN_FEATURE_SOURCES` in `weather_experiment_design.py` refuses the IMD folder as a feature source (tested).
- **2025 files** (rain, Tmax, Tmin): IMD's page text still says rainfall covers "1901–2024", so they **may be provisional**. They are used only in `imd_validation.csv` and labelled as such. They are not re-downloaded or replaced until IMD's status and revision policy are verified.
- The existing validation artefacts (`imd_validation.csv`, the 2022 comparisons) are unchanged.
- **Validation data** are a reference for judging a source. **Feature data** are inputs dated before the origin. The two roles never mix.

### 8.9 Pre-registered price + weather experiment (`exp-candidate-weather-v1`; **proposal, not executed**)

**Protocol and code:**
- Protocol: `experiments/exp_candidate_weather_v1/exp_candidate_weather_v1_protocol.json`, SHA-256 **`ac013ab7a3f7d6ba…`**, with `restricted_coverage.csv`.
- Feature code: `Code/candidates/weather_experiment_design.py`. Tests: `Code/tests/test_weather_experiment_design.py` (4).
- **Nothing is trained or scored.**

**Design:**
- **Question:** does price plus appropriately lagged weather improve on persistence for the same eligible markets and forecast dates?
- **Nature: exploratory.** The 2026 validation window has already scored the failed price-only learned model (§7.5). This would be a second model on the same window.
- **Population:** FAQ-only, h = 1, `eligible_d41` at the origin; canonical market in one of the 46 weather districts (exact state + district); every weather feature non-null.
- **Persistence and the model are scored on identical rows.**
- **Unchanged:** split, refits (`phase8_quarterly`), seed 20261022, 10,000 replicates, the guards (protocol and dataset hashes, test-window filter, no pre-2024-02-03 data, R09u off), plus the weather-manifest hash.

**Features:**

| Feature | Definition |
|---|---|
| `wx_rain_sum_7d`, `wx_rain_sum_28d` | rain over the 7 / 28 days ending **the day before the origin Sunday** |
| `wx_tmax_mean_7d`, `wx_tmin_mean_7d` | 7-day means over the same window |
| `wx_rain_anom_28d` | 28-day sum minus the mean of the same window 1–3 years earlier, using **only years whose window ended by the refit date** |

- **Excluded:** daily rain, same-day weather, observed weather used as a forecast, any IMD value.
- **Missing values:** a row lacking any feature is dropped from **both** methods, with no imputation.
- All of this is tested: same-day weather never enters, a missing day gives NaN, the climatology never sees weather after its refit.

**Models:**
- **Primary:** the unchanged `hgb_conservative` on the 9 registered price features plus the 5 weather features, trained per crop and refit on weather-district series under Phase 8's `eligible_by_refit` rule.
- **Diagnostic, not a gate:** the same estimator on the price features only, on the same rows, to isolate what weather adds.

**Acceptance rule:** **identical to §7.5**. Per crop: MAE below persistence in 2026Q1 **and** 2026Q2, with the market-cluster 95% interval of skill entirely above 0 in each. No new or relaxed threshold.

**Multiple comparisons:**
- Bonferroni-adjusted 99.17% intervals (6 crop × quarter tests) are reported beside the 95% ones.
- Any pass is an exploratory signal that needs confirmation on data after 2026-10-20 before any test-window request.

**Pre-registered sensitivity analyses** (reported, never used to select):
- the real-time lag: windows ending 6 days before the origin (about the ERA5 delay);
- 7-day features only;
- excluding high-bias locations (|Tmax| or |Tmin| bias > 2 °C);
- a state-cluster bootstrap and leave-one-state-out.

**Coverage and selection bias [V]** (validation, counts only):

| Crop | Quarter | Weather rows (% of eligible) | Markets | States | Top state (share) |
|---|---|---|---|---|---|
| Onion | Q1 / Q2 | 204 (19.7%) / 247 (26.3%) | 20 / 22 | 6 / 7 | West Bengal (38% / 31%) |
| Potato | Q1 / Q2 | 156 (14.6%) / 210 (20.8%) | 19 / 17 | 3 / 3 | West Bengal (42% / 53%) |
| Wheat | Q1 / Q2 | 255 (19.7%) / 413 (20.3%) | 23 / 29 | 3 / 4 | Madhya Pradesh (55% / 55%) |

**Disclosure:** with only 17–29 market clusters per cell, intervals will be wide, and the rule may fail even if weather helps a little. That is a **power limitation, not evidence of no effect**. The markets are reconciled, continuing and weather-district markets only.

### 8.10 Arrivals access (draft prepared; nothing sent or downloaded)

**DMI request:**
- **Draft:** `Documentation/Requests/DMI_Arrivals_Access_Request_DRAFT.md`, **not sent**, with placeholders for sender, institution and supervisor.
- **It asks for:** documented access, licence and terms, research-use permission, historical coverage, units, commodity, variety and grade definitions, stable market identifiers and an old-to-new crosswalk, update frequency, revisions, and placeholder guidance.
- **Post-access plan:** the AQ-1 v1 rules and the units, duplicate and identity steps are listed in its internal notes.
- The undocumented backend stays unused.

**CEDA Agri Market Data (Ashoka University):**
- **Reachability:** `agmarknet.ceda.ashoka.edu.in` is **unreachable from this machine** (connection refused, over HTTPS and HTTP, on three occasions); `ceda.ashoka.edu.in` answers 403 to automated requests. The following comes **only from public search results** and is not verified first-hand:
  - **Terms:** free non-commercial download and use, with attribution, no implied endorsement and no warranty. A republishing page mentions a Creative Commons licence, which conflicts.
  - **Citation and coverage:** the citation reads "CEDA Agri Market Data (CEDA-AMD), **2000–2023**", so it **probably does not cover 2024-02 onward**.
  - **Content:** commodity-level daily arrivals and prices, mapped to Census 2011 districts; raw data downloadable.
- **Unresolved:** the actual end date, the download method, the exact licence for bulk files, and whether its market identifiers match Agmarknet's. Ask ceda@ashoka.edu.in or check the portal from a browser. **No CEDA data was downloaded.**

### 8.11 `exp-candidate-weather-v1` result (2026-10-24): **FAILED the pre-registered acceptance rule for every crop**

**Protocol digest:**
- Full SHA-256: `ac013ab7a3f7d6baeadbbfa9d6f7a8bf861c69b467d99ee228504380fae56c97`.
- §8.9 recorded only its first 16 characters. The full digest was established three ways:
  1. it is the value printed when the protocol was written;
  2. **regenerating the protocol from the frozen code and data is byte-identical** to the file;
  3. every hash embedded in it still matches: price protocol, v1.1 manifest, learned pre-registration, weather manifest, and the 5 code files.
- The runner refuses to run if any of these fails.

**Runner and outputs:**
- Runner: `Code/candidates/weather_experiment_run.py`. It is a new file, so no protocol-hashed file changed. Tests: `Code/tests/test_weather_experiment_run.py` (3).
- Outputs: `experiments/exp_candidate_weather_v1/run/` (11 files). **Two runs are byte-identical.**

**Rows and leakage controls [V]:**
- All guarded model rows lay in 2024-02-05 → 2026-06-22 (target weeks), so no test-window or pre-2024-02-03 row was loaded.
- Weather came only from the registered extension folder; IMD was refused.
- Scored rows: Onion 451, Potato 366, Wheat 668. Every weather-district eligible row had all 5 weather features, so 0 rows were dropped.
- Persistence, price + weather and the price-only diagnostic were scored on identical rows.
- Training rows per refit (weather-district, `eligible_by_refit`, every feature non-null): Onion 2,990 / 3,782 / 4,230; Potato 2,852 / 3,602 / 3,856; Wheat 1,384 / 2,005 / 2,656. All training targets ended by their refit.

**Primary result** (95% market-cluster CI; Bonferroni 99.17% in brackets; 10,000 replicates, seed 20261022):

| Crop | Quarter | Rows / markets / states | MAE price + weather vs persistence | Skill [95% CI] | [99.17% CI] | Pass |
|---|---|---|---|---|---|---|
| Onion | Q1 | 204 / 20 / 6 | 126.5 vs 107.8 | −0.17 [−0.34, −0.07] | [−0.42, −0.04] | no |
| Onion | Q2 | 247 / 22 / 7 | 158.9 vs 107.4 | −0.48 [−0.80, −0.26] | [−0.94, −0.20] | no |
| Potato | Q1 | 156 / 19 / 3 | 51.5 vs 44.7 | −0.15 [−0.29, −0.04] | [−0.34, +0.00] | no |
| Potato | Q2 | 210 / 17 / 3 | 38.3 vs 28.4 | −0.35 [−0.64, −0.18] | [−0.76, −0.13] | no |
| Wheat | Q1 | 255 / 23 / 3 | 56.4 vs 56.0 | −0.01 [−0.03, +0.01] | [−0.04, +0.02] | no |
| Wheat | Q2 | 413 / 29 / 4 | 48.7 vs 49.6 | +0.02 [−0.02, +0.05] | [−0.04, +0.05] | no |

**`passes_preregistered_rule` = False for Onion, Potato and Wheat.** The rule is unchanged.

**Diagnostic: price-only on the same rows** (isolates the weather contribution; not a gate):
- Skill: Onion −0.15 / −0.45, Potato −0.16 / −0.32, Wheat −0.05 / −0.02.
- Weather changes little for Onion and Potato: both models are worse than persistence.
- For Wheat, weather moves the model from slightly worse than persistence to level with it, about +3–4 points over price-only. The interval includes 0.

**Pre-registered sensitivity analyses** (reported, not selected; skill and 95% CI):

| Sensitivity | Onion Q1 / Q2 | Potato Q1 / Q2 | Wheat Q1 / Q2 |
|---|---|---|---|
| Real-time lag (window ends 6 days before origin) | −0.18 / −0.43 | −0.22 / −0.40 | 0.00 [−0.01, 0.01] / +0.01 [−0.02, 0.03] |
| 7-day features only | −0.15 / −0.45 | −0.15 / −0.34 | −0.01 / +0.02 [−0.02, 0.05] |
| Excluding high-bias locations (|Tmax or Tmin bias| > 2 °C) | −0.13 / −0.25 | −0.18 / −0.32 | unchanged (no Wheat point excluded) |

- **State-cluster bootstrap:** only 3–7 clusters. Every Onion and Potato interval is below 0; both Wheat intervals include 0.
- **Leave-one-state-out skill:** Onion −0.44 to −0.25, Potato −0.31 to −0.12, Wheat −0.05 to +0.02.

**Composition:**
- Onion: West Bengal 78 / 76 rows, then Punjab, Gujarat, Rajasthan, Madhya Pradesh, Uttar Pradesh and Haryana.
- Potato: West Bengal, Uttar Pradesh and Punjab only.
- Wheat: Madhya Pradesh 139 / 228 rows; Gujarat, Uttar Pradesh and one Rajasthan row.

**Interpretation:**
- **Exploratory, not confirmatory.** This is the second model on a validation window already used by the failed price-only model (§7.5).
- No crop shows evidence that price + lagged weather beats persistence. For Onion and Potato the evidence is against it on these rows.
- The Wheat result (level with persistence; slightly better than price-only) is **not** a signal under the registered rule. Testing it would need fresh data after 2026-10-20, not the test window.
- Power is limited (17–29 market clusters per cell), so this does not prove weather can never help. It shows no benefit for this model, these features and this population.
- **Persistence remains the default. The test window stays closed.**

### 8.12 Closure (D-51, 2026-10-24)

- **Final result:** `exp-candidate-weather-v1` is closed as **failed for all three crops**. No defect was found, and nothing was re-run or altered.
- **No further tuning:** no more weather-model tuning on the 2026 validation window. A Wheat follow-up needs data after 2026-10-20 and a new pre-registration.
- **Not in the pipeline:** weather stays out of the candidate and production forecasting pipeline. The historical weather analysis, the Phase 3/4 panel, the `wx_*` features, the Phase 8 weather artefacts, the integration code and the 2026-10-24 candidate vintage are all kept unchanged.

---

## 9. Arrivals access and the next research path (2026-10-24; investigation only)

### 9.1 CEDA Agri Market Data (Ashoka University)

**Verified first-hand** (fetched 2026-10-24; pages carry no date):
- **[CEDA API Terms and Conditions](https://ceda.ashoka.edu.in/api-terms-conditions/):**
  - users may "download, display or include the data in other products **for non-commercial purposes at no cost**";
  - the citation is "**CEDA Agri Market Data (CEDA-AMD), 2000-2023**", credited to the Centre for Economic Data & Analysis, Ashoka University;
  - visualisations and applications show the CEDA logo and a text credit;
  - "The Centre makes **no warranties** with respect to the accuracy of the data";
  - **no licence is named**; **bulk-download conditions and rate limits are not stated**.
- **[CEDA Republishing Guidelines](https://ceda.ashoka.edu.in/republish-policy/):**
  - data products are "made available for **non-commercial use** by researchers, students, policymakers, journalists, and educators" and may be "used, shared, or adapted under the same Creative Commons license as our editorial content" unless otherwise stated;
  - the editorial licence links to **CC BY-ND 4.0**, which forbids derivatives and conflicts with "adapted";
  - credit to CEDA is required; CEDA "may modify, update, or restrict access to datasets at any time".
- **Not reachable** from this environment:
  - the data portal `agmarknet.ceda.ashoka.edu.in` (and `/home/download`): connection refused, repeatedly, by both direct request and the web-fetch tool. `ceda.ashoka.edu.in/agmarknet` redirects there;
  - `cedadataportal.ashoka.edu.in`: DNS failure;
  - the Internet Archive: not fetchable by this tool.
- No access control was bypassed, and **no CEDA data was downloaded**.

**From search results only (not verified):**
- the source is the Ministry's Agmarknet;
- **commodity-level daily arrivals** and modal prices since about 2001;
- monthly visualisation at all-India, state and district level;
- markets mapped to **Census 2011** state and district boundaries;
- raw data "downloadable".

**Unresolved:**
- the **actual end date** (the citation's "2000–2023" suggests it does **not** cover the post-2024-02 gap);
- whether arrivals are at market level or only aggregated;
- the units, market identifiers and their relation to Agmarknet codes;
- revisions;
- the exact licence for bulk files (CC BY-ND against "non-commercial, may be adapted").

**Assessment:**
- Even if reachable, CEDA probably **cannot fill the 2024-02 → 2026-10 arrivals gap**. At best it is a cross-check of the existing 2001–2024 arrivals.
- Before any use: confirm the end date, granularity and bulk licence in writing (ceda@ashoka.edu.in, per the search results), and check whether ND permits the derived weekly features.

### 9.2 DMI request status

- **File:** `Documentation/Requests/DMI_Arrivals_Access_Request_DRAFT.md`, **not sent**.
- **Revised:** added question 9 (format, schema, a sample extract) and question 10 (pre-2021 availability, for a units overlap check), plus an **authorised-sender checklist**: owner and supervisor approval, real details only, official contact address, institutional email, no credentials or data attached, record the submission date.
- **The draft asks for:** documented access, licence and terms, research-use permission, historical coverage, units, commodity, variety and grade definitions, stable market identifiers and an old-to-new code crosswalk, update frequency, revisions, placeholder and data-quality guidance, and format and schema.

### 9.3 Conditional research paths (no model or protocol is built now)

**Path A: lawful, sufficiently detailed arrivals become available** (DMI or a verified source).
1. **Provenance:** store the raw data unchanged in a new `Dataset_Candidates/` folder, with retrieval date, parameters and SHA-256.
2. **Units and definitions:** confirm tonnes against quintals and the commodity, variety and grade grain from the documentation. Check against the existing 2021-01-01 → 2024-02-02 arrivals on identical markets and dates (paired, never assumed).
3. **Quality:** apply Phase 9 AQ-1 v1 unchanged (the classes, tiny-value and unit signatures, the Madhya Pradesh placeholder pattern, Wheat March–May review, `aq1_available_from` at refits) and the R03 / type-variant duplicate logic.
4. **Identity:** market identifiers, or approved `candidate-market-map-v1` identities only; never price similarity.
5. **Coverage:** report it against the D-41-eligible validation population before any design decision.
6. **Design only then:** a new pre-registered price + arrivals protocol. **Important:** the 2026 validation window has already been used twice (§7.5, §8.11). A fresh evaluation period (data after 2026-10-20) is required, or an explicit owner decision recorded on reusing the window.

**Path B: arrivals access unavailable or refused.**
1. **Finalise the price-based scope:** candidate-prices-v1.1 (D-50), with **persistence as the default** and the baseline results (§7.4: persistence beats seasonal naive and climatology everywhere).
2. **Keep the negative results as findings:** the failed price-only learned model (§7.5) and the failed price + weather model (§8.11).
3. **The test window stays closed** unless the owner authorises a single, frozen persistence-only test run (§7.5 recommendation). The 2023 holdout stays reserved (D-50).
4. Document the arrivals gap (none after 2024-02-02) as a scope limitation.

**Common to both paths:**
- No new model, protocol or test access until the data, evaluation design and owner approval exist.
- The final notebook revamp is **not started**.

---

## 7. New Training and Testing Experiment Plan (`exp-v2-prices`, proposed)

**Why retraining on "replacement" history is not proposed.** For 2002–2022 the candidate data equals what we already hold (§5.1). Retraining on it would reproduce the same models. The value is a **new, never-scored test window**.

1. **Target and horizons:** unchanged from D-38. Weekly median modal price per crop × market × variety, h = 1/2/4 weeks, Onion/Potato/Wheat definitions as before.
2. **Splits (chronological, no shuffling):**
   - train: 2002 → 2018;
   - validation: 2019 and 2020, unchanged and identical to Phase 8;
   - **new test: target weeks 2024-03-03 → last complete week before the pull, scored once.**
   - The 2021–2022 test and the 2023 holdout keep their existing status.
3. **Leakage rules:**
   - Imputers, scalers and encoders are fitted on training rows only.
   - Features use data dated ≤ origin.
   - Horizon gap as in Phase 8.
   - No series identity from post-2024 crosswalk decisions leaks into training (the crosswalk is built without looking at prices).
4. **Rolling origin:** expanding window, weekly origins inside the test window, refits at the Phase 8 cadence.
5. **Baselines:** persistence (primary), seasonal naive and calendar-only, scored on exactly the same rows.
6. **Metrics:** MAE, RMSE and MAPE by crop × horizon × year, plus a paired series-cluster bootstrap against persistence (`Code/modelling/uncertainty.py`).
7. **Reporting:**
   - Every split reports usable observations, series, markets, states, date range and missingness.
   - Continuing series (crosswalked) and new series are reported separately.
8. **Comparability:** results must **not** be compared with the D-42 2021–2022 test numbers as an "improvement". Different window, different market mix, no weather. The only valid claims are relative to persistence within the same window.
9. **Separation:**
   - The experiment has its own config (`Processed_Data/v2/experiment/exp_config.json`), data manifest, validation results and artifacts.
   - D-42/D-45 models and their freeze manifests are untouched.
   - No production model is replaced without a new Decision Log entry.
10. **Arrivals:** there is no post-2024 target, so the Phase 9 models cannot be re-tested on the new window. State this; do not substitute.

### 7.1 Dashboard and pipeline compatibility

- **`Code/app/data.py`:** it hard-blocks 2023+ data and price origins after 2020-12-27, by design. v2 data must use **new loaders and new endpoints** (for example `/api/v2/markets/*`), never a relaxation of the existing checks.
- **Market and forecast pages:** they need a "source / period" indicator distinguishing the "AGMARKNET history (to 2024-02)" and "data.gov.in (2024-02+)" segments. They also need a series-break marker where a market's name changed.
- **Provenance and freshness:**
  - Add `retrieved` and `last_record_date` to `/api/meta`.
  - Add data.gov.in attribution.
  - **Fixed 2026-10-24:** the climate chart in the Overview card (`frontend/src/pages/Overview.tsx`) now shows "Weather data by Open-Meteo.com (CC BY 4.0)" with a link, as the licence requires. The link is asserted in `frontend/src/test/app.test.tsx`.
- **Setup docs:** `README_Setup.md` would need the API-key environment variable and the v2 pipeline command.
- No change is required to routing or warehouses.

---

## 8. Remaining Risks, Licensing Issues and Data Gaps

**Unresolved decisions [U]:**
- **U1:** Register a personal data.gov.in key? Its record limit per call is unknown until tested. The sample key makes bulk pulls impractical: about 60k calls per crop for the post-2024 window alone.
  - **Harness ready:** `Code/candidates/datagov_key_check.py`, with offline tests in `Code/tests/test_datagov_key_check.py`.
  - **Key:** it reads `DATAGOV_API_KEY` or the git-ignored file `.secrets/datagov_api_key`, and redacts the key from saved responses.
  - **What it checks:** pages one known day (Onion, 17/01/2024) within an 80-call budget, then checks page size, duplicates, gaps, repeated-page stability, malformed records and the modal-price match with the existing data.
  - **Exit codes:** 0 pass, 1 unreliable, 2 no key, 3 access restricted.
  - **Status:** run live with a personal key on 2026-10-24. Offset paging failed, and §5.5 diagnoses why.
  - **Replacement method:** one call per partition (`datagov_partition_check.py`). It passed on 4 commodity-days, with tests in `Code/tests/test_datagov_partition_check.py`.
  - **Pilot:** the authorised pilot over 30 crop-days passed in 136 calls (§5.6).
  - **Next:** stage S1 of §6.1, awaiting approval.
- **U2:** Ask DMI (Agmarknet) for documented access to market-level arrivals after 2024-02 and confirmation of terms. Without it, arrivals after 2024 do not exist for this project.
- **U3:** Phase 8 §P holdout protocol. Scoring 2024+ uses 2023 data as lag history at the first origins. Is reading 2023 inputs (not scoring them) acceptable, or must the new test start after a buffer?
- **U4:** IMD gridded data redistribution terms. If redistribution is not allowed, keep derived district aggregates only and cite.
- **U5:** District boundaries (needed for IMD district means). The candidate open sources (for example geoBoundaries ADM2) were **not** evaluated here.

**Licensing:**
- data.gov.in: GODL-India requires attribution **[A]**, because the API response does not state a per-resource licence.
- Open-Meteo: CC BY 4.0, with a link next to displayed data; free tier non-commercial **[A]**.
- IMD: unstated.
- India Data Portal: ODC-By (mirror licence; underlying DES/UPAg terms not separately stated).
- NASA POWER: unrestricted.

**Data gaps:**
- No arrivals after 2024-02-02.
- No district production for Onion or Potato after 2022-23 (UPAg covers field crops only). The NHB state-level series is the fallback; not evaluated.
- Weather covers 46 district points.
- The mandi dataset's original download location is unknown, but its content is shown to equal the official feed (§5.1).
- Crop calendars, irrigation and soil were not added: no current model has a stated use for them.

**Measured risks:**
- Post-go-live market renaming (3.4% exact name match).
- New grades and markets change the series composition.
- API paging duplicates 15–17%.
- Open-Meteo Tmax runs 1.2–2.0 °C cooler than IMD at three points.
- Daily-count gaps of up to +12.5% between the API and our copy for some 2010–2016 days are unexplained.

**Not done** (by design, pending approval):
- no bulk downloads;
- no v2 pipeline;
- no model training;
- no dashboard changes;
- no commits.
