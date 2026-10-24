import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import type { MapPoint } from "../components/MapView";

// Leaflet needs a real browser; the stub records exactly which points a page plots.
vi.mock("../components/MapView", () => ({
  MapView: ({ points, line }: { points: MapPoint[]; line?: [number, number][] | null }) => (
    <div data-testid="map" data-count={points.length} data-tones={points.map((p) => p.tone).join(",")} data-line={line?.length ?? 0} />
  ),
}));

const loc = (id: number, district: string, state: string, crops: string) => ({ id, district, state, crops, latitude: 20 + id, longitude: 75 + id, resolution_status: "phase3_verified" });
const LOCS = [loc(0, "Nashik", "Maharashtra", "Onion"), loc(1, "Amreli", "Gujarat", "Wheat"), loc(2, "Agra", "Uttar Pradesh", "Onion,Potato")];
const act = (reported: number[]) => LOCS.map((l) => ({
  ...l, apy_state: l.state, apy_district: l.district, year: "2019-2020",
  ...(reported.includes(l.id) ? { mandi_records: 100, mandi_markets: 3, mandi_arrivals_tonnes_sum: 5000 * (l.id + 1), mandi_modal_price_median: 1600 } : { mandi_records: null, mandi_markets: null, mandi_arrivals_tonnes_sum: null, mandi_modal_price_median: null }),
}));
const week = (d: string, a: number, p: number) => ({ week_start: `${d}T00:00:00`, records: 10, markets: 5, arrivals_tonnes_sum: a, modal_price_median: p });
const CAPS = [{ capability: "Road network and road distances", status: "available", detail: "OSM" }, { capability: "Transport cost", status: "missing_data", detail: "none" }];
const node = (id: number, name: string, state: string) => ({ node_id: `D:${state}|${name}`, name, state, district: name, crops: "Onion", latitude: 20 + id, longitude: 75 + id, verification: "passed", location_meaning: "district reference point", access_gap_km: 1.2, network_status: "on_network" });
const NODES = [node(0, "Nashik", "Maharashtra"), node(1, "Pune", "Maharashtra"), node(2, "Agra", "Uttar Pradesh")];
const ROUTE = (status: string) => ({
  origin_id: "D:Maharashtra|Nashik", dest_id: "D:Maharashtra|Pune", objective: "shortest", status,
  road_distance_km: status === "ok" ? 211.4 : null, travel_time_h: status === "ok" ? 4.5 : null, straight_line_km: 164.3,
  origin_access_gap_km: 0.4, dest_access_gap_km: 0.8, motorway_trunk_share_pct: 80, maxspeed_tagged_share_pct: 10, provider: "OSM", snapshot_date: "2026-10-22",
  attribution: "© OpenStreetMap contributors", labels: {}, alternatives: { shortest: { road_distance_km: 211.4, travel_time_h: 4.5 }, fastest: { road_distance_km: 215, travel_time_h: 4.2 } },
  transport_cost: { available: false, reason: "no sourced cost" }, geometry: status === "ok" ? [[20, 75], [20.5, 75.2], [21, 76]] : null, geometry_note: null,
  nearby_warehouses: { origin: [], dest: [{ warehouse_id: "W:osm:landuse_a:1", name: "FCI Pune", operator_class: "fci", facility_type: "warehouse", road_distance_km: 12.5, travel_time_h: 0.3 }] },
});
const WH = (i: number, name: string, op: string) => ({ warehouse_id: `W:osm:landuse_a:${i}`, name, latitude: 19 + i / 10, longitude: 74, operator_class: op, facility_type: op === "cold_storage" ? "cold_storage" : "warehouse", location_status: "reported_unverified", capacity_status: "unknown", charges_status: "unknown" });
const WHS = [WH(1, "FCI Pune", "fci"), WH(2, "CWC Kalamboli", "cwc"), WH(3, "Agra Cold Storage", "cold_storage")];
const unknownField = (cols: string[]) => ({ status: "unknown", values: Object.fromEntries(cols.map((c) => [c, null])) });

const FIXTURES: Record<string, unknown> = {
  "/api/health": { status: "ok", market_history_end: "2020-06-30", production_values_end: "2018-2019", live_data: false },
  "/api/meta": {
    crops: ["Onion", "Potato", "Wheat"], horizons: [1, 2, 4], latest_full_year: "2019-2020", verified_locations: 3,
    states_by_crop: { Onion: ["Maharashtra", "Gujarat"], Potato: ["Uttar Pradesh"], Wheat: ["Gujarat"] },
    market_years: ["2019-2020", "2018-2019"], production_years: ["2018-2019", "2017-2018"], predictions_available: { price: true, arrivals: true },
  },
  "/api/overview": { crop: "Onion", state: "Maharashtra", reports_processed: 1, kpis: { year: "2019-2020", previous_year: "2018-2019", arrivals_tonnes: 4731451, arrivals_change_pct: -22.2, typical_price_rs_per_quintal: 1600, price_change_pct: 109.8, typical_markets_per_week: 64, weeks_reported: 53 }, coverage: { first_week: "2001-02-05", last_week: "2020-06-29", states_reporting: 32, pipeline_cross_check_passed: true } },
  "/api/markets/weekly": [week("2018-07-02", 900, 800), week("2019-07-01", 1000, 1500), week("2019-07-08", 1200, 1700)],
  "/api/markets/states": [{ state: "Maharashtra", agri_year: "2019-2020", arrivals_tonnes: 4731451, typical_price: 1600, typical_markets: 64, weeks: 53 }, { state: "Gujarat", agri_year: "2019-2020", arrivals_tonnes: 1057169, typical_price: 1850, typical_markets: 17, weeks: 53 }],
  "/api/markets/yearly": [{ state: "Maharashtra", agri_year: "2019-2020", arrivals_tonnes: 4731451, typical_price: 1600, typical_markets: 64, weeks: 53 }],
  "/api/markets/top-districts": [{ apy_state: "Maharashtra", apy_district: "Nashik", mandi_arrivals_tonnes_sum: 2201797, mandi_records: 3550, arrivals_rank: 1 }],
  "/api/production": { year: "2018-2019", basis: "verified_total", provider_query_pending: false, rows: [{ apy_state: "Andhra Pradesh", apy_district: "Kurnool", production_tonnes: 751476, area_ha: 21827, yield_t_per_ha: 34.4, pq_class: "ok", pq_reasons: null }] },
  "/api/production/reserved": { message: "counts only", counts: [{ crop: "Onion", source_apy_year: "2019-2020", ok: 231, annotated: 241, review: 0, unusable: 2 }] },
  "/api/locations": LOCS,
  "/api/locations/0/climate": { state: "Maharashtra", district: "Nashik", kind: "historical", period: "2001-2022", source: "Open-Meteo", months: Array.from({ length: 12 }, (_, i) => ({ month: i + 1, rain_mm: i * 10, tmax_c: 30 })) },
  "/api/routes": { available: true, message: "Road routes", provider: "OSM", snapshot_date: "2026-10-22", attribution: "© OpenStreetMap contributors", pairs: { ok: 2070 }, speed_assumptions: [{ road_class: "motorway", assumed_kmh: 65, basis: "assumption" }], capabilities: CAPS },
  "/api/routes/nodes": NODES,
  "/api/warehouses": { available: true, message: "3 mapped", records: 3, by_operator: { fci: 1, cwc: 1, cold_storage: 1 }, field_status: { location: { reported_unverified: 3 }, capacity: { unknown: 3 }, charges: { unknown: 3 } }, sources: ["OpenStreetMap"], attribution: "© OpenStreetMap contributors", capabilities: CAPS },
  "/api/warehouses/W:osm:landuse_a:1": { ...WH(1, "FCI Pune", "fci"), derivation: "keyword rule", coord_method: "centroid of OSM area", source: "OpenStreetMap", source_record: "landuse_a osm_id 1", licence: "ODbL", retrieved_utc: "2026-10-24", verified_on: null,
    fields: { location: { status: "reported_unverified", values: { latitude: 19.1, longitude: 74 } }, operator: { status: "derived", values: { operator_class: "fci" } }, suitability: unknownField(["suits_onion"]), capacity: unknownField(["capacity_total_t"]), charges: unknownField(["storage_charge_rs_per_t_month"]), availability: unknownField(["available_from"]) } },
  "/api/outlook/prices/summary": { baseline_kept: 8, cases: 9, onion_1w_test_change_pct: -1.58, test: [], validation: [] },
  "/api/outlook/arrivals/summary": { cells: 18, cells_better: 18, min_improvement_pct: 2.3, max_improvement_pct: 13.5, test: [] },
  "/api/outlook/prices/series-options": [{ state: "Kerala", district: "Alappuzha", market: "Chengannur", variety: "Small", origins: 104 }],
  "/api/outlook/prices/series": [{ origin_date: "2019-01-06T00:00:00", period: "val_2019", observed: 4000, persistence: 3450, hgb_conservative: 3700 }],
  "/api/about": { sources: [{ data: "Mandi prices", source: "Open data", coverage: "to Jun 2020" }], spark: { version: "4.2.0", java: "21", window: "<= 2020-06-30", note: "local", mapreduce_label: "not Hadoop", rows_read: 7983133, last_run_seconds: 107.8, parity: [{ column: "key_set", rows_compared: 16673, mismatches: 0 }] }, reserved_production: { message: "counts only", counts: [] } },
};

let calls: URL[] = [];
let overrides: Record<string, number> = {};

beforeEach(() => {
  calls = [];
  overrides = {};
  vi.stubGlobal("fetch", vi.fn(async (input: string) => {
    const url = new URL(input, "http://test");
    calls.push(url);
    const status = overrides[url.pathname];
    if (status) return new Response(JSON.stringify({ detail: "boom" }), { status });
    let body = FIXTURES[decodeURIComponent(url.pathname)];
    if (url.pathname === "/api/routes/route") body = ROUTE(url.searchParams.get("dest")?.includes("Agra") ? "no_route" : "ok");
    if (url.pathname === "/api/warehouses/list") {
      const op = url.searchParams.get("operator");
      body = { records: WHS.filter((w) => !op || w.operator_class === op), note: null };
    }
    if (url.pathname === "/api/locations/activity") body = act(url.searchParams.get("crop") === "Onion" ? [0, 1] : [2]);
    return body === undefined ? new Response(JSON.stringify({ detail: "not found" }), { status: 404 }) : new Response(JSON.stringify(body), { status: 200 });
  }));
});

function renderAt(path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>);
}
const heading = () => screen.getByRole("heading", { level: 1 });

describe("navigation", () => {
  it("reaches all six sections from the top nav", async () => {
    const user = userEvent.setup();
    renderAt();
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const [link, title] of [["Markets", "Markets"], ["Price Outlook", "Price Outlook"], ["Routes", "Routes"], ["Warehouses", "Warehouses"], ["About & Data", "About & Data"], ["Overview", "Maharashtra"]]) {
      await user.click(within(nav).getByRole("link", { name: link }));
      await waitFor(() => expect(heading()).toHaveTextContent(title));
    }
  });
});

describe("overview", () => {
  it("shows API KPIs and filters the verified-location list", async () => {
    const user = userEvent.setup();
    renderAt();
    expect(await screen.findByTestId("kpi-arrivals")).toHaveTextContent("4.73M");
    const list = screen.getByTestId("location-list");
    await waitFor(() => expect(within(list).getAllByRole("button", { expanded: false })).toHaveLength(3));
    await user.click(screen.getByRole("button", { name: /Wheat/, pressed: false }));
    expect(within(list).getAllByRole("button", { expanded: false })).toHaveLength(1);
    expect(within(list).getByText("Amreli")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "All" }));
    await user.type(screen.getByPlaceholderText("Search district or state"), "agra");
    expect(within(list).getByText("Agra")).toBeInTheDocument();
    expect(within(list).queryByText("Nashik")).not.toBeInTheDocument();
    await user.clear(screen.getByPlaceholderText("Search district or state"));
    await user.type(screen.getByPlaceholderText("Search district or state"), "zzz");
    expect(within(list).getByText("No matching locations")).toBeInTheDocument();
  });

  it("marks only points with 2019-20 reports as reported", async () => {
    renderAt();
    await waitFor(() => expect(screen.getByTestId("map")).toHaveAttribute("data-count", "3"));
    const tones = screen.getByTestId("map").dataset.tones!.split(",");
    expect(tones.filter((t) => t === "ok")).toHaveLength(2);            // Nashik, Amreli have Onion reports; Agra does not
  });

  it("opens the floating detail card with historical climate", async () => {
    const user = userEvent.setup();
    renderAt();
    await user.click(await screen.findByRole("button", { name: /Nashik/ }));
    const card = await screen.findByTestId("floating-card");
    expect(card).toHaveTextContent("Historical averages, not a forecast");
    expect(await within(card).findByRole("img", { name: /monthly rainfall/i })).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Open-Meteo.com" })).toHaveAttribute("href", "https://open-meteo.com/");
  });

  it("shows an error state when the API fails", async () => {
    overrides["/api/overview"] = 500;
    renderAt();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load this data (500)");
  });
});

async function choose(user: ReturnType<typeof userEvent.setup>, box: string, option: string) {
  await user.click(await screen.findByRole("combobox", { name: box }));
  await user.click(await screen.findByRole("option", { name: option }));
}

describe("routes and warehouses", () => {
  it("routes: shows the computed road route, labelled estimates and no cost", async () => {
    const user = userEvent.setup();
    renderAt("/routes");
    await waitFor(() => expect(screen.getByTestId("map")).toHaveAttribute("data-count", "3"));
    expect(screen.getByTestId("map")).toHaveAttribute("data-line", "0");                    // nothing drawn before a route exists
    await choose(user, "From", "Nashik, Maharashtra");
    await choose(user, "To", "Pune, Maharashtra");
    await user.click(screen.getByRole("button", { name: "Find route" }));
    const res = await screen.findByTestId("route-result");
    expect(res).toHaveTextContent("211 km");
    expect(res).toHaveTextContent("4 h 30 min");
    expect(res).toHaveTextContent("Straight line (not a road distance)");
    expect(res).toHaveTextContent(/Transport cost\s*not available/);
    expect(res).toHaveTextContent("FCI Pune");
    expect(screen.getByTestId("map")).toHaveAttribute("data-line", "3");                    // the API's road geometry, unchanged
    expect(screen.getByTestId("map").dataset.tones).toBe("ink,ok,muted");
  });

  it("routes: a shared link preselects and loads the route", async () => {
    renderAt("/routes?from=D%3AMaharashtra%7CNashik&to=D%3AMaharashtra%7CPune&objective=fastest");
    expect(await screen.findByTestId("route-result")).toHaveTextContent("211 km");
    expect(calls.some((u) => u.pathname === "/api/routes/route" && u.searchParams.get("objective") === "fastest")).toBe(true);
  });

  it("routes: an unroutable pair shows no numbers and no line", async () => {
    const user = userEvent.setup();
    renderAt("/routes");
    await choose(user, "From", "Nashik, Maharashtra");
    await choose(user, "To", "Agra, Uttar Pradesh");
    await user.click(screen.getByRole("button", { name: "Find route" }));
    expect(await screen.findByTestId("route-unavailable")).toHaveTextContent("No road route");
    expect(screen.getByTestId("map")).toHaveAttribute("data-line", "0");
    expect(screen.queryByTestId("route-result")).not.toBeInTheDocument();
  });

  it("warehouses: markers, operator filter, and unknown capacity and charges", async () => {
    const user = userEvent.setup();
    renderAt("/warehouses");
    await waitFor(() => expect(screen.getByTestId("map")).toHaveAttribute("data-count", "3"));
    await user.click(within(screen.getByRole("group", { name: "Filter by operator" })).getByRole("button", { name: "FCI" }));
    await waitFor(() => expect(screen.getByTestId("map")).toHaveAttribute("data-count", "1"));
    expect(calls.some((u) => u.pathname === "/api/warehouses/list" && u.searchParams.get("operator") === "fci")).toBe(true);
    await user.click(within(screen.getByTestId("warehouse-list")).getByRole("button", { name: /FCI Pune/ }));
    const card = await screen.findByTestId("warehouse-detail");
    expect(card).toHaveTextContent("Reported, unverified");
    expect(within(card).getAllByText("Unknown").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("No comparable charges")).toBeInTheDocument();
    // counts of known values ("With known capacity: 0") are fine; capacity or tariff figures are not
    expect(document.body.textContent).not.toMatch(/\d+\s?(t|tonnes)\s+capacity|₹\s?\d+\s*(\/|per)\s*t/i);
  });
});

describe("data boundaries", () => {
  it("offers production values only through 2018-19 and reserved years as counts", async () => {
    renderAt("/markets");
    const card = await screen.findByTestId("production-card");
    expect(await within(card).findByText("Kurnool")).toBeInTheDocument();
    const years = calls.filter((u) => u.pathname === "/api/production").map((u) => u.searchParams.get("year")!);
    expect(years.length).toBeGreaterThan(0);
    expect(years.every((y) => y <= "2018-2019")).toBe(true);
    const notice = within(card).getByTestId("reserved-notice");
    expect(notice).toHaveTextContent("2019-20: 474 rows");
    expect(notice.textContent).not.toMatch(/tonnes|ha\b|yield/i);
  });

  it("never requests holdout periods or dates after the stored windows", async () => {
    renderAt("/outlook");
    expect(await screen.findByText("Chengannur, Alappuzha")).toBeInTheDocument();
    for (const u of calls) {
      expect(u.search).not.toMatch(/holdout|202[3-9]/);
    }
  });
});
