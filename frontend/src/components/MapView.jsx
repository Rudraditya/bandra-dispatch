import { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, Tooltip, Polyline, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useSimulation } from "../context/SimulationContext";

const BANDRA_CENTER = [19.0596, 72.8295];

function divIcon(html, size) {
  return L.divIcon({
    html,
    className: "",
    iconSize: size,
    iconAnchor: [size[0] / 2, size[1] / 2],
  });
}

const depotIcon = divIcon(
  '<div class="marker-depot-wrap"><div class="marker-depot-roof"></div><div class="marker-depot-body"></div></div>',
  [20, 22]
);
const idleIcon = divIcon('<div class="marker-vehicle-idle"></div>', [9, 9]);
const orderIconNormal = divIcon(
  '<div class="marker-order-wrap"><div class="marker-order-pulse"></div><div class="marker-order-pin"></div></div>',
  [22, 28]
);
const orderIconSlaBreach = divIcon(
  '<div class="marker-order-wrap"><div class="marker-order-pulse sla-breach"></div><div class="marker-order-pin sla-breach"></div></div>',
  [22, 28]
);
const orderIconWaitlisted = divIcon(
  '<div class="marker-order-wrap"><div class="marker-order-pin waitlisted"></div></div>',
  [22, 28]
);

function enrouteIcon(angle) {
  return divIcon(
    `<div class="veh-enroute-wrap" style="transform: rotate(${angle}deg)"><div class="veh-enroute-glow"></div><div class="veh-enroute-arrow"></div></div>`,
    [16, 16]
  );
}

function returningIcon(angle) {
  return divIcon(
    `<div class="veh-returning-wrap" style="transform: rotate(${angle}deg)"><div class="veh-returning-glow"></div><div class="veh-returning-arrow"></div></div>`,
    [16, 16]
  );
}

// Status-severity ramp for congested segments (warning -> serious -> critical).
function congestionColor(level) {
  if (level < 0.4) return "#fab219";
  if (level < 0.7) return "#ec835a";
  return "#d03b3b";
}

function formatMMSS(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function ClickHandler({ enabled, onDrop }) {
  useMapEvents({
    click(e) {
      if (enabled) {
        onDrop(e.latlng.lat, e.latlng.lng);
      }
    },
  });
  return null;
}

export default function MapView({ dropMode }) {
  const { depots, vehicles, orders, traffic, metrics, dropOrder } = useSimulation();
  const prevPositions = useRef(new Map());
  const [headings, setHeadings] = useState({});

  useEffect(() => {
    const next = {};
    for (const v of vehicles) {
      const prev = prevPositions.current.get(v.id);
      if (prev && (prev.lat !== v.lat || prev.lon !== v.lon)) {
        const dLat = v.lat - prev.lat;
        const dLon = v.lon - prev.lon;
        next[v.id] = (Math.atan2(dLon, dLat) * 180) / Math.PI;
      } else {
        next[v.id] = prev?.angle ?? 0;
      }
      prevPositions.current.set(v.id, { lat: v.lat, lon: v.lon, angle: next[v.id] });
    }
    setHeadings(next);
  }, [vehicles]);

  return (
    <MapContainer
      center={BANDRA_CENTER}
      zoom={15}
      className={`h-full w-full ${dropMode ? "cursor-crosshair" : ""}`}
      zoomControl
      preferCanvas
    >
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        attribution='&copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, DeLorme, NAVTEQ'
        maxZoom={19}
        maxNativeZoom={16}
      />

      {traffic.map((seg, i) => (
        <Polyline
          key={`traffic-${i}`}
          positions={seg.path}
          pathOptions={{
            color: congestionColor(seg.level),
            weight: 4,
            opacity: 0.5,
            lineCap: "round",
          }}
        />
      ))}

      <ClickHandler enabled={dropMode} onDrop={dropOrder} />

      {depots.map((d) => (
        <Marker key={`depot-${d.node}`} position={[d.lat, d.lon]} icon={depotIcon}>
          <Tooltip permanent direction="top" offset={[0, -18]} className="app-tooltip depot-tooltip">
            {d.name}
          </Tooltip>
        </Marker>
      ))}

      {vehicles.map((v) => {
        let icon = idleIcon;
        if (v.status === "en_route") icon = enrouteIcon(headings[v.id] ?? 0);
        else if (v.status === "returning") icon = returningIcon(headings[v.id] ?? 0);

        const statusLabel =
          v.status === "en_route" ? "En route" : v.status === "returning" ? "Returning to depot" : "Idle";

        return (
          <Marker key={`veh-${v.id}`} position={[v.lat, v.lon]} icon={icon}>
            <Tooltip direction="top" offset={[0, -8]} className="app-tooltip">
              {`Van #${v.id} · Depot ${String.fromCharCode(65 + v.depot_index)} · ${statusLabel}`}
            </Tooltip>
          </Marker>
        );
      })}

      {orders.map((o) => {
        const waitlisted = o.status === "waitlisted";
        const elapsed = Math.max(0, metrics.tick - o.created_tick);
        const overSla = !waitlisted && elapsed > (metrics.sla_threshold_sec ?? 1080);
        const icon = waitlisted ? orderIconWaitlisted : overSla ? orderIconSlaBreach : orderIconNormal;

        return (
          <Marker key={`ord-${o.id}`} position={[o.lat, o.lon]} icon={icon}>
            <Tooltip
              permanent
              direction="top"
              offset={[0, -24]}
              className={`app-tooltip order-tooltip${overSla ? " sla-breach-tooltip" : ""}${
                waitlisted ? " waitlisted-tooltip" : ""
              }`}
            >
              {waitlisted ? `${o.id} · waitlisted` : `${o.id} · ${formatMMSS(elapsed)}`}
            </Tooltip>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
