import * as RSelect from "@radix-ui/react-select";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Check, ChevronDown, Inbox, Loader2, Search } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../lib/format";

export function Card({ className, children, glass, ...rest }: { className?: string; children: ReactNode; glass?: boolean } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...rest} className={cn("rounded-2xl border border-line/80 shadow-soft", glass ? "glass" : "bg-surface/90", className)}>
      {children}
    </div>
  );
}

export function IconButton({ className, children, label, active, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; active?: boolean }) {
  return (
    <button
      type="button" aria-label={label} title={label} {...rest}
      className={cn("grid size-9 shrink-0 place-items-center rounded-xl border border-line bg-white/80 text-ink/70 shadow-pill transition",
        "hover:bg-white hover:text-ink disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-ok", active && "bg-ink text-white hover:bg-ink hover:text-white", className)}
    >
      {children}
    </button>
  );
}

export function Pill({ active, className, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      type="button" {...rest}
      className={cn("inline-flex h-9 shrink-0 items-center gap-2 rounded-xl px-3.5 text-[13px] font-medium transition focus-visible:outline-2 focus-visible:outline-ok",
        active ? "bg-white text-ink shadow-pill" : "bg-[#e6e9eb] text-ink/70 hover:bg-[#dde1e3] hover:text-ink", className)}
    >
      {children}
    </button>
  );
}

export const Dot = ({ tone = "muted" }: { tone?: "ok" | "bad" | "muted" | "ink" }) => (
  <span aria-hidden className={cn("inline-block size-1.5 shrink-0 rounded-full", { ok: "bg-ok", bad: "bg-bad", muted: "bg-faint", ink: "bg-ink" }[tone])} />
);

export function Chip({ tone = "muted", children }: { tone?: "ok" | "bad" | "muted"; children: ReactNode }) {
  return (
    <span className={cn("inline-flex h-6 items-center rounded-lg px-2.5 text-[11px] font-medium",
      { ok: "bg-ok text-white", bad: "bg-bad text-white", muted: "bg-[#e6e9eb] text-muted" }[tone])}>
      {children}
    </span>
  );
}

/** Small square arrow badge from the reference KPIs; neutral when the direction carries no good/bad meaning. */
export function ChangeBadge({ value, neutral }: { value: number | null | undefined; neutral?: boolean }) {
  if (value === null || value === undefined) return null;
  const up = value >= 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span aria-label={`${up ? "up" : "down"} ${Math.abs(value).toFixed(1)}%`}
      className={cn("grid size-4 place-items-center rounded-[5px] text-white", neutral ? "bg-muted" : up ? "bg-ok" : "bg-bad")}>
      <Icon size={11} strokeWidth={2.5} />
    </span>
  );
}

/** Thin-bar sparkline: grey history, last bar coloured by direction. */
export function Sparkline({ values, tone = "ok" }: { values: number[]; tone?: "ok" | "bad" | "muted" }) {
  if (values.length < 2) return <div className="h-10 w-13" />;
  const max = Math.max(...values) || 1;
  const w = 52, h = 40, step = w / values.length;
  const color = { ok: "var(--color-ok)", bad: "var(--color-bad)", muted: "var(--color-muted)" }[tone];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden className="shrink-0">
      {values.map((v, i) => {
        const bh = Math.max(2, (v / max) * (h - 2));
        const last = i === values.length - 1;
        return <rect key={i} x={i * step + step / 2 - (last ? 1 : 0.5)} y={h - bh} width={last ? 2 : 1} height={bh} fill={last ? color : "#cfd4d7"} />;
      })}
    </svg>
  );
}

export function KpiStat({ value, label, change, spark, neutral, testId }: {
  value: string; label: string; change?: number | null; spark?: number[]; neutral?: boolean; testId?: string;
}) {
  const tone = change === null || change === undefined || neutral ? "muted" : change >= 0 ? "ok" : "bad";
  return (
    <div className="flex min-w-0 items-center gap-3" data-testid={testId}>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[30px] leading-none font-light tracking-tight text-ink tabular-nums">{value}</span>
          <ChangeBadge value={change} neutral={neutral} />
        </div>
        <div className="mt-1.5 truncate text-[13px] text-muted">{label}</div>
      </div>
      {spark && <Sparkline values={spark} tone={tone} />}
    </div>
  );
}

/** Reference slider: thin track, coloured fill, triangle marker under the value. */
export function Meter({ label, value, display }: { label: string; value: number; display: string }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <div className="w-28 shrink-0 2xl:w-40" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)}>
      <div className="flex justify-between text-[11px] text-muted"><span>{label}</span><span className="text-ink/80">{display}</span></div>
      <div className="relative mt-1.5 h-0.5 rounded-full bg-line">
        <div className="absolute inset-y-0 left-0 rounded-full bg-ok" style={{ width: `${v * 100}%` }} />
        <div className="absolute top-1 size-0 -translate-x-1/2 border-x-4 border-t-[5px] border-x-transparent border-t-ink/60" style={{ left: `${v * 100}%` }} />
      </div>
    </div>
  );
}

export function AnalyticsCard({ title, value, unit, change, meter, actions, children, className, neutral }: {
  title: string; value: string; unit: string; change?: number | null; meter?: ReactNode; actions?: ReactNode;
  children: ReactNode; className?: string; neutral?: boolean;
}) {
  return (
    <Card glass className={cn("flex min-w-0 flex-col p-5 pb-3", className)}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-[17px] font-normal text-ink">{title}</h3>
        <div className="flex gap-2">{actions}</div>
      </div>
      <div className="mt-3 flex items-end justify-between gap-4">
        <div className="flex items-baseline gap-2">
          <span className="self-center"><ChangeBadge value={change} neutral={neutral} /></span>
          <span className="text-[30px] leading-none font-light tracking-tight tabular-nums">{value}</span>
          <span className="text-[12px] whitespace-nowrap text-muted">/ {unit}</span>
        </div>
        {meter}
      </div>
      <div className="mt-3 min-h-0 flex-1">{children}</div>
    </Card>
  );
}

export function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label className="flex h-9 items-center gap-2 rounded-xl border border-line bg-white/70 px-3 text-[13px] focus-within:border-ok/60">
      <Search size={15} className="text-muted" aria-hidden />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={placeholder}
        className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-faint" />
    </label>
  );
}

export function Select({ value, onChange, options, label, className, placeholder }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; label: string; className?: string; placeholder?: string;
}) {
  return (
    <RSelect.Root value={value} onValueChange={onChange}>
      <RSelect.Trigger aria-label={label}
        className={cn("inline-flex h-9 min-w-0 items-center justify-between gap-2 rounded-xl border border-line bg-white/80 px-3 text-[13px] text-ink shadow-pill outline-none hover:bg-white focus-visible:border-ok/60 data-[placeholder]:text-faint", className)}>
        <span className="truncate"><RSelect.Value placeholder={placeholder} /></span>
        <RSelect.Icon><ChevronDown size={14} className="text-muted" /></RSelect.Icon>
      </RSelect.Trigger>
      <RSelect.Portal>
        <RSelect.Content position="popper" sideOffset={6}
          className="z-[1000] max-h-[min(360px,var(--radix-select-content-available-height))] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-xl border border-line bg-white/95 shadow-soft backdrop-blur">
          <RSelect.Viewport className="thin-scroll p-1">
            {options.map((o) => (
              <RSelect.Item key={o.value} value={o.value}
                className="relative flex h-8 cursor-default items-center rounded-lg pr-8 pl-2.5 text-[13px] text-ink/80 outline-none select-none data-[highlighted]:bg-canvas data-[state=checked]:text-ink">
                <RSelect.ItemText>{o.label}</RSelect.ItemText>
                <RSelect.ItemIndicator className="absolute right-2"><Check size={13} className="text-ok" /></RSelect.ItemIndicator>
              </RSelect.Item>
            ))}
          </RSelect.Viewport>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}

export function Segmented<T extends string | number>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex h-9 shrink-0 items-center gap-0.5 rounded-xl bg-[#e6e9eb] p-0.5">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} onClick={() => onChange(o.value)}
          className={cn("h-8 rounded-[10px] px-2.5 text-[13px] font-medium transition 2xl:px-3",
            o.value === value ? "bg-white text-ink shadow-pill" : "text-ink/60 hover:text-ink")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Loading({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div role="status" className={cn("flex items-center justify-center gap-2 py-6 text-[13px] text-muted", className)}>
      <Loader2 size={15} className="animate-spin" aria-hidden /> {label}…
    </div>
  );
}

export function Empty({ title, children, className }: { title: string; children?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center gap-2 px-4 py-6 text-center", className)}>
      <span className="grid size-9 place-items-center rounded-xl bg-white text-muted shadow-pill"><Inbox size={16} aria-hidden /></span>
      <p className="text-[14px] text-ink">{title}</p>
      {children && <div className="max-w-sm text-[12px] leading-relaxed text-muted">{children}</div>}
    </div>
  );
}

export function ErrorState({ error, className }: { error: { message: string; status?: number } | null; className?: string }) {
  return (
    <div role="alert" className={cn("flex items-start gap-2.5 rounded-xl bg-bad-soft/70 px-3.5 py-3 text-[12.5px] text-ink", className)}>
      <AlertTriangle size={15} className="mt-0.5 shrink-0 text-bad" aria-hidden />
      <div>
        <p className="font-medium">Could not load this data{error?.status ? ` (${error.status})` : ""}</p>
        <p className="mt-0.5 text-muted">{error?.message ?? "Unknown error"}. Is the API running on 127.0.0.1:8000?</p>
      </div>
    </div>
  );
}

/** Wraps a query: loading / error / empty / content. */
export function Q<T>({ query, empty, children, loading }: {
  query: { data?: T; isLoading: boolean; error: { message: string; status?: number } | null };
  empty?: (d: T) => boolean; children: (d: T) => ReactNode; loading?: string;
}) {
  if (query.isLoading) return <Loading label={loading} />;
  if (query.error) return <ErrorState error={query.error} />;
  if (query.data === undefined) return null;
  if (empty?.(query.data)) return <Empty title="Nothing to show for this selection" />;
  return <>{children(query.data)}</>;
}
