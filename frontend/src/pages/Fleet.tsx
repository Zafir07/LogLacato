import { ArrowLeft, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Empty, ErrorBox, Field, Loading, Modal, PageHeader, Pagination, Section, SimTag, TripStatusBadge } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useAsync } from "../hooks/useAsync";
import { api, qs } from "../services/api";
import { agoFrom, dateTime, int } from "../services/format";
import type { Device, Driver, Page, Trip, Vehicle } from "../types/api";

const VSTATUS: Record<string, string> = { ativo: "Ativo", manutencao: "Em manutenção", inativo: "Inativo" };

// ------------------------------------------------------------------ veículos
export function Vehicles() {
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState<Vehicle | "new" | null>(null);
  const { data, error, loading, reload } = useAsync(() => api.get<Page<Vehicle>>(`/api/v1/vehicles${qs({ page, page_size: 25, q })}`), [page, q]);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Veículos"
        subtitle="Caminhões-tanque, capacidade, dispositivo instalado e situação"
        actions={can("gestor") && (
          <button className="btn-primary" onClick={() => setEdit("new")}>
            <Plus size={16} /> Novo veículo
          </button>
        )}
      />
      <label className="label max-w-sm">
        Pesquisar
        <input className="input" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Placa ou modelo" />
      </label>
      {error && <ErrorBox message={error} onRetry={reload} />}
      <div className="card p-2">
        {!data && loading && <Loading />}
        {data && data.items.length === 0 && <Empty>Nenhum veículo.</Empty>}
        {data && data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px]">
              <thead>
                <tr>
                  <th className="th">Placa</th>
                  <th className="th">Modelo</th>
                  <th className="th text-right">Capacidade</th>
                  <th className="th">Dispositivo</th>
                  <th className="th">Situação</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((v) => (
                  <tr key={v.id}>
                    <td className="td">
                      <Link to={`/veiculos/${v.id}`} className="num font-semibold text-brand">
                        {v.plate}
                      </Link>{" "}
                      {v.is_simulated && <SimTag />}
                    </td>
                    <td className="td">{v.model}</td>
                    <td className="td num text-right">{int(v.capacity_liters)} L</td>
                    <td className="td num">{v.device_id ?? <span className="text-muted">nenhum</span>}</td>
                    <td className="td">
                      <Badge tone={v.status === "ativo" ? "brand" : v.status === "manutencao" ? "warn" : "neutral"}>{VSTATUS[v.status]}</Badge>
                    </td>
                    <td className="td text-right">
                      {can("gestor") && (
                        <button className="btn-ghost h-8" onClick={() => setEdit(v)}>
                          Editar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-2">
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
            </div>
          </div>
        )}
      </div>
      {edit && <VehicleForm vehicle={edit === "new" ? undefined : edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </div>
  );
}

function VehicleForm({ vehicle, onClose, onSaved }: { vehicle?: Vehicle; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ plate: vehicle?.plate ?? "", model: vehicle?.model ?? "", capacity_liters: vehicle ? String(vehicle.capacity_liters) : "", status: vehicle?.status ?? "ativo" });
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      if (vehicle) await api.patch(`/api/v1/vehicles/${vehicle.id}`, { model: f.model, capacity_liters: Number(f.capacity_liters), status: f.status });
      else await api.post("/api/v1/vehicles", { plate: f.plate, model: f.model, capacity_liters: Number(f.capacity_liters), status: f.status });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <Modal title={vehicle ? `Editar ${vehicle.plate}` : "Novo veículo"} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Placa" hint="Formato ABC1D23 ou ABC1234">
          <input className="input num uppercase" required disabled={!!vehicle} value={f.plate} onChange={(e) => setF({ ...f, plate: e.target.value })} />
        </Field>
        <Field label="Modelo">
          <input className="input" required minLength={2} value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} />
        </Field>
        <Field label="Capacidade (L)">
          <input className="input num" type="number" min={1} required value={f.capacity_liters} onChange={(e) => setF({ ...f, capacity_liters: e.target.value })} />
        </Field>
        <Field label="Situação">
          <select className="input" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as Vehicle["status"] })}>
            <option value="ativo">Ativo</option>
            <option value="manutencao">Em manutenção</option>
            <option value="inativo">Inativo</option>
          </select>
        </Field>
        {error && <ErrorBox message={error} />}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn-primary">Salvar</button>
        </div>
      </form>
    </Modal>
  );
}

export function VehicleDetail() {
  const { id } = useParams();
  const { data, error, loading, reload } = useAsync(async () => {
    const [v, trips] = await Promise.all([api.get<Vehicle>(`/api/v1/vehicles/${id}`), api.get<Trip[]>(`/api/v1/vehicles/${id}/trips?limit=50`)]);
    const device = v.device_id ? await api.get<Device>(`/api/v1/devices/${v.device_id}`) : null;
    return { v, trips, device };
  }, [id]);
  if (!data && loading) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const { v, trips, device } = data;
  return (
    <div className="flex flex-col gap-5">
      <Link to="/veiculos" className="inline-flex items-center gap-1 text-sm text-muted no-underline hover:text-ink">
        <ArrowLeft size={14} /> Veículos
      </Link>
      <PageHeader title={v.plate} subtitle={<span className="inline-flex items-center gap-2">{v.model} · {int(v.capacity_liters)} L {v.is_simulated && <SimTag />}</span>} />
      <Section title="Monitoramento">
        {device ? (
          <dl className="grid gap-4 text-sm [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]">
            <div>
              <dt className="text-xs text-muted">Dispositivo</dt>
              <dd className="num font-medium">{device.id}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Conexão</dt>
              <dd>
                <Badge tone={device.connection_status === "online" ? "brand" : "bad"}>{device.connection_status}</Badge>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Última comunicação</dt>
              <dd className="num">{agoFrom(device.last_seen_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Firmware</dt>
              <dd className="num">{device.firmware_version ?? "—"}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-muted">Nenhum dispositivo instalado. Associe em Dispositivos.</p>
        )}
      </Section>
      <Section title="Histórico de viagens" aside={`${trips.length}`}>
        {trips.length === 0 ? (
          <Empty>Este veículo ainda não fez viagens.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead>
                <tr>
                  <th className="th">Viagem</th>
                  <th className="th">Motorista</th>
                  <th className="th">Saída</th>
                  <th className="th text-right">Volume</th>
                  <th className="th">Status</th>
                  <th className="th text-right">Alertas abertos</th>
                </tr>
              </thead>
              <tbody>
                {trips.map((t) => (
                  <tr key={t.id}>
                    <td className="td">
                      <Link to={`/viagens/${t.id}`} className="num font-semibold text-brand">
                        {t.code}
                      </Link>
                    </td>
                    <td className="td">{t.driver_name}</td>
                    <td className="td num">{dateTime(t.departure_at)}</td>
                    <td className="td num text-right">{t.volume_liters != null ? `${int(t.volume_liters)} L` : "—"}</td>
                    <td className="td">
                      <TripStatusBadge status={t.status} />
                    </td>
                    <td className="td num text-right">{t.open_alerts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

// ------------------------------------------------------------------ motoristas
export function Drivers() {
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState<Driver | "new" | null>(null);
  const { data, error, loading, reload } = useAsync(() => api.get<Page<Driver>>(`/api/v1/drivers${qs({ page, page_size: 25, q })}`), [page, q]);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Motoristas" actions={can("gestor") && <button className="btn-primary" onClick={() => setEdit("new")}><Plus size={16} /> Novo motorista</button>} />
      <label className="label max-w-sm">
        Pesquisar
        <input className="input" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Nome ou documento" />
      </label>
      {error && <ErrorBox message={error} onRetry={reload} />}
      <div className="card p-2">
        {!data && loading && <Loading />}
        {data && data.items.length === 0 && <Empty>Nenhum motorista.</Empty>}
        {data && data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px]">
              <thead>
                <tr>
                  <th className="th">Nome</th>
                  <th className="th">Documento</th>
                  <th className="th">Telefone</th>
                  <th className="th">Situação</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((d) => (
                  <tr key={d.id}>
                    <td className="td font-medium">{d.name}</td>
                    <td className="td num">{d.document}</td>
                    <td className="td num">{d.phone ?? "—"}</td>
                    <td className="td">
                      <Badge tone={d.status === "ativo" ? "brand" : "neutral"}>{d.status}</Badge>
                    </td>
                    <td className="td text-right">{can("gestor") && <button className="btn-ghost h-8" onClick={() => setEdit(d)}>Editar</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-2">
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
            </div>
          </div>
        )}
      </div>
      {edit && <DriverForm driver={edit === "new" ? undefined : edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </div>
  );
}

function DriverForm({ driver, onClose, onSaved }: { driver?: Driver; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ name: driver?.name ?? "", document: driver?.document ?? "", phone: driver?.phone ?? "", status: driver?.status ?? "ativo" });
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      if (driver) await api.patch(`/api/v1/drivers/${driver.id}`, { name: f.name, phone: f.phone || null, status: f.status });
      else await api.post("/api/v1/drivers", { ...f, phone: f.phone || null });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <Modal title={driver ? `Editar ${driver.name}` : "Novo motorista"} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Nome">
          <input className="input" required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </Field>
        <Field label="Documento (CPF ou CNH)">
          <input className="input num" required minLength={3} disabled={!!driver} value={f.document} onChange={(e) => setF({ ...f, document: e.target.value })} />
        </Field>
        <Field label="Telefone">
          <input className="input num" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
        </Field>
        <Field label="Situação">
          <select className="input" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as Driver["status"] })}>
            <option value="ativo">Ativo</option>
            <option value="inativo">Inativo</option>
          </select>
        </Field>
        {error && <ErrorBox message={error} />}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
          <button className="btn-primary">Salvar</button>
        </div>
      </form>
    </Modal>
  );
}

// ------------------------------------------------------------------ dispositivos
export function Devices() {
  const { can } = useAuth();
  const [edit, setEdit] = useState<Device | "new" | null>(null);
  const { data, error, loading, reload } = useAsync(() => api.get<Device[]>("/api/v1/devices"), []);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Dispositivos"
        subtitle="Cada T-Beam (ou o simulador) usa o próprio id como usuário no broker MQTT. Para conectar, o id e a senha também precisam estar em MQTT_DEVICE_CREDENTIALS no .env."
        actions={can("admin") && <button className="btn-primary" onClick={() => setEdit("new")}><Plus size={16} /> Novo dispositivo</button>}
      />
      {error && <ErrorBox message={error} onRetry={reload} />}
      <div className="card p-2">
        {!data && loading && <Loading />}
        {data && data.length === 0 && <Empty>Nenhum dispositivo.</Empty>}
        {data && data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr>
                  <th className="th">Id</th>
                  <th className="th">Veículo</th>
                  <th className="th">Conexão</th>
                  <th className="th">Última comunicação</th>
                  <th className="th">Firmware</th>
                  <th className="th">Série</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody>
                {data.map((d) => (
                  <tr key={d.id}>
                    <td className="td num font-semibold">
                      {d.id} {d.is_simulated && <SimTag />}
                    </td>
                    <td className="td num">{d.vehicle_plate ?? <span className="text-muted">nenhum</span>}</td>
                    <td className="td">
                      <Badge tone={d.connection_status === "online" ? "brand" : d.connection_status === "offline" ? "bad" : "neutral"}>{d.connection_status}</Badge>
                    </td>
                    <td className="td num">{agoFrom(d.last_seen_at)}</td>
                    <td className="td num">{d.firmware_version ?? "—"}</td>
                    <td className="td">{d.serial_number ?? "—"}</td>
                    <td className="td text-right">{can("admin") && <button className="btn-ghost h-8" onClick={() => setEdit(d)}>Associar</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {edit && <DeviceForm device={edit === "new" ? undefined : edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </div>
  );
}

function DeviceForm({ device, onClose, onSaved }: { device?: Device; onClose: () => void; onSaved: () => void }) {
  const { data: vehicles } = useAsync(() => api.get<Page<Vehicle>>("/api/v1/vehicles?page_size=200"), []);
  const [f, setF] = useState({ id: device?.id ?? "", serial_number: device?.serial_number ?? "", vehicle_id: device?.vehicle_id ? String(device.vehicle_id) : "", is_simulated: device?.is_simulated ?? false });
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      if (device) await api.patch(`/api/v1/devices/${device.id}`, { serial_number: f.serial_number || null, vehicle_id: f.vehicle_id ? Number(f.vehicle_id) : null, unassign: !f.vehicle_id });
      else await api.post("/api/v1/devices", { id: f.id, serial_number: f.serial_number || null, vehicle_id: f.vehicle_id ? Number(f.vehicle_id) : null, is_simulated: f.is_simulated });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <Modal title={device ? `Dispositivo ${device.id}` : "Novo dispositivo"} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Id (usuário MQTT)" hint="Letras minúsculas, números e hífen. Ex.: esp32-002">
          <input className="input num" required pattern="[a-z0-9][a-z0-9-]{1,39}" disabled={!!device} value={f.id} onChange={(e) => setF({ ...f, id: e.target.value })} />
        </Field>
        <Field label="Número de série / descrição">
          <input className="input" value={f.serial_number} onChange={(e) => setF({ ...f, serial_number: e.target.value })} />
        </Field>
        <Field label="Veículo">
          <select className="input" value={f.vehicle_id} onChange={(e) => setF({ ...f, vehicle_id: e.target.value })}>
            <option value="">Nenhum</option>
            {vehicles?.items.map((v) => (
              <option key={v.id} value={v.id}>
                {v.plate}
                {v.device_id && v.device_id !== device?.id ? ` (já tem ${v.device_id})` : ""}
              </option>
            ))}
          </select>
        </Field>
        {!device && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-[18px] w-[18px]" checked={f.is_simulated} onChange={(e) => setF({ ...f, is_simulated: e.target.checked })} /> Dispositivo simulado
          </label>
        )}
        {error && <ErrorBox message={error} />}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
          <button className="btn-primary">Salvar</button>
        </div>
      </form>
    </Modal>
  );
}
