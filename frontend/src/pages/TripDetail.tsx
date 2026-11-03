import { ArrowLeft, CheckCircle2, ClipboardPlus, FileDown, Pencil, Play, XCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { TimeChart } from "../charts/charts";
import GpsMap from "../charts/GpsMap";
import { Badge, Empty, ErrorBox, Field, Kpi, Loading, Modal, PageHeader, Section, SeverityBadge, SimTag, TripStatusBadge } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useLive } from "../hooks/live";
import { useAsync } from "../hooks/useAsync";
import { useParameters } from "../hooks/useParameters";
import { api, download } from "../services/api";
import { ALERT_TYPE_LABEL, dateTime, fromLocalInput, int, num, toLocalInput } from "../services/format";
import type { Alert, Reading, Sample, Trip } from "../types/api";
import { TripForm } from "./Trips";

interface Summary {
  duration_min: number | null;
  readings_valid: number;
  readings_invalid: number;
  readings_from_queue: number;
  first_reading_at: string | null;
  last_reading_at: string | null;
  ph_avg: number | null;
  ph_min: number | null;
  ph_max: number | null;
  milk_temp_avg: number | null;
  milk_temp_max: number | null;
  samples: number;
  samples_rejected: number;
  acidity_avg: number | null;
  volume_collected: number | null;
  alerts_total: number;
  last_gps: { lat: number; lon: number; at: string } | null;
}

export default function TripDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const limits = useParameters();
  const [editing, setEditing] = useState(false);
  const [sampling, setSampling] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, error, loading, reload } = useAsync(async () => {
    const [trip, summary, readings, track, alerts, samples] = await Promise.all([
      api.get<Trip>(`/api/v1/trips/${id}`),
      api.get<Summary>(`/api/v1/trips/${id}/summary`),
      api.get<Reading[]>(`/api/v1/trips/${id}/telemetry?only_valid=true&limit=3000`),
      api.get<{ lat: number; lon: number; at: string }[]>(`/api/v1/trips/${id}/track`),
      api.get<Alert[]>(`/api/v1/trips/${id}/alerts`),
      api.get<Sample[]>(`/api/v1/trips/${id}/samples`),
    ]);
    return { trip, summary, readings, track, alerts, samples };
  }, [id]);

  useLive((m) => {
    if (data?.trip.status === "em_andamento" && ((m.type === "telemetry" && m.data?.trip_id === data.trip.id) || m.type === "event")) reload();
  });

  if (!data && loading) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const { trip, summary: s } = data;

  const act = async (path: string) => {
    setActionError(null);
    try {
      await api.post(`/api/v1/trips/${trip.id}/${path}`);
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  const tL = limits("milk_temperature", "transporte");
  const pL = limits("ph", "transporte");
  const pts = (key: "milk_temperature" | "ph") =>
    data.readings.filter((r) => r.measured_at && r[key] != null).map((r) => ({ t: r.measured_at!, avg: Number(r[key]) }));
  const step = (arr: { t: string; avg: number }[]) => (arr.length > 600 ? arr.filter((_, i) => i % Math.ceil(arr.length / 600) === 0) : arr);

  return (
    <div className="flex flex-col gap-5">
      <Link to="/viagens" className="inline-flex items-center gap-1 text-sm text-muted no-underline hover:text-ink">
        <ArrowLeft size={14} /> Viagens
      </Link>
      <PageHeader
        title={`Viagem ${trip.code}`}
        subtitle={
          <span className="inline-flex flex-wrap items-center gap-2">
            <TripStatusBadge status={trip.status} /> {trip.is_simulated && <SimTag />} {trip.origin} → {trip.destination}
          </span>
        }
        actions={
          <>
            <button className="btn-ghost" onClick={() => download(`/api/v1/reports/trips/${trip.id}.pdf`, `viagem-${trip.code}.pdf`).catch((e) => setActionError(e.message))}>
              <FileDown size={16} /> PDF
            </button>
            <button className="btn-ghost" onClick={() => download(`/api/v1/reports/telemetry.xlsx?trip_id=${trip.id}`, `leituras-${trip.code}.xlsx`).catch((e) => setActionError(e.message))}>
              <FileDown size={16} /> Leituras (Excel)
            </button>
            {can("coletor") && trip.status !== "cancelada" && (
              <button className="btn-ghost" onClick={() => setSampling(true)}>
                <ClipboardPlus size={16} /> Registrar coleta
              </button>
            )}
            {can("gestor") && trip.status === "planejada" && (
              <button className="btn-primary" onClick={() => act("start")}>
                <Play size={16} /> Iniciar
              </button>
            )}
            {can("gestor") && trip.status === "em_andamento" && (
              <button className="btn-primary" onClick={() => setFinishing(true)}>
                <CheckCircle2 size={16} /> Finalizar
              </button>
            )}
            {can("gestor") && (trip.status === "planejada" || trip.status === "em_andamento") && (
              <>
                <button className="btn-ghost" onClick={() => setEditing(true)}>
                  <Pencil size={16} /> Editar
                </button>
                <button className="btn-ghost text-bad" onClick={() => act("cancel")}>
                  <XCircle size={16} /> Cancelar
                </button>
              </>
            )}
          </>
        }
      />
      {actionError && <ErrorBox message={actionError} />}

      <Section title="Informações logísticas">
        <dl className="grid gap-4 text-sm [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]">
          <Info k="Veículo" v={<Link to={`/veiculos/${trip.vehicle_id}`} className="font-semibold text-brand">{trip.vehicle_plate}</Link>} />
          <Info k="Motorista" v={trip.driver_name} />
          <Info k="Dispositivo" v={trip.device_id ?? "nenhum"} mono />
          <Info k="Volume" v={trip.volume_liters != null ? `${int(trip.volume_liters)} L` : "—"} mono />
          <Info k="Saída" v={dateTime(trip.departure_at)} mono />
          <Info k="Chegada prevista" v={dateTime(trip.expected_arrival_at)} mono />
          <Info k="Chegada" v={dateTime(trip.arrival_at)} mono />
          <Info k="Duração" v={s.duration_min != null ? `${Math.floor(s.duration_min / 60)} h ${s.duration_min % 60} min` : "—"} mono />
        </dl>
        {trip.notes && <p className="text-sm text-muted">{trip.notes}</p>}
      </Section>

      <section aria-label="Resumo da operação" className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
        <Kpi label="Leituras válidas" value={int(s.readings_valid)} note={`${s.readings_invalid} inválidas · ${s.readings_from_queue} vieram da fila`} />
        <Kpi label="Temp. do leite (média · máx.)" value={num(s.milk_temp_avg)} unit={`°C · ${num(s.milk_temp_max)}`} tone={tL?.max != null && s.milk_temp_max != null && s.milk_temp_max > tL.max ? "bad" : "ink"} />
        <Kpi label="pH (média)" value={num(s.ph_avg, 2)} note={s.ph_min != null ? `mín. ${num(s.ph_min, 2)} · máx. ${num(s.ph_max, 2)}` : "sem leitura"} />
        <Kpi label="Acidez (média das coletas)" value={num(s.acidity_avg)} unit="°D" note={`${s.samples} coletas · ${s.samples_rejected} recusada(s)`} tone={s.samples_rejected ? "warn" : "ink"} />
        <Kpi label="Alertas" value={int(s.alerts_total)} tone={s.alerts_total ? "bad" : "brand"} note={`${trip.open_alerts} em aberto`} />
      </section>

      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr))]">
        <Section title="Temperatura do leite" aside="°C">
          {pts("milk_temperature").length ? <TimeChart points={step(pts("milk_temperature"))} unit="°C" limits={tL} /> : <Empty>Sem leitura de temperatura do leite nesta viagem.</Empty>}
        </Section>
        <Section title="pH">
          {pts("ph").length ? <TimeChart points={step(pts("ph"))} unit="" limits={pL} color="brand" digits={2} /> : <Empty>Sem leitura de pH nesta viagem.</Empty>}
        </Section>
      </div>

      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr))]">
        <Section title="Rastro do GPS" aside={s.last_gps ? `última posição ${dateTime(s.last_gps.at)}` : "sem GPS"}>
          <GpsMap track={data.track} height={320} />
        </Section>
        <Section title="Alertas registrados" aside={`${data.alerts.length}`}>
          {data.alerts.length === 0 ? (
            <Empty>Nenhum alerta nesta viagem.</Empty>
          ) : (
            <ul className="flex flex-col divide-y divide-line">
              {data.alerts.map((a) => (
                <li key={a.id} className="flex flex-col gap-1 py-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={a.severity} />
                    <span className="font-semibold">{a.title}</span>
                    <Badge tone={a.status === "encerrado" ? "neutral" : "warn"}>{a.status}</Badge>
                  </div>
                  <span className="text-sm text-muted">
                    {ALERT_TYPE_LABEL[a.type] ?? a.type} · {dateTime(a.first_seen_at)} · {a.occurrences} ocorrência(s)
                  </span>
                  {a.description && <span className="text-sm">{a.description}</span>}
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section title="Coletas na fazenda" aside="registro do coletor">
        {data.samples.length === 0 ? (
          <Empty>Nenhuma coleta registrada.</Empty>
        ) : (
          <SamplesTable samples={data.samples} />
        )}
      </Section>

      {editing && <TripForm trip={trip} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); reload(); }} />}
      {sampling && <SampleForm trip={trip} onClose={() => setSampling(false)} onSaved={() => { setSampling(false); reload(); }} />}
      {finishing && <FinishForm trip={trip} onClose={() => setFinishing(false)} onSaved={() => { setFinishing(false); reload(); }} />}
    </div>
  );
}

function Info({ k, v, mono }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-xs text-muted">{k}</dt>
      <dd className={`font-medium ${mono ? "num" : ""}`}>{v}</dd>
    </div>
  );
}

export function SamplesTable({ samples, showTrip }: { samples: Sample[]; showTrip?: boolean }) {
  const bad = (s: Sample, f: string) => (s.out_of_range.includes(f) ? "text-bad font-semibold" : "");
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px]">
        <thead>
          <tr>
            <th className="th">Data</th>
            {showTrip && <th className="th">Viagem</th>}
            <th className="th">Produtor</th>
            <th className="th text-right">Acidez</th>
            <th className="th text-right">Densidade</th>
            <th className="th text-right">pH</th>
            <th className="th text-right">Temp.</th>
            <th className="th text-right">Litros</th>
            <th className="th">Lacre</th>
            <th className="th">Decisão</th>
          </tr>
        </thead>
        <tbody>
          {samples.map((s) => (
            <tr key={s.id}>
              <td className="td num">{dateTime(s.collected_at)}</td>
              {showTrip && (
                <td className="td">
                  <Link to={`/viagens/${s.trip_id}`} className="num font-semibold text-brand">
                    {s.trip_code}
                  </Link>
                </td>
              )}
              <td className="td">
                {s.producer}
                {s.corrects_id && <div className="text-xs text-muted">corrige a coleta #{s.corrects_id}</div>}
              </td>
              <td className={`td num text-right ${bad(s, "acidity_dornic")}`}>{s.acidity_dornic != null ? `${num(s.acidity_dornic)} °D` : "—"}</td>
              <td className={`td num text-right ${bad(s, "density")}`}>{num(s.density, 3)}</td>
              <td className={`td num text-right ${bad(s, "ph_manual")}`}>{num(s.ph_manual, 2)}</td>
              <td className={`td num text-right ${bad(s, "milk_temperature")}`}>{s.milk_temperature != null ? `${num(s.milk_temperature)} °C` : "—"}</td>
              <td className="td num text-right">{int(s.volume_liters)}</td>
              <td className="td num">{s.seal_code ?? "—"}</td>
              <td className="td">
                <Badge tone={s.decision === "aceito" ? "brand" : s.decision === "recusado" ? "bad" : "warn"}>{s.decision}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SampleForm({ trip, onClose, onSaved }: { trip: Trip; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ collected_at: toLocalInput(new Date()), producer: "", acidity_dornic: "", density: "", ph_manual: "", milk_temperature: "", volume_liters: "", seal_code: "", decision: "aceito", notes: "" });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Sample | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const numOrNull = (v: string) => (v.trim() === "" ? null : v.replace(",", "."));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const s = await api.post<Sample>(`/api/v1/trips/${trip.id}/samples`, {
        collected_at: fromLocalInput(f.collected_at),
        producer: f.producer,
        acidity_dornic: numOrNull(f.acidity_dornic),
        density: numOrNull(f.density),
        ph_manual: numOrNull(f.ph_manual),
        milk_temperature: numOrNull(f.milk_temperature),
        volume_liters: f.volume_liters ? Number(f.volume_liters) : null,
        seal_code: f.seal_code || null,
        decision: f.decision,
        notes: f.notes || null,
      });
      if (s.out_of_range.length) setResult(s);
      else onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  if (result)
    return (
      <Modal title="Coleta registrada" onClose={onSaved}>
        <div className="flex flex-col gap-3 text-sm">
          <ErrorBox message={`Fora da faixa de referência: ${result.out_of_range.join(", ")}. Um alerta foi aberto e o laticínio será avisado.`} />
          <button className="btn-primary self-end" onClick={onSaved}>
            Entendi
          </button>
        </div>
      </Modal>
    );
  return (
    <Modal title={`Registrar coleta · ${trip.code}`} onClose={onClose} wide>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-3">
        <div className="sm:col-span-2">
          <Field label="Produtor / propriedade">
            <input className="input" required minLength={2} value={f.producer} onChange={set("producer")} />
          </Field>
        </div>
        <Field label="Data e hora">
          <input className="input" type="datetime-local" required value={f.collected_at} onChange={set("collected_at")} />
        </Field>
        <Field label="Acidez titulável (°D)" hint="Titulação Dornic, NaOH 1/9N">
          <input className="input num" inputMode="decimal" value={f.acidity_dornic} onChange={set("acidity_dornic")} placeholder="16,0" />
        </Field>
        <Field label="Densidade (g/mL a 15 °C)" hint="Termolactodensímetro">
          <input className="input num" inputMode="decimal" value={f.density} onChange={set("density")} placeholder="1,031" />
        </Field>
        <Field label="pH (peagômetro)">
          <input className="input num" inputMode="decimal" value={f.ph_manual} onChange={set("ph_manual")} placeholder="6,70" />
        </Field>
        <Field label="Temperatura do leite (°C)">
          <input className="input num" inputMode="decimal" value={f.milk_temperature} onChange={set("milk_temperature")} placeholder="4,0" />
        </Field>
        <Field label="Litragem coletada (L)">
          <input className="input num" type="number" min={0} value={f.volume_liters} onChange={set("volume_liters")} />
        </Field>
        <Field label="Lacre da amostra testemunha">
          <input className="input num" value={f.seal_code} onChange={set("seal_code")} maxLength={40} />
        </Field>
        <Field label="Decisão">
          <select className="input" value={f.decision} onChange={set("decision")}>
            <option value="aceito">Aceito</option>
            <option value="recusado">Recusado</option>
            <option value="reclassificado">Reclassificado</option>
          </select>
        </Field>
        <div className="sm:col-span-2">
          <Field label="Observações">
            <input className="input" value={f.notes} onChange={set("notes")} maxLength={2000} />
          </Field>
        </div>
        {error && (
          <div className="sm:col-span-3">
            <ErrorBox message={error} />
          </div>
        )}
        <p className="text-xs text-muted sm:col-span-3">A coleta não pode ser alterada depois de gravada. Para corrigir, registre uma nova coleta que a substitua.</p>
        <div className="flex justify-end gap-2 sm:col-span-3">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn-primary">Registrar</button>
        </div>
      </form>
    </Modal>
  );
}

function FinishForm({ trip, onClose, onSaved }: { trip: Trip; onClose: () => void; onSaved: () => void }) {
  const [arrival, setArrival] = useState(toLocalInput(new Date()));
  const [volume, setVolume] = useState(trip.volume_liters != null ? String(trip.volume_liters) : "");
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post(`/api/v1/trips/${trip.id}/finish`, { arrival_at: fromLocalInput(arrival), volume_liters: volume ? Number(volume) : null });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <Modal title={`Finalizar ${trip.code}`} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Chegada ao laticínio">
          <input className="input" type="datetime-local" required value={arrival} onChange={(e) => setArrival(e.target.value)} />
        </Field>
        <Field label="Volume entregue (L)">
          <input className="input num" type="number" min={0} value={volume} onChange={(e) => setVolume(e.target.value)} />
        </Field>
        {error && <ErrorBox message={error} />}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Voltar
          </button>
          <button className="btn-primary">Finalizar viagem</button>
        </div>
      </form>
    </Modal>
  );
}
