import { Check, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Empty, ErrorBox, Field, Loading, Modal, PageHeader, Pagination, SeverityBadge, SimTag } from "../components/ui";
import { useAuth } from "../hooks/auth";
import { useLive } from "../hooks/live";
import { useAsync } from "../hooks/useAsync";
import { api, qs } from "../services/api";
import { ALERT_TYPE_LABEL, dateTime, num, PARAM_LABEL } from "../services/format";
import type { Alert, Page } from "../types/api";

export default function Alerts() {
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("ativos");
  const [severity, setSeverity] = useState("");
  const [type, setType] = useState("");
  const [sim, setSim] = useState(false);
  const [closing, setClosing] = useState<Alert | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setPage(1), [status, severity, type, sim]);

  const { data, error, loading, reload } = useAsync(
    () =>
      api.get<Page<Alert>>(
        `/api/v1/alerts${qs({ page, page_size: 20, status: status === "ativos" ? undefined : status, active_only: status === "ativos", severity, type, include_simulated: sim })}`,
      ),
    [page, status, severity, type, sim],
  );
  useLive((m) => {
    if (m.type === "event" && String(m.event ?? "").startsWith("alerta")) reload();
  });

  const ack = async (a: Alert) => {
    setErr(null);
    try {
      await api.post(`/api/v1/alerts/${a.id}/acknowledge`);
      reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Central de alertas" subtitle="Uma ocorrência contínua gera um alerta só, que se atualiza; ele fecha sozinho quando a condição volta ao normal com folga (histerese)." />
      <div className="flex flex-wrap items-end gap-3">
        <label className="label flex-[1_1_160px]">
          Situação
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="ativos">Ativos (abertos e reconhecidos)</option>
            <option value="aberto">Abertos</option>
            <option value="reconhecido">Reconhecidos</option>
            <option value="encerrado">Encerrados</option>
            <option value="">Todos</option>
          </select>
        </label>
        <label className="label flex-[1_1_140px]">
          Classificação
          <select className="input" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">Todas</option>
            <option value="critico">Crítico</option>
            <option value="atencao">Atenção</option>
            <option value="info">Informativo</option>
          </select>
        </label>
        <label className="label flex-[1_1_180px]">
          Tipo
          <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">Todos</option>
            {Object.entries(ALERT_TYPE_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="flex h-10 items-center gap-2 text-sm">
          <input type="checkbox" className="h-[18px] w-[18px]" checked={sim} onChange={(e) => setSim(e.target.checked)} /> Incluir simulados
        </label>
      </div>
      {(error || err) && <ErrorBox message={(error || err)!} onRetry={reload} />}
      <div className="card divide-y divide-line">
        {!data && loading && <Loading />}
        {data && data.items.length === 0 && <Empty>Nenhum alerta com esses filtros.</Empty>}
        {data?.items.map((a) => (
          <article key={a.id} className="flex flex-wrap items-start gap-4 p-4">
            <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={a.severity} />
                <h3 className="font-semibold">{a.title}</h3>
                {a.is_simulated && <SimTag />}
                <Badge tone={a.status === "aberto" ? "bad" : a.status === "reconhecido" ? "warn" : "neutral"}>{a.status}</Badge>
              </div>
              {a.description && <p className="text-sm">{a.description}</p>}
              <p className="text-xs text-muted">
                {ALERT_TYPE_LABEL[a.type] ?? a.type}
                {a.parameter ? ` · ${PARAM_LABEL[a.parameter] ?? a.parameter}` : ""}
                {a.measured_value != null ? ` · medido ${num(a.measured_value, 2)}` : ""}
                {a.reference_min != null || a.reference_max != null ? ` · referência ${a.reference_min != null ? num(a.reference_min, 2) : ""}${a.reference_min != null && a.reference_max != null ? "–" : a.reference_max != null ? "≤ " : ""}${a.reference_max != null ? num(a.reference_max, 2) : ""}` : ""}
                {" · "}
                {a.occurrences} ocorrência(s) · desde {dateTime(a.first_seen_at)} · última {dateTime(a.last_seen_at)}
                {a.trip_id && (
                  <>
                    {" · "}
                    <Link to={`/viagens/${a.trip_id}`} className="font-semibold text-brand">
                      {a.trip_code}
                    </Link>
                  </>
                )}
                {a.device_id && ` · ${a.device_id}`}
              </p>
              {a.close_reason && <p className="text-xs text-muted">Encerrado: {a.close_reason}</p>}
            </div>
            {can("gestor") && a.status !== "encerrado" && (
              <div className="flex gap-2">
                {a.status === "aberto" && (
                  <button className="btn-ghost" onClick={() => ack(a)}>
                    <Check size={16} /> Reconhecer
                  </button>
                )}
                <button className="btn-ghost" onClick={() => setClosing(a)}>
                  <X size={16} /> Encerrar
                </button>
              </div>
            )}
          </article>
        ))}
        {data && data.total > 0 && (
          <div className="px-4 py-2">
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
          </div>
        )}
      </div>
      {closing && <CloseForm alert={closing} onClose={() => setClosing(null)} onDone={() => { setClosing(null); reload(); }} />}
    </div>
  );
}

function CloseForm({ alert, onClose, onDone }: { alert: Alert; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal title="Encerrar ocorrência" onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api.post(`/api/v1/alerts/${alert.id}/close`, { reason });
            onDone();
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        <p className="text-sm">{alert.title}</p>
        <Field label="Motivo / providência tomada">
          <input className="input" required minLength={3} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ex.: lote redirecionado para recepção prioritária" />
        </Field>
        {error && <ErrorBox message={error} />}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Voltar
          </button>
          <button className="btn-primary">Encerrar</button>
        </div>
      </form>
    </Modal>
  );
}
