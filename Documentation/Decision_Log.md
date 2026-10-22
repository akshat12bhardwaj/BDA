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
