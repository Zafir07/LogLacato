import { Plus } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ErrorBox, Field, Loading, Modal, PageHeader, Pagination, SimTag, TripStatusBadge, Empty } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useAsync } from "../hooks/useAsync";
import { api, qs } from "../services/api";
import { dateTime, fromLocalInput, int, toLocalInput } from "../services/format";
import type { Driver, Page, Trip, Vehicle } from "../types/api";

export default function Trips() {
  const [sp, setSp] = useSearchParams();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [sim, setSim] = useState(false);
  const [q, setQ] = useState(sp.get("q") ?? "");
  const [creating, setCreating] = useState(false);
  const { can } = useAuth();
  const nav = useNavigate();

  useEffect(() => setQ(sp.get("q") ?? ""), [sp]);
  useEffect(() => setPage(1), [status, sim, q]);

  const { data, error, loading, reload } = useAsync(
    () => api.get<Page<Trip>>(`/api/v1/trips${qs({ page, page_size: 20, status, q, include_simulated: sim })}`),
    [page, status, sim, q],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Viagens"
        subtitle="Cadastro, acompanhamento e encerramento das viagens de coleta"
        actions={can("gestor") && (
          <button className="btn-primary" onClick={() => setCreating(true)}>
            <Plus size={16} /> Nova viagem
          </button>
        )}
      />
      <div className="flex flex-wrap items-end gap-3">
        <label className="label flex-[2_1_240px]">
          Pesquisar
          <input
            className="input"
            value={q}
            placeholder="Código, placa, motorista, origem…"
            onChange={(e) => {
              setQ(e.target.value);
              setSp(e.target.value ? { q: e.target.value } : {}, { replace: true });
            }}
          />
        </label>
        <label className="label flex-[1_1_160px]">
          Status
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Todos</option>
            <option value="planejada">Planejada</option>
            <option value="em_andamento">Em andamento</option>
            <option value="finalizada">Finalizada</option>
            <option value="cancelada">Cancelada</option>
          </select>
        </label>
        <label className="flex h-10 items-center gap-2 text-sm">
          <input type="checkbox" className="h-[18px] w-[18px]" checked={sim} onChange={(e) => setSim(e.target.checked)} /> Incluir simuladas
        </label>
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      <div className="card p-2">
        {!data && loading ? (
          <Loading />
        ) : data && data.items.length === 0 ? (
          <Empty>Nenhuma viagem encontrada.</Empty>
        ) : (
          data && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px]">
                <thead>
                  <tr>
                    <th className="th">Código</th>
                    <th className="th">Veículo · motorista</th>
                    <th className="th">Origem → destino</th>
                    <th className="th text-right">Volume</th>
                    <th className="th">Saída</th>
                    <th className="th">Chegada</th>
                    <th className="th">Status</th>
                    <th className="th text-right">Alertas</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((t) => (
                    <tr key={t.id} className="cursor-pointer hover:bg-sunken" onClick={() => nav(`/viagens/${t.id}`)}>
                      <td className="td">
                        <Link to={`/viagens/${t.id}`} className="num font-semibold text-brand" onClick={(e) => e.stopPropagation()}>
                          {t.code}
                        </Link>{" "}
                        {t.is_simulated && <SimTag />}
                      </td>
                      <td className="td">
                        {t.vehicle_plate} · {t.driver_name}
                      </td>
                      <td className="td text-muted">
                        {t.origin} → {t.destination}
                      </td>
                      <td className="td num text-right">{t.volume_liters != null ? `${int(t.volume_liters)} L` : "—"}</td>
                      <td className="td num">{dateTime(t.departure_at)}</td>
                      <td className="td num">{dateTime(t.arrival_at)}</td>
                      <td className="td">
                        <TripStatusBadge status={t.status} />
                      </td>
                      <td className={`td num text-right ${t.open_alerts ? "font-semibold text-bad" : ""}`}>{t.open_alerts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="px-2 pb-1">
                <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
              </div>
            </div>
          )
        )}
      </div>
      {creating && (
        <TripForm
          onClose={() => setCreating(false)}
          onSaved={(t) => {
            setCreating(false);
            nav(`/viagens/${t.id}`);
          }}
        />
      )}
    </div>
  );
}

export function TripForm({ trip, onClose, onSaved }: { trip?: Trip; onClose: () => void; onSaved: (t: Trip) => void }) {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [f, setF] = useState({
    vehicle_id: trip?.vehicle_id ? String(trip.vehicle_id) : "",
    driver_id: trip?.driver_id ? String(trip.driver_id) : "",
    origin: trip?.origin ?? "",
    destination: trip?.destination ?? "",
    volume_liters: trip?.volume_liters != null ? String(trip.volume_liters) : "",
    departure_at: trip?.departure_at ? toLocalInput(new Date(trip.departure_at)) : toLocalInput(new Date()),
    expected_arrival_at: trip?.expected_arrival_at ? toLocalInput(new Date(trip.expected_arrival_at)) : "",
    status: "planejada",
    notes: trip?.notes ?? "",
  });
  useEffect(() => {
    api.get<Page<Vehicle>>("/api/v1/vehicles?page_size=200&status=ativo").then((p) => setVehicles(p.items));
    api.get<Page<Driver>>("/api/v1/drivers?page_size=200&status=ativo").then((p) => setDrivers(p.items));
  }, []);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const common = {
      driver_id: Number(f.driver_id),
      origin: f.origin,
      destination: f.destination,
      volume_liters: f.volume_liters ? Number(f.volume_liters) : null,
      departure_at: fromLocalInput(f.departure_at),
      expected_arrival_at: fromLocalInput(f.expected_arrival_at),
      notes: f.notes || null,
    };
    try {
      const saved = trip
        ? await api.patch<Trip>(`/api/v1/trips/${trip.id}`, common)
        : await api.post<Trip>("/api/v1/trips", { ...common, vehicle_id: Number(f.vehicle_id), status: f.status });
      onSaved(saved);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={trip ? `Editar ${trip.code}` : "Nova viagem"} onClose={onClose} wide>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <Field label="Veículo">
          <select className="input" required value={f.vehicle_id} onChange={set("vehicle_id")} disabled={!!trip}>
            <option value="">Selecione…</option>
            {vehicles.map((v) => (
              <option key={v.id} value={v.id}>
                {v.plate} · {v.model} ({int(v.capacity_liters)} L){v.is_simulated ? " · SIMULADO" : ""}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Motorista">
          <select className="input" required value={f.driver_id} onChange={set("driver_id")}>
            <option value="">Selecione…</option>
            {drivers.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Origem">
          <input className="input" required minLength={2} value={f.origin} onChange={set("origin")} placeholder="Ex.: Linha Ijuí Norte" />
        </Field>
        <Field label="Destino">
          <input className="input" required minLength={2} value={f.destination} onChange={set("destination")} placeholder="Ex.: Laticínio" />
        </Field>
        <Field label="Volume previsto (L)">
          <input className="input num" type="number" min={0} value={f.volume_liters} onChange={set("volume_liters")} />
        </Field>
        {!trip && (
          <Field label="Situação inicial">
            <select className="input" value={f.status} onChange={set("status")}>
              <option value="planejada">Planejada</option>
              <option value="em_andamento">Em andamento (já saiu)</option>
            </select>
          </Field>
        )}
        <Field label="Saída">
          <input className="input" type="datetime-local" value={f.departure_at} onChange={set("departure_at")} />
        </Field>
        <Field label="Chegada prevista" hint="Passou do horário sem finalizar → alerta de atraso">
          <input className="input" type="datetime-local" value={f.expected_arrival_at} onChange={set("expected_arrival_at")} />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Observações">
            <textarea className="input h-20 py-2" value={f.notes} onChange={set("notes")} maxLength={2000} />
          </Field>
        </div>
        {error && (
          <div className="sm:col-span-2">
            <ErrorBox message={error} />
          </div>
        )}
        <div className="flex justify-end gap-2 sm:col-span-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn-primary" disabled={saving}>
            {saving ? "Salvando…" : "Salvar"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
