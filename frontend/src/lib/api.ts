import { useQuery } from "@tanstack/react-query";

// Shapes returned by the read-only FastAPI service (Code/api/main.py).
export type Crop = "Onion" | "Potato" | "Wheat";
export const CROPS: Crop[] = ["Onion", "Potato", "Wheat"];

export interface Meta {
  crops: Crop[]; horizons: number[]; states_by_crop: Record<Crop, string[]>; market_years: string[];
  production_years: string[]; latest_full_year: string; verified_locations: number;
  predictions_available: { price: boolean; arrivals: boolean };
}
export interface Kpis {
  year: string; previous_year: string; arrivals_tonnes: number; arrivals_change_pct: number | null;
  typical_price_rs_per_quintal: number; price_change_pct: number | null; typical_markets_per_week: number; weeks_reported: number;
}
export interface Overview {
  crop: Crop; state: string; kpis: Kpis; reports_processed: number;
  coverage: { first_week: string; last_week: string; states_reporting: number; pipeline_cross_check_passed: boolean };
}
export interface Week { week_start: string; records: number; markets: number; arrivals_tonnes_sum: number; modal_price_median: number }
export interface StateYear { state: string; agri_year: string; arrivals_tonnes: number; typical_price: number; typical_markets: number; weeks: number }
export interface TopDistrict { apy_state: string; apy_district: string; mandi_arrivals_tonnes_sum: number; mandi_records: number; arrivals_rank: number }
export interface ProductionRow { apy_state: string; apy_district: string; production_tonnes: number; area_ha: number; yield_t_per_ha: number; pq_class: string; pq_reasons: string | null }
export interface Production { year: string; basis: string; provider_query_pending: boolean; rows: ProductionRow[] }
export interface ReservedCount { crop: Crop; source_apy_year: string; ok: number; annotated: number; review: number; unusable: number }
export interface Location { id: number; state: string; district: string; crops: string; latitude: number; longitude: number; resolution_status: string }
export interface Activity extends Location {
  apy_state: string | null; apy_district: string | null; mandi_records: number | null; mandi_markets: number | null;
  mandi_arrivals_tonnes_sum: number | null; mandi_modal_price_median: number | null; year: string;
}
export interface Climate { state: string; district: string; kind: string; period: string; source: string; months: { month: number; rain_mm: number; tmax_c: number }[] }
export interface Capability { capability: string; status: "available" | "estimate" | "planned" | "missing_data"; detail: string }
export interface RoutingMeta {
  available: boolean; message: string; provider: string; snapshot_date: string; attribution: string;
  pairs: Record<string, number>; speed_assumptions: { road_class: string; assumed_kmh: number; basis: string }[]; capabilities: Capability[];
}
export interface RouteNode {
  node_id: string; name: string; state: string; district: string; crops: string; latitude: number; longitude: number;
  verification: string; location_meaning: string; access_gap_km?: number; network_status?: "on_network" | "endpoint_off_network";
}
export interface NearbyWarehouse { warehouse_id: string; name: string; operator_class: string; facility_type: string; road_distance_km: number; travel_time_h: number }
export interface RouteResult {
  origin_id: string; dest_id: string; objective: "shortest" | "fastest"; status: "ok" | "no_route" | "endpoint_off_network";
  road_distance_km: number | null; travel_time_h: number | null; straight_line_km: number; origin_access_gap_km: number; dest_access_gap_km: number;
  motorway_trunk_share_pct: number | null; maxspeed_tagged_share_pct: number | null; provider: string; snapshot_date: string; attribution: string;
  labels: Record<string, string>; alternatives: Record<string, { road_distance_km: number | null; travel_time_h: number | null }>;
  transport_cost: { available: boolean; reason: string }; geometry: [number, number][] | null; geometry_note: string | null;
  nearby_warehouses: { origin: NearbyWarehouse[]; dest: NearbyWarehouse[] };
}
export type FieldStatus = "verified" | "reported_unverified" | "derived" | "unknown";
export interface WarehouseMeta {
  available: boolean; message: string; records: number; by_operator: Record<string, number>;
  field_status: Record<string, Partial<Record<FieldStatus, number>>>; sources: string[]; attribution: string; capabilities: Capability[];
}
export interface WarehouseRow {
  warehouse_id: string; name: string; latitude: number; longitude: number; operator_class: string; facility_type: string;
  location_status: FieldStatus; capacity_status: FieldStatus; charges_status: FieldStatus; road_distance_km?: number; travel_time_h?: number;
}
export interface WarehouseDetail extends WarehouseRow {
  fields: Record<string, { status: FieldStatus; values: Record<string, string | number | boolean | null> }>;
  derivation: string; coord_method: string; source: string; source_record: string; licence: string; retrieved_utc: string; verified_on: string | null;
}
export interface SeriesKey { state: string; district: string; market: string; variety: string }
export interface SeriesOption extends SeriesKey { origins?: number; test_weeks?: number }
export interface PricePoint { origin_date: string; period: string; observed: number; persistence: number; hgb_conservative: number }
export interface ArrivalPoint { week_no: number; period: string; observed: number; persistence: number; hgb_conservative: number }
export interface PriceMetric { crop: Crop; horizon_weeks: number; approach?: string; config: string; period: string; mae: number; persistence_mae: number; rel_mae_improvement_pct: number }
export interface PriceSummary { baseline_kept: number; cases: number; onion_1w_test_change_pct: number; test: PriceMetric[]; validation: PriceMetric[] }
export interface ArrivalMetric { crop: Crop; horizon_weeks: number; period: string; rel_log_mae_improvement_pct: number; wape_pct: number; persistence_wape_pct: number }
export interface ArrivalsSummary { cells: number; cells_better: number; min_improvement_pct: number; max_improvement_pct: number; test: ArrivalMetric[] }
export interface About {
  sources: { data: string; source: string; coverage: string }[];
  spark: { version: string; java: string; window: string; note: string; mapreduce_label: string; rows_read: number; last_run_seconds: number;
    parity: { column: string; rows_compared: number; mismatches: number }[] };
  reserved_production: { message: string; counts: ReservedCount[] };
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function getJson<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]));
  const res = await fetch(`/api${path}${qs.size ? `?${qs}` : ""}`);
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const d = body?.detail;
    throw new ApiError(res.status, typeof d === "string" ? d : d?.message ?? `Request failed (${res.status})`);
  }
  return body as T;
}

const q = <T,>(key: unknown[], path: string, params?: Record<string, string | number | undefined>, enabled = true) =>
  useQuery<T, ApiError>({ queryKey: [path, ...key], queryFn: () => getJson<T>(path, params), enabled, staleTime: Infinity, retry: false });

export const useMeta = () => q<Meta>([], "/meta");
export const useOverview = (crop: Crop, state?: string) => q<Overview>([crop, state], "/overview", { crop, state });
export const useWeekly = (crop: Crop, state?: string) => q<Week[]>([crop, state], "/markets/weekly", { crop, state }, !!state);
export const useStates = (crop: Crop, year: string) => q<StateYear[]>([crop, year], "/markets/states", { crop, year }, !!year);
export const useYearly = (crop: Crop, states: string[]) => q<StateYear[]>([crop, states.join(",")], "/markets/yearly", { crop, states: states.join(",") }, states.length > 0);
export const useTopDistricts = (crop: Crop, year: string) => q<TopDistrict[]>([crop, year], "/markets/top-districts", { crop, year }, !!year);
export const useProduction = (crop: Crop, year: string, basis: string, quality: string) =>
  q<Production>([crop, year, basis, quality], "/production", { crop, year, basis, quality }, !!year);
export const useReserved = () => q<{ message: string; counts: ReservedCount[] }>([], "/production/reserved");
export const usePriceSummary = () => q<PriceSummary>([], "/outlook/prices/summary");
export const useArrivalsSummary = () => q<ArrivalsSummary>([], "/outlook/arrivals/summary");
export const useSeriesOptions = (kind: "prices" | "arrivals", crop: Crop, horizon: number) =>
  q<SeriesOption[]>([crop, horizon], `/outlook/${kind}/series-options`, { crop, horizon });
export const usePriceSeries = (crop: Crop, horizon: number, s?: SeriesKey) =>
  q<PricePoint[]>([crop, horizon, s], "/outlook/prices/series", { crop, horizon, ...s }, !!s);
export const useArrivalSeries = (crop: Crop, horizon: number, period: string, s?: SeriesKey) =>
  q<ArrivalPoint[]>([crop, horizon, period, s], "/outlook/arrivals/series", { crop, horizon, period, ...s }, !!s);
export const useLocations = () => q<Location[]>([], "/locations");
export const useActivity = (crop: Crop) => q<Activity[]>([crop], "/locations/activity", { crop });
export const useClimate = (id?: number) => q<Climate>([id], `/locations/${id}/climate`, undefined, id !== undefined);
export const useRoutesMeta = () => q<RoutingMeta>([], "/routes");
export const useRouteNodes = () => q<RouteNode[]>([], "/routes/nodes");
export const useRoute = (origin?: string, dest?: string, objective = "shortest") =>
  q<RouteResult>([origin, dest, objective], "/routes/route", { origin, dest, objective }, !!origin && !!dest);
export const useWarehousesMeta = () => q<WarehouseMeta>([], "/warehouses");
export const useWarehouseList = (p: { q?: string; operator?: string; near?: string; radius_km?: number }) =>
  q<{ records: WarehouseRow[]; note: string | null }>([p], "/warehouses/list", p);
export const useWarehouse = (id?: string) => q<WarehouseDetail>([id], `/warehouses/${encodeURIComponent(id ?? "")}`, undefined, !!id);
export const useAbout = () => q<About>([], "/about");
