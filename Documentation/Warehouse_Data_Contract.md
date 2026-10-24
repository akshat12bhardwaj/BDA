# Warehouse data contract (v1)

**Table:** `Processed_Data/routing/warehouses_v1.csv`. Built by `python -B -m Code.routing.storage build`; `check` rebuilds it from the pinned snapshot and compares byte for byte.
**Validation:** `Code/routing/storage.py::validate`. It runs on every build and on every curated input file.

## 1. Value status

Every group of attributes has a `<group>_status` column with one of four values:

| Status | Meaning | Display rule |
|---|---|---|
| `verified` | Checked against an authoritative source on `verified_on` | Show the value with "verified on <date>" |
| `reported_unverified` | Stated by a source and not independently checked (v1: OpenStreetMap contributors) | Show the value with "reported, unverified" |
| `derived` | Computed by a documented rule; the rule is named in `derivation` | Show the value with "derived" and the rule |
| `unknown` | No credible source | Show "unknown". **The value columns must be empty** |

**Hard rules, enforced by `validate`:**
- An `unknown` group has no values.
- A known group has its first value.
- A `verified` value needs `verified_on`.
- Every record has a source and a licence.
- Capacities and charges are numeric and non-negative.
- Available capacity is never above total capacity.
- Coordinates lie within India.
- `warehouse_id` is unique.
- Columns match the contract exactly.

## 2. Columns

| Group (status column) | Value columns | Units / vocabulary |
|---|---|---|
| — | `warehouse_id` | `W:osm:<layer>:<osm_id>` for OSM records; curated sources use their own stable prefix |
| name | `name` | original name, unchanged |
| location | `latitude`, `longitude` | WGS84 degrees; `coord_method` says how they were obtained |
| operator | `operator_class` | `cwc`, `fci`, `swc`, `cold_storage` |
| facility | `facility_type`, `storage_method` | `warehouse` or `cold_storage`; `refrigerated` or empty |
| suitability | `suits_onion`, `suits_potato`, `suits_wheat` | true / false |
| capacity | `capacity_total_t`, `capacity_available_t`, `capacity_as_of` | tonnes; ISO date |
| charges | `storage_charge_rs_per_t_month`, `handling_charge_rs_per_t`, `charges_as_of` | Rs per tonne-month, Rs per tonne; ISO date |
| availability | `available_from` | ISO date |
| provenance | `derivation`, `coord_method`, `source`, `source_record`, `licence`, `retrieved_utc`, `verified_on` | free text, ISO timestamps |

**Not collected:** contact details. Public registers often list personal mobile numbers, and they are not republished.

## 3. Sources in v1

### OpenStreetMap
- **Snapshot:** the Geofabrik India zone extracts, snapshot 2026-10-22 (`261022`), ODbL 1.0. Members and hashes are in `Processed_Data/routing/osm_snapshot_storage.csv`.
- **Layers:** POIs, POI areas and landuse areas.
- **Inclusion rule** (derived, `Code/routing/storage.py RULES`): the name must name a public storage operator, or name a cold store:
  - Central Warehousing Corporation (CWC);
  - Food Corporation of India (FCI);
  - a state warehousing corporation (SWC);
  - a cold store, on areas only. Point POIs named "cold storage" are mostly shops.
- **Excluded:**
  - names indicating staff colonies, offices, roads, schools and similar;
  - features whose OSM class is residential, park, school, hospital and similar;
  - generic "godown" or "warehouse" names, because they give no operator and no agricultural link.
- **De-duplication:** features of the same operator class within 300 m are treated as one facility. The area is preferred over the point.

| Field group | Status in v1 |
|---|---|
| Name | reported, unverified |
| Location | reported, unverified |
| Operator and facility type | derived |
| Suitability, capacity, charges and availability | **unknown for every record** |

### Curated files (`Dataset/warehouses/*.csv`)
- Optional. They must already be in the contract's column layout and carry their licence.
- They are validated, never altered.
- **None exist yet.**

## 4. Sources reviewed and not integrated (checked 2026-10-24)

| Source | What it has | Why not integrated |
|---|---|---|
| WDRA registered-warehouse lists (wdra.gov.in) | name, address, district, registered capacity (t), registration number, validity; some list personal mobile numbers | Downloadable lists date from 2013–2016 (a 2019 list is hosted by Invest India). The live list is a per-state web form with no bulk download. The site states "All rights reserved" and offers no reuse licence. There are no coordinates. **Needs written permission or an open-licence release.** |
| NHB cold-storage subsidy lists (nhb.gov.in PDFs) | name, address, district, capacity (MT) for subsidy-assisted units | Covers subsidy-assisted units only. There are no coordinates. Reuse terms are not stated. |
| data.gov.in / PIB / Parliament answers | state-wise or zone-wise counts and capacity (FCI, CWC, cold storage) | Aggregates only; no facility records |

## 5. What is still needed (data-collection requirement)

1. **Verified facility list.** A licensed or permitted register with coordinates, or addresses geocoded under the D-16-style verification rule. Candidates are WDRA (with permission) and the state warehousing corporations' published depot lists.
2. **Capacity, total and available, with an as-of date.** There is no public live source. This needs operator data or a user-supplied, labelled assumption.
3. **Storage and handling tariffs.** These come from CWC/SWC published tariff schedules, which need checking per state and per year.
4. **Crop suitability.** This means the storage method per facility: ventilated onion stores, cold stores for potato, and grain godowns or silos for wheat. A facility type taken from its name is not evidence of suitability.

Until these exist, the UI shows capacity, charges, availability and suitability as **unknown**. It also makes no storage recommendation.
