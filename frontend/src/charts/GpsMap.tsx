import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from "react-leaflet";
import { useColors } from "./charts";

export interface GpsPoint {
  lat: number;
  lon: number;
  label?: string;
}

/**
 * Rastro do GPS (não há roteirização: a rota é o caminho que o caminhão de fato fez).
 * Os blocos do mapa vêm do OpenStreetMap, então precisam de internet no navegador.
 */
export default function GpsMap({ track = [], markers = [], height = 300 }: { track?: GpsPoint[]; markers?: GpsPoint[]; height?: number }) {
  const c = useColors();
  const all = [...track, ...markers];
  if (all.length === 0) {
    return (
      <div className="grid place-items-center rounded-xl border border-dashed border-line text-sm text-muted" style={{ height }}>
        Sem posição de GPS registrada.
      </div>
    );
  }
  const lats = all.map((p) => p.lat);
  const lons = all.map((p) => p.lon);
  const bounds: [[number, number], [number, number]] = [
    [Math.min(...lats) - 0.005, Math.min(...lons) - 0.005],
    [Math.max(...lats) + 0.005, Math.max(...lons) + 0.005],
  ];
  const last = track[track.length - 1];
  return (
    <div style={{ height }} className="overflow-hidden rounded-xl border border-line">
      <MapContainer bounds={bounds} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }} attributionControl>
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {track.length > 1 && <Polyline positions={track.map((p) => [p.lat, p.lon])} pathOptions={{ color: c.data, weight: 4, opacity: 0.85 }} />}
        {track.length > 0 && (
          <CircleMarker center={[track[0].lat, track[0].lon]} radius={6} pathOptions={{ color: c.muted, fillColor: c.surface, fillOpacity: 1, weight: 2 }}>
            <Tooltip>Início do rastro</Tooltip>
          </CircleMarker>
        )}
        {last && (
          <CircleMarker center={[last.lat, last.lon]} radius={8} pathOptions={{ color: c.surface, fillColor: c.brand, fillOpacity: 1, weight: 3 }}>
            <Tooltip>{last.label ?? "Última posição"}</Tooltip>
          </CircleMarker>
        )}
        {markers.map((m, i) => (
          <CircleMarker key={i} center={[m.lat, m.lon]} radius={8} pathOptions={{ color: c.surface, fillColor: c.brand, fillOpacity: 1, weight: 3 }}>
            {m.label && <Tooltip>{m.label}</Tooltip>}
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
