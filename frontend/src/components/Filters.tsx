import { useEffect, useState } from "react";
import { api } from "../services/api";
import { toLocalInput } from "../services/format";
import type { Driver, Page, Trip, Vehicle } from "../types/api";

export interface FilterState {
  period: "24h" | "7d" | "30d" | "custom";
  from: string;
  to: string;
  vehicle_id: string;
  driver_id: string;
  trip_id: string;
  include_simulated: boolean;
}

export function defaultFilters(): FilterState {
  const now = new Date();
  return { period: "7d", from: toLocalInput(new Date(now.getTime() - 7 * 864e5)), to: toLocalInput(now), vehicle_id: "", driver_id: "", trip_id: "", include_simulated: false };
}

/** Converte os filtros da tela em parâmetros da API (datas em ISO/UTC). */
export function filterParams(f: FilterState) {
  const now = Date.now();
  const span = { "24h": 864e5, "7d": 7 * 864e5, "30d": 30 * 864e5 } as const;
  const from = f.period === "custom" ? new Date(f.from) : new Date(now - span[f.period]);
  const to = f.period === "custom" ? new Date(f.to) : new Date(now);
  return {
    date_from: from.toISOString(),
    date_to: to.toISOString(),
    vehicle_id: f.vehicle_id || undefined,
    driver_id: f.driver_id || undefined,
    trip_id: f.trip_id || undefined,
    include_simulated: f.include_simulated || undefined,
  };
}

export default function Filters({ value, onChange }: { value: FilterState; onChange: (f: FilterState) => void }) {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);

  useEffect(() => {
    api.get<Page<Vehicle>>("/api/v1/vehicles?page_size=200").then((p) => setVehicles(p.items)).catch(() => {});
    api.get<Page<Driver>>("/api/v1/drivers?page_size=200").then((p) => setDrivers(p.items)).catch(() => {});
  }, []);
  useEffect(() => {
    api
      .get<Page<Trip>>(`/api/v1/trips?page_size=100${value.include_simulated ? "&include_simulated=true" : ""}`)
      .then((p) => setTrips(p.items))
      .catch(() => {});
  }, [value.include_simulated]);

  const set = (patch: Partial<FilterState>) => onChange({ ...value, ...patch });
  const sel = "input pr-8";

  return (
    <section aria-label="Filtros" className="flex flex-wrap items-end gap-3">
      <label className="label flex-[1_1_170px]">
        Período
        <select className={sel} value={value.period} onChange={(e) => set({ period: e.target.value as FilterState["period"] })}>
          <option value="24h">Últimas 24 horas</option>
          <option value="7d">Últimos 7 dias</option>
          <option value="30d">Últimos 30 dias</option>
          <option value="custom">Personalizado</option>
        </select>
      </label>
      {value.period === "custom" && (
        <>
          <label className="label flex-[1_1_190px]">
            De
            <input type="datetime-local" className="input" value={value.from} onChange={(e) => set({ from: e.target.value })} />
          </label>
          <label className="label flex-[1_1_190px]">
            Até
            <input type="datetime-local" className="input" value={value.to} onChange={(e) => set({ to: e.target.value })} />
          </label>
        </>
      )}
      <label className="label flex-[1_1_150px]">
        Veículo
        <select className={sel} value={value.vehicle_id} onChange={(e) => set({ vehicle_id: e.target.value })}>
          <option value="">Todos</option>
          {vehicles
            .filter((v) => value.include_simulated || !v.is_simulated)
            .map((v) => (
              <option key={v.id} value={v.id}>
                {v.plate}
                {v.is_simulated ? " (simulado)" : ""}
              </option>
            ))}
        </select>
      </label>
      <label className="label flex-[1_1_150px]">
        Motorista
        <select className={sel} value={value.driver_id} onChange={(e) => set({ driver_id: e.target.value })}>
          <option value="">Todos</option>
          {drivers.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </label>
      <label className="label flex-[1_1_150px]">
        Viagem
        <select className={sel} value={value.trip_id} onChange={(e) => set({ trip_id: e.target.value })}>
          <option value="">Todas</option>
          {trips.map((t) => (
            <option key={t.id} value={t.id}>
              {t.code}
            </option>
          ))}
        </select>
      </label>
      <label className="flex h-10 items-center gap-2 text-sm">
        <input type="checkbox" className="h-[18px] w-[18px] accent-[rgb(var(--sim))]" checked={value.include_simulated} onChange={(e) => set({ include_simulated: e.target.checked, trip_id: "" })} />
        Incluir dados simulados
      </label>
    </section>
  );
}
