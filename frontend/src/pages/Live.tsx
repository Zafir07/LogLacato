import { CloudOff, FlaskConical, Radio, Wifi, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkline } from "../charts/charts";
import { Badge, Empty, ErrorBox, Loading, PageHeader, Section, SimTag } from "../components/ui";
import { useLive } from "../hooks/live";
import { useAsync } from "../hooks/useAsync";
import { isOut, useParameters, type Limits } from "../hooks/useParameters";
import { api } from "../services/api";
import { ago, agoFrom, dateTime, num, time } from "../services/format";
import type { LiveDevice, Reading } from "../types/api";

interface LiveResponse {
  live_window_s: number;
  server_time: string;
  devices: LiveDevice[];
}

const n = (v: unknown) => (v === null || v === undefined ? null : Number(v));

export default function Live() {
  const { data, error, loading, reload, setData } = useAsync(() => api.get<LiveResponse>("/api/v1/live"), []);
  const [selected, setSelected] = useState<string | null>(null);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [now, setNow] = useState(Date.now());
  const limits = useParameters();

  const devices = data?.devices ?? [];
  const dev = devices.find((d) => d.device_id === selected) ?? devices[0];

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (!dev) return;
    api
      .get<Reading[]>(`/api/v1/devices/${dev.device_id}/readings?limit=60`)
      .then(setReadings)
      .catch(() => setReadings([]));
  }, [dev?.device_id]);

  const wsOk = useLive((m) => {
    if (m.type === "telemetry" && m.data) {
      const r = m.data as Reading;
      setData((prev) =>
        prev
          ? {
              ...prev,
              devices: prev.devices.map((d) =>
                d.device_id === r.device_id && (r.validation_status === "valid" || r.validation_status === "partial")
                  ? { ...d, last_reading: r, connection_status: "online", last_seen_at: r.received_at }
                  : d,
              ),
            }
          : prev,
      );
      if (dev && r.device_id === dev.device_id) setReadings((prev) => [r, ...prev].slice(0, 60));
    }
    if (m.type === "device_status" || (m.type === "event" && String(m.event ?? "").startsWith("coleta"))) reload();
  });

  const tL = limits("milk_temperature", "transporte");
  const pL = limits("ph", "transporte");
  const aL = limits("acidity_dornic", "coleta");

  const series = useMemo(() => {
    const valid = readings.filter((r) => r.validation_status === "valid" || r.validation_status === "partial").slice().reverse();
    return { temp: valid.map((r) => n(r.milk_temperature)), ph: valid.map((r) => n(r.ph)) };
  }, [readings]);

  if (!data && loading) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!dev)
    return (
      <div className="flex flex-col gap-5">
        <PageHeader title="Monitoramento em tempo real" />
        <Empty>Nenhum dispositivo cadastrado.</Empty>
      </div>
    );

  const r = dev.last_reading;
  const age = r?.measured_at ? (now - new Date(r.measured_at).getTime()) / 1000 : null;
  const live = age !== null && age <= (data?.live_window_s ?? 60) && dev.connection_status === "online";
  const st = (dev.last_status ?? {}) as Record<string, any>;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Monitoramento em tempo real"
        subtitle="Leituras dos sensores do caminhão, atualizadas automaticamente"
        actions={
          <Badge tone={wsOk ? "brand" : "warn"}>
            <Radio size={12} aria-hidden /> {wsOk ? "Atualização automática ligada" : "Reconectando…"}
          </Badge>
        }
      />

      <div role="group" aria-label="Dispositivo" className="flex flex-wrap gap-2">
        {devices.map((d) => {
          const on = d.device_id === dev.device_id;
          return (
            <button key={d.device_id} aria-pressed={on} onClick={() => setSelected(d.device_id)} className={`btn h-11 border ${on ? "border-nav bg-nav text-white" : "border-line bg-surface text-ink hover:bg-sunken"}`}>
              <span className={`h-2 w-2 rounded-full ${d.is_simulated ? "bg-sim" : d.connection_status === "online" ? "bg-brand" : "bg-bad"}`} aria-hidden />
              {d.device_id}
              {d.vehicle_plate ? ` · ${d.vehicle_plate}` : ""}
              {d.is_simulated ? " · SIMULADO" : ""}
            </button>
          );
        })}
      </div>

      {!live && (
        <div role="alert" className="flex items-start gap-3 rounded-xl border border-bad/30 bg-bad-soft px-4 py-3 text-sm text-bad">
          <CloudOff size={18} className="mt-0.5 shrink-0" aria-hidden />
          <span>
            {r ? (
              <>
                <strong>{dev.connection_status === "online" ? "Sem leitura recente" : "Sem comunicação"} {ago(age)}.</strong> Os valores abaixo são as últimas leituras recebidas ({dateTime(r.measured_at)}) e não representam
                necessariamente a condição atual do leite.
              </>
            ) : (
              <strong>Este dispositivo ainda não enviou nenhuma leitura válida.</strong>
            )}
          </span>
        </div>
      )}
      {dev.is_simulated && (
        <div role="note" className="flex items-center gap-2 rounded-xl border border-sim/30 bg-sim-soft px-4 py-3 text-sm text-sim">
          <FlaskConical size={16} aria-hidden />
          <span>
            <strong>SIMULADO.</strong> Leituras do simulador de hardware. Ficam fora dos indicadores, relatórios e alertas reais.
          </span>
        </div>
      )}

      <div className={`grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr))] ${live ? "" : "opacity-60"}`}>
        <Indicator title="Temperatura do leite" unit="°C" value={n(r?.milk_temperature)} digits={1} limits={tL} live={live} spark={series.temp} noSensor="Sem sonda DS18B20 ligada" extra={["Ar (DHT22)", r?.air_temperature != null ? `${num(r.air_temperature)} °C · ${num(r.air_humidity, 0)} %` : "—"]} />
        <Indicator title="pH" unit="" value={n(r?.ph)} digits={2} limits={pL} live={live} spark={series.ph} color="brand" noSensor="Sem sinal do módulo de pH" extra={["Tensão Po", r?.ph_voltage != null ? `${num(r.ph_voltage, 3)} V` : "—"]} />
        <section className="card flex flex-col gap-3 border-dashed p-5" aria-label="Acidez titulável">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-[15px] font-semibold">Acidez titulável</h2>
            <Badge>Registro manual</Badge>
          </div>
          <div className="num text-5xl font-semibold tracking-tight">
            {num(dev.last_sample?.acidity_dornic)}
            <span className="ml-1 text-lg font-normal text-muted">°D</span>
          </div>
          <p className="text-sm text-muted">
            Não é leitura de sensor: é a titulação Dornic do coletor.{" "}
            <strong className="text-ink">{dev.last_sample ? `${dev.last_sample.producer}, ${agoFrom(dev.last_sample.collected_at)}.` : "Nenhuma coleta nesta viagem."}</strong>
          </p>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-muted">Faixa</dt>
              <dd className="num">{aL ? `${num(aL.min)} – ${num(aL.max)} °D` : "—"}</dd>
            </div>
            <div>
              <dt className="text-muted">Método</dt>
              <dd>NaOH 1/9N</dd>
            </div>
          </dl>
        </section>
      </div>

      <Section title="Dispositivo e conexão">
        <dl className="grid gap-4 text-sm [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]">
          <Info label="Última leitura" value={<span className={live ? "text-brand" : "text-bad"}>{r ? `${ago(age)} · ${time(r.measured_at, true)}` : "nunca"}</span>} />
          <Info label="Dispositivo" value={`${dev.device_id} · fw ${dev.firmware_version ?? "?"}`} mono />
          <Info
            label="Wi-Fi"
            value={
              dev.connection_status === "online" && st.wifi_rssi != null ? (
                <span className="inline-flex items-center gap-1 text-brand">
                  <Wifi size={14} aria-hidden /> {st.wifi_rssi} dBm
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-muted">
                  <WifiOff size={14} aria-hidden /> {dev.is_simulated ? "n/a (simulador)" : "desconhecido"}
                </span>
              )
            }
          />
          <Info label="MQTT" value={<span className={dev.connection_status === "online" ? "text-brand" : "text-bad"}>{dev.connection_status === "online" ? "Conectado · QoS 1" : dev.connection_status === "offline" ? "Offline (Last Will)" : "Desconhecido"}</span>} />
          <Info label="Viagem vinculada" value={dev.trip ? <Link to={`/viagens/${dev.trip.id}`} className="num font-semibold text-brand">{dev.trip.code}</Link> : "nenhuma em andamento"} />
          <Info label="Fila offline" value={st.queue ? `${st.queue.pending ?? 0} pendentes` : "—"} mono />
          <Info label="Fonte do horário" value={r?.time_source?.toUpperCase() ?? "—"} mono />
          <Info label="Sensores" value={sensors(st, r)} />
        </dl>
      </Section>

      <Section title="Últimas leituras recebidas" aside="“fila” = guardada sem conexão e enviada depois, com o horário original">
        {readings.length === 0 ? (
          <Empty>Nenhuma leitura deste dispositivo.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr>
                  <th className="th">Medida às</th>
                  <th className="th">Recebida às</th>
                  <th className="th text-right">pH</th>
                  <th className="th text-right">Leite °C</th>
                  <th className="th text-right">Ar °C</th>
                  <th className="th">Origem</th>
                  <th className="th">Validação</th>
                </tr>
              </thead>
              <tbody>
                {readings.slice(0, 12).map((x) => (
                  <tr key={x.id}>
                    <td className="td num">{time(x.measured_at, true)}</td>
                    <td className="td num text-muted">{time(x.received_at, true)}</td>
                    <td className={`td num text-right ${isOut(n(x.ph), pL) ? "text-warn font-semibold" : ""}`}>{num(x.ph, 2)}</td>
                    <td className={`td num text-right ${isOut(n(x.milk_temperature), tL) ? "text-bad font-semibold" : ""}`}>{num(x.milk_temperature)}</td>
                    <td className="td num text-right text-muted">{num(x.air_temperature)}</td>
                    <td className="td">{x.is_simulated ? <SimTag /> : x.buffered ? <Badge tone="warn">fila</Badge> : "ao vivo"}</td>
                    <td className="td text-sm">
                      {x.validation_status === "valid" ? (
                        <span className="text-brand">válida</span>
                      ) : x.validation_status === "partial" ? (
                        <span className="text-warn" title={(x.validation_errors ?? []).join("; ")}>
                          parcial
                        </span>
                      ) : (
                        <span className="text-bad" title={(x.validation_errors ?? []).join("; ")}>
                          {x.validation_status === "invalid" ? "inválida" : "sem horário"}
                        </span>
                      )}
                    </td>
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

function sensors(st: Record<string, any>, r: Reading | null): string {
  if (st.sensors && typeof st.sensors === "object") {
    return Object.entries(st.sensors as Record<string, any>)
      .map(([k, v]) => `${k} ${typeof v === "object" ? v.state : v}`)
      .join(" · ");
  }
  if (!r) return "—";
  const f = r.sensor_flags;
  return [`pH ${f & 6 ? "falha" : "ok"}`, `DHT22 ${f & 1 ? "falha" : "ok"}`, `DS18B20 ${f & 8 ? "ausente" : f & 16 ? "falha" : "ok"}`].join(" · ");
}

function Info({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`font-medium ${mono ? "num" : ""}`}>{value}</dd>
    </div>
  );
}

function Indicator({
  title,
  unit,
  value,
  digits,
  limits,
  live,
  spark,
  color = "data",
  noSensor,
  extra,
}: {
  title: string;
  unit: string;
  value: number | null;
  digits: number;
  limits: Limits;
  live: boolean;
  spark: (number | null)[];
  color?: "data" | "brand";
  noSensor: string;
  extra: [string, string];
}) {
  const out = isOut(value, limits);
  const status: [string, string] =
    value === null ? ["Sem medição", "bg-sunken text-muted"] : !live ? ["Leitura antiga", "bg-sunken text-muted"] : out ? ["Fora da faixa", "bg-bad-soft text-bad"] : ["Dentro da faixa", "bg-brand-soft text-brand-ink"];
  const range = limits ? (limits.min != null && limits.max != null ? `${num(limits.min, digits === 2 ? 1 : 1)} – ${num(limits.max, 1)}` : limits.max != null ? `≤ ${num(limits.max)} ${unit}` : `≥ ${num(limits.min)} ${unit}`) : "sem parâmetro";
  return (
    <section className={`card flex flex-col gap-3 p-5 ${out && live ? "border-bad/50" : ""}`} aria-label={title}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold">{title}</h2>
        <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${status[1]}`}>{status[0]}</span>
      </div>
      <div className={`num text-5xl font-semibold tracking-tight ${out && live ? "text-bad" : ""}`}>
        {value === null ? <span className="text-2xl text-muted">{noSensor}</span> : num(value, digits)}
        {value !== null && unit && <span className="ml-1 text-lg font-normal text-muted">{unit}</span>}
      </div>
      <Sparkline values={spark} limit={limits ?? undefined} color={color} />
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <dt className="text-muted">Limite</dt>
          <dd className="num">{range}</dd>
        </div>
        <div>
          <dt className="text-muted">{extra[0]}</dt>
          <dd className="num">{extra[1]}</dd>
        </div>
      </dl>
    </section>
  );
}
