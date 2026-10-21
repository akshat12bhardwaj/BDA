# Crop Feasibility Audit — Phase 2

**Status: [COMPLETED].** This document records the full crop-selection methodology, evidence, and outcome, so no future phase needs to re-derive why Onion, Potato and Wheat were selected.

## Candidate Crops Examined

- **Mandi dataset**: 325 commodity files; 5 confirmed empty in Phase 1 (`Jaggery`, `Ladies Finger`, `Nargasi`, `Saffron`, `Seegu`) → **320 real candidates**.
- Of these 320, **48 passed normalized name-matching against the APY dataset** (40 exact string matches + 8 manually reviewed and confirmed aliases) and form the audited shortlist. The remaining ~272 candidates lack a safe, evidenced APY match and were not carried into detailed auditing — their APY absence would make them unable to support the future Supply Prediction phase regardless of mandi volume. The full 320-row normalization result is preserved in `Processed_Data/crop_name_mapping.csv`.

## Normalization Method

Implemented in `Code/utils/crop_matching.py`:
1. **Normalize**: lowercase, strip parentheses/slashes/dashes/ampersands/periods, collapse whitespace.
2. **Exact match** on the normalized string (40 mandi crops matched an APY crop name exactly this way).
3. **Token-overlap match**: compare meaningful word tokens (length ≥ 3, excluding a stopword list of generic crop-category words — "gram", "seed", "pulses", "bean", "nut", "fruit", "melon", etc. — that were found to cause false positives, e.g. "Alasande Gram" incorrectly matching "Moong(Green Gram)" on the bare word "gram").
4. **Manual review**: every token-overlap match was reviewed. 8 were confirmed as genuine aliases with a documented reason each (e.g. `Jowar(Sorghum)` mandi ↔ `Jowar` APY — same crop, Hindi/English name pair). Others were explicitly rejected as false positives (e.g. "Black Gram" vs "Black Pepper" sharing only the generic word "black"; various unrelated gourds sharing only "gourd"). One case — APY `Rice` vs mandi `Paddy(Dhan)(Common)` — was explicitly **not merged**, since APY production statistics for "Rice" conventionally measure paddy while mandi "Paddy" and mandi "Rice" trade as distinct commodities with different prices; merging them would have been a real misrepresentation.

No aggressive/unreviewed fuzzy matching (edit-distance, phonetic, etc.) was used — every accepted match is either an exact normalized match or a manually justified alias, each visible in `Code/utils/crop_matching.py:MANUAL_ALIAS_NOTES`.

## Audit Criteria (computed, not assumed)

**Mandi**: records, date range, years of coverage, continuity ratio (years with data ÷ year span), states, districts, markets, varieties, price/arrivals missingness, duplicate rows, zero-price rows, min>max-price rows.

**APY**: records, years of coverage, states, districts, seasons, production/yield missingness, zero-production/zero-yield percentage.

**Agri Market**: presence/absence per crop (normalized match against its 5 commodities), with the Phase 1-established caveat that its coverage is Maharashtra/Amravati-only and therefore regional, not national.

## Evidence Summary for the Selected Crops

| Metric | Onion | Potato | Wheat |
|---|---|---|---|
| Mandi records | 2,624,379 | 2,764,987 | 2,593,767 |
| Mandi years (continuity) | 25/25 (1.00) | 25/25 (1.00) | 24/24 (1.00) |
| Mandi states / markets | 32 / 1,714 | 33 / 1,604 | 28 / **1,956** |
| Price missing % | 0.002% | 0.000% | 0.000% |
| APY years | 26/26 | 26/26 | 26/26 |
| APY states | 25 | 28 | 31 |
| APY zero-production % | 0.40% | 0.26% | 0.25% |
| Agri Market coverage | Not available | Not available | Available (Maharashtra/Amravati region only) |

Full computed tables: `Processed_Data/crop_feasibility_mandi.csv`, `Processed_Data/crop_feasibility_apy.csv`, `Processed_Data/crop_dataset_overlap.csv`.

## Why Onion, Potato and Wheat

- All three have **among the highest mandi record counts, market counts and state coverage of the entire 320-crop candidate universe**, and **full or near-full 24–26-year APY coverage with the lowest zero-production rates observed** in the audited shortlist.
- Wheat additionally has **independent Agri Market Dataset cross-validation** (regional, Maharashtra-only, but real), which none of the vegetable candidates have — a genuine triple-source validation case for the project to demonstrate.
- Onion and Potato are high-volatility, highly perishable commodities — the textbook use case for the project's procurement/storage/transportation/selling optimization objective. Wheat adds a government-MSP-influenced staple for contrast, testing the pipeline's crop-agnostic design across different market dynamics.

## Why Close Competitors Were Not Selected

| Crop | Mandi Records | APY Years | Agri Market | Reason not selected |
|---|---|---|---|---|
| Tomato | 2,338,352 (4th highest) | **5 years only**, 22.85% zero-production | No | **Excluded despite high mandi volume** — APY coverage too sparse/unreliable to support Supply Prediction. Direct proof selection was not row-count-driven. |
| Rice | 1,436,499 | 26 (0.16% zero-production — best of all candidates) | No | Comparable APY strength to Wheat but fewer mandi markets (1,167 vs 1,956) and no Agri Market validation. Documented as the strongest alternative cereal. |
| Maize | 1,077,217 | 26 (highest APY record count, 30,781) | No | Strong APY but mandi volume under half of the selected three; adds no diversity beyond Wheat. |
| Soyabean / Cotton / Jowar | 694k–888k | 24–26 | **Yes** | Agri Market bonus present, but primary mandi coverage (states/markets/records) is roughly a third of the selected crops'. |
| Groundnut | 494,008 | 26 (18,623 APY records) | No | Mandi volume well below the selected three. |
| Bengal Gram ("Gram") | 1,165,365 | 26 | No | APY match required a "merged with caution" manual alias rather than an exact match; equally strong exact-matched alternatives were preferred. |

## Important Limitations Carried Forward

1. Zero-price rows (Onion 27,432; Potato 32,502; Wheat 13,327 modal-price zeros) and Min>Max-price rows (~3,000–4,000 per crop) exist in all three selected crops — flagged for Phase 5 cleaning, not fixed here.
2. Duplicate rows exist in all three (Onion 708, Potato 570, Wheat 488) — negligible relative to millions of records, but to be resolved in Phase 5.
3. Wheat's Agri Market cross-validation is regionally restricted (Maharashtra/Amravati only) — it cannot validate Wheat market activity nationally.
4. Onion and Potato have no Agri Market cross-validation source at all.
5. No coordinates exist for any market — Phase 3 must source them from a documented external public source.

## Datasets Used Per Selected Crop

| Crop | Mandi file | APY crop_name | Agri Market | Weather |
|---|---|---|---|---|
| Onion | `Onion.csv` | `Onion` | Not available | Phase 3 (state/district geocoding required) |
| Potato | `Potato.csv` | `Potato` | Not available | Phase 3 (state/district geocoding required) |
| Wheat | `Wheat.csv` | `Wheat` | Available (Maharashtra/Amravati region only) | Phase 3 (state/district geocoding required) |

## Unresolved Issues for Phase 3+

- Determine which states/districts of Onion/Potato/Wheat's mandi footprint to prioritize for weather collection (likely top markets by volume, given full national coverage would be a very large API workload).
- Resolve zero-price / min>max-price rows in Phase 5, with a documented treatment decision (not blind deletion).
- Decide the final date/geographic granularity for integration in Phase 4.

## Status Tags

- Phase 2 — Crop Feasibility Audit & Selection: **[COMPLETED]**
- Phase 3 — Weather Collection: **[CURRENT]**
- Phases 4–14: **[FUTURE]**
