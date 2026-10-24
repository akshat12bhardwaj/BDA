# Phase 11 Plan — Logistics, Routing and Weather-Aware Route Assessment (proposal)

**Status: [PARTLY IMPLEMENTED, 2026-10-24].** Steps 11a, 11b and 11c, and the storage part of 11e, are built on the owner's instruction of 2026-10-24. 11d (weather along routes), the cost part of 11e, and 11f's decision support are not. See §0. §1 below is the 2026-10-23 audit, kept as written.
- **Numbering:** roadmap Phase 11 ("Logistics / Dijkstra"). The number and name are unchanged, because D-49 (renaming) is not accepted.
- **Not changed:** nothing in this plan alters D-01 – D-48, any frozen output, or the evaluation boundaries.
- **Crops:** the project's selected crops are **Onion, Potato and Wheat** (D-10). Tomato was considered and excluded at selection (insufficient APY coverage). The design below takes any crop as a parameter, so Tomato or another crop can be added later through the normal selection evidence.

---

## 0. Implementation record (2026-10-24)

### RQ-2 — network source: decision and evidence

| Option | Licence / cost | Coverage | Limits | Windows / setup | Verdict |
|---|---|---|---|---|---|
| **Self-built OSM graph**: Geofabrik India zone shapefiles, roads layer; Dijkstra in `scipy.sparse.csgraph` | ODbL 1.0, free | all India; quality varies by region | none (offline) | no new dependency (stdlib shapefile reader + numpy/scipy/shapely already installed); ~10 min build | **chosen**: free, open, offline, byte-reproducible |
| Self-hosted engine (OSRM / openrouteservice) | open source, free | all India from the same OSM data | none | needs Docker or WSL, which is **not installed**; installing it needs approval | not used |
| Self-hosted GraphHopper | Apache-2.0, free | all India | none | runs on the existing JDK 21, but adds a new binary dependency and a server process | possible later upgrade (better speed model); needs approval |
| Hosted openrouteservice | free tier needs an **API key / sign-up** | all India | 2,000 directions / 500 matrix requests per day | — | not used (no sign-up or keys allowed) |
| Public Overpass API (for road extraction) | ODbL, free | — | 2026-10-24: "server at capacity"; asks automated users to run their own instance | — | not used |
| OSRM public demo | free, light use only | — | best-effort; heavy use blocked | — | used **only for four spot-check requests** (validation, below) |

**Snapshot (pinned)**
- **Source files:** `https://download.geofabrik.de/asia/india/<zone>-zone-261022-free.shp.zip` for the central, eastern, northern, southern and western zones, with OSM data up to 2026-10-22. The north-eastern zone holds no verified point.
- **What is stored:**
  - only the roads members are fetched, each by an HTTP range request;
  - each is checked against the zip's CRC-32;
  - hashes are recorded in `Processed_Data/routing/osm_snapshot.csv`;
  - files live outside the repository (`%USERPROFILE%\bda-env\osm`).

### What is built

| Step | Code | Outputs (`Processed_Data/routing/`) | Result |
|---|---|---|---|
| 11a nodes | `Code/routing/nodes.py` | `nodes_v1.csv`, `market_nodes_v1.csv`, `nodes_manifest_v1.csv` | See the 11a notes below |
| 11b network | `Code/routing/osm.py`, `network.py` | `osm_snapshot.csv`, `speed_assumptions_v1.csv`, `routing_manifest_v1.csv` | See the 11b notes below |
| 11c routes | `Code/routing/router.py`, `pipeline.py` | `od_matrix_v1.csv` (4,140 rows), `node_snap_v1.csv`, `route_geometry_v1.parquet` (git-ignored) | See the 11c notes below |
| 11e storage | `Code/routing/storage.py`; contract `Documentation/Warehouse_Data_Contract.md` | `warehouses_v1.csv`, `node_warehouse_v1.csv`, `osm_snapshot_storage.csv`, `osm_buildings_subset_manifest.csv` | See the 11e notes below |
| 11f UI | `Code/api/logistics.py`; `frontend/src/pages/Routes.tsx` | — | See the 11f notes below |

**11a — nodes**
- **46 district points pass.** Each was re-validated against the stored Phase 4 geocoder evidence (exact coordinate match, admin1 = state, coordinates within India).
- **IDs** are stable: `D:<state>|<district>`.
- **Ambiguity:** 8 points had more than one same-district candidate. This is recorded, not changed.
- **Markets:** all 2,657 are listed as `unresolved` (no coordinates). None is placed at a district point.
- **Reproducibility:** `check` rebuilds the table byte for byte.

**11b — network**
- **Roads included:** motorway, trunk, primary, secondary and tertiary, plus their links.
- **Size:** 875,877 ways, 23.1 M vertices, 44.1 M directed edges, 1.21 M km of road.
- **One-way roads** are respected.
- **Join points:** a point joins the network at the nearest two-way vertex of the largest strongly connected component. All 46 points are within 0.91 km.
- **Tertiary roads matter:** without them, direct links such as Yamuna Nagar → Ambala detoured to 108 km, against a real distance of about 60 km.

**11c — routes**
- **All 2,070 ordered pairs route** under both objectives, *shortest* (km) and *fastest* (estimated hours).
- **Road distance:** a network distance.
- **Travel time:** an **estimate**, from assumed goods-vehicle speeds per road class, capped by the OSM `maxspeed` tag. Tags cover 5.2% of edges.
- **Detour ratio** (road ÷ straight line): median 1.15, range 1.02–1.90. The largest values are Nashik ↔ Amreli (around the Gulf of Khambhat) and Kottayam ↔ Alappuzha (the backwaters).
- **Sanity checks:**
  - road distance is never less than the straight line between the joined vertices;
  - shortest is never longer than fastest;
  - fastest is never slower than shortest.
- **Reproducibility:** `check` rebuilds the CSVs byte for byte.

**11e — storage (part)**
- **168 facilities** mapped in OSM: 92 FCI, 35 cold stores, 27 state warehousing corporation, 14 CWC.
- **Name and location:** `reported_unverified`.
- **Operator and type:** `derived`, by documented keyword rules.
- **Capacity, charges, suitability and availability:** `unknown` for every record.
- **Road distances** run from each node to facilities within 150 km of network distance: 278 pairs, 34 nodes, 93 facilities.

**11f — UI (part)**
- **API:** `/api/routes`, `/api/routes/nodes`, `/api/routes/route`, `/api/warehouses`, `/api/warehouses/list`, `/api/warehouses/{id}`.
- **Routes page:** road geometry, labelled estimates, the alternative objective, storage near the destination, "transport cost: not available", provenance and assumed speeds.
- **Warehouses page:** markers, search, operator and near-node filters, detail card with status chips, a coverage card, and an honest "no comparable charges" card.

**Independent validation: four requests to the OSRM public demo, car profile, 2026-10-23T21:26Z** (`validation_osrm_spotcheck_v1.csv`)

| Pair | OSRM km | Ours, shortest km | Difference |
|---|---|---|---|
| Nashik → Pune | 212.6 | 207.7 | −2.3% |
| Yamuna Nagar → Ambala | 59.3 | 60.6 | +2.1% |
| Ludhiana → Ernakulam | 2,714.8 | 2,640.8 | −2.7% |
| Rajkot → Ujjain | 603.7 | 573.7 | −5.0% |

- **Why ours is slightly shorter:** OSRM returns its fastest car route; ours is the shortest-distance route.
- **Travel times:** ours (fastest objective) are 19–45% above OSRM's car times, as intended for a loaded goods vehicle without traffic data. They are labelled as estimates.

### Still not available

**Transport cost**
- No sourced Rs per tonne-km exists (RQ-3), so there is **no cheapest objective**.

**Live data**
- No traffic, closures or road-condition feed (RQ-5).

**Other Phase 11 gaps**
- Weather along the route (11d).
- Market geocoding.
- Verified warehouse capacity and tariffs (see the data contract, §5).
- No buy–store–sell recommendation is made.

### Tests (2026-10-24)

- **`Code/tests/test_routing.py`** (35 tests): synthetic Dijkstra, the one-way and removed-edge cases, unreachable targets, the two-way join rule, the shapefile readers, node validation (bad and missing coordinates, duplicates), warehouse-contract violations, the name rules, de-duplication, and the real OD invariants.
- **`test_api_logistics.py`** (9 tests): real routes, labels, validation errors (404 / 422), 503 when outputs are missing, no numbers on unrouted pairs, and the warehouse contract over the API.
- **Frontend:** 11 Vitest tests.
- **Final verification (2026-10-24):**
  - full suite in the venv: **330 passed, 1 skipped** (the opt-in real-data Spark parity);
  - project Python: **321 passed, 1 skipped**;
  - frontend: **11 passed**; production build OK;
  - integrity audit: **PASS**. That covers the 62 protected hashes, the D-42 and D-45 freezes, AQ-1, and the Phase 8 and 9 outputs unchanged against HEAD;
  - the Phase 10 hash snapshots are unchanged;
  - `nodes check`, `storage check` and `pipeline check` each reproduce byte for byte.

---

## 1. Current-state audit (evidence, 2026-10-23)

| Capability | Status | Evidence |
|---|---|---|
| Road network / routing graph | **Planned but not implemented** | no graph, OSM data or routing code in `Code/`; no road data in `Dataset/` |
| Market / mandi coordinates | **Partially implemented** | 46 verified **district-level** points (`Processed_Data/integration/weather_location_resolution.csv`, admin1 + admin2 rule, D-16). None of the **2,657** distinct markets (567 districts, 33 states, 3 crops) has coordinates. Coordinates must never be guessed (D-16) |
| Warehouse / storage-facility locations | **Blocked by missing data** | no source in the project |
| Distance / travel-time matrix | **Planned but not implemented** | none. `haversine_km` in `Code/integration/pipeline.py` exists only to check geocoding corrections; straight-line distance is not road distance |
| Historical weather | **Data available but not integrated (for routing)** | Open-Meteo daily archive 2001–2022 for the 46 points (`Processed_Data/weather/raw/`, 47 files incl. the Ferozpur correction): temperature mean/max/min, rain, humidity, wind, ET0. Used today only as Phase 6 features |
| Weather forecasts (live) | **Planned but not implemented** | no forecast calls; the collector uses the historical archive only |
| Road closures, traffic, road condition | **Blocked by missing data or external dependencies** | no source; none found with free, India-wide coverage (§4) |
| Routing algorithm / optimisation model | **Planned but not implemented** | `networkx` installed but unused; no PuLP or OR-Tools (Integration Plan §7) |
| Transport cost estimates | **Blocked by missing data** | no Rs/t-km, loading or toll data (the cost-evidence research track P is only proposed: Phase 10 plan §9 / D-49, not accepted) |
| Route visualisation / map | **Planned but not implemented** | no map in the dashboard; `pydeck` comes with Streamlit in the venv but is unused |
| Tests / reproducible outputs for any of the above | **Planned but not implemented** | none |

**Conclusion.** Routing is entirely future work. The only usable inputs today are 46 verified district points and their historical weather.

## 2. Confirmed gaps

1. **Market nodes:** no verified coordinates for markets. Phase 11 cannot route between mandis until markets are geocoded under the D-16 verification rule.
2. **Road network:** no road graph, and no road distance or travel time for any pair of points.
3. **Storage:** no storage or cold-store locations, capacities or tariffs.
4. **Costs:** no transport cost, loading, toll or vehicle data.
5. **Live data:** no live weather forecast and no road-condition, closure or traffic feed.
6. **Decision model:** no buy–store–sell model for routes to feed (Phase 12 is not started).

## 3. Proposed architecture and module boundaries

```
Code/routing/
  nodes.py        node table: verified points only (district centroids now; markets/stores once verified)
  network.py      road graph build from a pinned OSM extract (major roads), or import of a provider OD matrix
  costs.py        edge weights: distance, time, cost, risk; parameters loaded from a sourced, versioned table
  weather.py      route-level weather: historical (archive) vs forecast (live), labelled, cached with timestamps
  router.py       shortest / fastest / cheapest path (Dijkstra; A* on large graphs); feasibility checks
  storage.py      warehouse / cold-store table and storage costs: sourced entries only, each with provenance
  pipeline.py     run_routing(): build nodes -> network -> OD matrix -> manifest (hashes, sources, dates)
Processed_Data/routing/   nodes.csv, od_matrix.csv, edge_attributes.csv, provenance.csv, manifest.csv
Code/app/                 (later) a read-only "Routes" tab over Processed_Data/routing/ only
```

**Boundaries:**
- `router.py` never calls the network; the pipeline does.
- The dashboard reads only cached, versioned outputs, as it does today.
- No module writes into Phase 4–10 folders.

## 4. Candidate data sources and APIs (checked 2026-10-23; recheck before use)

| Need | Candidate | Cost / licence | Limits and caveats |
|---|---|---|---|
| Road geometry | OpenStreetMap extracts (Geofabrik India, six zones) | free, ODbL (attribution and share-alike on the derived database) | about 1.56 GB of `.osm.pbf` across six zones. Coverage and attribute quality (speed limits, surface) vary by region and are not guaranteed |
| Routing engine (self-hosted) | OSRM, GraphHopper, openrouteservice on-premise | free, open source | needs a server process (Docker or WSL; **neither is installed**) and several GB of RAM to build India-scale graphs |
| Routing API (hosted) | openrouteservice free plan | free with an API key | Directions 2,000 per day (40 per minute); Matrix 500 per day (40 per minute); "additional restrictions apply" |
| Routing API (hosted) | OSRM public demo server | free | light, non-commercial, best-effort only; heavy use is blocked; requires ODbL and OSRM attribution and a real User-Agent |
| Commercial routing / traffic | Google Maps Platform (India pricing), Mappls (MapmyIndia), TomTom, HERE | free monthly tiers, then paid | needs a key and billing set-up; terms vary; I found **no free, India-wide road-closure or incident feed** |
| Historical weather | Open-Meteo Historical Weather API (already used) | free for non-commercial use, CC BY 4.0 | < 10,000 calls per day, 5,000 per hour, 600 per minute; reanalysis values are not station observations |
| Weather forecast (live) | Open-Meteo Forecast API | same terms | a forecast is not an observation; it says nothing about the actual state of a road |
| River flood indicator | Open-Meteo Flood API (GloFAS river discharge) | licence to be confirmed | river discharge at grid points, not road flooding; usable only as a risk flag |

**Rule:** every external value is stored with its provider, endpoint, parameters, retrieval time (UTC), licence and attribution text. No live call is made in tests.

## 5. Schemas and location identifiers

- **`nodes.csv`:** `node_id` (stable, e.g. `D:<state>|<district>` or `M:<state>|<district>|<market>`), `node_type` ∈ {district_point, market, storage, destination}, `name`, `state`, `district`, `latitude`, `longitude`, `coord_source`, `verification` (D-16 admin1 + admin2 result), `verified_on`.
  - Markets are joined to the mandi data only through the existing (state, district, market) keys and the D-18 crosswalk. There is no fuzzy matching.
- **`od_matrix.csv`:** `origin_id`, `dest_id`, `road_distance_km`, `travel_time_h`, `profile` (e.g. HGV or car), `provider`, `provider_version`, `osm_snapshot_date`, `retrieved_utc`, `status` ∈ {ok, no_route, not_computed}.
- **`edge_attributes.csv`** (self-built graph only): `u`, `v`, `length_km`, `road_class`, `maxspeed_source` ∈ {osm_tag, assumed_by_class}, `surface`, `toll`.
- **`cost_parameters.csv`:** `parameter`, `value`, `unit`, `vehicle_class`, `source`, `valid_from`. Every value must be **sourced**; anything else is an explicitly labelled assumption approved by decision.
- **`route_weather.csv`:** `route_id`, `sample_point`, `date`, `kind` ∈ {historical, forecast}, `variables`, `provider`, `retrieved_utc`.

## 6. Routing algorithm and cost function

- **Shortest distance:** Dijkstra on non-negative edge lengths. This is exact and simple, and suits a graph of major roads (motorway, trunk, primary, secondary) or a few hundred nodes.
- **Large graphs:** A* with a straight-line (haversine) heuristic is admissible for distance and much faster. For time, the heuristic must divide by the maximum plausible speed to stay admissible.
- **India-scale networks:** at that size, a routing engine (contraction hierarchies in OSRM or GraphHopper) is the practical choice. The project would then store the engine's OD matrix rather than run its own search.
- **Three objectives, reported separately:**
  - *shortest*: minimises km;
  - *fastest*: minimises hours, which needs credible speeds;
  - *cheapest*: minimises Rs, which needs sourced cost parameters.

  These usually pick different routes. A highway detour can be longer but faster and cheaper per tonne, so the UI must show the trade-off rather than one "best" route.
- **Edge weights:**
  - distance = `length_km`;
  - time = `length_km / speed`, where speed comes from the OSM `maxspeed` tag, otherwise from a **labelled, assumed speed per road class**;
  - cost = `tonnes × Rs/t-km × length_km` plus sourced fixed costs (loading, tolls);
  - risk = a weather penalty (§7), kept as a separate column and never folded silently into cost.
- **Feasibility:**
  - An edge with a confirmed closure (only from a reliable feed) is removed.
  - An edge without data is never marked "safe": its status is `unknown`.
  - A route is shown as **feasible** only if every edge has data and no hard constraint is violated. Otherwise it is shown as **not assessable**, with the reason.

## 7. Weather and road-condition strategy

- **Historical vs live:**
  - Historical weather (archive) is used for backtests and seasonal risk profiles, e.g. how often a corridor sees heavy rain in July.
  - Forecasts are used only for current-week warnings.
  - The two are never mixed, and every value is labelled with its kind and timestamp.
- **Rainfall warning flags:** use the India Meteorological Department daily-rainfall categories, *heavy* ≥ 64.5 mm and *very heavy* ≥ 115.6 mm. **Verify these thresholds against IMD's published table before use.** They are flags and penalties, not closures.
- **Heat:** high maximum temperatures matter mainly for **produce quality** (onion and potato sprouting or rotting in transit), not for road feasibility. They are reported as shipment-quality risk.
- **Flooding:** GloFAS river discharge is only a regional risk indicator. It is not evidence that a road is flooded.
- **Road condition:**
  - Without a reliable feed, the plan uses OSM road class and surface tags, labelled "network attributes, not observed condition".
  - The system never claims to know closures or traffic from weather.
  - If a commercial traffic or incident API is approved later, its coverage and timestamp are shown on every result.

## 8. Validation, missing data and fallback

- **Node coordinates:** reuse the D-16 rule (the geocoder's admin1 and admin2 must match). Anything unverified stays unresolved, never guessed.
- **OD sanity checks:**
  - road distance ≥ straight-line distance;
  - travel times within plausible bounds;
  - matrix symmetry within a tolerance (one-way roads allowed).

  Violations are flagged, not fixed.
- **Missing pairs:** `status = not_computed` or `no_route`. A missing pair is never filled with straight-line distance presented as road distance.
- **Provider outage:** use the last cached snapshot, labelled with its retrieval date, or show "not available". Results are never fabricated.

## 9. Tests and end-to-end validation

- **Unit tests** on a small synthetic graph:
  - Dijkstra and A* agree and match known shortest paths;
  - A* gives the same result as Dijkstra when its heuristic is admissible;
  - removing a closed edge changes the route;
  - an edge without data gives `unknown`, not feasible;
  - the cost and time functions compute correctly;
  - weather labels are tagged historical or forecast;
  - no live network call is made (the HTTP client is mocked).
- **Data tests:** nodes have verified coordinates; road distance ≥ haversine; the manifest's hashes match the files.
- **End-to-end:** a pinned OSM snapshot (or cached provider matrix) for a small region, such as the Nashik / Pune / Ahmednagar district points, gives a reproducible OD matrix. It should be spot-checked against published road distances.

## 10. Performance and reproducibility

- **Pinned inputs:** pin the OSM extract (file name, date, SHA-256), or cache the provider matrix with its retrieval date. Rerunning then reproduces the outputs byte for byte, as Phases 4–10 and the Spark component do.
- **Scale:**
  - Start with the 46 verified points: a 46 × 46 matrix is 2,116 pairs, which fits a few free matrix requests.
  - Extend to markets only after they are verified. All 2,657 markets would be about 7 million pairs, which needs a self-hosted engine or a narrower candidate set (for example, the top markets per district by arrivals).
- **No live calls** inside the dashboard or the tests.

## 11. Integration with forecasting, storage and buy–store–sell

- **Phase 12 inputs:** the decision model (LP, then MILP) consumes:
  - the OD **cost** and **time** matrix;
  - price forecasts (D-42: persistence in most cells);
  - arrivals forecasts (D-45);
  - production context (D-46: a slow prior only; **no** production-based cap or marketable surplus).
- **Storage options** wait for sourced storage locations, capacities and tariffs (register P).
- **No sourcing plan before the inputs exist:** route results feed the decision model only when every needed input is sourced. Until then the UI shows routes as **logistics information**, not as a buy–sell recommendation.

## 12. Future map / dashboard requirements (not built in this task)

A read-only "Routes" tab, reading only `Processed_Data/routing/`. It should show:

1. **Selectors:** origin (verified mandi or district point) and destination (market or storage facility). Only verified nodes are selectable.
2. **Route map:** the road route on an interactive map (pydeck or `st.map`, with the OSM attribution shown), plus alternatives.
3. **Route numbers:** road distance (km) and travel time (h), each labelled *computed from network / provider* with the snapshot date. Estimated cost only when sourced parameters exist; otherwise "cost inputs not available".
4. **Weather along the route:** historical climatology for the chosen month, or the current forecast, each labelled with kind, provider and retrieval time.
5. **Warnings:** closures or road-condition warnings only from a reliable feed; otherwise an explicit "no road-condition data" notice.
6. **Comparison table:** distance, time, cost and risk for the alternatives, with feasibility status (feasible / not assessable + reason).
7. **Decision context:** a link to the price and arrivals forecasts for the destination market, and the production context at the origin. For example: "persistence forecast at destination; arrivals trend", but never a profit claim without cost inputs.
8. **Provenance panel:** every source, licence, timestamp and assumption, separating live observations, estimates and historical conditions.

## 13. Dependencies, risks and open decisions

**New dependencies** (approval needed; none installed): `osmnx` or `pyrosm` (for a self-built graph), a routing engine via Docker or WSL (self-hosted), or an openrouteservice API key (hosted). The map can probably use the existing `pydeck`.

**Risks:**
- **Coordinates:** unverified market coordinates; the 46 points are district centroids, not markets.
- **Licences:** API quotas and terms change; ODbL share-alike applies to derived databases.
- **Speeds:** speed assumptions by road class are not observations.
- **Weather:** weather is not road state.
- **Costs:** no cost data, so no "cheapest" route at first.

**Open decisions for the owner:**
- **RQ-1:** node scope. Recommend starting with the 46 verified district points, then markets after verification.
- **RQ-2:** network source. Self-built OSM major-road graph, self-hosted engine, or hosted API.
- **RQ-3:** cost parameters. The sources, or explicit approved assumptions.
- **RQ-4:** weather risk thresholds. Verify the IMD categories.
- **RQ-5:** whether any paid traffic or closure provider is acceptable.
- **RQ-6:** whether Tomato is to be added (needs Phase 2-style evidence).

## 14. Implementation milestones (separate, in order; each needs its own approval)

### Step 11a — Verified geographic node table
- **Scope:** stable identifiers (§5) for district points and markets; destinations and storage facilities only from reliable sources.
- **Validation:** keep the 46 points that passed the D-16 admin1 + admin2 rule. Geocode markets with the same rule. A candidate with a mismatched admin2, several plausible matches, or no match stays **unresolved**; it is never placed at a district centroid or a guessed point.
- **Storage facilities:** included only from a named, dated source (§15). No location is inferred from a market or district name.
- **Accepted when:** every node has `verification = passed` or is listed as unresolved with a reason; there are tests for the identifier scheme and the verification rule; no coordinate exists without a source.

### Step 11b — Road-network foundation
- **Scope:** choose the network source (RQ-2) from §4:
  - a pinned Geofabrik OSM extract with a major-road graph;
  - a self-hosted OSRM / GraphHopper / openrouteservice (needs Docker or WSL, not installed);
  - or the hosted openrouteservice matrix (500 matrix and 2,000 directions requests per day).
- **Representation:** an OD matrix between verified nodes, plus edge attributes when the graph is self-built. Initial search: Dijkstra; A* or contraction hierarchies when the graph is large (§6).
- **Distances:** road distance is always computed on the network. Straight-line distance is used only for sanity checks (road ≥ straight line) and as an A* heuristic, and never shown as road distance.
- **Accepted when:** the source, licence (ODbL / provider terms), attribution, quota and snapshot date are recorded in the manifest, and an offline rerun from the pinned snapshot reproduces the matrix byte for byte.

### Step 11c — Baseline route estimates
- **Scope:** road distance and estimated travel time where the network supports them. **Shortest-distance**, **fastest** and **cheapest** are separate objectives with separate outputs. "Cheapest" stays empty until 11e supplies sourced costs.
- **Feasibility:** an edge or pair without data is `unknown`; a route is `feasible` only if every edge has data and no hard constraint is broken (§6).
- **Accepted when:** unit tests on a synthetic graph cover known shortest paths, Dijkstra / A* agreement, a removed edge changing the route, missing-edge → `not assessable`, and road ≥ straight line.

### Step 11d — Weather integration
- **Scope:** Open-Meteo, or another approved source (§4), sampled along routes.
  - **Historical:** the archive, for climatology and backtests (already collected for the 46 points, 2001–2022).
  - **Forecast:** for current warnings only.
- **Labelling:** every value carries its kind (historical / forecast), provider, retrieval time (UTC) and licence attribution (CC BY 4.0).
- **Never** treated as proof of road condition: rain and heat become **warnings or penalties** with approved thresholds (RQ-4), not closures.
- **Accepted when:** tests show historical and forecast data are never mixed, every value has a timestamp and source, and no live call happens in tests or the dashboard.

### Step 11e — Warehousing and transport cost
- **Scope:** the data in §15. Every value is classed as **measured / published** (with a source), **user-supplied assumption** (entered and labelled as such), or **estimate** (with its method).
- **Model connection:** costs feed the cheapest-route objective and, later, the Phase 12 decision model. The frozen price (D-42) and arrivals (D-45) outputs are only **read**, never retrained or altered. Production context stays a slow prior (D-46), with no cap or marketable surplus.
- **Accepted when:** every cost parameter has a provenance row, no default value is invented, and the cheapest route shows which inputs are assumptions.

### Step 11f — Route visualisation and decision support
- **Scope:** the read-only Routes tab in §12:
  - an interactive map;
  - origin and destination selection (verified nodes only);
  - route alternatives with distance, estimated time and (when available) cost;
  - weather context;
  - only the warnings that are supported by data;
  - a provenance panel.
- **Labelling:** every figure is marked as live observation, estimate, historical condition, or **unavailable**.
- **Accepted when:**
  - an AppTest covers every view, including missing-data states;
  - no live call is made from the app;
  - an end-to-end test runs a pinned small-region fixture through nodes → matrix → route → tab.

### Then Phase 12
The OD cost/time matrix goes to the decision model only after the costs (11e) and storage (§15) are sourced, and Phase 12 itself is approved.

## 15. Warehousing and storage: data needed

| Item | Needed for | Status in this project |
|---|---|---|
| Warehouse / cold-store locations (verified coordinates) | storage nodes | **not available**; candidates are public registries (e.g. WDRA-registered warehouses, state cold-storage lists), each to be checked for licence and accuracy |
| Capacity (tonnes), suitability per crop (onion: ventilated; potato: cold store) | feasibility | not available |
| Storage tariff (Rs/t-month), handling and loading charges | storage cost | not available; would come from published tariffs or user-supplied assumptions |
| Perishability: losses per week by crop and storage type | holding decisions | not available; needs a literature or agronomic source, never a made-up rate |
| Transport cost (Rs/t-km), vehicle classes and payloads, tolls | transport cost | not available (the proposed research track P, D-49, is not accepted) |
| Market fees and commission | sell-side cost | not available |

## 16. Dependencies the existing datasets cannot satisfy

- **No road data:** the project has no road network, distance or travel time; it needs OSM or a routing provider (11b).
- **No market coordinates:** the 2,657 markets need verified geocoding; only 46 district points exist (11a).
- **No storage, cost or perishability data at all** (11e, §15).
- **No live weather and no road condition:**
  - the collected weather is historical only, ending 2022-12-31;
  - no free, India-wide closure, traffic or road-quality feed has been identified (§4, §7).
- **No Phase 12 decision model yet:** routing alone cannot produce buy–store–sell recommendations.
---

**Sources (checked 2026-10-23; recheck before implementation):**
- [OSRM API usage policy](https://github.com/Project-OSRM/osrm-backend/wiki/API%20Usage%20Policy)
- [openrouteservice plans](https://openrouteservice.org/plans/)
- [Open-Meteo terms](https://open-meteo.com/en/terms)
- [Geofabrik India extracts](https://download.geofabrik.de/asia/india.html)
- [TomTom pricing](https://docs.tomtom.com/pricing/price-announcement)
- [Google Maps Platform India pricing](https://mapsplatform.google.com/intl/en_in/pricing/)
