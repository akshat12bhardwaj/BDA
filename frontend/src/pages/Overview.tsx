import { ChevronDown, LayoutGrid, MapPin, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Legend, Lines, SERIES, ThinBars } from "../components/charts";
import { PageHeader, useCrop, Workspace } from "../components/Layout";
import { MapView, type MapPoint } from "../components/MapView";
import { AnalyticsCard, Card, Chip, Dot, Empty, ErrorState, IconButton, KpiStat, Loading, Meter, Pill, SearchBox, Segmented, Select } from "../components/ui";
import { CROPS, useActivity, useClimate, useMeta, useOverview, useStates, useWeekly, type Activity, type Crop, type Week } from "../lib/api";
import { agriYear, cn, compact, int, MONTHS, rs, shortDate, yr } from "../lib/format";

export const cropOptions = CROPS.map((c) => ({ value: c, label: c }));

/** Verified-locations panel + map + floating detail card + weekly arrivals / price cards. */
export default function Overview() {
  const { crop, setCrop } = useCrop();
  const meta = useMeta();
  const [stateSel, setStateSel] = useState<string>();
  const states = meta.data?.states_by_crop[crop] ?? [];
  const state = stateSel && states.includes(stateSel) ? stateSel : states[0];
  const ov = useOverview(crop, state);
  const weekly = useWeekly(crop, state);
  const india = useStates(crop, meta.data?.latest_full_year ?? "");
  const act = { Onion: useActivity("Onion"), Potato: useActivity("Potato"), Wheat: useActivity("Wheat") };
  const [selected, setSelected] = useState<number>();

  const k = ov.data?.kpis;
  const last26 = (weekly.data ?? []).slice(-26);
  const thisYear = useMemo(() => (weekly.data ?? []).filter((w) => agriYear(w.week_start) === k?.year), [weekly.data, k?.year]);
  const indiaTotal = (india.data ?? []).reduce((s, r) => s + r.arrivals_tonnes, 0);

  return (
    <>
      <PageHeader
        icon={<LayoutGrid size={18} />}
        title={state ?? "Overview"}
        subtitle={<>{crop} · {k ? yr(k.year) : "…"} agri year · historical</>}
        kpis={ov.error ? <ErrorState error={ov.error} /> : !k ? <Loading label="Loading KPIs" /> : (
          <>
            <KpiStat testId="kpi-arrivals" value={compact(k.arrivals_tonnes)} label={`Arrivals t · ${yr(k.year)}`} change={k.arrivals_change_pct} spark={last26.map((w) => w.arrivals_tonnes_sum)} />
            <KpiStat testId="kpi-price" value={rs(k.typical_price_rs_per_quintal)} label="Typical price / quintal" change={k.price_change_pct} neutral spark={last26.map((w) => w.modal_price_median)} />
            <KpiStat testId="kpi-markets" value={int(k.typical_markets_per_week)} label="Markets / week" spark={last26.map((w) => w.markets)} />
          </>
        )}
        controls={
          <>
            <Segmented label="Crop" value={crop} onChange={(c) => { setCrop(c); setStateSel(undefined); }} options={cropOptions} />
            <Select label="State" className="w-40" value={state ?? ""} onChange={setStateSel} options={states.map((s) => ({ value: s, label: s }))} />
          </>
        }
      />
      <OverviewWorkspace crop={crop} act={act} selected={selected} setSelected={setSelected}
        bottom={<>
          <AnalyticsCard title="Weekly arrivals" value={k ? compact(k.arrivals_tonnes) : "–"} unit={`tonnes · ${k ? yr(k.year) : ""}`} change={k?.arrivals_change_pct}
            meter={k && indiaTotal > 0 && <Meter label="Share of India" value={k.arrivals_tonnes / indiaTotal} display={`${((k.arrivals_tonnes / indiaTotal) * 100).toFixed(0)}%`} />}>
            {weekly.isLoading ? <Loading /> : weekly.error ? <ErrorState error={weekly.error} /> :
              <div className="h-[130px]" aria-label={`Weekly ${crop} arrivals in ${state}, ${k?.year}`}>
                <ThinBars data={thisYear.map((w) => ({ ...w, week: shortDate(w.week_start) }))} x="week" y="arrivals_tonnes_sum" name="Arrivals (t)" fmt={(v) => `${int(v)} t`} />
              </div>}
          </AnalyticsCard>
          <PriceTrendCard weekly={weekly.data ?? []} year={k?.year} prev={k?.previous_year} price={k?.typical_price_rs_per_quintal} change={k?.price_change_pct} weeks={k?.weeks_reported} />
        </>}
      />
    </>
  );
}

function PriceTrendCard({ weekly, year, prev, price, change, weeks }: { weekly: Week[]; year?: string; prev?: string; price?: number; change?: number | null; weeks?: number }) {
  // Align the two agricultural years week by week (week 1 = first July week).
  const data = useMemo(() => {
    const cur = weekly.filter((w) => agriYear(w.week_start) === year);
    const old = weekly.filter((w) => agriYear(w.week_start) === prev);
    return Array.from({ length: Math.max(cur.length, old.length) }, (_, i) => ({
      week: cur[i] ? shortDate(cur[i].week_start) : `Week ${i + 1}`, current: cur[i]?.modal_price_median ?? null, previous: old[i]?.modal_price_median ?? null,
    }));
  }, [weekly, year, prev]);
  return (
    <AnalyticsCard title="Price trend" value={price ? int(price) : "–"} unit="₹ per quintal, median" change={change} neutral
      meter={weeks !== undefined && <Meter label="Weeks reported" value={weeks / 53} display={`${weeks}/53`} />}>
      <div className="flex h-[130px] flex-col">
        <Legend items={[{ name: yr(year ?? ""), color: SERIES.accent }, { name: yr(prev ?? ""), color: SERIES.reference, dashed: true }]} />
        <div className="min-h-0 flex-1">
          <Lines data={data} x="week" fmt={(v) => `₹${int(v)}`}
            lines={[{ key: "previous", name: yr(prev ?? ""), color: SERIES.reference, dashed: true, width: 1.5 }, { key: "current", name: yr(year ?? ""), color: SERIES.accent }]} />
        </div>
      </div>
    </AnalyticsCard>
  );
}

const FILTERS = ["All", ...CROPS] as const;

function OverviewWorkspace({ crop, act, selected, setSelected, bottom }: {
  crop: Crop; act: Record<Crop, ReturnType<typeof useActivity>>; selected?: number; setSelected: (id?: number) => void; bottom: React.ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const cur = act[crop];
  const rows = cur.data ?? [];
  const maxArr = Math.max(1, ...rows.map((r) => r.mandi_arrivals_tonnes_sum ?? 0));
  const shown = rows
    .filter((r) => filter === "All" || r.crops.split(",").includes(filter))
    .filter((r) => `${r.district} ${r.state}`.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => (b.mandi_arrivals_tonnes_sum ?? -1) - (a.mandi_arrivals_tonnes_sum ?? -1));
  const points: MapPoint[] = shown.map((r) => ({ id: r.id, lat: r.latitude, lng: r.longitude, label: `${r.district}, ${r.state}`, tone: r.mandi_records !== null ? "ok" : "muted" }));
  const sel = rows.find((r) => r.id === selected);

  const panel = (
    <Card glass className="flex h-full max-h-[640px] flex-col overflow-hidden lg:max-h-none">
      <div className="flex items-center justify-between gap-2 border-b border-line/70 px-5 pt-4 pb-3">
        <div>
          <h2 className="text-[17px] font-normal">Verified locations</h2>
          <p className="text-[11px] text-muted">District reference points · {rows.length || 46} verified</p>
        </div>
        <span className="flex items-center gap-1.5 text-[11px] text-muted"><Dot tone="ok" /> {crop} reports {cur.data?.[0] ? yr(cur.data[0].year) : ""}</span>
      </div>
      <div className="space-y-3 px-4 pt-3">
        <SearchBox value={query} onChange={setQuery} placeholder="Search district or state" />
        <div className="no-scrollbar flex gap-1.5 overflow-x-auto" role="group" aria-label="Filter by verified crop">
          {FILTERS.map((f) => (
            <Pill key={f} active={filter === f} onClick={() => setFilter(f)} aria-pressed={filter === f} className="h-8 px-3">
              {f !== "All" && <Dot tone={f === crop ? "ok" : "muted"} />}{f}
            </Pill>
          ))}
        </div>
      </div>
      <div className="thin-scroll mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto px-4 pb-4" data-testid="location-list">
        {cur.isLoading ? <Loading label="Loading locations" /> : cur.error ? <ErrorState error={cur.error} /> : shown.length === 0 ? (
          <Empty title="No matching locations">Try a different search or crop filter.</Empty>
        ) : shown.map((r) => (
          <LocationCard key={r.id} r={r} open={r.id === selected} max={maxArr} act={act} onToggle={() => setSelected(r.id === selected ? undefined : r.id)} />
        ))}
      </div>
    </Card>
  );

  return (
    <Workspace
      panel={panel}
      map={<MapView points={points} selectedId={selected} onSelect={setSelected} fitKey={`${crop}-${filter}-${query}`} className="h-full w-full" />}
      floating={sel && <FloatingCard r={sel} onClose={() => setSelected(undefined)} />}
      bottom={bottom}
    />
  );
}

function LocationCard({ r, open, max, act, onToggle }: { r: Activity; open: boolean; max: number; act: Record<Crop, ReturnType<typeof useActivity>>; onToggle: () => void }) {
  const reported = r.mandi_records !== null;
  const share = (r.mandi_arrivals_tonnes_sum ?? 0) / max;
  return (
    <div className={cn("rounded-2xl border transition", open ? "border-line bg-white/85 shadow-soft" : "border-transparent bg-white/45 hover:bg-white/70")}>
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center gap-3 px-3 py-2.5 text-left">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#e9ecee] text-ink/60"><MapPin size={15} /></span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] text-ink">{r.district}</span>
          <span className="flex items-center gap-1.5 text-[11px] text-muted"><Dot tone={reported ? "ok" : "muted"} />{r.state}</span>
        </span>
        <span className="text-right text-[12px] text-ink/80 tabular-nums">{reported ? `${compact(r.mandi_arrivals_tonnes_sum)} t` : "–"}</span>
        <span className={cn("grid size-7 place-items-center rounded-lg bg-white/80 text-muted transition", open && "rotate-180")}><ChevronDown size={14} /></span>
      </button>
      {open && (
        <div className="px-3 pb-3">
          <div className="flex justify-between text-[11px] text-muted"><span>Arrivals vs largest point</span><span className="text-ink/80">{(share * 100).toFixed(0)}%</span></div>
          <div className="relative mt-1.5 mb-3 h-px bg-line">
            <div className="absolute inset-y-0 left-0 bg-ok" style={{ width: `${share * 100}%` }} />
            <div className="absolute top-1 size-0 -translate-x-1/2 border-x-4 border-t-[5px] border-x-transparent border-t-ink/60" style={{ left: `${share * 100}%` }} />
          </div>
          <table className="w-full rounded-xl bg-surface text-[12px]">
            <caption className="sr-only">2019-20 mandi activity in {r.district}</caption>
            <thead className="text-[10px] text-faint"><tr><th className="py-1.5 pl-2.5 text-left font-normal">Crop</th><th className="text-right font-normal">Arrivals</th><th className="text-right font-normal">Median</th><th className="pr-2.5 text-right font-normal">Status</th></tr></thead>
            <tbody>
              {CROPS.map((c) => {
                const a = act[c].data?.find((x) => x.id === r.id);
                const ok = a && a.mandi_records !== null;
                return (
                  <tr key={c} className="border-t border-line/60">
                    <td className="py-1.5 pl-2.5"><span className="inline-flex items-center gap-1.5"><Dot tone={r.crops.split(",").includes(c) ? "ink" : "muted"} />{c}</span></td>
                    <td className="text-right tabular-nums">{ok ? `${compact(a.mandi_arrivals_tonnes_sum)} t` : "–"}</td>
                    <td className="text-right tabular-nums">{ok ? rs(a.mandi_modal_price_median) : "–"}</td>
                    <td className="py-1.5 pr-2.5 text-right"><Chip tone={ok ? "ok" : "muted"}>{ok ? "Reported" : "No match"}</Chip></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-[10.5px] leading-snug text-faint">District totals for {yr(r.year)} matched through the district crosswalk. Dark dot = crop the point was verified for.</p>
        </div>
      )}
    </div>
  );
}

function FloatingCard({ r, onClose }: { r: Activity; onClose: () => void }) {
  const climate = useClimate(r.id);
  const nav = useNavigate();
  const months = climate.data?.months ?? [];
  const maxRain = Math.max(1, ...months.map((m) => m.rain_mm));
  return (
    <Card glass className="p-4" data-testid="floating-card">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-[17px]">{r.district}</h3>
          <p className="flex items-center gap-1.5 text-[11px] text-muted"><Dot tone="ok" />{r.state} · verified district point</p>
        </div>
        <IconButton label="Close details" onClick={onClose} className="size-8"><X size={14} /></IconButton>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <Spec label="Reports" value={r.mandi_records !== null ? int(r.mandi_records) : "–"} />
        <Spec label="Markets" value={r.mandi_markets !== null ? int(r.mandi_markets) : "–"} />
        <Spec label="Median" value={r.mandi_modal_price_median !== null ? rs(r.mandi_modal_price_median) : "–"} />
      </div>
      <div className="mt-3 rounded-xl bg-white/60 p-2.5">
        <div className="flex justify-between text-[11px] text-muted"><span>Monthly rainfall, mm</span><span>{climate.data?.period ?? ""}</span></div>
        {climate.isLoading ? <Loading className="py-2" /> : climate.error ? <ErrorState error={climate.error} /> : (
          <div className="mt-2 flex h-12 items-end gap-[5px]" role="img" aria-label={`Average monthly rainfall in ${r.district}, ${months.map((m) => `${MONTHS[m.month - 1]} ${m.rain_mm.toFixed(0)}mm`).join(", ")}`}>
            {months.map((m) => (
              <div key={m.month} className="flex flex-1 flex-col items-center gap-1" title={`${m.rain_mm.toFixed(0)} mm`}>
                <div className="w-[3px] rounded-t-sm bg-ok/80" style={{ height: `${Math.max(2, (m.rain_mm / maxRain) * 36)}px` }} />
                <span className="text-[8px] text-faint">{MONTHS[m.month - 1]}</span>
              </div>
            ))}
          </div>
        )}
        {/* CC BY 4.0: Open-Meteo requires a link wherever its data is displayed */}
        <p className="mt-1.5 text-[10px] text-faint">Weather data by <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer" className="underline hover:text-ink">Open-Meteo.com</a> (CC BY 4.0)</p>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-[10.5px] text-faint">Historical averages, not a forecast</span>
        <button type="button" onClick={() => nav(`/markets?state=${encodeURIComponent(r.state)}`)}
          className="h-8 rounded-xl bg-[#e6e9eb] px-3 text-[12px] font-medium text-ink transition hover:bg-ink hover:text-white">View markets</button>
      </div>
    </Card>
  );
}

const Spec = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-xl bg-white/60 px-2.5 py-2"><div className="text-faint">{label}</div><div className="mt-0.5 text-[13px] text-ink tabular-nums">{value}</div></div>
);
