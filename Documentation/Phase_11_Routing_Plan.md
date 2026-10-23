# Phase 11 Plan — Logistics, Routing and Weather-Aware Route Assessment (proposal)

**Status: [PLAN ONLY, 2026-10-23; nothing implemented; no decision accepted].**
- **Re-audited 2026-10-23** after the repository cleanup and history path fix: every finding in §1 is unchanged. There is still no routing, storage or cost code, data or test.
- **Numbering:** roadmap Phase 11 ("Logistics / Dijkstra"). The number and name are unchanged, because D-49 (renaming) is not accepted.
- **Not changed:** nothing in this plan alters D-01 – D-48, any frozen output, or the evaluation boundaries.
- **Crops:** the project's selected crops are **Onion, Potato and Wheat** (D-10). Tomato was considered and excluded at selection (insufficient APY coverage). The design below takes any crop as a parameter, so Tomato or another crop can be added later through the normal selection evidence.

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
