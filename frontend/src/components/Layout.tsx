import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { createContext, useContext, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { getJson, type Crop } from "../lib/api";
import { cn } from "../lib/format";

export const NAV = [
  { to: "/", label: "Overview" },
  { to: "/markets", label: "Markets" },
  { to: "/outlook", label: "Price Outlook" },
  { to: "/routes", label: "Routes" },
  { to: "/warehouses", label: "Warehouses" },
  { to: "/about", label: "About & Data" },
];

const CropCtx = createContext<{ crop: Crop; setCrop: (c: Crop) => void }>({ crop: "Onion", setCrop: () => {} });
export const useCrop = () => useContext(CropCtx);

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5" aria-label="Mandi Insights home">
      <span className="grid size-9 place-items-center rounded-[11px] bg-ok text-white shadow-pill">
        <svg viewBox="0 0 32 32" width="20" height="20" aria-hidden><path d="M16 25V13m0 0c0-4 3-6 7-6 0 4-3 6-7 6Zm0 4c0-3-2.5-5-6-5 0 3 2.5 5 6 5Z" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </span>
      <span className="leading-tight">
        <span className="block text-[14px] font-semibold text-ink">Mandi Insights</span>
        <span className="block text-[11px] text-muted">Market intelligence</span>
      </span>
    </Link>
  );
}

function ApiStatus() {
  const h = useQuery({ queryKey: ["health"], queryFn: () => getJson<{ market_history_end: string; live_data: boolean }>("/health"), retry: false, staleTime: Infinity });
  const ok = !!h.data;
  return (
    <span className="hidden h-9 items-center gap-2 rounded-xl border border-line bg-white/70 px-3 text-[12px] text-muted shadow-pill md:inline-flex"
      title={ok ? "Read-only API connected. All data is historical, nothing is live." : "API not reachable"}>
      <span className={cn("size-1.5 rounded-full", h.isLoading ? "bg-faint" : ok ? "bg-ok" : "bg-bad")} />
      {h.isLoading ? "Connecting" : ok ? `Historical · to ${new Date(h.data!.market_history_end).toLocaleDateString("en-GB", { month: "short", year: "numeric" })}` : "API offline"}
    </span>
  );
}

export function Layout() {
  const [crop, setCrop] = useState<Crop>("Onion");
  return (
    <CropCtx.Provider value={{ crop, setCrop }}>
      <div className="min-h-full bg-canvas">
        <header className="mx-auto flex max-w-[1680px] items-center gap-4 px-4 pt-5 pb-3 sm:px-6 lg:px-8">
          <div className="w-[200px] shrink-0 max-md:w-auto"><Logo /></div>
          <nav aria-label="Main" className="no-scrollbar min-w-0 flex-1 overflow-x-auto">
            <div className="mx-auto flex w-max gap-1.5">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}
                className={({ isActive }) => cn("inline-flex h-9 shrink-0 items-center rounded-xl px-3.5 text-[13px] font-medium transition",
                  isActive ? "bg-white text-ink shadow-pill" : "bg-[#e6e9eb] text-ink/65 hover:bg-[#dde1e3] hover:text-ink")}>
                {n.label}
              </NavLink>
            ))}
            </div>
          </nav>
          <div className="flex w-[200px] shrink-0 justify-end gap-2 max-md:w-auto">
            <ApiStatus />
            <Link to="/about" aria-label="About the data" title="About the data"
              className="grid size-9 place-items-center rounded-xl border border-line bg-white/80 text-ink/70 shadow-pill hover:bg-white hover:text-ink"><Info size={16} /></Link>
          </div>
        </header>
        <main className="mx-auto max-w-[1680px] px-4 pb-8 sm:px-6 lg:px-8"><Outlet /></main>
      </div>
    </CropCtx.Provider>
  );
}

export function PageHeader({ icon, title, subtitle, kpis, controls }: { icon: ReactNode; title: string; subtitle: ReactNode; kpis?: ReactNode; controls?: ReactNode }) {
  return (
    <section className="flex flex-wrap items-center gap-x-6 gap-y-4 py-4">
      <div className={cn("flex min-w-0 items-center gap-4", kpis && "xl:max-w-[300px] xl:shrink")}>
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#e6e9eb] text-ink/70">{icon}</span>
        <div className="min-w-0">
          <h1 className="truncate text-[34px] leading-tight font-light tracking-tight text-ink">{title}</h1>
          <p className="truncate text-[13px] text-muted">{subtitle}</p>
        </div>
      </div>
      {kpis && <div className="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-4 xl:flex-nowrap">{kpis}</div>}
      {controls && <div className="ml-auto flex flex-wrap items-center gap-2 max-lg:ml-0 max-lg:w-full">{controls}</div>}
    </section>
  );
}

/**
 * Map-led workspace from the reference: a full-bleed map with a glass list panel on the left, an optional floating
 * card, and two analytics cards along the bottom. Below 1024px it stacks: panel, map, cards.
 */
export function Workspace({ map, panel, floating, bottom }: { map: ReactNode; panel: ReactNode; floating?: ReactNode; bottom?: ReactNode }) {
  return (
    <section className="flex flex-col gap-4 lg:relative lg:block lg:h-[max(640px,calc(100vh-190px))] lg:overflow-hidden lg:rounded-[22px] lg:border lg:border-line/70 lg:bg-[#eef1f2]">
      <div className="order-2 h-[420px] overflow-hidden rounded-2xl border border-line/70 lg:absolute lg:inset-0 lg:h-auto lg:rounded-none lg:border-0">{map}</div>
      <div className="order-1 lg:absolute lg:top-4 lg:bottom-4 lg:left-4 lg:z-[600] lg:w-[360px]">{panel}</div>
      {floating && <div className="order-3 lg:absolute lg:top-4 lg:right-20 lg:z-[600] lg:w-[300px]">{floating}</div>}
      {bottom && <div className="order-4 grid gap-4 md:grid-cols-2 lg:absolute lg:right-4 lg:bottom-4 lg:left-[392px] lg:z-[600] lg:h-[250px]">{bottom}</div>}
    </section>
  );
}
