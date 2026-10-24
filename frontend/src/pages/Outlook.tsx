import * as Tabs from "@radix-ui/react-tabs";
import { ChevronDown, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Legend, Lines, SERIES, type Line_ } from "../components/charts";
import { PageHeader, useCrop } from "../components/Layout";
import { Card, Chip, Empty, ErrorState, KpiStat, Loading, Q, SearchBox, Segmented, Select } from "../components/ui";
import { useArrivalSeries, useArrivalsSummary, useMeta, usePriceSeries, usePriceSummary, useSeriesOptions, type SeriesKey } from "../lib/api";
import { cn, int, pct, shortDate } from "../lib/format";
import { cropOptions } from "./Overview";

type Kind = "prices" | "arrivals";
const PERIODS = [
  { value: "val_2019", label: "Validation 2019" }, { value: "val_2020", label: "Validation 2020" },
  { value: "test_2021", label: "Test 2021" }, { value: "test_2022", label: "Test 2022" },
];
const LINES: Line_[] = [
  { key: "persistence", name: "Baseline (last value)", color: SERIES.reference, dashed: true, width: 1.5 },
  { key: "observed", name: "Actual", color: SERIES.actual, width: 1.5 },
  { key: "hgb_conservative", name: "Model", color: SERIES.accent },
];
const keyOf = (s: SeriesKey) => `${s.state}|${s.district}|${s.market}|${s.variety}`;

export default function Outlook() {
  const { crop, setCrop } = useCrop();
  const [kind, setKind] = useState<Kind>("prices");
  const [horizon, setHorizon] = useState(1);
  const [period, setPeriod] = useState("test_2022");
  const ps = usePriceSummary();
  const as = useArrivalsSummary();
  const meta = useMeta();

  return (
    <Tabs.Root value={kind} onValueChange={(v) => setKind(v as Kind)}>
      <PageHeader icon={<TrendingUp size={18} />} title="Price Outlook" subtitle="Stored backtest results · no live forecasts"
        kpis={<>
          {ps.error ? <ErrorState error={ps.error} /> : ps.data && <>
            <KpiStat value={`${ps.data.baseline_kept}/${ps.data.cases}`} label="Price cases: baseline kept" />
            <KpiStat value={pct(ps.data.onion_1w_test_change_pct)} label="Onion 1-wk vs baseline" change={ps.data.onion_1w_test_change_pct} />
          </>}
          {as.data && <KpiStat value={`${as.data.cells_better}/${as.data.cells}`} label="Arrival cells beat baseline" />}
        </>}
        controls={<>
          <Tabs.List aria-label="Outlook type" className="inline-flex h-9 items-center gap-0.5 rounded-xl bg-[#e6e9eb] p-0.5">
            {(["prices", "arrivals"] as Kind[]).map((k) => (
              <Tabs.Trigger key={k} value={k} className="h-8 rounded-[10px] px-3 text-[13px] font-medium text-ink/60 capitalize data-[state=active]:bg-white data-[state=active]:text-ink data-[state=active]:shadow-pill">{k}</Tabs.Trigger>
            ))}
          </Tabs.List>
          <Segmented label="Crop" value={crop} onChange={setCrop} options={cropOptions} />
          <Segmented label="Horizon" value={horizon} onChange={setHorizon} options={(meta.data?.horizons ?? [1, 2, 4]).map((h) => ({ value: h, label: `${h} wk` }))} />
          {kind === "arrivals" && <Select label="Period" className="w-40" value={period} onChange={setPeriod} options={PERIODS} />}
        </>}
      />
      {(["prices", "arrivals"] as Kind[]).map((k) => (
        <Tabs.Content key={k} value={k}>
          <SeriesExplorer kind={k} horizon={horizon} period={period} />
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}

function SeriesExplorer({ kind, horizon, period }: { kind: Kind; horizon: number; period: string }) {
  const { crop } = useCrop();
  const opts = useSeriesOptions(kind, crop, horizon);
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState<string>();
  const list = opts.data ?? [];
  const series = list.find((s) => keyOf(s) === sel) ?? list[0];
  const key = series && { state: series.state, district: series.district, market: series.market, variety: series.variety };
  const shown = list.filter((s) => `${s.market} ${s.district} ${s.state} ${s.variety}`.toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
      <Card glass className="flex max-h-[520px] flex-col overflow-hidden lg:h-[max(600px,calc(100vh-200px))] lg:max-h-none">
        <div className="border-b border-line/70 px-5 pt-4 pb-3">
          <h2 className="text-[17px]">Market series</h2>
          <p className="text-[11px] text-muted">{crop} · {horizon}-week horizon · {list.length} series</p>
        </div>
        <div className="px-4 pt-3"><SearchBox value={query} onChange={setQuery} placeholder="Search market, district or state" /></div>
        <div className="thin-scroll mt-3 min-h-0 flex-1 overflow-y-auto px-4 pb-4" data-testid="series-list">
          {opts.isLoading ? <Loading label="Loading series" /> : opts.error ? <ErrorState error={opts.error} /> : !shown.length ? <Empty title="No matching series" /> : (
            <ul className="space-y-1.5">
              {shown.slice(0, 150).map((s) => (
                <li key={keyOf(s)}>
                  <button type="button" onClick={() => setSel(keyOf(s))} aria-current={series && keyOf(s) === keyOf(series)}
                    className={cn("w-full rounded-xl px-3 py-2 text-left transition", series && keyOf(s) === keyOf(series) ? "bg-white shadow-soft" : "bg-white/40 hover:bg-white/70")}>
                    <div className="truncate text-[13px]">{s.market}</div>
                    <div className="truncate text-[11px] text-muted">{s.district}, {s.state} · {s.variety}</div>
                  </button>
                </li>))}
              {shown.length > 150 && <li className="px-2 pt-1 text-[11px] text-faint">Showing 150 of {shown.length}; refine the search.</li>}
            </ul>
          )}
        </div>
      </Card>
      <div className="flex min-w-0 flex-col gap-4">
        <Card glass className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="truncate text-[20px] font-light">{series ? `${series.market}, ${series.district}` : "Select a series"}</h2>
              <p className="text-[11.5px] text-muted">
                {kind === "prices" ? `Modal price, ₹/quintal · ${horizon}-week-ahead · validation 2019–2020 only` : `Arrivals, tonnes/day · ${horizon}-week-ahead · ${PERIODS.find((p) => p.value === period)?.label}`}
              </p>
            </div>
            <Legend items={LINES.map((l) => ({ name: l.name, color: l.color, dashed: l.dashed }))} />
          </div>
          <div className="mt-4 h-[360px]" data-testid="outlook-chart">
            {kind === "prices" ? <PriceChart horizon={horizon} s={key} /> : <ArrivalChart horizon={horizon} period={period} s={key} />}
          </div>
        </Card>
        <Metrics kind={kind} horizon={horizon} />
      </div>
    </div>
  );
}

function PriceChart({ horizon, s }: { horizon: number; s?: SeriesKey }) {
  const { crop } = useCrop();
  const q = usePriceSeries(crop, horizon, s);
  if (!s) return <Empty title="No series selected" />;
  return <Q query={q} empty={(d) => !d.length} loading="Loading series">{(d) => <Lines data={d} x="origin_date" xFmt={shortDate} fmt={(v) => `₹${int(v)}`} lines={LINES} />}</Q>;
}

function ArrivalChart({ horizon, period, s }: { horizon: number; period: string; s?: SeriesKey }) {
  const { crop } = useCrop();
  const q = useArrivalSeries(crop, horizon, period, s);
  if (!s) return <Empty title="No series selected" />;
  return <Q query={q} empty={(d) => !d.length} loading="Loading series">{(d) => <Lines data={d.map((r) => ({ ...r, week: `Week ${r.week_no + 1}` }))} x="week" fmt={(v) => `${v.toFixed(1)} t/day`} lines={LINES} />}</Q>;
}

function Metrics({ kind, horizon }: { kind: Kind; horizon: number }) {
  const { crop } = useCrop();
  const ps = usePriceSummary();
  const as = useArrivalsSummary();
  const [open, setOpen] = useState(false);
  return (
    <Card className="p-5">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between text-left">
        <span><span className="block text-[17px]">Evaluation metrics</span><span className="text-[11px] text-muted">{crop} · positive % = model error lower than the last-value baseline</span></span>
        <span className={cn("grid size-8 place-items-center rounded-lg bg-white text-muted shadow-pill transition", open && "rotate-180")}><ChevronDown size={15} /></span>
      </button>
      {open && (
        <div className="mt-4 overflow-x-auto">
          {kind === "prices" ? (
            <Q query={ps}>{(d) => (
              <table className="w-full text-[12.5px]">
                <thead className="text-[10.5px] text-faint"><tr><th className="py-1.5 text-left font-normal">Horizon</th><th className="text-left font-normal">Period</th><th className="text-left font-normal">Kept</th><th className="text-right font-normal">MAE ₹</th><th className="text-right font-normal">Baseline MAE ₹</th><th className="text-right font-normal">Change</th></tr></thead>
                <tbody>
                  {[...d.validation.filter((r) => r.crop === crop && r.horizon_weeks === horizon && r.config === "no_weather").map((r) => ({ ...r, approach: "validation" })),
                    ...d.test.filter((r) => r.crop === crop)].map((r, i) => (
                    <tr key={i} className={cn("border-t border-line/70", r.horizon_weeks === horizon ? "" : "text-muted")}>
                      <td className="py-1.5">{r.horizon_weeks} wk</td><td>{r.period.replace("_", " ")}</td>
                      <td><Chip tone={r.approach === "persistence" ? "muted" : r.approach === "validation" ? "muted" : "ok"}>{r.approach === "persistence" ? "baseline" : r.approach === "validation" ? "model (val)" : "model"}</Chip></td>
                      <td className="text-right tabular-nums">{int(r.mae)}</td><td className="text-right tabular-nums">{int(r.persistence_mae)}</td>
                      <td className="text-right tabular-nums">{pct(r.rel_mae_improvement_pct)}</td>
                    </tr>))}
                </tbody>
              </table>)}</Q>
          ) : (
            <Q query={as}>{(d) => (
              <table className="w-full text-[12.5px]">
                <thead className="text-[10.5px] text-faint"><tr><th className="py-1.5 text-left font-normal">Horizon</th><th className="text-left font-normal">Period</th><th className="text-right font-normal">Model WAPE</th><th className="text-right font-normal">Baseline WAPE</th><th className="text-right font-normal">Log-MAE change</th></tr></thead>
                <tbody>{d.test.filter((r) => r.crop === crop).map((r, i) => (
                  <tr key={i} className={cn("border-t border-line/70", r.horizon_weeks === horizon ? "" : "text-muted")}>
                    <td className="py-1.5">{r.horizon_weeks} wk</td><td>{r.period.replace("_", " ")}</td>
                    <td className="text-right tabular-nums">{r.wape_pct.toFixed(1)}%</td><td className="text-right tabular-nums">{r.persistence_wape_pct.toFixed(1)}%</td>
                    <td className="text-right tabular-nums">{pct(r.rel_log_mae_improvement_pct)}</td>
                  </tr>))}
                </tbody>
              </table>)}</Q>
          )}
          <p className="mt-3 text-[11px] text-faint">Test years 2021–2022 were scored once and appear here as metrics only. Price series charts show validation predictions; no 2023+ data is used.</p>
        </div>
      )}
    </Card>
  );
}
