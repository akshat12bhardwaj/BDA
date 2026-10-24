import L from "leaflet";
import { Maximize2, Minus, Plus } from "lucide-react";
import { useEffect, useRef } from "react";
import { cn } from "../lib/format";
import { IconButton } from "./ui";

export interface MapPoint { id: number; lat: number; lng: number; label: string; tone: "ok" | "muted" | "ink" }

const TONE = { ok: "#22b14c", muted: "#a9b0b4", ink: "#1d2124" };
const INDIA: L.LatLngTuple[] = [[7, 67], [36, 98]];

/** Space the overlays (left panel, bottom cards) take on wide screens, so fitted points stay visible. */
function overlayPadding(bottomCards = true): L.FitBoundsOptions {
  return window.innerWidth >= 1024 ? { paddingTopLeft: [400, 40], paddingBottomRight: [80, bottomCards ? 290 : 40] } : { padding: [30, 30] };
}

/**
 * Leaflet map of verified district reference points. Draws points only: no lines, routes or invented sites.
 * Imperative Leaflet (not react-leaflet) keeps the dependency list short.
 */
export function MapView({ points, selectedId, onSelect, className, fitKey, bottomCards = true, line }: {
  points: MapPoint[]; selectedId?: number; onSelect?: (id: number) => void; className?: string; fitKey?: string; bottomCards?: boolean;
  line?: [number, number][] | null;  // a computed road route (lat, lon); never a straight connector
}) {
  const pad = () => overlayPadding(bottomCards);
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;

  useEffect(() => {
    const m = L.map(el.current!, { zoomControl: false, attributionControl: true, minZoom: 4, maxZoom: 11, zoomSnap: 1, maxBounds: [[-5, 50], [45, 115]] });
    // Keyless light-grey basemap (CARTO's public tiles now require an API key).
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16, attribution: "Basemap &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
    }).addTo(m);
    m.fitBounds(INDIA, pad());
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    const ro = new ResizeObserver(() => m.invalidateSize());
    ro.observe(el.current!);
    return () => { ro.disconnect(); m.remove(); map.current = null; };
  }, []);

  // Redraw route and points; selected point gets a halo.
  useEffect(() => {
    const g = layer.current;
    if (!g) return;
    g.clearLayers();
    if (line?.length) {
      L.polyline(line, { color: "#ffffff", weight: 6, opacity: 0.9, interactive: false }).addTo(g);
      L.polyline(line, { color: TONE.ok, weight: 3, opacity: 1, interactive: false }).addTo(g);
    }
    for (const p of points) {
      const sel = p.id === selectedId;
      if (sel) L.circleMarker([p.lat, p.lng], { radius: 16, stroke: false, fillColor: TONE[p.tone], fillOpacity: 0.14, interactive: false }).addTo(g);
      L.circleMarker([p.lat, p.lng], {
        radius: sel ? 7 : 5, color: "#fff", weight: 2, fillColor: TONE[p.tone], fillOpacity: 1,
      })
        .bindTooltip(p.label, { className: "node-tip", direction: "top", offset: [0, -6] })
        .on("click", () => select.current?.(p.id))
        .addTo(g);
    }
  }, [points, selectedId, line]);

  // Fit to the route, else the point set, whenever its identity (fitKey) changes.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (line?.length) return void m.fitBounds(L.latLngBounds(line), { ...pad(), maxZoom: 9 });
    if (!points.length) return;
    m.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lng])), { ...pad(), maxZoom: 7 });
  }, [fitKey]);

  useEffect(() => {
    const m = map.current;
    const p = points.find((x) => x.id === selectedId);
    if (!m || !p) return;
    const b = L.latLngBounds([[p.lat, p.lng], [p.lat, p.lng]]);
    m.flyToBounds(b, { ...pad(), maxZoom: Math.max(m.getZoom(), 6), duration: 0.6 });
  }, [selectedId]);

  const fit = () => {
    const m = map.current;
    if (!m) return;
    m.flyToBounds(points.length ? L.latLngBounds(points.map((p) => [p.lat, p.lng])) : L.latLngBounds(INDIA), { ...pad(), maxZoom: 7, duration: 0.5 });
  };

  return (
    <div className={cn("relative isolate overflow-hidden", className)} data-testid="map">
      <div ref={el} className="absolute inset-0 z-0" role="region" aria-label="Map of verified district reference points" />
      <div className="absolute top-1/2 right-5 z-[500] flex -translate-y-1/2 flex-col gap-2 lg:right-6">
        <IconButton label="Zoom in" onClick={() => map.current?.zoomIn()}><Plus size={16} /></IconButton>
        <IconButton label="Zoom out" onClick={() => map.current?.zoomOut()}><Minus size={16} /></IconButton>
        <IconButton label="Fit to points" onClick={fit}><Maximize2 size={14} /></IconButton>
      </div>
    </div>
  );
}
