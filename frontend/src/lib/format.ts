import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...v: ClassValue[]) => twMerge(clsx(v));

/** 4731451 -> "4.73M", 12500 -> "12.5k". */
export function compact(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e6) return `${(n / 1e6).toFixed(digits)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(a >= 1e5 ? 0 : 1)}k`;
  return n.toFixed(a < 10 && a % 1 ? 1 : 0);
}
export const int = (n: number | null | undefined) => (n === null || n === undefined ? "–" : Math.round(n).toLocaleString("en-IN"));
export const rs = (n: number | null | undefined) => (n === null || n === undefined ? "–" : `₹${int(n)}`);
export const pct = (n: number | null | undefined, digits = 1) => (n === null || n === undefined ? "–" : `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`);
/** "2019-2020" -> "2019-20". */
export const yr = (y: string) => (y?.length === 9 ? `${y.slice(0, 5)}${y.slice(7)}` : y);
export const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
/** July–June agricultural year of an ISO date: "2019-08-05" -> "2019-2020". */
export function agriYear(iso: string): string {
  const y = Number(iso.slice(0, 4)), m = Number(iso.slice(5, 7));
  return m >= 7 ? `${y}-${y + 1}` : `${y - 1}-${y}`;
}
export const shortDate = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });
