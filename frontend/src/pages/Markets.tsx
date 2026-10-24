import { Store } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Legend, Lines, SERIES, ThinBars } from "../components/charts";
import { PageHeader, useCrop, Workspace } from "../components/Layout";
import { MapView, type MapPoint } from "../components/MapView";
import { AnalyticsCard, Card, Chip, Dot, Empty, ErrorState, KpiStat, Loading, Meter, Pill, Q, SearchBox, Segmented, Select } from "../components/ui";
import { useActivity, useMeta, useProduction, useReserved, useStates, useTopDistricts, useYearly } from "../lib/api";
import { cn, compact, int, rs, yr } from "../lib/format";
import { cropOptions } from "./Overview";

export default function Markets() {
  const { crop, setCrop } = useCrop();
  const meta = useMeta();
  const [params, setParams] = useSearchParams();
  const [yearSel, setYear] = useState<string>();
  const year = yearSel ?? meta.data?.latest_full_year ?? "";
  const states = useStates(crop, year);
  const rows = states.data ?? [];
  const wanted = params.get("state");
  const state = rows.find((r) => r.state === wanted)?.state ?? rows[0]?.state;
  const setState = (s: string) => setParams({ state: s }, { replace: true });
  const yearly = useYearly(crop, state ? [state] : []);
  const act = useActivity(crop);
  const [query, setQuery] = useState("");

  const total = rows.reduce((s, r) => s + r.arrivals_tonnes, 0);
  const cur = rows.find((r) => r.state === state);
  const hist = (yearly.data ?? []).filter((r) => r.agri_year <= year);
  const points: MapPoint[] = (act.data ?? []).filter((r) => r.state === state)
    .map((r) => ({ id: r.id, lat: r.latitude, lng: r.longitude, label: `${r.district} · ${r.mandi_records !== null ? `${compact(r.mandi_arrivals_tonnes_sum)} t in ${yr(r.year)}` : "no 2019-20 match"}`, tone: r.mandi_records !== null ? "ok" : "muted" }));

  const panel = (
    <Card glass className="flex h-full max-h-[560px] flex-col overflow-hidden lg:max-h-none">
      <div className="border-b border-line/70 px-5 pt-4 pb-3">
        <h2 className="text-[17px]">States</h2>
        <p className="text-[11px] text-muted">{crop} mandi arrivals · {yr(year)} · ranked</p>
      </div>
      <div className="px-4 pt-3"><SearchBox value={query} onChange={setQuery} placeholder="Search state" /></div>
      <div className="thin-scroll mt-3 min-h-0 flex-1 overflow-y-auto px-4 pb-4" data-testid="state-list">
        <Q query={states} loading="Loading states">{(d) => {
          const list = d.filter((r) => r.state.toLowerCase().includes(query.trim().toLowerCase()));
          if (!list.length) return <Empty title="No matching states" />;
          return (
            <ul className="space-y-1.5">
              {list.map((r) => (
                <li key={r.state}>
                  <button type="button" onClick={() => setState(r.state)} aria-current={r.state === state}
                    className={cn("w-full rounded-xl px-3 py-2 text-left transition", r.state === state ? "bg-white shadow-soft" : "bg-white/40 hover:bg-white/70")}>
                    <div className="flex items-center justify-between gap-2 text-[13px]"><span className="truncate">{r.state}</span><span className="text-ink/80 tabular-nums">{compact(r.arrivals_tonnes)} t</span></div>
                    <div className="mt-1.5 h-px bg-line"><div className="h-px bg-ok" style={{ width: `${(r.arrivals_tonnes / d[0].arrivals_tonnes) * 100}%` }} /></div>
                    <div className="mt-1 flex justify-between text-[11px] text-muted"><span>{rs(r.typical_price)} typical</span><span>{int(r.typical_markets)} markets/wk</span></div>
                  </button>
                </li>
              ))}
            </ul>
          );
        }}</Q>
      </div>
    </Card>
  );

  return (
    <>
      <PageHeader icon={<Store size={18} />} title="Markets" subtitle={<>{crop} · {yr(year)} · historical mandi reports</>}
        kpis={states.error ? <ErrorState error={states.error} /> : !rows.length ? <Loading label="Loading" /> : (
          <>
            <KpiStat value={int(rows.length)} label="States reporting" />
            <KpiStat value={compact(total)} label={`India arrivals t · ${yr(year)}`} />
            <KpiStat value={cur ? rs(cur.typical_price) : "–"} label={`${state} typical / quintal`} />
          </>
        )}
        controls={<>
          <Segmented label="Crop" value={crop} onChange={setCrop} options={cropOptions} />
          <Select label="Agricultural year" className="w-36" value={year} onChange={setYear} options={(meta.data?.market_years ?? []).map((y) => ({ value: y, label: yr(y) }))} />
        </>}
      />
      <Workspace panel={panel}
        map={<MapView points={points} fitKey={`${crop}-${state}`} className="h-full w-full" />}
        floating={state && (
          <Card glass className="p-4">
            <h3 className="text-[15px]">{state}</h3>
            <p className="mt-1 text-[11.5px] leading-snug text-muted">
              {points.length ? `${points.length} verified district point${points.length > 1 ? "s" : ""} shown.` : "No verified district points in this state yet."} Market coordinates are not geocoded, so individual mandis are not placed on the map.
            </p>
          </Card>
        )}
        bottom={<>
          <AnalyticsCard title="Yearly arrivals" value={cur ? compact(cur.arrivals_tonnes) : "–"} unit={`tonnes · ${yr(year)}`}
            meter={cur && total > 0 && <Meter label="Share of India" value={cur.arrivals_tonnes / total} display={`${((cur.arrivals_tonnes / total) * 100).toFixed(0)}%`} />}>
            <div className="h-[130px]">{yearly.isLoading ? <Loading /> : yearly.error ? <ErrorState error={yearly.error} /> :
              <ThinBars data={hist.map((r) => ({ ...r, y: yr(r.agri_year) }))} x="y" y="arrivals_tonnes" name="Arrivals (t)" fmt={(v) => `${int(v)} t`} highlight={(r) => r.agri_year === year} />}
            </div>
          </AnalyticsCard>
          <AnalyticsCard title="Typical price by year" value={cur ? int(cur.typical_price) : "–"} unit="₹ per quintal, median" neutral
            meter={cur && <Meter label="Weeks reported" value={cur.weeks / 53} display={`${cur.weeks}/53`} />}>
            <div className="flex h-[130px] flex-col">
              <Legend items={[{ name: `${state ?? ""} typical price`, color: SERIES.accent }]} />
              <div className="min-h-0 flex-1"><Lines data={hist.map((r) => ({ ...r, y: yr(r.agri_year) }))} x="y" fmt={(v) => `₹${int(v)}`} lines={[{ key: "typical_price", name: "Typical price", color: SERIES.accent }]} /></div>
            </div>
          </AnalyticsCard>
        </>}
      />
      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
        <TopDistricts year={year} />
        <ProductionCard />
      </div>
    </>
  );
}

function TopDistricts({ year }: { year: string }) {
  const { crop } = useCrop();
  const top = useTopDistricts(crop, year);
  return (
    <Card className="p-5">
      <h2 className="text-[17px]">Top districts by arrivals</h2>
      <p className="text-[11px] text-muted">{crop} · {yr(year)} · mandi reports matched to districts</p>
      <div className="mt-3">
        <Q query={top} empty={(d) => d.length === 0}>{(d) => (
          <table className="w-full text-[12.5px]">
            <thead className="text-[10.5px] text-faint"><tr><th className="py-1.5 text-left font-normal">#</th><th className="text-left font-normal">District</th><th className="text-right font-normal">Arrivals</th><th className="text-right font-normal">Reports</th></tr></thead>
            <tbody>{d.slice(0, 10).map((r) => (
              <tr key={`${r.apy_state}-${r.apy_district}`} className="border-t border-line/70">
                <td className="py-2 text-muted tabular-nums">{r.arrivals_rank}</td>
                <td><span className="text-ink">{r.apy_district}</span> <span className="text-muted">· {r.apy_state}</span></td>
                <td className="text-right tabular-nums">{compact(r.mandi_arrivals_tonnes_sum)} t</td>
                <td className="text-right tabular-nums text-muted">{int(r.mandi_records)}</td>
              </tr>))}
            </tbody>
          </table>
        )}</Q>
      </div>
    </Card>
  );
}

const BASES = [
  { value: "verified_total", label: "Verified annual total" },
  { value: "whole_year_row", label: "Whole-year row" },
  { value: "single_named_season", label: "Single named season" },
];

function ProductionCard() {
  const { crop } = useCrop();
  const meta = useMeta();
  const years = meta.data?.production_years ?? []; // design window only (<= 2018-19), straight from the API
  const [ySel, setY] = useState<string>();
  const year = ySel ?? years[0] ?? "";
  const [basis, setBasis] = useState("verified_total");
  const [quality, setQuality] = useState<string[]>(["ok", "annotated"]);
  const prod = useProduction(crop, year, basis, quality.join(","));
  const reserved = useReserved();
  const toggle = (q: string) => setQuality((v) => (v.includes(q) ? v.filter((x) => x !== q) : [...v, q]));

  return (
    <Card className="p-5" data-testid="production-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[17px]">District production</h2>
          <p className="text-[11px] text-muted">{crop} · as published (APY) · values to {yr(years[0] ?? "")} only</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select label="Production year" className="w-32" value={year} onChange={setY} options={years.map((y) => ({ value: y, label: yr(y) }))} />
          <Select label="Basis" className="w-48" value={basis} onChange={setBasis} options={BASES} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-1.5" role="group" aria-label="Quality classes">
        {["ok", "annotated", "review"].map((q) => (
          <Pill key={q} className="h-8 px-3" active={quality.includes(q)} aria-pressed={quality.includes(q)} onClick={() => toggle(q)}>
            <Dot tone={q === "ok" ? "ok" : q === "review" ? "bad" : "muted"} />{q}
          </Pill>
        ))}
        <span className="ml-1 text-[11px] text-faint">Classes are filtered, never merged.</span>
      </div>
      <div className="thin-scroll mt-3 max-h-[300px] overflow-y-auto">
        {!quality.length ? <Empty title="Select at least one quality class" /> : (
          <Q query={prod}>{(p) => (<>
            {p.provider_query_pending && <p className="mb-2 rounded-xl bg-bad-soft/60 px-3 py-2 text-[11.5px]">Some rows for this year await a provider query (R13): treat them with caution.</p>}
            {!p.rows.length ? <Empty title="No rows for this year, basis and quality" /> : (
              <table className="w-full text-[12.5px]">
                <thead className="sticky top-0 bg-surface text-[10.5px] text-faint"><tr><th className="py-1.5 text-left font-normal">District</th><th className="text-right font-normal">Production</th><th className="text-right font-normal">Area</th><th className="text-right font-normal">Yield</th><th className="text-right font-normal">Class</th></tr></thead>
                <tbody>{p.rows.slice(0, 40).map((r) => (
                  <tr key={`${r.apy_state}-${r.apy_district}`} className="border-t border-line/70">
                    <td className="py-1.5"><span className="text-ink">{r.apy_district}</span> <span className="text-muted">· {r.apy_state}</span></td>
                    <td className="text-right tabular-nums">{compact(r.production_tonnes)} t</td>
                    <td className="text-right tabular-nums text-muted">{compact(r.area_ha)} ha</td>
                    <td className="text-right tabular-nums text-muted">{r.yield_t_per_ha?.toFixed(1) ?? "–"}</td>
                    <td className="text-right"><Chip tone={r.pq_class === "ok" ? "ok" : r.pq_class === "review" ? "bad" : "muted"}>{r.pq_class}</Chip></td>
                  </tr>))}
                </tbody>
              </table>)}
          </>)}</Q>
        )}
      </div>
      <div className="mt-4 rounded-xl bg-white/70 p-3" data-testid="reserved-notice">
        <p className="text-[12px] text-ink">Reserved years: counts only</p>
        {reserved.error ? <ErrorState error={reserved.error} /> : (
          <p className="mt-1 text-[11.5px] leading-relaxed text-muted">
            {(reserved.data?.counts ?? []).filter((c) => c.crop === crop).map((c) => `${yr(c.source_apy_year)}: ${c.ok + c.annotated + c.review + c.unusable} rows`).join(" · ")}
            {" "}— values are withheld so they cannot leak into evaluation.
          </p>
        )}
      </div>
    </Card>
  );
}
