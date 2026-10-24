import { ArrowDownUp, ChevronDown, Route as RouteIcon, Warehouse, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader, Workspace } from "../components/Layout";
import { MapView, type MapPoint } from "../components/MapView";
import { AnalyticsCard, Card, Chip, Dot, Empty, ErrorState, IconButton, Loading, Pill, Q, SearchBox, Segmented, Select } from "../components/ui";
import {
  useRoute, useRouteNodes, useRoutesMeta, useWarehouse, useWarehouseList, useWarehousesMeta,
  type Capability, type FieldStatus, type NearbyWarehouse, type RouteNode, type RouteResult,
} from "../lib/api";
import { cn, int } from "../lib/format";

const STATUS: Record<Capability["status"], { tone: "ok" | "muted" | "bad"; label: string }> = {
  available: { tone: "ok", label: "Available" }, estimate: { tone: "muted", label: "Estimate" },
  planned: { tone: "muted", label: "Planned" }, missing_data: { tone: "bad", label: "Missing data" },
};
const FIELD: Record<FieldStatus, { tone: "ok" | "muted" | "bad"; label: string }> = {
  verified: { tone: "ok", label: "Verified" }, reported_unverified: { tone: "muted", label: "Reported, unverified" },
  derived: { tone: "muted", label: "Derived" }, unknown: { tone: "bad", label: "Unknown" },
};
const OPERATORS: Record<string, string> = { cwc: "Central Warehousing Corp.", fci: "Food Corporation of India", swc: "State Warehousing Corp.", cold_storage: "Cold storage" };
const OP_SHORT: Record<string, string> = { cwc: "CWC", fci: "FCI", swc: "SWC", cold_storage: "Cold storage" };

export const hours = (h: number | null | undefined) => {
  if (h === null || h === undefined) return "–";
  const m = Math.round(h * 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
};
const km = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${v >= 100 ? int(v) : v.toFixed(1)} km`);

function Capabilities({ items }: { items: Capability[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between text-[12px] text-muted">
        <span>Data coverage</span><ChevronDown size={14} className={cn("transition", open && "rotate-180")} />
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5" aria-label="Capabilities">
          {items.map((c) => (
            <li key={c.capability} className="flex items-center gap-3 rounded-xl bg-white/50 px-3 py-2">
              <div className="min-w-0 flex-1"><div className="truncate text-[12.5px] text-ink">{c.capability}</div><div className="truncate text-[11px] text-muted">{c.detail}</div></div>
              <Chip tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Chip>
            </li>))}
        </ul>
      )}
    </div>
  );
}

const Stat = ({ label, value, note }: { label: string; value: string; note?: string }) => (
  <div className="rounded-xl bg-white/60 px-3 py-2">
    <div className="text-[11px] text-faint">{label}</div>
    <div className="mt-0.5 text-[18px] font-light text-ink tabular-nums">{value}</div>
    {note && <div className="text-[10.5px] leading-snug text-muted">{note}</div>}
  </div>
);

function NearbyList({ title, items }: { title: string; items: NearbyWarehouse[] }) {
  return (
    <div>
      <div className="mb-1 text-[11px] text-muted">{title}</div>
      {!items.length ? <p className="text-[11.5px] text-faint">No mapped storage facility within 150 km by road.</p> : (
        <ul className="space-y-1">
          {items.map((w) => (
            <li key={w.warehouse_id} className="flex items-center justify-between gap-2 text-[12px]">
              <span className="truncate"><span className="text-ink">{w.name}</span> <span className="text-muted">· {OP_SHORT[w.operator_class]}</span></span>
              <span className="shrink-0 text-muted tabular-nums">{km(w.road_distance_km)}</span>
            </li>))}
        </ul>
      )}
    </div>
  );
}

function RouteSummary({ r, nodes }: { r: RouteResult; nodes: Map<string, RouteNode> }) {
  const o = nodes.get(r.origin_id)!, d = nodes.get(r.dest_id)!;
  if (r.status !== "ok") {
    return (
      <div role="status" className="rounded-xl border border-line bg-white/80 p-3 text-[12px] leading-relaxed" data-testid="route-unavailable">
        <p className="font-medium text-ink">No road route</p>
        <p className="mt-1 text-muted">{r.status === "endpoint_off_network"
          ? "One of the points is more than 10 km from the road network, so no road distance is given."
          : "The road network has no directed path between these points."}</p>
      </div>
    );
  }
  const other = r.objective === "shortest" ? "fastest" : "shortest";
  const alt = r.alternatives[other];
  return (
    <div className="space-y-3" data-testid="route-result">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Road distance" value={km(r.road_distance_km)} note="on the OSM road network (motorway to tertiary)" />
        <Stat label="Travel time (estimate)" value={hours(r.travel_time_h)} note="assumed speeds; no traffic or stops" />
      </div>
      <dl className="space-y-1 text-[11.5px]">
        <div className="flex justify-between gap-2"><dt className="text-muted">Straight line (not a road distance)</dt><dd className="tabular-nums">{km(r.straight_line_km)}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-muted">Access gap, {o.name} / {d.name}</dt><dd className="tabular-nums">{km(r.origin_access_gap_km)} / {km(r.dest_access_gap_km)}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-muted">On motorway or trunk roads</dt><dd className="tabular-nums">{r.motorway_trunk_share_pct?.toFixed(0)}%</dd></div>
        {alt && <div className="flex justify-between gap-2"><dt className="text-muted">{other === "fastest" ? "Fastest" : "Shortest"} route instead</dt><dd className="tabular-nums">{km(alt.road_distance_km)} · {hours(alt.travel_time_h)}</dd></div>}
        <div className="flex justify-between gap-2"><dt className="text-muted">Transport cost</dt><dd className="text-bad">not available</dd></div>
      </dl>
      {r.geometry_note && <p className="text-[11px] text-muted">{r.geometry_note}</p>}
      <NearbyList title={`Storage near ${d.name} (road distance)`} items={r.nearby_warehouses.dest} />
      <p className="text-[10.5px] leading-snug text-faint">No buy–store–sell recommendation: transport cost, storage capacity and charges are not sourced.</p>
    </div>
  );
}

/** Road routes between verified district points, from the precomputed OSM network outputs. */
export function Routes() {
  const nodesQ = useRouteNodes();
  const meta = useRoutesMeta();
  // ?from=&to=&objective= preselects a route (shareable link)
  const [params, setParams] = useSearchParams();
  const [from, setFrom] = useState<string | undefined>(params.get("from") ?? undefined);
  const [to, setTo] = useState<string | undefined>(params.get("to") ?? undefined);
  const [objective, setObjective] = useState<"shortest" | "fastest">(params.get("objective") === "fastest" ? "fastest" : "shortest");
  const [asked, setAsked] = useState<{ from: string; to: string } | undefined>(from && to ? { from, to } : undefined);
  const route = useRoute(asked?.from, asked?.to, objective);
  const list = nodesQ.data ?? [];
  const byId = useMemo(() => new Map(list.map((n) => [n.node_id, n])), [list]);
  const index = useMemo(() => new Map(list.map((n, i) => [n.node_id, i])), [list]);
  const opts = list.map((n) => ({ value: n.node_id, label: `${n.name}, ${n.state}${n.network_status === "endpoint_off_network" ? " (off network)" : ""}` }));
  const points: MapPoint[] = list.map((n, i) => ({
    id: i, lat: n.latitude, lng: n.longitude, label: `${n.name}, ${n.state}`,
    tone: n.node_id === from ? "ink" : n.node_id === to ? "ok" : "muted",
  }));
  const reset = () => setAsked(undefined);
  const line = asked && route.data?.status === "ok" ? route.data.geometry : null;

  const panel = (
    <Card glass className="flex h-full max-h-[620px] flex-col overflow-hidden lg:max-h-none">
      <div className="border-b border-line/70 px-5 pt-4 pb-3">
        <h2 className="text-[17px]">Plan a route</h2>
        <p className="text-[11px] text-muted">Between verified district points · road network</p>
      </div>
      <div className="thin-scroll min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {nodesQ.isLoading ? <Loading /> : nodesQ.error ? <ErrorState error={nodesQ.error} /> : (
          <form className="space-y-2.5" onSubmit={(e) => {
            e.preventDefault();
            if (!from || !to) return;
            setAsked({ from, to });
            setParams({ from, to, objective }, { replace: true });
          }}>
            <div className="flex items-center gap-2">
              <span className="w-10 text-[11px] text-muted">From</span>
              <Select label="From" placeholder="Choose a district" className="flex-1" value={from ?? ""} onChange={(v) => { setFrom(v); reset(); }} options={opts} />
            </div>
            <div className="flex items-center gap-2">
              <span className="w-10 text-[11px] text-muted">To</span>
              <Select label="To" placeholder="Choose a district" className="flex-1" value={to ?? ""} onChange={(v) => { setTo(v); reset(); }} options={opts.filter((o) => o.value !== from)} />
            </div>
            <Segmented label="Objective" value={objective} onChange={setObjective} options={[{ value: "shortest", label: "Shortest" }, { value: "fastest", label: "Fastest (est.)" }]} />
            <div className="flex gap-2 pt-1">
              <IconButton label="Swap endpoints" disabled={!from || !to} onClick={() => { setFrom(to); setTo(from); reset(); }}><ArrowDownUp size={15} /></IconButton>
              <button type="submit" disabled={!from || !to || !meta.data?.available}
                className={cn("h-9 flex-1 rounded-xl text-[13px] font-medium transition", from && to ? "bg-ink text-white hover:bg-ink/90" : "bg-[#e6e9eb] text-muted")}>Find route</button>
            </div>
          </form>
        )}
        {meta.data && !meta.data.available && <p role="status" className="rounded-xl bg-white/70 p-3 text-[12px] text-muted">{meta.data.message}</p>}
        {asked && (route.isLoading ? <Loading label="Loading route" /> : route.error ? <ErrorState error={route.error} /> :
          route.data && <RouteSummary r={route.data} nodes={byId} />)}
        <Q query={meta}>{(m) => <Capabilities items={m.capabilities} />}</Q>
      </div>
    </Card>
  );

  return (
    <>
      <PageHeader icon={<RouteIcon size={18} />} title="Routes" subtitle={meta.data?.available ? `OSM road network · snapshot ${meta.data.snapshot_date} · no live traffic` : "Road network between verified district points"} />
      <Workspace panel={panel}
        map={<MapView points={points} line={line} selectedId={to ? index.get(to) : undefined}
          fitKey={line ? `${asked?.from}-${asked?.to}-${objective}` : "all"} bottomCards={false} className="h-full w-full" />}
        floating={meta.data?.available && (
          <Card glass className="p-4 text-[11.5px]" data-testid="route-provenance">
            <p className="text-[13px] text-ink">How routes are computed</p>
            <p className="mt-1 leading-snug text-muted">Dijkstra on OSM motorway, trunk, primary, secondary and tertiary roads (one-way respected). Points join the network at the nearest two-way road vertex.</p>
            <table className="mt-2 w-full">
              <caption className="pb-1 text-left text-[10.5px] text-faint">Assumed speeds, km/h (not observed)</caption>
              <tbody>{meta.data.speed_assumptions.filter((s) => !s.road_class.endsWith("_link")).map((s) => (
                <tr key={s.road_class}><td className="text-muted capitalize">{s.road_class}</td><td className="text-right tabular-nums">{s.assumed_kmh}</td></tr>))}
              </tbody>
            </table>
            <p className="mt-2 text-[10px] text-faint">{meta.data.attribution}</p>
          </Card>
        )} />
    </>
  );
}

// ---------------------------------------------------------------- warehouses
function WarehouseCard({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useWarehouse(id);
  return (
    <Card glass className="p-4" data-testid="warehouse-detail">
      <Q query={q} loading="Loading facility">{(w) => (<>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-[16px] leading-snug">{w.name}</h3>
            <p className="flex items-center gap-1.5 text-[11px] text-muted"><Dot tone="ink" />{OPERATORS[w.operator_class]} · {w.coord_method}</p>
          </div>
          <IconButton label="Close details" onClick={onClose} className="size-8"><X size={14} /></IconButton>
        </div>
        <ul className="mt-3 space-y-1.5 text-[12px]">
          {[["Location", "location"], ["Operator / type", "operator"], ["Crop suitability", "suitability"], ["Capacity", "capacity"],
            ["Storage charges", "charges"], ["Availability", "availability"]].map(([label, k]) => {
            const f = w.fields[k];
            return (
              <li key={k} className="flex items-center justify-between gap-2 rounded-xl bg-white/60 px-3 py-1.5">
                <span className="text-muted">{label}</span><Chip tone={FIELD[f.status].tone}>{FIELD[f.status].label}</Chip>
              </li>);
          })}
        </ul>
        <p className="mt-3 text-[10.5px] leading-snug text-faint">{w.source} · {w.source_record} · {w.licence}. Operator and type are derived from the name; capacity, charges and suitability have no source.</p>
      </>)}</Q>
    </Card>
  );
}

export function Warehouses() {
  const meta = useWarehousesMeta();
  const nodes = useRouteNodes();
  const [query, setQuery] = useState("");
  const [operator, setOperator] = useState<string>();
  const [near, setNear] = useState<string>();
  const [radius, setRadius] = useState(100);
  const [sel, setSel] = useState<string>();
  const list = useWarehouseList({ q: query.trim() || undefined, operator, near, radius_km: near ? radius : undefined });
  const rows = list.data?.records ?? [];
  const points: MapPoint[] = rows.map((w, i) => ({ id: i, lat: w.latitude, lng: w.longitude, label: w.name, tone: w.warehouse_id === sel ? "ok" : "ink" }));
  const selIndex = rows.findIndex((w) => w.warehouse_id === sel);
  const m = meta.data;

  const panel = (
    <Card glass className="flex h-full max-h-[620px] flex-col overflow-hidden lg:max-h-none">
      <div className="border-b border-line/70 px-5 pt-4 pb-3">
        <h2 className="text-[17px]">Storage facilities</h2>
        <p className="text-[11px] text-muted">{m ? `${m.records} mapped · 0 verified` : "…"} · OpenStreetMap</p>
      </div>
      <div className="space-y-3 px-4 pt-3">
        <SearchBox value={query} onChange={setQuery} placeholder="Search facilities" />
        <div className="no-scrollbar flex gap-1.5 overflow-x-auto" role="group" aria-label="Filter by operator">
          <Pill className="h-8 px-3" active={!operator} aria-pressed={!operator} onClick={() => setOperator(undefined)}>All</Pill>
          {Object.keys(OPERATORS).map((o) => (
            <Pill key={o} className="h-8 px-3" active={operator === o} aria-pressed={operator === o} onClick={() => setOperator(o)}>{OP_SHORT[o]}</Pill>))}
        </div>
        <div className="flex items-center gap-2">
          <Select label="Near district point" placeholder="Near a district point…" className="min-w-0 flex-1" value={near ?? ""} onChange={setNear}
            options={(nodes.data ?? []).map((n) => ({ value: n.node_id, label: `${n.name}, ${n.state}` }))} />
          {near && <IconButton label="Clear location filter" onClick={() => setNear(undefined)}><X size={14} /></IconButton>}
        </div>
        {near && <Segmented label="Road distance" value={radius} onChange={setRadius} options={[50, 100, 150].map((r) => ({ value: r, label: `${r} km` }))} />}
      </div>
      <div className="thin-scroll mt-3 min-h-0 flex-1 space-y-1.5 overflow-y-auto px-4 pb-4" data-testid="warehouse-list">
        {list.isLoading ? <Loading /> : list.error ? <ErrorState error={list.error} /> : !rows.length ? (
          <Empty title={m?.available ? "No facility matches" : "No warehouse data yet"}>{list.data?.note ?? (near ? `None within ${radius} km by road.` : m?.message)}</Empty>
        ) : rows.slice(0, 300).map((w) => (
          <button key={w.warehouse_id} type="button" onClick={() => setSel(w.warehouse_id === sel ? undefined : w.warehouse_id)} aria-pressed={w.warehouse_id === sel}
            className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition", w.warehouse_id === sel ? "bg-white shadow-soft" : "bg-white/45 hover:bg-white/70")}>
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-[#e9ecee] text-ink/60"><Warehouse size={14} /></span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px]">{w.name}</span>
              <span className="block truncate text-[11px] text-muted">{OP_SHORT[w.operator_class]} · location reported, unverified</span>
            </span>
            {w.road_distance_km !== undefined && <span className="shrink-0 text-[11.5px] text-muted tabular-nums">{km(w.road_distance_km)}</span>}
          </button>
        ))}
        {rows.length > 300 && <p className="px-2 text-[11px] text-faint">Showing 300 of {rows.length}; refine the search.</p>}
      </div>
    </Card>
  );

  const known = (k: string) => (m?.field_status[k]?.verified ?? 0) + (m?.field_status[k]?.reported_unverified ?? 0);
  return (
    <>
      <PageHeader icon={<Warehouse size={18} />} title="Warehouses" subtitle="Mapped storage facilities · names and locations reported, not verified" />
      <Workspace panel={panel}
        map={<MapView points={points} selectedId={selIndex >= 0 ? selIndex : undefined} onSelect={(i) => setSel(rows[i]?.warehouse_id)}
          fitKey={`${operator}-${near}-${radius}-${query}`} className="h-full w-full" />}
        floating={sel && <WarehouseCard id={sel} onClose={() => setSel(undefined)} />}
        bottom={m && <>
          <AnalyticsCard title="Coverage" value={int(m.records)} unit="facilities mapped">
            <ul className="space-y-1.5 text-[12px]" data-testid="warehouse-coverage">
              {Object.entries(m.by_operator).map(([o, n]) => (
                <li key={o} className="flex items-center gap-2">
                  <span className="w-40 truncate text-muted">{OPERATORS[o]}</span>
                  <span className="h-1.5 flex-1 rounded-full bg-line"><span className="block h-1.5 rounded-full bg-ink/70" style={{ width: `${(n / m.records) * 100}%` }} /></span>
                  <span className="w-10 text-right tabular-nums">{n}</span>
                </li>))}
              <li className="pt-1 text-[11px] text-faint">With known capacity: {known("capacity")} · known charges: {known("charges")}</li>
            </ul>
          </AnalyticsCard>
          <AnalyticsCard title="Storage charges" value="–" unit="₹ per tonne-month">
            <Empty title="No comparable charges" className="py-2">No published storage or handling tariffs are in the data, so charges are not compared.</Empty>
          </AnalyticsCard>
        </>} />
    </>
  );
}
