import { Database } from "lucide-react";
import { PageHeader } from "../components/Layout";
import { Card, Chip, KpiStat, Q } from "../components/ui";
import { useAbout, usePriceSummary } from "../lib/api";
import { compact, pct, yr } from "../lib/format";

const LIMITS = [
  "All data is historical. Market history ends 30 June 2020; nothing is live.",
  "Production values are shown to 2018-19 only. Later years are reserved and appear as row counts.",
  "Map points are district reference centres, not market, warehouse or route locations.",
  "Routes and warehouses are not built: no road network, market coordinates, storage data or transport costs are sourced.",
  "Spark ran in local mode on one machine. It is not a cluster benchmark and not Hadoop.",
];

export default function About() {
  const about = useAbout();
  const ps = usePriceSummary().data;
  const limits = ps ? [LIMITS[0], `A price model was selected over the last-value baseline in only ${ps.cases - ps.baseline_kept} of ${ps.cases} crop-horizon cases (Onion, 1 week), and it was ${pct(ps.onion_1w_test_change_pct)} vs the baseline on the one-time test.`, ...LIMITS.slice(1)] : LIMITS;
  return (
    <>
      <PageHeader icon={<Database size={18} />} title="About & Data" subtitle="Sources, processing, checks and limits"
        kpis={about.data && <>
          <KpiStat value={compact(about.data.spark.rows_read)} label="Market reports read" />
          <KpiStat value={`${Math.round(about.data.spark.last_run_seconds)} s`} label="Last Spark run (local)" />
          <KpiStat value={String(about.data.spark.parity.reduce((s, p) => s + p.mismatches, 0))} label="Spark vs pandas mismatches" />
        </>} />
      <Q query={about} loading="Loading project information">{(a) => (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <Card className="p-5 xl:col-span-2">
            <h2 className="text-[17px]">Data sources</h2>
            <table className="mt-3 w-full text-[12.5px]">
              <thead className="text-[10.5px] text-faint"><tr><th className="py-1.5 text-left font-normal">Data</th><th className="text-left font-normal">Source</th><th className="text-left font-normal">Coverage</th></tr></thead>
              <tbody>{a.sources.map((s) => <tr key={s.data} className="border-t border-line/70"><td className="py-2 pr-3 text-ink">{s.data}</td><td className="pr-3 text-muted">{s.source}</td><td className="text-muted">{s.coverage}</td></tr>)}</tbody>
            </table>
          </Card>
          <Card className="p-5">
            <h2 className="text-[17px]">Method</h2>
            <ol className="mt-3 list-decimal space-y-1.5 pl-4 text-[12.5px] text-muted marker:text-faint">
              <li>PySpark reads raw daily reports with an explicit schema and counts quality issues without repairing them.</li>
              <li>Spark SQL builds weekly and July–June district-year summaries.</li>
              <li>Models are compared with a last-value baseline on validation, then scored once on 2021–2022.</li>
            </ol>
          </Card>
          <Card className="p-5">
            <h2 className="text-[17px]">Spark processing</h2>
            <dl className="mt-3 space-y-1.5 text-[12.5px]">
              {[["Spark", a.spark.version], ["Java", a.spark.java], ["Window", a.spark.window], ["Run", a.spark.note]].map(([k, v]) => (
                <div key={k} className="flex gap-3"><dt className="w-16 shrink-0 text-faint">{k}</dt><dd className="text-muted">{v}</dd></div>))}
            </dl>
            <p className="mt-3 rounded-xl bg-white/70 px-3 py-2 text-[11.5px] text-muted">{a.spark.mapreduce_label}</p>
          </Card>
          <Card className="p-5">
            <h2 className="text-[17px]">Parity check</h2>
            <p className="text-[11px] text-muted">Spark SQL vs the pandas pipeline</p>
            <ul className="mt-3 space-y-1">
              {a.spark.parity.map((p) => (
                <li key={p.column} className="flex items-center justify-between text-[12px]">
                  <span className="text-muted">{p.column.replaceAll("_", " ")}</span>
                  <Chip tone={p.mismatches === 0 ? "ok" : "bad"}>{p.mismatches === 0 ? `0 / ${p.rows_compared.toLocaleString("en-IN")}` : `${p.mismatches} mismatches`}</Chip>
                </li>))}
            </ul>
          </Card>
          <Card className="p-5">
            <h2 className="text-[17px]">Reserved production years</h2>
            <p className="text-[11px] text-muted">{a.reserved_production.message}</p>
            <table className="mt-3 w-full text-[12px]" data-testid="reserved-table">
              <thead className="text-[10.5px] text-faint"><tr><th className="py-1 text-left font-normal">Crop</th><th className="text-left font-normal">Year</th><th className="text-right font-normal">ok</th><th className="text-right font-normal">annotated</th><th className="text-right font-normal">review</th><th className="text-right font-normal">unusable</th></tr></thead>
              <tbody>{a.reserved_production.counts.map((c) => (
                <tr key={c.crop + c.source_apy_year} className="border-t border-line/70 tabular-nums">
                  <td className="py-1">{c.crop}</td><td>{yr(c.source_apy_year)}</td><td className="text-right">{c.ok}</td><td className="text-right">{c.annotated}</td><td className="text-right">{c.review}</td><td className="text-right">{c.unusable}</td>
                </tr>))}</tbody>
            </table>
          </Card>
          <Card className="p-5 lg:col-span-2 xl:col-span-3">
            <h2 className="text-[17px]">Limitations</h2>
            <ul className="mt-3 grid gap-2 text-[12.5px] text-muted md:grid-cols-2">
              {limits.map((l) => <li key={l} className="rounded-xl bg-white/60 px-3 py-2">{l}</li>)}
            </ul>
          </Card>
        </div>
      )}</Q>
    </>
  );
}
