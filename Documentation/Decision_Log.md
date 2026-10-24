# Decision Log

Records major technical decisions as they are made. Never retroactively rewritten to look predetermined — decisions are logged at the phase they were actually made in.

---

### D-01 — Dataset folder is read-only for the entire project
**Decision**: `Dataset/` is never modified, renamed, or written into. All derived data goes to `Processed_Data/`, `Outputs/`, or `Documentation/`.
**Reason**: User requirement; also standard data-science practice to preserve raw source integrity and reproducibility.
**Alternatives considered**: None — this was a hard constraint from the outset.
**Impact**: Every phase's I/O design must read from `Dataset/` and write elsewhere.
**Phase**: 1 (reaffirmed every phase).

### D-02 — No crop is predetermined; selection deferred to Phase 2
**Decision**: Phase 1 establishes the candidate crop universe (325 mandi filenames, minus 5 empty files = 320) and the metrics Phase 2 will need, but performs no scoring or selection.
**Reason**: User requirement — selection must be evidence-based, not assumed (explicitly not Onion/Potato/Tomato by default).
**Alternatives considered**: Pre-filtering to "obviously large" crops in Phase 1 — rejected, since Phase 1 findings (Section 7 of the notebook) already show record count alone is a poor proxy for full-pipeline feasibility (e.g. Agri Market Dataset coverage is unrelated to mandi volume).
**Impact**: Phase 2 must independently compute the full metric set for all 320 candidates (or a data-driven shortlist derived transparently from Phase 1's record-count distribution).
**Phase**: 1.

### D-03 — Existing scripts are audited, not deleted, in Phase 1
**Decision**: `inspect_agriculture.py`, `inspect_top.py`, `test_openmeteo.py` remain in `Code/` unmodified. Their reusable logic has been generalized into `Code/utils/data_audit.py` (crop-agnostic functions), but the originals are not removed yet.
**Reason**: User requirement to inspect before deleting; also these scripts remain useful as a record of the project's exploratory starting point.
**Alternatives considered**: Immediate deletion after refactor — rejected as premature; deferred until Phase 2 confirms no unique logic is still needed from them.
**Impact**: `Code/` currently has both legacy scripts and the new `Code/utils/` module; cleanup is a Phase 2+ decision.
**Phase**: 1.

### D-04 — Mandi column-name and date-format inconsistencies are normalized via a shared utility, not per-notebook code
**Decision**: `Code/utils/data_audit.py` defines `MANDI_COLUMN_ALIASES` (maps unit-free column names like `Arrivals` to their unit-suffixed canonical form `Arrivals (Tonnes)`) and `parse_mixed_dates()` (handles both `DD Mon YYYY` and ISO date formats via `pd.to_datetime(..., format="mixed")`).
**Reason**: Column naming and date formatting were found to be inconsistent across the 325 mandi files (Phase 1, Section 4) — a shared, tested normalization function avoids repeating ad hoc fixes in every future phase/notebook.
**Alternatives considered**: Fixing inconsistencies file-by-file inline in each notebook — rejected as non-reusable and error-prone across 320 files.
**Impact**: All future phases reading mandi CSVs should use `load_mandi_file()` / `parse_mixed_dates()` rather than raw `pd.read_csv()`.
**Phase**: 1.

### D-05 — Weather API is inspected but not called at scale in Phase 1
**Decision**: `Code/test_openmeteo.py` was reviewed by reading its source only; no live API call was made in the Phase 1 notebook.
**Reason**: Phase 1 scope is data understanding of existing artifacts, not data collection; avoids unnecessary/premature API calls before Phase 3 defines the actual required locations and date ranges (which depend on Phase 2's crop selection).
**Alternatives considered**: Running a live smoke-test call in Phase 1 — rejected as out of scope and potentially wasteful before locations are known.
**Impact**: Phase 3 is responsible for both the first real API calls and building the reusable collector.
**Phase**: 1.

### D-06 — Agri Market Dataset is treated as a bonus/regional validation source, not a hard requirement for crop selection
**Decision**: Because Agri Market Dataset covers only 1 state (Maharashtra), 5 districts, and 5 commodities, it will not be required to cover all three finally-selected crops.
**Reason**: Making it a hard requirement would improperly bias crop selection toward a narrow, regionally atypical dataset rather than the strongest overall (mandi + APY + weather-feasibility) evidence.
**Alternatives considered**: Requiring Agri Market Dataset coverage for at least one selected crop as a "bonus" criterion — left open as a possible tie-breaker in Phase 2, not a filter.
**Impact**: Phase 2's scoring methodology must document this explicitly so the final selection isn't second-guessed as having ignored a source.
**Phase**: 1.

### D-07 — Project folder structure extended with `Notebooks/`, `Processed_Data/`, `Outputs/`, `Documentation/`, `Code/utils/`
**Decision**: Created these new folders (all empty of any original data) alongside the existing `Code/` and `Dataset/`.
**Reason**: Required to keep derived artifacts strictly separate from read-only `Dataset/`, per D-01, and to give every phase a dedicated notebook location and output location.
**Alternatives considered**: None — this matches the structure agreed in the Master Project Plan.
**Impact**: All future phases write into these folders.
**Phase**: 1.

### D-08 — Full feasibility audit restricted to a normalized-match shortlist, not all 320 candidates
**Decision**: Detailed mandi feasibility metrics (states/districts/markets/continuity/missingness) were computed only for the 48 mandi crops that passed normalized name-matching against APY (40 exact + 8 confirmed manual aliases), not all 320 non-empty mandi files.
**Reason**: A crop with no evidenced APY match cannot support the future Supply Prediction phase regardless of mandi volume, so auditing it in full would not change the selection outcome; this kept Phase 2 efficient without weakening the evidence base for selection.
**Alternatives considered**: Full detailed audit of all 320 files — rejected as unnecessary compute for candidates that are disqualified by APY absence regardless of mandi strength; the lighter-weight name-mapping step (`crop_name_mapping.csv`) still covers all 320 for transparency.
**Impact**: `Processed_Data/crop_feasibility_mandi.csv` / `crop_feasibility_apy.csv` cover 48 crops; `crop_name_mapping.csv` covers all 320.
**Phase**: 2.

### D-09 — Replaced `pd.to_datetime(..., format="mixed")` with a per-file format-detection parser for bulk auditing
**Decision**: Added `Code/utils/data_audit.py:parse_dates_fast()`, which samples a file's dates, picks the best-fitting fixed format (`%d %b %Y` or `%Y-%m-%d`), and parses the whole column with that single format, falling back to the slower mixed-format parser only for rows the detected format can't handle.
**Reason**: A first attempt to audit 48 shortlisted crops using `format="mixed"` (Phase 1's parser, correct but element-by-element) did not complete within 10+ minutes and was killed; per-file fixed-format parsing audited the same 48 crops (~2.8 GB) in ~60 seconds, exploiting the Phase 1 finding that format is consistent *within* a file even though it differs *between* files.
**Alternatives considered**: Keeping `format="mixed"` and accepting the runtime — rejected as impractical for repeated use across future phases; a naive single global fixed format — rejected because it would silently mis-parse files using the other format.
**Impact**: `parse_dates_fast()` is now the recommended date parser for any future phase working with more than a few mandi files; `parse_mixed_dates()` remains available for the general/small-scale case (as used in Phase 1).
**Phase**: 2.

### D-10 — Final crop selection: Onion, Potato, Wheat
**Decision**: Selected Onion, Potato and Wheat as the project's three crops.
**Reason**: All three have among the highest mandi and APY coverage of the full candidate universe (see `Documentation/Crop_Feasibility_Audit.md` for complete evidence); Wheat additionally has independent (regional) Agri Market cross-validation; Onion/Potato are highly perishable, price-volatile commodities matching the project's trading/storage decision-support objective, while Wheat adds crop-type diversity (MSP-influenced staple vs. free-market vegetables).
**Alternatives considered**: Rice (strong APY, fewer mandi markets, no Agri Market validation), Maize (strong APY, materially lower mandi volume), Soyabean/Cotton/Jowar (Agri Market bonus, but ~3x lower mandi volume than the selected crops), Groundnut (lower mandi volume), Bengal Gram (APY match only via a lower-confidence manual alias), Tomato (high mandi volume but critically weak APY coverage — 5 years, 22.85% zero-production).
**Impact**: Phases 3–14 proceed with exactly these three crops.
**Phase**: 2.

### D-11 — Weather granularity: representative district-level coordinates, not per-mandi
**Decision**: One weather location is used per (state, district) pair, not per individual mandi/market.
**Reason**: Weather does not vary meaningfully within a district for this project's purposes, and the mandi dataset has up to ~512 unique districts per crop — per-mandi collection would multiply API calls with no meaningful gain in spatial resolution.
**Alternatives considered**: Per-market weather (rejected — excessive API volume for negligible benefit); state-level-only weather (rejected — too coarse, would lose meaningful regional variation across a state as large as e.g. Maharashtra or Uttar Pradesh).
**Impact**: `Code/weather/location_mapper.py` maps at district granularity; Phase 4 will need a documented rule for mandis in non-mapped districts.
**Phase**: 3.

### D-12 — Weather collected only for the top-20-by-volume districts per crop, not all districts
**Decision**: Rather than geocoding and collecting weather for every district a crop appears in (up to ~512), only the 20 highest-mandi-volume districts per crop were selected, de-duplicated into a 46-location union across Onion/Potato/Wheat.
**Reason**: These districts already carry a disproportionate share of each crop's trading activity; collecting weather for the long tail of low-volume districts would multiply API calls for comparatively little benefit to the future forecasting/optimization phases, which will realistically focus on high-activity markets.
**Alternatives considered**: Full district-level collection for all ~500 districts per crop — rejected as impractical given free-tier API rate limits (encountered directly in this phase) and of low marginal value given the long-tail distribution found in Section 7 of the Phase 3 notebook.
**Impact**: Weather coverage in this project reflects the top-volume districts only; this must be stated clearly whenever weather coverage is reported (see `Documentation/Weather_Data_Collection.md`).
**Phase**: 3.

### D-13 — Unresolved geocoding locations left unresolved rather than manually corrected in Phase 3
**Decision**: 10 of 46 representative locations (e.g. mandi "Bhatinda" vs official gazetteer "Bathinda") failed geocoding due to spelling mismatches and were recorded as unresolved rather than manually corrected in this phase.
**Reason**: Manually guessing the "likely" official spelling for each mismatch risks introducing an unverified coordinate under time pressure; better to document the limitation transparently and leave the correction as an explicit, reviewable future step.
**Alternatives considered**: Building a manual spelling-alias table immediately — deferred, not rejected; it remains a reasonable Phase 4+ task once each correction can be verified against an authoritative source.
**Impact**: 10 high-mandi-volume districts currently have no weather data; Phase 4 must explicitly decide how these are handled (excluded vs. assigned to a nearby mapped location, with the choice documented).
**Phase**: 3.

### D-14 — Historical weather window fixed at 2001-01-01 to 2022-12-31
**Decision**: Weather was collected for this calendar-year range specifically.
**Reason**: This is the overlap between mandi reporting (active for all three crops from ~2000–2001) and APY coverage (agricultural years 1997-98 through 2022-23); 2022-12-31 is the last calendar year fully inside APY's coverage.
**Alternatives considered**: Extending to mandi's full range (through 2024) — rejected because APY has no coverage past the 2022-23 agricultural year, so additional weather years would have no matching production data to eventually integrate with.
**Impact**: Any future Phase 4+ analysis is implicitly bounded to this window unless a later phase deliberately extends it (with a matching justification).
**Phase**: 3.

### D-15 — Phase 4 integration grain: separate outputs at each source's native grain, mandi table row-preserving
**Decision**: Instead of one giant daily table, Phase 4 produces separate outputs (`Processed_Data/integration/`): `mandi_integrated_<crop>.parquet` (one row per raw mandi record, `source_row` = 0-based CSV row), `weather_daily_panel.parquet` (location × date), `apy_season.csv` / `apy_annual.csv` (APY's own grains), `mandi_apy_district_year.csv` (crop × APY district × agricultural year), `district_crosswalk.csv`, `agrimarket_wheat_crosscheck.csv`, plus `audit/` tables. Every join uses `pandas.merge(validate="m:1"/"1:1")`, asserts the left row count is unchanged, and is logged in `audit/merge_log.csv`.
**Reason**: The sources have different grains (daily market records, daily district weather, annual district-season production). A single table would repeat annual values onto daily rows or multiply rows through many-to-many joins.
**Alternatives considered**: One wide daily table with APY values broadcast onto each record — rejected (repeated annual values would look like independent daily observations); aggregating mandi to district-day — rejected for Phase 4 (would hide duplicates and anomalies that Phase 5 must see).
**Impact**: Phase 5+ start from row-preserving, traceable mandi tables and join APY only at APY's grain.
**Phase**: 4.

### D-16 — Weather locations verified with an admin1 + admin2 rule; 10 unresolved resolved, 1 Phase 3 mapping corrected
**Decision**: A geocoder candidate is accepted only if `admin1` equals the state AND `admin2` equals the mandi district, its APY (DES) official name, or a documented equivalent (`ADMIN2_EQUIVALENTS` in `Code/integration/pipeline.py`); district seats (PPLA/PPLA2) are preferred, then population. Applied to all 46 Phase 3 locations, with alternative search terms (official spelling or headquarters town) for the 10 unresolved and for Ferozpur. All candidates are stored as evidence in `Processed_Data/integration/geocoder_evidence_phase4.csv`.
**Result**: 35 Phase 3 coordinates verified unchanged; 10 previously unresolved locations resolved; Phase 3's "Ferozpur" point (*Ferozpura*, admin2 = Narowal District) failed the rule and was corrected to *Firozpur* (admin2 = Firozpur), 159.2 km away. Weather for the 11 new or corrected points was collected with the existing Phase 3 collector into new cache files (e.g. `Punjab_Ferozpur_corrected.csv`) and passed the Phase 3 validator (0 missing dates/values). The Phase 3 `Punjab_Ferozpur.csv` file is kept untouched but is no longer used.
**Reason**: State-only matching (Phase 3) accepted a point in the wrong district; admin2 is the geocoder's own district field and makes acceptance verifiable. Supersedes the deferral recorded in D-13.
**Alternatives considered**: Keeping the 10 unresolved — rejected because verifiable evidence existed; guessing coordinates — never acceptable.
**Phase**: 4.

### D-17 — Mandi → weather: exact (state, district) match only; no nearest-location proxy
**Decision**: A mandi record gets weather only if its exact (state, district) is one of the verified weather locations, joined on the same calendar day. Records without a location, or dated outside 2001-01-01..2022-12-31, keep weather = NaN and are labelled (`weather_match` = `no_weather_location` / `exact_district_outside_weather_window`).
**Reason**: A same-state nearest-location proxy needs a verified coordinate for each unmapped district (≈470 per crop) and an evidence-based distance threshold; neither exists, so "nearest" cannot be computed honestly.
**Alternatives considered**: Same-state nearest mapped location — not adopted (no coordinates for the source districts); state-level average weather — rejected (D-11).
**Impact**: About 25% of Onion and Wheat records and 24% of Potato records have same-day weather (see `audit/coverage_summary.csv`). 0 proxy matches were made.
**Phase**: 4.

### D-18 — Mandi → APY district crosswalk via a reviewed alias table; no fuzzy auto-matching
**Decision**: Matching order: reviewed alias (`Code/integration/district_aliases.csv`, 131 rows each with a basis; 9 explicit exclusions) → exact normalized name → unique parenthetical part. Two state spellings are aliased (Chattisgarh, Uttrakhand). Split or reorganised districts (Burdwan, Kanpur, Bangalore, Tripura South/West District) and urban districts without APY rows (Mumbai, Kolkata, Hyderabad, Chennai) are deliberately unmatched. The pipeline raises if an alias target is not an APY district.
**Reason**: APY uses official DES names and mandi uses older spellings; edit-distance matching produced plausible-looking but wrong candidates (e.g. Kanpur → Jaunpur, similarity 0.77).
**Alternatives considered**: Automatic similarity threshold — rejected as unverifiable.
**Impact**: About 96% of Onion and Potato records and 98% of Wheat records have an APY district.
**Phase**: 4.

### D-19 — Temporal alignment: July–June agricultural year as a key, no broadcasting of annual values
**Decision**: Each mandi record gets `apy_year` (the agricultural year containing its date, July–June) and `apy_year_lag1` (the previous one). APY values are joined to mandi only after aggregating mandi to (crop, APY district, apy_year) in `mandi_apy_district_year.csv` (outer, 1:1, `link_status` kept). The original APY year label is never converted into a date.
**Reason**: APY years are labelled `YYYY-YYYY`, consistent with India's July–June agricultural year (A-13). Joining at APY's grain avoids repeating annual values across daily rows. `apy_year_lag1` provides a leakage-safe reference, since same-year APY is unknown at a record's date.
**Alternatives considered**: Calendar-year mapping — rejected (splits a Rabi season across two years); broadcasting APY onto daily rows — rejected (D-15).
**Impact**: Phase 6 must choose the APY lag explicitly; publication lag is at least one year.
**Phase**: 4.

### D-20 — APY annual value: Total row, else single season, else left missing
**Decision**: `apy_annual.csv` uses APY's `Total` season row where present (4,142 district-years); otherwise the only season row (28,851); and leaves the 18 district-years with several seasons but no `Total` as missing (`ambiguous_multi_season_no_total`).
**Reason**: `Total` equals the sum of the other seasons (verified on 99.9% of groups), so summing it with the seasons double counts. When `Total` is absent, Whole Year + Rabi/Kharif may overlap.
**Phase**: 4.

### D-21 — Duplicate mandi keys flagged, not dropped
**Decision**: Rows sharing (state, district, market, variety, group, date) get `dup_key_count` and `dup_type` (`exact_duplicate` = identical values, `conflicting` = values differ). No row is removed in Phase 4.
**Reason**: Keeping the first row is arbitrary; treatment is a Phase 5 cleaning decision. Exact: 1,416 / 1,131 / 973 rows; conflicting: 68 / 165 / 106 rows (Onion / Potato / Wheat).
**Phase**: 4.

### D-22 — Market codes from final_data.csv only on a unique normalized key
**Decision**: `market_code` is attached when the normalized (state, district, market) matches exactly one `final_data.csv` row; the 11 duplicated name pairs in the reference are left uncoded (`ambiguous_in_reference`).
**Reason**: Choosing one of two codes would be a guess.
**Impact**: 99.5% of Onion, 99.0% of Potato and 99.9% of Wheat records have a unique market code.
**Phase**: 4.

### D-23 — Agri Market Wheat kept as a separate cross-check table; found not to be independent
**Decision**: Agri Market Wheat rows are standardized, kept with a `source` label, and compared to unique-key mandi Wheat rows on (district, market, variety, date) in `agrimarket_wheat_crosscheck.csv`.
**Finding**: 96.6% of Agri Market Wheat rows inside mandi's date coverage match a mandi record, and 100% of matches have identical modal price and arrivals. The two datasets almost certainly share an upstream source (Agmarknet). This confirms key consistency but is not independent validation of mandi values. Refines A-04.
**Phase**: 4.

### D-24 — Test structure established under Code/tests (pytest)
**Decision**: Added `Code/tests/` (pytest), with synthetic edge-case tests and real-output tests including a re-run consistency check. pytest was installed into the Python 3.13 interpreter used by the project's Jupyter kernel (it was only present in a separate Anaconda Python 3.12).
**Reason**: Phase 4 requires automated validation; no test structure existed before.
**Phase**: 4.

### D-25 — Phase 5 output design: cleaned copies + flags, Phase 4 kept immutable
**Decision**: `Code/cleaning/pipeline.py:run_cleaning()` reads only `Processed_Data/integration/mandi_integrated_<crop>.parquet` and writes `Processed_Data/cleaned/mandi_cleaned_<crop>.parquet` plus `Processed_Data/cleaning_audit/`. The cleaned grain is one row per distinct observation: identical copies are collapsed, and conflicting versions stay as separate flagged rows. All 33 Phase 4 columns are kept, and 14 documented columns are added (`cleaning_audit/added_columns.csv`). Exclusions are expressed as two boolean views, `usable_modal_price` and `usable_arrivals`, instead of row deletion. The pipeline refuses input that already carries Phase 5 columns, so cleaned data is never cleaned twice. It also fingerprints the Phase 4 inputs before and after each run.
**Reason**: Every change stays reversible through `source_row`, and Phase 4 remains reproducible.
**Alternatives considered**: Deleting anomalous rows — rejected (irreversible, hides evidence); overwriting the Phase 4 files — rejected.
**Phase**: 5.

### D-26 — Duplicates: identical copies collapsed, conflicting versions retained unresolved
**Decision**: Rows sharing (state, district, market, variety, group, date) with identical arrivals/min/max/modal are collapsed to one row. The lowest `source_row` is kept; the copies are identical, so the choice carries no information. `n_identical_copies` records the count, and every removed `source_row` is listed in `cleaning_audit/removed_identical_copies.csv`. Removed: 708 / 570 / 488 rows (Onion / Potato / Wheat). Key groups with differing measurements are all kept with `dup_status = conflict_unresolved`, excluded from both usable views, and listed in `review_records.csv`: 68 / 164 / 106 rows in 34 / 82 / 53 groups.
**Evidence**: In every conflicting group, arrivals are identical and prices differ (0 groups with agreeing prices and differing arrivals). No source field distinguishes a correction from a second, ungraded lot.
**Alternatives considered**: Keep the first row — rejected (arbitrary); average the prices — rejected (invents a price).
**Phase**: 5.

### D-27 — Zero prices are "not reported" placeholders → set missing
**Decision**: A min, max or modal price of 0 is set to missing, with `<field>_status = zero_set_missing`. Values set missing: min 127,554 / 135,376 / 128,063; max 120,203 / 127,106 / 122,496; modal 27,431 / 32,501 / 13,326 (Onion / Potato / Wheat, after collapsing copies).
**Evidence**: Almost all zero-price rows have positive arrivals, and goods cannot trade at Rs 0. No row has all three prices zero. Every min > max case (3,282 / 3,990 / 3,436) disappears once zeros are treated as missing, and modal-outside-range falls from more than 120,000 rows per crop to 99 / 63 / 683.
**Alternatives considered**: Keep zeros as prices — rejected (creates impossible prices and the consistency violations); drop the rows — rejected (their other fields are valid).
**Phase**: 5.

### D-28 — Remaining price inconsistencies flagged, not corrected
**Decision**: After D-27, `min_gt_max` (0 rows in all crops) and `modal_outside_range` (99 / 63 / 683 rows) are flagged and excluded from `usable_modal_price`; the values are kept.
**Reason**: One of the three numbers is wrong, but which one is unknown.
**Phase**: 5.

### D-29 — Implausible price levels: leakage-safe trailing reference with unit-factor thresholds
**Decision**: Each price is compared with the trailing 30-day median of the crop's national daily median modal price, using only past and same-day data. If max(price/ref, ref/price) ≥ 10, the row is flagged `review` (kept and still usable). If it is ≥ 50, the row is flagged `scale_error_suspected` (kept but excluded from `usable_modal_price`). Counts — review: 22,330 / 2,339 / 471; scale error: 422 / 415 / 148 (Onion / Potato / Wheat).
**Reason**: The thresholds follow unit mix-ups (Rs/tonne vs Rs/quintal = 10×, Rs/kg vs Rs/quintal = 100×) rather than an arbitrary universal cut, and the reference is crop- and time-specific. Examples: Potato at Rs 1.12 crore/quintal (Parassala, 2018); Wheat at Rs 1.45 lakh/quintal (Soyatkalan, 2014).
**Limitation**: Genuine onion price crises produce many `review` rows; they stay usable.
**Phase**: 5.

### D-30 — Implausible arrivals: compared with the same market's past-365-day peak
**Decision**: arrivals / (maximum arrivals at the same market over the previous 365 days, strictly earlier dates, ≥ 10 past observations). Ratio ≥ 10 → `review`; ≥ 100 → `entry_error_suspected` (kept, excluded from `usable_arrivals`). Counts — entry error: 75 / 62 / 53; review: 399 / 399 / 484; insufficient history: 30,409 / 29,208 / 43,707 (Onion / Potato / Wheat). Zero arrivals (9 / 3 / 14) are genuine and kept as 0.
**How this was chosen**: A first design used the trailing *median* with a 1000× threshold (kg vs tonne). Its trial run also contained a row-alignment bug in the grouped rolling computation. A brute-force spot check (Kannauj Potato) exposed the bug, which was fixed by using contiguous integer group ids; two regression tests now compare the reference with a brute-force calculation on synthetic and real data. With the corrected computation, the median reference still flagged 997 Wheat rows, 754 of them in April — the procurement peak (e.g. Amritsar, Uchana). Genuine harvest days look like outliers against an off-season median, so the past-peak reference was adopted. Its flags are spread across months and markets.
**Phase**: 5.

### D-31 — No imputation in Phase 5; coverage gaps stay missing
**Decision**: No price, arrivals, weather or APY value is imputed. Weather gaps (1,961,172 / 2,111,939 / 1,939,054 rows) and APY-unavailable rows (1,392,360 / 1,039,572 / 167,806) are Phase 4 coverage limits, reported separately in `missingness_before_after.csv` (category column) and never treated as data errors.
**Reason**: Any imputation would have to be leakage-safe and model-specific, which is a Phase 6 decision.
**Phase**: 5.

### D-32 — Phase 6 feature table: row-preserving, one per Phase 5 row, with a role registry
**Decision**: `Code/features/pipeline.py:run_features()` writes `Processed_Data/features/features_<crop>.parquet` with exactly the Phase 5 rows (same `source_row`): 2,623,671 / 2,764,417 / 2,593,279 rows (Onion / Potato / Wheat), 85 columns. It also writes `Processed_Data/features_audit/` (registry, row counts, feature statistics, validation report, input fingerprints, manifest). Every column has a role — identifier, target, eligibility_flag, audit_only or predictor — in `feature_registry.csv`. Phase 4/5 same-day weather columns and other cleaning detail are not carried; they remain reachable through `source_row`.
**Reason**: Traceability and no silent row changes. Leaving out same-day weather removes an easy leakage path.
**Phase**: 6.

### D-33 — Series identity = (crop, state, district, market, variety)
**Decision**: Every lag and window is computed within a series defined by crop, state, district, market and variety.
**Evidence**: Under this key, the only rows sharing a date are the Phase 5 `conflict_unresolved` rows (34 / 82 / 53). Under market alone, 1.8–5.8% of market-days quote several varieties at different prices, so "the previous price" would be ambiguous.
**Phase**: 6.

### D-34 — Information cutoff and history eligibility
**Decision**: Every history feature for a row dated t uses only rows of the same series dated strictly before t (pandas time-based rolling with `closed="left"`; `merge_asof` with `allow_exact_matches=False`). Price history uses only `usable_modal_price` rows and arrivals history only `usable_arrivals` rows, so the Phase 5 policies apply unchanged: unresolved conflicts, modal outside [min, max], suspected scale or entry errors and missing values never become history. Ineligible rows still receive features. No imputation, forward-fill, back-fill or zero-fill is done.
**Reason**: This prevents target and future leakage, and same-day conflict rows cannot inform each other.
**Phase**: 6.

### D-35 — Two explicit lag types and calendar-day windows
**Decision**: `*_prev_obs` (previous available eligible observation, with `*_prev_obs_days_ago`) is kept separate from exact calendar lags `*_lag_1d` and `*_lag_7d` (NaN when the series did not report on that exact day). Windows are calendar-day windows [t−w, t) for w = 7, 30, 90, each with an explicit `count`. The price change is a percentage (eligible prices are > 0 after Phase 5); the arrivals change is absolute (genuine zero arrivals make a percentage undefined).
**Evidence**: Reporting is irregular but dense: 66–76% of gaps between eligible price observations are 1 day and about 96–98% are ≤ 7 days, so calendar windows are meaningful. Calendar lags are missing 22–34% of the time, which is why the previous-observation lag exists.
**Phase**: 6.

### D-36 — Weather as trailing windows; APY lagged two agricultural years
**Decision**: Weather features are computed on the Phase 4 daily panel (exact-location policy unchanged): the previous calendar day's value and full-coverage trailing windows (7/30/90 days), left missing if any day of the window is unavailable. APY production/area/yield are taken for agricultural year t−2 (`*_lag2`), constant within district × agricultural year.
**Reason**: Same-day weather describes day t itself. Lag-1 APY is not usable for much of each year: the only observed publication date (2022-23 data in the 14-12-2023 release) implies about 6 months' delay (A-19). This supersedes D-19's suggestion of `apy_year_lag1` as the earliest leakage-safe reference.
**Phase**: 6.

### D-37 — Calendar features; no crop harvest-season feature
**Decision**: Added `year`, `month`, `quarter`, `day_of_week`, `month_sin` / `month_cos`, `agri_year_start` (July–June) and `imd_season` (IMD meteorological seasons). No crop harvest/arrival season was created.
**Reason**: Harvest timing differs by crop and region, and no verified crop calendar exists in the project. The IMD seasons are a documented meteorological definition and do not claim to describe harvests.
**Phase**: 6.

### D-38 — [ACCEPTED in Phase 8 planning; proposed in Phase 7] Forecast target, horizon and information cutoff
**Proposal**:
- **Primary Phase 8 task:** the weekly median usable modal price of a series (crop × market × variety), h = 1, 2 and 4 weeks ahead (≈ 7–28 days).
- **Forecast origin:** the end of week W, using only information dated on or before the origin.
- **Secondary baseline:** the next reported observation.
- **No exact calendar-day targets.**
- **Phase 6 feature calculations stay unchanged;** any aggregation of features must keep the ≤ origin cutoff.
**Evidence**: An exact target day is observed only 55–78% of the time (at 30 days: 55% Wheat, 63% Onion, 66% Potato), against 81–92% for a target calendar week. The median gap between observations is 1 day and the p90 is 3–4 days (`Processed_Data/eda/horizon_feasibility.csv`, `weekly_horizon_feasibility.csv`).
**Alternatives considered**: Exact-day targets — rejected (biases evaluation toward regular reporters); next-observation only — kept as a baseline, but its irregular horizon does not match the 7–30-day planning need.
**Status**: Proposed in Phase 7; **accepted without change in Phase 8 planning (2026-10-22)**.
**Accepted form**:
- Primary target: weekly median usable modal price per series. The series key is D-33's (crop, state, district, market, variety), written "crop × market × variety" above.
- Horizons h = 1, 2 and 4 weeks. Weeks run Monday–Sunday, as in Phase 7.
- Forecast origin: the end of week W. Only information dated on or before the origin may be used.
- No exact future calendar-day price as the primary target. Next-reported-observation forecasting is kept as a secondary baseline.
- Phase 6 feature calculations are preserved, and any aggregation or selection of predictors respects the origin cutoff.
- Construction rules: `Phase_08_Modelling_Plan.md` §A.3 and §B.
**Phase**: 7 (proposed); 8 planning (accepted).

### D-39 — [ACCEPTED in Phase 8 planning; proposed in Phase 7] Treatment of flagged observations
**Proposal**:
- Use only `usable_modal_price` / `usable_arrivals` rows for targets and history. This excludes suspected scale/entry errors and the 338 unresolved conflicts.
- Keep Phase 5 `review` rows in the primary experiments.
- Run a sensitivity analysis without `review` targets.
- Never delete flagged rows.
**Evidence**: Review rows are 0.86% / 0.09% / 0.02% of usable prices (Onion / Potato / Wheat). They leave medians and p99 almost unchanged but raise standard deviations by about 7% (Onion) and 13% (Potato) (`review_flag_effect.csv`).
**Status**: Proposed in Phase 7; **accepted without change in Phase 8 planning (2026-10-22)**.
**Accepted form**:
- `usable_modal_price` / `usable_arrivals` eligibility applies to targets and history, as appropriate.
- Eligible `review` observations stay in the primary experiment.
- A sensitivity experiment excludes `review` targets: examples whose target week contains a `review` price row are dropped.
- Flagged source records and audit columns stay intact.
- Suspected errors and unresolved conflicts are never admitted into usable targets to increase sample size.
- Details: `Phase_08_Modelling_Plan.md` §A.5.
**Phase**: 7 (proposed); 8 planning (accepted).

### D-40 — [ACCEPTED WITH VALIDATION REPORTING REFINEMENT in Phase 8 planning; proposed in Phase 7] Chronological out-of-time evaluation
**Proposal**: expanding-window training on 2002–2018, validation on 2019–2020, a single-use test on 2021–2022 (weather and APY available), and a holdout of 2023-01-01 – 2024-02-02 for models without weather.
- Use rolling (e.g. monthly) forecast origins.
- Leave a gap of at least the forecast horizon between the last training target and the first test origin.
- Fit any preprocessing on training data only.
- Report metrics by crop, horizon and series-history group.
- **No random row splits.**
**Evidence**: Within-series rank correlation with the previous observation is about 0.95, so random splits would leak neighbouring observations. 87–97% of 2021–2022 active series have earlier history. Weather ends on 2022-12-31, and Wheat reporting fell 27% in 2020 (`split_evidence.csv`, `relationship_summary.csv`).
**Status**: Proposed in Phase 7; **accepted with a refinement in Phase 8 planning (2026-10-22)**.
**Accepted form**:
- Train 2002–2018.
- Validation 2019 and 2020, with metrics reported **for each year separately and for the combined period**.
- Test 2021–2022, reserved for one final evaluation.
- Additional no-weather holdout 2023-01-01 – 2024-02-02, subject to actual target and input availability.
- Expanding-window training with rolling (weekly) forecast origins and quarterly refits.
- A horizon-appropriate gap: an example belongs to the period of its target week's Sunday, and training uses only targets that end on or before the refit date.
- Preprocessing is fitted on training data only. Never a random row split.
- Collected weather ends on 2022-12-31, so the 2023–2024 holdout uses a no-weather feature configuration.
**Refinement**: 2020 was an unusual market year (Wheat reporting −27%). Model selection reports 2019 and 2020 separately so a selection driven by 2020 is visible rather than hidden in an aggregate score.
**Protocol**: `Phase_08_Modelling_Plan.md` §C.
**Phase**: 7 (proposed); 8 planning (accepted).

### D-41 — [ACCEPTED in Phase 8 planning] Series-inclusion rule for the primary modelling population
**Decision**: A series (crop, state, district, market, variety) qualifies for the primary Phase 8 population if it has **at least 365 rows with `usable_modal_price == True`**, counted over the full feature-table history. Usable rows are unique per series-date, so this equals 365 distinct usable reporting days.
**Evidence** (recounted from `Processed_Data/features/features_<crop>.parquet` on 2026-10-22; matches Phase 7 `quality_readiness.csv`): 1,473 / 1,551 / 1,540 series keep 93.27% / 93.00% / 90.55% of usable price rows (Onion / Potato / Wheat).
**Excluded series**: these are not forgotten. Phase 8 reports their coverage, baseline errors and model errors separately where meaningful.
**Alternatives considered**: span ≥ 2 years with reporting density ≥ 0.5 (491 / 592 / 335 series; 45% / 51% / 32% of usable rows). Not the primary rule because of the coverage cost; it may become a later sensitivity experiment and is not implemented now.
**Known caveat**: the full-history count uses information from the evaluation years. Counting only rows dated ≤ 2018-12-31 would keep 1,173 / 1,199 / 1,298 series, all inside the D-41 set. Phase 8 reports this subgroup separately (`Phase_08_Modelling_Plan.md` §A.4, §F).
**Clarification (Phase 8 implementation, 2026-10-22; requested by the project owner)**:
- For modelling and evaluation, the rule is applied **at each forecast origin**: a series is in the primary population at origin W when it has ≥ 365 distinct usable price dates dated on or before that origin (`eligible_at_origin` in `Code/modelling/dataset.py`).
- The full-history count above is retrospective and used for reporting only, never to select examples.
- The threshold and the counting unit are unchanged; only the information cutoff is made explicit.
- Series origin-eligible by the end of train (2018-12-30): 1,173 / 1,199 / 1,297. At any origin: 1,473 / 1,551 / 1,540.
**Clarification 2 (Phase 8 implementation, 2026-10-22; requested by the project owner)**:
- **Training** eligibility is judged at the **refit date**. A model refitted at T may train on every example of a series that had ≥ 365 usable dates on or before T, including that series' earlier weeks, provided the example's target week ended by T. In code: `eligible_from_origin <= T` in `training_examples()`.
- **Evaluation** eligibility stays at the origin.
- Future observations can never make a series eligible earlier; regression tests cover this.
- The threshold is unchanged. This recovers 90,533–122,043 training examples per crop × horizon at the 2018-12-30 and 2020-12-27 cutoffs (`Processed_Data/modelling/phase08/training_population.csv`).
**Phase**: 8 planning; clarified in Phase 8 implementation.

### D-42 — [ACCEPTED in Phase 8, 2026-10-22, by the project owner; frozen before any test evaluation] Final Phase 8 model selection
**Decision**:

| Crop | 1 week | 2 weeks | 4 weeks |
|---|---|---|---|
| Onion | **conservative HistGradientBoosting** (`hgb_conservative`, weather feature config) | persistence | persistence |
| Potato | persistence | persistence | persistence |
| Wheat | persistence | persistence | persistence |

- **Persistence** = the last known weekly median (`origin_week_median`).
- **`hgb_conservative`** settings: `HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=1000, l2_regularization=10.0, early_stopping=False, random_state=0)`. It is trained on `design_matrix(feature_columns(registry, "weather"))` to predict log(target / origin-week median).
**Reason**: in validation, Onion h = 1 `hgb_conservative` was the only candidate that passed all four pre-specified criteria (`Phase_08_Modelling_Plan.md` §L.2, §M):
- intervals above zero in 2019 and 2020 under both series and market clusters
- Bonferroni z 9.0 / 27.2
- +5.5% / +13.7% relative MAE improvement
- holds without review-flagged targets

All other cells had no candidate passing all four.
**Onion h = 4 Ridge (exploratory, not selected)**: Ridge (weather) also met all four criteria (+2.7% / +27.6%). However, the 2% minimum-gain criterion was introduced **after** its intervals were observed, and its 2019 gain is only just above that floor. The project owner therefore kept persistence. The Ridge result is recorded as exploratory evidence only.
**Alternatives considered**: control `hgb`, Ridge (both feature configs), calendar climatology, calendar-adjusted persistence, `hgb_conservative` no_weather (no review-sensitivity run, so criterion 4 could not be checked) (§J–§M).
**Frozen before the test**:
- Code: the SHA-256 of every modelling source file is recorded in `Processed_Data/modelling/phase08/test_freeze_manifest.csv` before the test runs.
- Features, preprocessing (row-wise `design_matrix`; no fitted preprocessing in HGB), metrics (example-weighted MAE, RMSE and MAPE) and the protocol below.
- No setting, model or selection may change as a result of test results.
**Test protocol (run once)**:
- **Periods:** test target Sundays 2021-01-03 … 2022-12-25. Results are reported for target years 2021 and 2022 separately, and combined.
- **Rows:** origin-eligible examples (D-41, eligibility at the origin), primary experiment.
- **Refits:** each origin uses the latest quarterly refit on or before it (2020-10-04 … 2022-10-02), the same rule as in validation (§I). Each refit trains on `training_examples(ex, refit)`: targets ended ≤ the refit date, with eligibility judged at the refit date. Targets in earlier test weeks therefore enter later refits once they are in the past (rolling origin). No 2023+ target can enter, because the last refit is 2022-10-02.
- **Comparison:** each selected approach vs persistence on identical rows. For persistence cells the two are identical, so the improvement is 0 by construction.
- **Uncertainty:** for the one learned cell, the same paired bootstrap as §K (series and market clusters, 10,000 replicates, seed 20261022, 95% percentile intervals).
- The 2023+ no-weather holdout is **not** evaluated and stays reserved.
**Impact**: Phase 8 forecasts used downstream are persistence everywhere except Onion h = 1. Test results are reported as they are and do not reopen this selection.
**Test outcome (reported only; the decision is unchanged)**: the test was run once after the freeze was verified (`Phase_08_Modelling_Plan.md` §N). Onion h = 1 `hgb_conservative` vs persistence, MAE improvement:
- 2021: −5.2% [−6.3, −4.1] (worse)
- 2022: +3.3% [+0.0, +5.9] (borderline)
- combined: −1.6% [−3.2, −0.2]

RMSE improved in both years. Any change to the selection would need a new decision, and new evidence beyond 2019–2022.
**Phase**: 8.

### D-43 — [ACCEPTED 2026-10-22 by the project owner; proposed earlier the same day] Phase 9 arrivals target, protocol and baseline
**Proposal**:
- **Target:** the weekly median of usable daily arrivals of a series, in **tonnes per reported day**. Series = (crop, state, district, market, variety) as in D-33. Not a weekly sum, and not demand (A-02).
- **Weeks and horizons:** Monday–Sunday weeks; the origin is the end of Sunday of week W; horizons h = 1, 2 and 4 weeks (as D-38).
- **Missing reports:** a day without a record is "not reported", **never zero arrivals**. A target week without a usable record yields no example. Genuine reported zeros stay 0.
- **Periods:** train on targets ending 2002–2018; validate on 2019 and 2020, reported separately and combined. Quarterly expanding refits, with training targets ending ≤ the refit date (as D-40). 2021–2022 is reserved as a test; 2023+ is the holdout. Phase 9 code reads no data after 2020-12-27.
- **Eligibility:** ≥ 365 distinct usable arrival dates, counted on or before the origin for evaluation and on or before the refit date for training (the D-41 approach applied to arrivals).
- **Baseline:** **persistence** (the origin-week median) is the primary baseline and the provisional forecast in `phase9-arrivals-forecast-v1`.
- **Wheat calendar adjustment:** calendar-adjusted persistence for Wheat is **exploratory** until its uncertainty is assessed (`Phase_09_Arrivals_Plan.md` §10).
**Evidence**: `Phase_09_Arrivals_Plan.md` §1 (data audit) and §9 (validation baselines).
**Status**: proposed 2026-10-22 for project-owner review; **accepted 2026-10-22 by the project owner without change**. The proposal text above is kept as written.
**Accepted form and audit notes**:
- All definitions above stand as written.
- **Eligibility** counts Phase 5 `usable_arrivals` dates. The AQ-1 quality flags (proposed separately) do **not** change eligibility or any input used at the forecast origin; see `Phase_09_Arrivals_Plan.md` §12.
- **Reserved periods:** 2021–2022 and 2023+ stay untouched. No Phase 9 code reads data after 2020-12-27.
- **Not decided here:** the Wheat calendar adjustment stays exploratory, and no learned arrivals model is selected or authorised.
**Phase**: 9.

### D-44 — [ACCEPTED 2026-10-22 by the project owner; proposed earlier the same day] Phase 9 learned-arrivals experiment protocol
**Proposal**: `phase9-arrivals-protocol-v1` (`Phase_09_Model_Protocol.md`):
- **Candidates:** Ridge and the Phase 8 conservative HGB. The baseline is persistence; calendar adjustment is exploratory only.
- **Features:** 15 origin-time features, computed from weeks ≤ the origin on the Phase 5 view.
- **Populations:** AQ-1 v1 `aq1_likely` as primary, with the original as sensitivity.
- **Evaluation:** log MAE on identical rows, 2019 and 2020 judged separately, paired series/market bootstrap.
- **Selection:** intervals above 0 in both years, Bonferroni z > 3.197, ≥ 2% gain in each year, and agreement on the original population. Otherwise persistence is kept.
**Status**: proposed 2026-10-22, when `arrivals_models.PROTOCOL_STATUS` was `"PROPOSED"` and no learned arrivals model could be fitted; **accepted 2026-10-22 by the project owner**. The proposal text above is kept as written. Fitting is authorised only under this exact protocol, with no added candidates, no tuning and no change to the selection rule after results are seen.
**Accepted together with the open protocol questions** (`Phase_09_Model_Protocol.md` §8), recorded exactly as approved:
- **U2:** AQ-1 v1 likely-error exclusion (`aq1_likely`) is the primary evaluation-target population. The original population remains a sensitivity analysis.
- **U3:** the primary analysis uses AQ-1 class-based handling. A separate sensitivity run additionally excludes **all** flagged Madhya Pradesh `provider_query_pending` rows from targets. It is reported only and is not part of the selection rule.
- **U4:** the Wheat calendar adjustment stays exploratory and cannot be selected as a learned model.
- **U5:** approved runs use the existing Python 3.13 runner (`Code/utils/run_phase09_notebook.py`). The Jupyter configuration is not changed.
- **U6:** the Madhya Pradesh data-provider query stays **drafted and unsent**.
**Implementation**: `arrivals_models.PROTOCOL_STATUS = "APPROVED"`. `require_approved()` also checks that this entry's heading reads ACCEPTED.
**Phase**: 9.

### D-45 — [ACCEPTED 2026-10-23 by the project owner, as written; proposed earlier the same day] Phase 9 arrivals model selection
**Evidence** (D-44 experiment, run 2026-10-22 with Python 3.13.7 and scikit-learn 1.8.0; validation 2019–2020 only):
- Files: `Processed_Data/modelling/phase09_models/candidate_selection.csv`, `candidate_bootstrap_{primary,original,mp_excluded}.csv` and `candidate_metrics.csv`.
- The selection rule was applied unchanged: intervals above 0 in both years under both clusterings, Bonferroni z > 3.197, ≥ 2% gain in each year, and agreement on the original population.

| Crop | h = 1: % lower log MAE vs persistence, 2019 / 2020 | h = 2 | h = 4 |
|---|---|---|---|
| Onion | **hgb_conservative** +5.90 / +4.43 (Ridge +2.50 / +1.82, fails) | **hgb_conservative** +6.24 / +5.04 (Ridge fails) | **hgb_conservative** +5.86 / +7.12 (Ridge +2.41 / +3.73 also passes) |
| Potato | **hgb_conservative** +4.45 / +3.10 (Ridge fails) | **hgb_conservative** +3.86 / +4.37 (Ridge fails) | **hgb_conservative** +2.57 / +4.71 (Ridge fails) |
| Wheat | **hgb_conservative** +8.75 / +5.94 (Ridge fails) | **hgb_conservative** +11.14 / +6.83 (Ridge fails) | **hgb_conservative** +14.89 / +9.14 (Ridge +2.66 / +4.16 also passes) |

- **Sensitivities:** on the original population and with all flagged Madhya Pradesh rows excluded (U3), conservative boosting's improvements change by at most 0.73 percentage points (series clusters, per year), and every verdict is unchanged.
- **Wheat calendar adjustment:** not eligible (U4).

**Proposal**:
- Select **conservative HistGradientBoosting** (`arrivals_models.CANDIDATES["hgb_conservative"]`, settings unchanged) for **all nine** crop × horizon arrivals cells.
  - It is the candidate with the higher worst-year improvement in every cell.
  - Ridge, which also passes for Onion and Wheat at h = 4, is recorded but not proposed.
- After approval, freeze the code and selection by hash, as in D-42, and run the reserved **2021–2022 arrivals test once**, under D-43 / D-44 and a run-once guard.
- Nothing in this proposal changes D-43, D-44 or any Phase 8 decision.

**Cautions**:
- The results cover two validation years only, and the intervals do not capture nationwide shocks.
- In Phase 8, a model that passed validation failed its test (D-42 test outcome).

**Status**: proposed 2026-10-23, when it was not accepted, the models were proposed and not selected, and the arrivals test (2021–2022) and holdout (2023+) could not be accessed. **Accepted 2026-10-23 by the project owner, as written.**
**Accepted form**:
- Conservative HistGradientBoosting is **selected** for all nine cells (Onion, Potato and Wheat × h = 1, 2 and 4), with settings unchanged.
- The project owner authorised a freeze manifest, run-once safeguards, and **one** evaluation on the reserved 2021–2022 arrivals test period. The 2023+ holdout stays reserved.
- The test result cannot revise this selection.
- The freeze and the test are implemented in `Code/modelling/arrivals_final.py`, with outputs in `Processed_Data/modelling/phase09_models/test_2021_2022/`.
**Phase**: 9.
### D-46 — [ACCEPTED 2026-10-23 by the project owner; proposed earlier the same day] Phase 10 scope: descriptive district production context, contract `phase10-production-context-v1`
**Evidence**: `Phase_10_Production_Context_Plan.md` §2 (F1–F17, design window ≤ 2018-19) and §4.
- At most 22 annual points per district in the design window (median 17 / 18 / 22 for Onion / Potato / Wheat).
- A 2–3-year effective forecast horizon under D-47.
- District re-labelling and splits (F14, F15); reporting-method changes in 184 / 179 / 19 districts (F10).

**Proposal**: as `Phase_10_Production_Context_Plan.md` §14, D-46.
**Alternatives considered**: Option B (production forecasting): rejected for now. The annual points are too few and non-stationary, the targets contain unresolved anomalies, and no downstream need has been shown.
**Status**: proposed 2026-10-23; **accepted 2026-10-23 by the project owner** in the form below.
**Accepted form**:
1. **Option A:** Phase 10 builds a descriptive district production context from APY. No production-forecasting model is built or authorised.
2. **Contract `phase10-production-context-v1`** as plan §5, including `available_from`, `information_rule`, `annual_comparability` and `apy_district_code` (APY's own code as published; not an LGD/Census code).
   - Grain: one row per (crop, APY state, APY district, decision agricultural year) where the source district-year exists. A missing row means "not reported" and is never filled.
   - Values are kept as published in `apy_annual.csv`. The only change: yield is null where production is null.
3. **Comparability:** verified annual totals (`verified_total`), Whole Year rows (`whole_year_row`), named-season rows (`single_named_season`) and `ambiguous` records are distinct classes in every output and summary. They are never merged.
4. The three-year trailing summary is **deferred to v1.1**.
5. **Not authorised:** production-based procurement caps and marketable-surplus estimates.

**Phase**: 10.

### D-47 — [ACCEPTED 2026-10-23 by the project owner; proposed earlier the same day] APY information availability (`apy_lag2_policy_v1`) and the Phase 10 design / reserved windows
**Evidence**:
- A-19: one observed release (2022-23 data in the 14-12-2023 update).
- National 2022-23 final estimates appeared in October 2023 (field crops) and about March 2024 (horticulture) (plan S6, S7; secondary sources; the primary pages could not be opened).
- District compilation can lag the national estimates (S5).
- No district-level release history has been verified. Secondary, unverified metadata (India Data Portal; a February 2023 Kaggle mirror) indicates that district coverage of the most recent years was incomplete long after those years ended.

**Proposal**: as `Phase_10_Production_Context_Plan.md` §14, D-47.
**Alternatives considered**: lag 1 (rejected: not available for much of each year, D-36); release-date-specific availability (not possible without a release history).
**Status**: proposed 2026-10-23; **accepted 2026-10-23 by the project owner** in the form below.
**Accepted form**:
1. **`apy_lag2_policy_v1`:** APY year Y1–Y2 becomes usable from 1 July of Y2 + 1. Decision agricultural year t therefore uses source year t − 2 only: never t − 1, and never a later year to backfill an earlier decision. This is a documented **policy assumption**, not a verified or universal publication schedule.
2. **Publication-timing caveat:** the rule is not shown to be conservative for source years 2019-20 onward, and every result that uses those years states this. The file is a single 2023 vintage, so earlier years carry revised, not first-published, values.
3. **Design window:** no quality rule is designed or tuned using source years later than 2018-19. Disclosure: an earlier exploratory profile computed aggregate statistics up to 2020-21; no PQ-1 v1 rule or threshold is derived from it.
4. **Reserved:** source years 2019-20, 2020-21 and 2021-22 are reserved until the contract and PQ-1 are frozen by hash. Later processing is mechanical and follows the approved protocol: only counts per `pq_class` are reported, and the values are read only by approved downstream protocols.
5. **Excluded:** source year 2022-23 is excluded from v1.
6. **Unchanged:** D-36, D-40, D-42, D-45, A-19 and the Phase 6 `apy_*_lag2` features.

**Phase**: 10.

### D-48 — [ACCEPTED 2026-10-23 by the project owner; proposed earlier the same day] PQ-1 v1 production quality rules (flags only; no numerical thresholds active)
**Evidence**: plan §2 F1–F15 (design window only) and §6. The revision 1 candidate hit counts (R6 low side: 120 / 172 / 32 rows) are kept as the record of why thresholds were withdrawn.
**Proposal**: as `Phase_10_Production_Context_Plan.md` §14, D-48.
**Status**: proposed 2026-10-23; **accepted 2026-10-23 by the project owner** in the form below, with **R13 Option 1**.
**Accepted form**:
1. PQ-1 v1 only flags and annotates. It never repairs, clips, imputes or deletes source observations. No unsupported numerical threshold is active.
2. **Specified rules** as plan §6: R1, R2, R4 (manifest diagnostic only; no row flag), R8a, R9 (all crops; no Wheat exception), R10, R11 and R12, with two clarifications:
   - (a) R8a is computed per crop and state;
   - (b) R10 compares against the most recent earlier source year containing a row for the same crop, state and district.
3. **R3** (zero production with positive area) assigns `review`.
4. **R13 (Option 1):** all annual rows for (West Bengal, Potato, 1997-98) and (Gujarat, Potato, 1997-98) are `review`, pending a response from DES. The cause is not labelled a unit error, and the rows are not excluded.
5. **Blocked and inactive** until their evidence exists: the R4 row flag, R5, R6, R7 and R8b. Any activation requires a new decision and a new PQ version.
6. **`pq_class` precedence:** `unusable` (R1, R11, R12) > `review` (R3, R13) > `annotated` (R2, R8a, R9, R10) > `ok`.
7. **Withdrawn, kept on record:** the 10× / 0.1× national-median conventions for R6 / R7, the 1% R4 tolerance, and the Wheat Rabi exception to R9.

**Phase**: 10.
### D-50 — [ACCEPTED 2026-10-24 by the project owner] Candidate price dataset `candidate-prices-v1`: date boundary, scale rule, identities and grade design
**Evidence**: `Data_Source_Review.md` §5.5–§6.11; `Processed_Data/candidates/datagov_prices/decisions_v1/` (mapping decisions, medium review worksheet, R09u evidence, approval checklist).
**Scope**: the versioned candidate experiment only. No production table, frozen output, model or dashboard changes.
**Accepted form**:
1. **U3 / date boundary:** `candidate-prices-v1` uses no data dated before **2024-02-03**. The guard (`CANDIDATE_START`, `assert_no_holdout_inputs`) stays. The reserved 2023 holdout (Phase 8 §P) is **not** evaluated as part of this work, and 2023 is **not** treated as ordinary history. D-40, D-42 and D-45 are unchanged.
2. **R09u:** **not approved and disabled** (`R09U_APPROVED = False`). It is computed for evidence only (`r09u_s1_evidence.csv`), for a separate future review. Phase 5 R09 applies exactly as documented: review ≥ 10× kept; scale error ≥ 50× excluded.
3. **Mappings:** only the 440 recorded one-to-one `approved_candidate_experiment` pairs (`candidate-market-map-v1`). The 14 rejected, 81 unresolved, 605 low-confidence and all 1,053 medium-confidence pairs stay separate identities. The build proceeds with 0 medium-review decisions recorded.
4. **Grades:** primary experiment FAQ-only. FAQ + Local and pooled grades are separate sensitivity experiments. Source grade labels are never changed, and de-duplication never crosses grades.
5. **Duplicates:** exact duplicates are de-duplicated only within an approved identity and the same crop, variety, grade and date, with provenance logged. Conflicting groups are flagged and excluded from targets, never averaged. The March–April 2026 double-reporting pairs stay unresolved; identity is never inferred from matching prices alone.
6. **Price-only:** no arrivals or weather values are created for the candidate period.
**Phase**: candidate data upgrade (not a numbered phase).

### D-51 — [ACCEPTED 2026-10-24 by the project owner] Close the candidate weather experiment; arrivals access next
**Evidence**: `Data_Source_Review.md` §8.7–§8.11 (protocol SHA-256 `ac013ab7a3f7d6baeadbbfa9d6f7a8bf861c69b467d99ee228504380fae56c97`; outputs `Processed_Data/candidates/datagov_prices/experiments/exp_candidate_weather_v1/run/`).
**Accepted form**:
1. **Result recorded as final:** the pre-registered price + weather experiment `exp-candidate-weather-v1` **failed its acceptance rule for Onion, Potato and Wheat**.
   - Skill: Onion −0.17 / −0.48, Potato −0.15 / −0.35, Wheat −0.01 / +0.02, with every 95% interval including or below 0.
   - **Persistence remains the default forecast.**
   - The negative results, the intervals (95% and Bonferroni 99.17%), the multiple-comparison caveat (the second model on the same validation window), the coverage limits (17–29 market clusters per cell) and the byte-identical reproducibility are retained as recorded.
   - The test window and the 2023 holdout were never accessed.
2. **No further weather-model tuning** on the 2026 validation window: no new features, settings, thresholds or populations. A Wheat follow-up would require data after 2026-10-20 and a new pre-registration.
3. **Weather stays out of the candidate and production forecasting pipeline.**
   - The original Phase 3/4 panel, the Phase 6 `wx_*` features, Phase 8 artefacts and the integration code are kept unchanged, as historical analysis.
   - The 2026-10-24 weather vintage stays a candidate artefact (§8.7 version policy).
4. **Next data question:** lawful market-level arrivals.
   - The DMI request draft is prepared but **not sent** (§8.10, `Documentation/Requests/`).
   - CEDA terms are partially verified (§9.1).
   - No new model or protocol until data, evaluation design and approval exist (§9.2).
**Phase**: candidate data upgrade (not a numbered phase).

### D-52 — [ACCEPTED 2026-10-24 by the project owner] One persistence-only evaluation on the candidate test window (prepared; awaiting the final execution gate)
**Named approver**: the project owner.
**Evidence**: `Final_Evaluation_and_Revamp_Plan.md` §1; frozen protocol `exp_candidate_v1_protocol.json` (`Data_Source_Review.md` §7.2.2); D-50, D-51.
**Accepted form**:
1. **Authorisation:** exactly **one** persistence-only evaluation of `exp-candidate-v1` on the reserved candidate test window. The owner explicitly acknowledges that the run reads the test window and is its single use.
2. **Purpose:** estimate the out-of-sample error of the default persistence forecast (prediction = `y_origin`, the origin-week median). Nothing is trained, refitted, tuned, compared for selection or selected. Skill against persistence is trivially 0 and is not reported. The seasonal-naive and climatology baselines are not scored; scoring them would need a separate approval.
3. **Authorised test period:** target-week Sundays **2026-07-05 → 2026-10-18** (target weeks starting Monday 2026-06-29 → 2026-10-12), as in the frozen protocol. Nothing outside it is evaluated.
4. **2023 holdout:** the reserved 2023 holdout (Phase 8 §P) stays inaccessible. No input dated before 2024-02-03 may enter (D-50 guard `CANDIDATE_START`, unchanged). The runner opens only `dataset_v1_1` files and refuses any origin before 2024-02-03.
5. **Frozen identities (SHA-256):**
   - protocol `experiment_design_v1_1/exp_candidate_v1_protocol.json`: LF-normalised `a6b1240c4c4f80da15a02fea946ca5f79f07617d9ccbabb7479ebb65193ae9ee` (the on-disk CRLF file hashes to `009669593eac277574ab5e07e8afecd1d02b1192da0f39d31681cfc6637a740a`);
   - dataset `candidate-prices-v1.1`: `dataset_v1_1/build_manifest.json` `4a04140dc4abd00e8db7beb74f91b56c0102545feab6f9e4c5659f9e226127d6`; `contract.json` `f2433fe2fad4afd0f628a236af58a3b9446085428b61d4716e8e30b606032e6e`; model tables `faq_only` `a2e3aad65a7917ed666ded2468b173365663b5320b799d92589f40870d3f7f2d`, `faq_local` `c2e0ee44b09d0f07e6d537dafd0a2385bd5dc1a9bd3ac768d56513acfa107d9f`, `pooled` `cfdd4ae602d3953618752dfe4f433e7b23504f905ab33d312c15aba9c69744e0`;
   - code, prior experiment outputs and package versions: the D-52 freeze manifest `Processed_Data/candidates/datagov_prices/experiments/exp_candidate_v1/persistence_test_d52/freeze_manifest.json`. It also records the SHA-256 of this entry's text (LF-normalised, up to the next `### ` heading), so any later edit to this entry makes the runner refuse.
6. **Frozen procedure (unchanged from the protocol):** designs `faq_only` (primary), `faq_local` and `pooled` (sensitivity); h = 1 (primary), 2 and 4 (secondary); population `eligible_d41` at the origin; period by target-week Sunday; MAE (primary), RMSE, MAPE with the instability flag (`MAPE_UNSTABLE_SHARE` = 0.20), median APE; market-cluster (`canonical_id`) bootstrap, 10,000 replicates, seed 20261022, here of the MAE level; state-cluster bootstrap and leave-one-state-out as robustness.
7. **Pre-run checks (all before any test row is read):** this entry is present and matches the freeze; every frozen file, code and prior-output hash matches; package versions match; the existing preflight passes (protocol, D-50 approvals, R09u disabled, every v1.1 output hash); the protocol test split equals item 3; no lock, completion record or output exists; the run is started with the explicit confirmation `--confirm-single-test-run D-52`.
8. **One-time guard:** `RUN_LOCK.json` is created with an exclusive create, and flushed to disk, before the first test row is read. Any existing lock refuses every later run, completed or not. **Recovery after an interruption:** the window counts as used. There is no bypass in code, and the lock must not be deleted to rerun. Recovery needs a new owner decision recorded in this log, for example to report the partial outputs, or to authorise one rerun of the identical frozen code.
9. **Reporting:** by crop × horizon × design, and by test month (the Thursday of the target week names the month); market-cluster 95% intervals with their cluster counts; state-level and leave-one-state-out where a crop has at least 2 states; row, market, state, series and target-week coverage; every excluded row with its reason. No precision is claimed beyond the sample (16 target weeks; Wheat concentrated in 5 states).
10. **Use of results:** reporting only. The results must not be used to tune models, select features, or change thresholds, populations or acceptance criteria. Any future learned price model or arrivals experiment needs a fresh evaluation period (data after 2026-10-20) unless separately approved.
11. **Status at recording:** prepared, not executed. Execution waits for the final execution gate. The results will be recorded in a later entry or in `Data_Source_Review.md`, so this entry stays byte-identical.
**Phase**: candidate data upgrade (not a numbered phase).
### D-53 — [RECORDED 2026-10-24 at the project owner's request] D-52 persistence-only test result (reporting only; the candidate test window is consumed)
**Evidence**: `Processed_Data/candidates/datagov_prices/experiments/exp_candidate_v1/persistence_test_d52/`: `RUN_LOCK.json`, `RUN_COMPLETED.json`, `run/run_manifest.json` (SHA-256 `d77f165ae87b7b144c2723f407f73622629788261c9f864c16625ab762999b91`) and six result CSVs; freeze manifest SHA-256 `3298a555e5fad649f10c4d68f1fb8b015960fb466d0f87209b72616e461f1fe7`; `Data_Source_Review.md` §7.6.
**Recorded result**:
1. **Run:** the authorised D-52 run executed **exactly once**, 2026-10-24 14:37:24 → 14:37:30 UTC, exit code 0. The lock was created before any test row was read. The completion record matches the run manifest, the run manifest matches the freeze, and all six outputs match their recorded hashes. The 27 loaded code modules are all in the freeze. It is never rerun.
2. **Scope as frozen:** persistence only (prediction = `y_origin`); target-week Sundays 2026-07-05 → 2026-10-18; designs `faq_only` (primary), `faq_local`, `pooled`; h = 1, 2, 4. Nothing was trained, refitted, tuned, compared or selected. No origin before 2024-02-03 was read, and the 2023 holdout was not accessed.
3. **Primary design `faq_only`** (Rs/quintal, rounded from `run/by_crop.csv`; 95% intervals: market-cluster and state-cluster bootstrap of the MAE level, 10,000 replicates, seed 20261022):

| Crop | h | Rows | Markets / states | MAE [95% market CI] | RMSE | MAPE % | Median APE % | State-cluster 95% CI |
|---|---|---|---|---|---|---|---|---|
| Onion | 1 | 1,048 | 72 / 8 | **231.3** [216.1, 247.7] | 374.3 | 7.6 | 4.3 | [219.4, 249.3] |
| Onion | 2 | 1,035 | 68 / 8 | **387.9** [364.3, 411.7] | 571.2 | 12.3 | 9.0 | [362.7, 402.3] |
| Onion | 4 | 1,023 | 68 / 8 | **678.8** [637.4, 719.3] | 894.5 | 21.0 | 19.6 | [608.4, 730.6] |
| Potato | 1 | 1,137 | 82 / 11 | **32.0** [24.8, 40.6] | 78.9 | 3.5 | 1.1 | [20.9, 55.2] |
| Potato | 2 | 1,122 | 80 / 10 | **45.8** [37.0, 56.6] | 92.7 | 5.1 | 2.6 | [33.4, 71.0] |
| Potato | 4 | 1,093 | 80 / 10 | **66.5** [55.6, 80.3] | 118.9 | 7.7 | 4.9 | [54.6, 92.3] |
| Wheat | 1 | 2,591 | 177 / 5 | **40.7** [34.6, 48.4] | 87.5 | 1.5 | 0.8 | [27.3, 60.4] |
| Wheat | 2 | 2,567 | 176 / 5 | **49.9** [43.7, 57.4] | 93.0 | 1.9 | 1.1 | [33.3, 74.0] |
| Wheat | 4 | 2,528 | 174 / 5 | **68.6** [61.3, 76.9] | 113.3 | 2.6 | 1.9 | [45.4, 104.4] |

   No crop × horizon × design cell, and no month cell, triggers the MAPE instability flag.
4. **Sensitivity designs, h = 1 MAE [95% market CI]:**
   - `faq_local`: Onion 262.8 [252.5, 273.1] (3,668 rows), Potato 33.9 [27.4, 41.3] (1,399), Wheat 40.6 [34.5, 47.8] (2,716);
   - `pooled`: Onion 264.1 [254.7, 273.7] (4,358), Potato 39.6 [33.7, 46.3] (2,058), Wheat 40.6 [35.3, 46.8] (3,207).
5. **By month** (Thursday of the target week; 5 / 4 / 4 / 3 target weeks in Jul / Aug / Sep / Oct):
   - `faq_only` h = 1, Jul / Aug / Sep / Oct: Onion 173.7 / 331.1 / 247.6 / 174.5; Potato 35.1 / 37.6 / 23.4 / 31.2; Wheat 36.0 / 40.4 / 43.4 / 45.4. August is Onion's hardest month at h = 1.
   - **Onion h = 4 September spike:** `faq_only` 1,178.4 [1,075.9, 1,282.8] (255 rows, 63 markets, MAPE 28.6%), against 573.8 / 565.5 / 345.2 in Jul / Aug / Oct. The same spike appears in `faq_local` (1,397.4) and `pooled` (1,361.8). It rests on 4 target weeks; its cause is not established.
6. **State uncertainty:**
   - State-cluster intervals are much wider than market-cluster ones (Wheat h = 1 [27.3, 60.4] from **5 states**; Potato h = 1 [20.9, 55.2]). The market-cluster intervals therefore understate uncertainty about other regions.
   - Leave-one-state-out moves Wheat h = 1 MAE between 28.9 and 57.4; Uttar Pradesh (1,448 rows, MAE 27.6) and Madhya Pradesh (938 rows, MAE 61.7) dominate.
   - Several state cells rest on 1–2 markets (Potato 5 states, Onion 2 states at `faq_only` h = 1) and are anecdotal.
7. **Coverage and exclusions:** every cell covers all **16 target weeks** (2026-06-29 → 2026-10-12). The only exclusion reason is `not_eligible_d41_at_origin` (`faq_only` h = 1: Onion 4,849, Potato 5,149, Wheat 12,962 rows); no row was excluded for a missing origin or a missing or non-positive target. **Limitation:** weeks without an observed target price never appear in the model table, so they cannot appear in the exclusion report; all coverage is conditional on an observed target.
8. **Validation comparison (descriptive only):** the `faq_only` h = 1 persistence MAE on validation (all eligible rows, `baselines_phase8_quarterly/faq_only_h1/persistence_all_eligible_rows.csv`) was Onion 94.7 / 99.7, Potato 57.7 / 41.1, Wheat 41.5 / 34.2 (2026 Q1 / Q2). The test window gives Onion 231.3, Potato 32.0, Wheat 40.7. The periods differ in season, rows and markets; this is **not evidence of a causal change** in forecast performance.
9. **Use:** reporting only (D-52 item 10). The consumed test window must not be used to tune, compare or select models, features, thresholds, populations or acceptance criteria. Future learned price or arrivals models need a fresh evaluation period (data after 2026-10-20) unless separately approved.
10. **Stale post-run test:** `test_real_freeze_verifies_without_reading_records` in the frozen `Code/tests/test_persistence_test_candidate.py` asserts that no lock exists, which was true only before the run. It now fails by design and is left **unchanged and not skipped**, because the file is bound by the D-52 freeze and editing it would break the freeze. The intended post-run invariant (a lock is accompanied by a completion record that matches the run manifest, and the outputs match their hashes) is tested in the new, unfrozen `Code/tests/test_persistence_test_postrun.py`.
**Phase**: candidate data upgrade (not a numbered phase).

### D-54 — [RECORDED 2026-10-25 at the project owner's request] Hadoop / HDFS is outside the implementation scope; PySpark stays an optional environment
**Decision**: Hadoop and HDFS are **not part of the implemented project**. The project owner confirmed on 2026-10-25 that a Hadoop / HDFS deployment is not mandatory for this course project (handout p5 A3 names "Big Data Tools, Hadoop and Pyspark" as a focus; the requirement is met with PySpark and Spark SQL). This closes the "pending instructor guidance" status recorded in `BigData_and_Dashboard_Spec.md`, `Final_Report.md` §8 and `Requirements_Checklist.md`.
**Architecture as built**:
1. **Storage:** local files only. Raw CSV / Excel in `Dataset/` (read-only, D-01); derived CSV and parquet in `Processed_Data/`. No distributed file system.
2. **Big Data processing:** PySpark 4.2.0 / Spark SQL in **local mode on one machine** (`Code/bigdata/mandi_spark.py`: ETL, Q1–Q3, parity against Phase 4 pandas; `mapreduce_demo.py`: a MapReduce-*style* RDD pattern, not Hadoop MapReduce). Its outputs in `Processed_Data/bigdata/` are tracked CSVs, so nothing downstream needs Spark.
3. **Analysis and models:** pandas / numpy / scikit-learn pipelines (Phases 1–10, candidate experiments), notebooks executed with the project interpreter.
4. **Application:** read-only FastAPI (`Code/api/`) over `Code/app/data.py`, and the React frontend (`frontend/`).
**What this is not**: Hadoop / HDFS was **not implemented, installed, benchmarked or experimentally compared**; it was not rejected on technical evidence. The Spark runtimes are single-machine observations, not cluster evidence.
**Dependencies**: PySpark is **not** in the default `requirements.txt`. It is needed only to rerun the Spark ETL or its tests, and lives in the separately documented venv with JDK 21 (root `README.md`, "Optional: Spark environment"); `Code/tests/test_bigdata_spark.py` skips without it. No Hadoop / HDFS code or dependency is added.
**Not changed**: every earlier decision, freeze and evaluation boundary (D-42, D-45, PQ-1, D-52 / D-53).
**Phase**: final scope (not a numbered phase).
