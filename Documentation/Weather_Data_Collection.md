# Weather Data Collection — Phase 3

**Status: [COMPLETED]** (with 10 of 46 representative locations left genuinely **[BLOCKED]** — unresolved geocoding, documented below, not fabricated).

## API Source

- **Historical weather**: Open-Meteo Historical Weather Archive API — `https://archive-api.open-meteo.com/v1/archive`
- **Geocoding**: Open-Meteo Geocoding API — `https://geocoding-api.open-meteo.com/v1/search`
- Both are free, public, and documented at https://open-meteo.com.

## API Key Status

**API key not required for the selected public Open-Meteo workflow.** This was verified two ways: (1) `Code/test_openmeteo.py`, reviewed in Phase 1 and re-verified in Phase 3, already worked key-less; (2) Phase 3 made a live, explicit, unauthenticated test call to both endpoints in the notebook (Section 4) and received HTTP 200. No `.env` file, no `Code/config/weather_config.example.env`, and no credential-handling code were created, since none are needed — adding that scaffolding anyway would be an unjustified, unused dependency. No API key, credential, or secret appears anywhere in this project's code, notebooks, outputs, or documentation. `Code/weather/config.py` documents this decision so a future phase does not reintroduce credential handling without first checking whether it is actually required (e.g. if a paid/higher-volume tier is ever needed).

## Geographic Mapping Method

**Source**: Open-Meteo Geocoding API, queried by district name with `country=IN`.

**Method**: for each (State, District) pair, the top candidate results are compared against the requested state (`admin1` field); a location is only accepted if a candidate's state matches. If no candidate matches, the location is recorded as **unresolved** — never guessed or defaulted to a fabricated coordinate. Implemented in `Code/weather/location_mapper.py:geocode_district()`.

**Granularity**: one representative coordinate per district (its principal town, as returned by the geocoder), not per-mandi. Mandi data has up to ~512 unique districts per crop; collecting separate weather per mandi/market would multiply API calls without adding meaningful spatial resolution. This is a deliberate, documented granularity decision (Decision Log D-11).

**Location sample**: rather than mapping all ~500 districts per crop, the **top 20 districts by mandi record volume** were selected per crop (a transparent, reproducible, data-driven sampling rule — not an arbitrary cut), then de-duplicated across Onion/Potato/Wheat into a union of 46 unique (state, district) locations.

**Result**: 36 of 46 (78%) successfully mapped to real coordinates; 10 (22%) unresolved.

## Unresolved Locations (documented, not fabricated)

| State | District | Reason |
|---|---|---|
| Punjab | Bhatinda | No geocoding result (likely official spelling "Bathinda") |
| Uttar Pradesh | Bulandshahar | No geocoding result (likely official spelling "Bulandshahr") |
| Kerala | Palakad | Result state mismatch (likely official spelling "Palakkad") |
| Maharashtra | Ahmednagar | Result state mismatch (renamed "Ahilyanagar" in some sources) |
| West Bengal | Coochbehar | No geocoding result (likely official spelling "Cooch Behar") |
| Rajasthan | Ganganagar | Result state mismatch (likely official name "Sri Ganganagar") |
| Gujarat | Sabarkantha | No geocoding result |
| Maharashtra | Buldhana | No geocoding result |
| Gujarat | Banaskanth | No geocoding result (likely official spelling "Banaskantha") |
| Gujarat | Junagarh | Result state mismatch (likely official spelling "Junagadh") |

These are mandi-dataset spelling variants that do not exactly match the geocoder's gazetteer entries. **No coordinate was guessed for any of these** — they remain `latitude`/`longitude` = null in `Processed_Data/weather/weather_location_mapping.csv`. A future phase could resolve most of these with a small manual spelling-correction alias table (similar in spirit to Phase 2's crop-name aliases), but that was not done in Phase 3 to avoid quietly introducing unverified coordinates under time pressure.

## Weather Variables Collected

| Variable | Source field | Unit | Resolution | Purpose |
|---|---|---|---|---|
| Mean temperature | `temperature_2m_mean` | °C | Daily | Growth/harvest timing (Phase 10 supply features) |
| Max temperature | `temperature_2m_max` | °C | Daily | Heat-stress indicator |
| Min temperature | `temperature_2m_min` | °C | Daily | Frost/cold-stress indicator |
| Rainfall | `rain_sum` | mm | Daily | Production/yield driver; affects arrivals timing |
| Relative humidity | `relative_humidity_2m_mean` | % | Daily | Post-harvest storage-loss driver (Onion/Potato perishability) |
| Wind speed | `wind_speed_10m_mean` | km/h | Daily | Secondary evapotranspiration/storage factor |
| Reference evapotranspiration | `et0_fao_evapotranspiration` | mm | Daily | Standard FAO crop-water-demand indicator |

**Investigated but excluded**: daily-aggregated soil moisture (`soil_moisture_0_to_10cm_mean`) — a live test call in Phase 3 returned `null` values with `"undefined"` units at daily resolution, so it was excluded on evidence, not by default assumption.

Source variable names and units are preserved exactly as Open-Meteo defines them.

## Historical Date Range

**2001-01-01 to 2022-12-31**, chosen as the overlap between mandi reporting (active for all three crops from ~2000–2001 onward, per Phase 1/2) and APY coverage (agricultural years 1997-98 through 2022-23). This is a calendar-year window; APY's agricultural-year format (e.g. `2022-2023`, spanning two calendar years) is **not** converted to a precise calendar alignment in this phase — that decision is explicitly deferred to Phase 4 (see Phase 4 Handoff below).

## Caching Strategy

Each location's weather series is cached to `Processed_Data/weather/raw/<State>_<District>.csv` on first successful fetch. Subsequent requests for the same location check the cache first and skip the API call entirely (verified live in the Phase 3 notebook, Section 12 — `from_cache: True`). This is what allowed Phase 3 to survive a temporary Open-Meteo rate limit (see Limitations) across multiple notebook re-runs without re-fetching already-successful locations.

## Validation Rules Applied

Implemented in `Code/weather/validator.py:validate_weather_dataset()`: expected base/variable columns present; requested date range matches returned range; duplicate dates; missing dates (gap count vs. the full expected calendar); missing values per variable; physically implausible values flagged against loose India-appropriate bounds (e.g. temperature outside −10°C to 55°C) — **flagged, never silently corrected**; coordinate validity (−90..90 / −180..180).

**Result**: all 36 successfully collected locations passed structural validation with **zero missing dates and zero missing values** across the full 2001–2022 window (see `Processed_Data/weather/weather_validation_report.csv`).

## Selected-Crop Coverage Summary

| Crop | States (repr. districts) | Districts in mandi data | Representative districts selected | Mapped | Successfully collected | Unresolved |
|---|---|---|---|---|---|---|
| Onion | 6 | 512 | 20 | 16 | 16 | 4 |
| Potato | 5 | 505 | 20 | 17 | 17 | 3 |
| Wheat | 4 | 457 | 20 | 14 | 14 | 6 |

Full detail: `Processed_Data/weather/weather_coverage_summary.csv`. **This reports coverage for the top-20-by-volume representative districts selected per crop, not for every mandi district each crop appears in** — this distinction is intentional (Section "Weather Granularity") and must not be misread as full district-level weather coverage.

## API Limitations Encountered

Open-Meteo's free public tier enforces per-minute and per-hour request limits. During iterative development, this project's repeated notebook re-runs (before caching was fully populated) triggered both a per-minute (HTTP 429, "Minutely API request limit exceeded") and later an hourly limit. The collector (`Code/weather/collector.py`) now waits out a detected per-minute limit (65s) automatically and paces fresh requests (1.5s between calls); the final successful run collected all 36 mapped locations without any remaining failures. This is documented as a real, encountered API characteristic — not glossed over.

## Reproducibility Instructions

1. Ensure `Code/weather/` is on the Python path (the notebook does this via `sys.path.append`).
2. Re-running `Notebooks/Phase_03_Weather_Data_Collection.ipynb` will reuse every cached file under `Processed_Data/weather/raw/` and only make new API calls for locations not yet cached.
3. To force a fresh fetch for a location, call `collect_weather(..., force_refresh=True)`.
4. No credentials need to be configured.

## Phase 4 Dependency / Handoff Contract

**Input Phase 4 will receive**:
- Selected crops: Onion, Potato, Wheat (Phase 2)
- `Processed_Data/weather/weather_location_mapping.csv` — district → coordinate mapping (36 mapped, 10 unresolved)
- `Processed_Data/weather/raw/*.csv` — validated daily weather series, 2001-01-01 to 2022-12-31, per mapped location
- `Processed_Data/weather/weather_coverage_summary.csv` — per-crop coverage detail
- Mandi data (Onion.csv, Potato.csv, Wheat.csv) and APY data (Phase 1/2)

**Phase 4 will need to decide (not yet done)**:
- How to align mandi records (specific market, specific date) to the nearest mapped weather location (only 36 of each crop's ~500 districts have weather — Phase 4 must decide how non-mapped districts are handled: excluded, or assigned to the nearest mapped location within the same state, with the method documented).
- How to reconcile APY's agricultural-year grain with weather's daily/calendar grain and mandi's daily grain.
- Whether/how to attempt resolving the 10 unresolved locations (e.g. a manual spelling-alias table) before integration, given they represent real, high-volume districts for these crops.

Phase 4 does **not** receive: any integrated/merged dataset (none exists yet — Phase 3 explicitly does not merge weather with mandi/APY).

## Phase 4 Update — Location Verification, Resolution and One Correction

*Added in Phase 4. The Phase 3 sections above are left as the historical record.*

Phase 4 re-checked all 46 locations with a stricter rule. A geocoder candidate is accepted only if `admin1` matches the state **and** `admin2` (the geocoder's district) matches the mandi district, its official APY name, or a documented equivalent (Decision Log D-16; evidence in `Processed_Data/integration/geocoder_evidence_phase4.csv`; result in `Processed_Data/integration/weather_location_resolution.csv`).

| Outcome | Count | Detail |
|---|---|---|
| Phase 3 coordinate verified | 35 | unchanged; Phase 3 cache files reused |
| Previously unresolved, now resolved | 10 | Bhatinda→Bathinda, Bulandshahar→Bulandshahr, Palakad→Palakkad, Ahmednagar→Ahilyanagar, Coochbehar→Koch Bihār (admin2 Cooch Behar), Ganganagar→Sri Ganganagar, Sabarkantha→Himatnagar (district seat, admin2 Sabar Kantha), Buldhana→Buldāna, Banaskanth→Palanpur (admin2 Banas Kantha), Junagarh→Junagadh |
| Phase 3 coordinate rejected and corrected | 1 | **Punjab/Ferozpur**: the Phase 3 point "Ferozpura" (32.30 N, 75.07 E) has admin2 = *Narowal District*, not Firozpur. Corrected to *Firozpur* (30.93 N, 74.61 E, admin2 Firozpur), 159.2 km away |

Weather for the 11 new or corrected points was collected with the unchanged Phase 3 collector into new cache files (the corrected point uses `Punjab_Ferozpur_corrected.csv`; the Phase 3 `Punjab_Ferozpur.csv` is kept but no longer used). All 11 passed the Phase 3 validator: 8,035 days each, 0 missing dates, 0 missing values. **All 46 representative locations now have validated 2001–2022 daily weather.** This is still coverage for the top-20-by-volume districts per crop only (D-12).

## Status Tags

- Phase 3 — Weather Data Collection: **[COMPLETED]** (core pipeline, 36/46 locations)
- Unresolved location set: **[RESOLVED in Phase 4]** — 10/10 resolved with admin2 evidence; 1 Phase 3 mapping (Ferozpur) corrected (see the Phase 4 Update above). Originally [BLOCKED] in Phase 3.
- Phase 4 — Data Integration: **[COMPLETED]**
- Phase 5 — Data Cleaning: **[COMPLETED]** (weather values untouched; no imputation)
- Phase 6 — Feature Engineering: **[COMPLETED]** (trailing weather windows from the Phase 4 panel; same-day weather not a predictor)
- Phase 7 — EDA: **[COMPLETED]** (weather associations analysed on the covered subset only; likely seasonal confounding)
- Phases 8–14: **[FUTURE]**
