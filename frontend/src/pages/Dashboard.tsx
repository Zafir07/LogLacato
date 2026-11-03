import { Activity, AlertTriangle, Beaker, Cpu, Droplets, FlaskConical, Gauge, Thermometer, Truck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { BarsChart, TimeChart } from "../charts/charts";
import GpsMap from "../charts/GpsMap";
import Filters, { defaultFilters, filterParams, type FilterState } from "../components/Filters";
import { Empty, ErrorBox, Kpi, Loading, PageHeader, Section, SimBanner, SimTag, TripStatusBadge } from "../components/ui";
import { useLive } from "../hooks/live";
import { useAsync } from "../hooks/useAsync";
import { api, qs } from "../services/api";
import { day, dateTime, int, num, STATUS_LABEL } from "../services/format";
import type { Overview, Series, TripComparison, TripStatus } from "../types/api";

interface Acidity {
  limits: { min: number | null; max: number | null } | null;
  samples: { id: number; trip_code: string; producer: string; collected_at: string; acidity_dornic: number; decision: string }[];
}

export default function Dashboard() {
  const [f, setF] = useState<FilterState>(defaultFilters);
  const params = qs(filterParams(f));
  const { data, error, loading, reload } = useAsync(
    async () => {
      const [ov, temp, ph, acid, vol, comp, pos] = await Promise.all([
        api.get<Overview>(`/api/v1/analytics/overview${params}`),
        api.get<Series>(`/api/v1/analytics/series${params}&metric=milk_temperature`),
        api.get<Series>(`/api/v1/analytics/series${params}&metric=ph`),
        api.get<Acidity>(`/api/v1/analytics/acidity${params}&limit=16`),
        api.get<{ day: string; volume_liters: number; trips: number }[]>(`/api/v1/analytics/volume-by-day${params}`),
        api.get<TripComparison[]>(`/api/v1/analytics/trip-comparison${params}&limit=8`),
        api.get<{ trip_code: string; vehicle_plate: string; lat: number; lon: number; at: string }[]>(
          `/api/v1/analytics/positions${f.include_simulated ? "?include_simulated=true" : ""}`,
        ),
      ]);
      return { ov, temp, ph, acid, vol, comp, pos };
    },
    [params],
  );

  // Atualiza sozinho quando chegam leituras ou alertas (no máximo a cada 15 s).
  const last = useRef(0);
  useLive((m) => {
    if (m.type !== "telemetry" && m.type !== "event") return;
    if (Date.now() - last.current < 15000) return;
    last.current = Date.now();
    reload();
  });
  useEffect(() => {
    const t = setInterval(reload, 60000);
    return () => clearInterval(t);
  }, [reload]);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Dashboard" subtitle="Visão gerencial · indicadores calculados sobre as leituras válidas gravadas no banco" />
      <Filters value={f} onChange={setF} />
      {f.include_simulated && <SimBanner />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && <Content d={data} />}
    </div>
  );
}

function Content({ d }: { d: { ov: Overview; temp: Series; ph: Series; acid: Acidity; vol: { day: string; volume_liters: number; trips: number }[]; comp: TripComparison[]; pos: { trip_code: string; vehicle_plate: string; lat: number; lon: number; at: string }[] } }) {
  const { ov } = d;
  const sev = ov.alerts_by_severity;
  const offline = ov.devices_total - ov.devices_online;
  const statuses: TripStatus[] = ["em_andamento", "finalizada", "planejada", "cancelada"];
  const maxStatus = Math.max(1, ...statuses.map((s) => ov.trips_by_status[s] ?? 0));
  // Limites vêm dos parâmetros de qualidade cadastrados (nunca fixos no código).
  const out = (v: number | null, l: { min: number | null; max: number | null } | null | undefined) =>
    v != null && !!l && ((l.min != null && v < l.min) || (l.max != null && v > l.max));
  const phL = d.ph.limits;
  const tL = d.temp.limits;
  const aL = d.acid.limits;

  return (
    <>
      {offline > 0 && (
        <div role="status" className="card flex flex-wrap items-center gap-3 border-bad/30 px-4 py-3 text-sm">
          <span className="rounded-md bg-bad-soft px-2 py-0.5 text-xs font-semibold uppercase text-bad">Sem comunicação</span>
          <span>
            {offline} de {ov.devices_total} dispositivo(s) sem conexão. O último valor recebido deles não representa a condição atual do leite.
          </span>
          <Link to="/tempo-real" className="ml-auto font-semibold text-brand">
            Ver tempo real
          </Link>
        </div>
      )}

      <section aria-label="Indicadores" className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(196px,1fr))]">
        <Kpi label="Volume transportado" value={int(ov.volume_liters)} unit="L" note={`${ov.trips} viagens no período`} icon={<Droplets size={16} />} />
        <Kpi label="Viagens" value={int(ov.trips)} note={`${ov.trips_by_status.em_andamento ?? 0} em andamento`} icon={<Truck size={16} />} />
        <Kpi label="Veículos em operação" value={int(ov.vehicles_in_operation)} unit={`de ${ov.vehicles_total}`} tone="data" note="agora" icon={<Gauge size={16} />} />
        <Kpi label="Viagens finalizadas" value={int(ov.trips_finished)} tone="brand" note={ov.trips ? `${Math.round((ov.trips_finished / ov.trips) * 100)}% do total` : "—"} icon={<Activity size={16} />} />
        <Kpi label="Temperatura média do leite" value={num(ov.milk_temp_avg)} unit="°C" note={ov.milk_temp_readings ? `${int(ov.milk_temp_readings)} leituras válidas` : "sem leitura de temperatura do leite"} icon={<Thermometer size={16} />} />
        <Kpi label="pH médio" value={num(ov.ph_avg, 2)} note={phL ? `faixa de referência ${num(phL.min)} – ${num(phL.max)}` : "sem parâmetro cadastrado"} tone={out(ov.ph_avg, phL) ? "warn" : "brand"} icon={<FlaskConical size={16} />} />
        <Kpi label="Acidez média" value={num(ov.acidity_avg)} unit="°D" note={ov.acidity_samples ? `${ov.acidity_samples} coletas · titulação Dornic` : "nenhuma coleta registrada"} icon={<Beaker size={16} />} />
        <Kpi label="Alertas ativos" value={int(ov.alerts_active)} tone={ov.alerts_active ? "bad" : "brand"} note={`${sev.critico ?? 0} crítico · ${sev.atencao ?? 0} atenção · ${sev.info ?? 0} info`} icon={<AlertTriangle size={16} />} />
        <Kpi label="Dispositivos conectados" value={int(ov.devices_online)} unit={`de ${ov.devices_total}`} tone={offline ? "warn" : "brand"} note={ov.simulated_devices ? `+${ov.simulated_devices} simulado(s) à parte` : "—"} icon={<Cpu size={16} />} />
      </section>

      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr))]">
        <Section title="Evolução da temperatura do leite" aside={d.temp.limits ? `limite ≤ ${num(d.temp.limits.max)} °C · transporte` : "°C"}>
          {d.temp.points.length ? (
            <TimeChart points={d.temp.points} unit="°C" limits={d.temp.limits} bucket={d.temp.bucket} />
          ) : (
            <Empty>Sem leitura de temperatura do leite no período. A ausência de leitura não significa que o leite esteve dentro do limite.</Empty>
          )}
        </Section>
        <Section title="Evolução do pH" aside={d.ph.limits ? `faixa ${num(d.ph.limits.min)} – ${num(d.ph.limits.max)}` : undefined}>
          {d.ph.points.length ? <TimeChart points={d.ph.points} unit="" limits={d.ph.limits} bucket={d.ph.bucket} color="brand" digits={2} /> : <Empty>Sem leitura de pH no período.</Empty>}
        </Section>
      </div>

      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr))]">
        <Section title="Acidez titulável por coleta" aside="°D · registrada pelo coletor">
          {d.acid.samples.length ? (
            <BarsChart
              data={d.acid.samples.map((s) => ({ label: day(s.collected_at), value: s.acidity_dornic, title: `${s.producer} · ${s.trip_code} · ${dateTime(s.collected_at)}`, flag: d.acid.limits?.max != null && s.acidity_dornic > d.acid.limits.max }))}
              unit="°D"
              digits={1}
              band={d.acid.limits}
            />
          ) : (
            <Empty>Nenhuma coleta com acidez no período.</Empty>
          )}
        </Section>
        <Section title="Volume transportado por dia" aside="litros">
          {d.vol.length ? <BarsChart data={d.vol.map((v) => ({ label: day(v.day), value: v.volume_liters, title: `${day(v.day)} · ${v.trips} viagem(ns)` }))} unit="L" highlight="data" /> : <Empty>Sem viagens no período.</Empty>}
        </Section>
        <Section title="Viagens por status" aside={`${ov.trips} no período`}>
          <div className="flex flex-col gap-4 pt-1">
            {statuses.map((s) => (
              <div key={s} className="flex flex-col gap-1.5">
                <div className="flex justify-between text-sm">
                  <span>{STATUS_LABEL[s]}</span>
                  <span className="num font-semibold">{ov.trips_by_status[s] ?? 0}</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-sunken">
                  <div className={`h-full rounded-full ${s === "finalizada" ? "bg-brand" : s === "em_andamento" ? "bg-data" : "bg-muted/50"}`} style={{ width: `${((ov.trips_by_status[s] ?? 0) / maxStatus) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Section>
      </div>

      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr))]">
        <Section title="Comparativo de qualidade entre viagens" aside={<Link to="/viagens" className="font-semibold text-brand">Ver todas</Link>} className="lg:col-span-2">
          {d.comp.length ? (
            <div className="overflow-x-auto -mx-1">
              <table className="w-full min-w-[760px]">
                <thead>
                  <tr>
                    <th className="th">Viagem</th>
                    <th className="th">Veículo · motorista</th>
                    <th className="th text-right">Volume</th>
                    <th className="th text-right">pH médio</th>
                    <th className="th text-right">Temp. máx.</th>
                    <th className="th text-right">Acidez</th>
                    <th className="th text-right">Alertas</th>
                    <th className="th">Situação</th>
                  </tr>
                </thead>
                <tbody>
                  {d.comp.map((t) => (
                    <tr key={t.id}>
                      <td className="td">
                        <Link to={`/viagens/${t.id}`} className="num font-semibold text-brand">
                          {t.code}
                        </Link>
                        <div className="text-xs text-muted">{dateTime(t.departure_at)}</div>
                      </td>
                      <td className="td">
                        {t.vehicle_plate} · {t.driver_name} {t.is_simulated && <SimTag />}
                      </td>
                      <td className="td num text-right">{t.volume_liters != null ? `${int(t.volume_liters)} L` : "—"}</td>
                      <td className={`td num text-right ${out(t.ph_avg, phL) ? "text-warn font-semibold" : ""}`}>{num(t.ph_avg, 2)}</td>
                      <td className={`td num text-right ${out(t.milk_temp_max, tL) ? "text-bad font-semibold" : ""}`}>{t.milk_temp_max != null ? `${num(t.milk_temp_max)} °C` : "—"}</td>
                      <td className={`td num text-right ${out(t.acidity_avg, aL) ? "text-bad font-semibold" : ""}`}>{t.acidity_avg != null ? `${num(t.acidity_avg)} °D` : "—"}</td>
                      <td className="td num text-right">{t.alerts}</td>
                      <td className="td">
                        <TripStatusBadge status={t.status} />
                        {t.samples_rejected > 0 && <div className="mt-1 text-xs text-bad">{t.samples_rejected} lote(s) recusado(s)</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 px-1 text-xs text-muted">“—” = sem leitura válida. A ausência de leitura não é tratada como valor normal.</p>
            </div>
          ) : (
            <Empty>Nenhuma viagem no período.</Empty>
          )}
        </Section>
        <Section title="Posição dos veículos em viagem" aside="GPS da T-Beam">
          <GpsMap height={300} markers={d.pos.map((p) => ({ lat: p.lat, lon: p.lon, label: `${p.trip_code} · ${p.vehicle_plate} · ${dateTime(p.at)}` }))} />
        </Section>
      </div>
    </>
  );
}
