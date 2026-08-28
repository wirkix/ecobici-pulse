"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { supabase, type StationSnapshot } from "@/lib/supabaseClient";

const CDMX_CENTER: [number, number] = [-99.1332, 19.4326];

// Free vector basemap, no API key required.
const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";

function occupancyColor(pct: number): string {
  // Both extremes are "bad" for a rider: no bikes to take, or no docks to
  // return one to. Mid-range is the healthy state.
  if (pct <= 15 || pct >= 90) return "var(--color-high)";
  if (pct <= 30 || pct >= 75) return "var(--color-mid)";
  return "var(--color-low)";
}

// How many stations to surface in each "top" list.
const TOP_N = 10;

export default function StationMap() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<Map<string, maplibregl.Marker>>(new Map());
  // Mirrors `markers` but keeps the raw snapshot data (bikes/docks counts,
  // is_renting/is_returning) that markers.current doesn't expose -- needed
  // to compute the top-N lists below.
  const stations = useRef<Map<string, StationSnapshot>>(new Map());
  const [stationCount, setStationCount] = useState(0);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [topBikes, setTopBikes] = useState<StationSnapshot[]>([]);
  const [topDocks, setTopDocks] = useState<StationSnapshot[]>([]);

  function recomputeTopLists() {
    const all = Array.from(stations.current.values());
    // Only recommend stations actually dispensing/accepting bikes right
    // now -- a station can carry a stale nonzero count while temporarily
    // not renting/returning (maintenance, rebalancing truck mid-visit).
    setTopBikes(
      all
        .filter((s) => s.is_renting)
        .sort((a, b) => b.bikes_available - a.bikes_available)
        .slice(0, TOP_N)
    );
    setTopDocks(
      all
        .filter((s) => s.is_returning)
        .sort((a, b) => b.docks_available - a.docks_available)
        .slice(0, TOP_N)
    );
  }

  function upsertMarker(station: StationSnapshot) {
    if (!map.current) return;
    const existing = markers.current.get(station.station_id);
    const el = existing ? existing.getElement() : document.createElement("div");
    el.style.width = "14px";
    el.style.height = "14px";
    el.style.borderRadius = "50%";
    el.style.border = "1.5px solid rgba(255,255,255,0.85)";
    el.style.background = occupancyColor(station.occupancy_pct);
    el.style.cursor = "pointer";

    const popupHtml = `<strong>${station.name}</strong><br/>
      ${station.bikes_available} bikes · ${station.docks_available} docks free<br/>
      ${station.occupancy_pct.toFixed(0)}% occupied`;

    if (existing) {
      existing.setLngLat([station.lon, station.lat]);
      existing.getPopup()?.setHTML(popupHtml);
    } else {
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([station.lon, station.lat])
        .setPopup(new maplibregl.Popup({ offset: 12 }).setHTML(popupHtml))
        .addTo(map.current);
      markers.current.set(station.station_id, marker);
    }
    stations.current.set(station.station_id, station);
    recomputeTopLists();
    setLastUpdate(new Date().toLocaleTimeString());
  }

  function focusStation(station: StationSnapshot) {
    if (!map.current) return;
    const marker = markers.current.get(station.station_id);
    if (!marker) return;
    map.current.flyTo({ center: [station.lon, station.lat], zoom: 15 });
    marker.togglePopup();
  }

  useEffect(() => {
    if (map.current || !mapContainer.current) return;
    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: MAP_STYLE,
      center: CDMX_CENTER,
      zoom: 12.5,
    });
    map.current.addControl(new maplibregl.NavigationControl(), "top-right");
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadInitialSnapshot() {
      const { data, error } = await supabase.from("station_snapshot").select("*");
      if (error) {
        console.error("failed to load station_snapshot", error);
        return;
      }
      if (cancelled || !data) return;
      setStationCount(data.length);
      data.forEach((row) => upsertMarker(row as StationSnapshot));
    }

    loadInitialSnapshot();

    const channel = supabase
      .channel("stations")
      .on("broadcast", { event: "station_update" }, ({ payload }) => {
        upsertMarker(payload as StationSnapshot);
      })
      .subscribe();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, []);

  return (
    <div className="relative h-full w-full">
      <div ref={mapContainer} className="h-full w-full" />
      <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-line bg-paper/85 px-3 py-2 text-sm text-muted backdrop-blur">
        <div className="text-ink">{stationCount} stations</div>
        {lastUpdate && <div>last update: {lastUpdate}</div>}
      </div>
      <div className="pointer-events-none absolute bottom-6 left-4 rounded-lg border border-line bg-paper/85 px-3 py-2 text-xs text-muted backdrop-blur">
        <div className="mb-1.5 text-ink">Station occupancy</div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-low)" }} />
          healthy -- bikes and docks both available
        </div>
        <div className="mt-1 flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-mid)" }} />
          getting scarce
        </div>
        <div className="mt-1 flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-high)" }} />
          nearly empty or nearly full
        </div>
      </div>
      <div className="absolute bottom-6 right-4 flex max-h-[calc(100%-3rem)] w-64 flex-col gap-3 overflow-y-auto rounded-lg border border-line bg-paper/85 px-3 py-2 text-xs text-muted backdrop-blur">
        <TopList title="Best for grabbing a bike" icon="🚲" stations={topBikes} metric="bikes_available" onSelect={focusStation} />
        <TopList title="Best for returning a bike" icon="🅿️" stations={topDocks} metric="docks_available" onSelect={focusStation} />
      </div>
    </div>
  );
}

function TopList({
  title,
  icon,
  stations,
  metric,
  onSelect,
}: {
  title: string;
  icon: string;
  stations: StationSnapshot[];
  metric: "bikes_available" | "docks_available";
  onSelect: (station: StationSnapshot) => void;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5 text-ink">
        <span>{icon}</span> {title}
      </div>
      {stations.length === 0 ? (
        <div className="px-1 py-0.5 text-muted">loading…</div>
      ) : (
        <ol>
          {stations.map((s, i) => (
            <li key={s.station_id}>
              <button
                type="button"
                onClick={() => onSelect(s)}
                title={s.name}
                className="flex w-full items-center justify-between gap-2 rounded px-1 py-0.5 text-left hover:bg-line/60"
              >
                <span className="truncate">
                  {i + 1}. {s.name}
                </span>
                <span className="shrink-0 text-ink">{s[metric]}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
