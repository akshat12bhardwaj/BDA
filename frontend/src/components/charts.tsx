import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { compact } from "../lib/format";

// Recessive axes and grid; text in ink tokens, colour only on marks.
const axis = { tick: { fontSize: 10, fill: "#8a9196" }, axisLine: false, tickLine: false } as const;
const tipStyle = { contentStyle: { borderRadius: 12, border: "1px solid #e3e6e8", boxShadow: "0 8px 24px rgb(20 30 40/.08)", fontSize: 12, padding: "6px 10px" }, labelStyle: { color: "#8a9196", marginBottom: 2 } };
export const SERIES = { actual: "#1d2124", reference: "#9aa2a7", accent: "#22b14c" };

export interface Line_ { key: string; name: string; color: string; dashed?: boolean; width?: number }

// Loose row type: rows come straight from the API.
type Row = Record<string, any>;
type H = number | `${number}%`;

export function ThinBars({ data, x, y, name, height = "100%", fmt = compact, highlight }: {
  data: Row[]; x: string; y: string; name: string; height?: H; fmt?: (v: number) => string; highlight?: (d: Row) => boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={1}>
        <CartesianGrid vertical={false} stroke="#e8ebec" />
        <XAxis dataKey={x} {...axis} minTickGap={36} />
        <YAxis {...axis} tickFormatter={(v) => compact(v, 0)} width={38} />
        <Tooltip {...tipStyle} cursor={{ fill: "rgb(34 177 76 / .08)" }} formatter={(v) => [fmt(Number(v)), name]} />
        <Bar dataKey={y} name={name} maxBarSize={3} fill={SERIES.accent} isAnimationActive={false}
          {...(highlight && { shape: (p: Row) => <rect x={p.x} y={p.y} width={p.width} height={p.height} rx={1} fill={highlight(p.payload) ? SERIES.accent : "#c9ced1"} /> })} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Lines({ data, x, lines, height = "100%", fmt = compact, xFmt }: {
  data: Row[]; x: string; lines: Line_[]; height?: H; fmt?: (v: number) => string; xFmt?: (v: string) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke="#e8ebec" />
        <XAxis dataKey={x} {...axis} minTickGap={40} tickFormatter={xFmt} />
        <YAxis {...axis} tickFormatter={(v) => compact(v, 1)} width={40} domain={["auto", "auto"]} />
        <Tooltip {...tipStyle} labelFormatter={(l) => (xFmt ? xFmt(String(l)) : String(l))} formatter={(v, n) => [v === null || v === undefined ? "–" : fmt(Number(v)), n]} />
        {lines.map((l) => (
          <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color} strokeWidth={l.width ?? 2} dot={false}
            strokeDasharray={l.dashed ? "4 3" : undefined} connectNulls isAnimationActive={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Legend({ items }: { items: { name: string; color: string; dashed?: boolean }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted" aria-label="Legend">
      {items.map((i) => (
        <li key={i.name + i.color} className="flex items-center gap-1.5">
          <svg width="14" height="4" aria-hidden><line x1="0" y1="2" x2="14" y2="2" stroke={i.color} strokeWidth="2" strokeDasharray={i.dashed ? "3 2" : undefined} /></svg>
          {i.name}
        </li>
      ))}
    </ul>
  );
}
