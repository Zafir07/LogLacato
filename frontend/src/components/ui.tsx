import { AlertTriangle, ChevronLeft, ChevronRight, FlaskConical, Inbox, Loader2, X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { STATUS_LABEL } from "../services/format";
import type { Severity, TripStatus } from "../types/api";

type Tone = "neutral" | "brand" | "data" | "warn" | "bad" | "sim";
const TONE: Record<Tone, string> = {
  neutral: "bg-sunken text-muted border-line",
  brand: "bg-brand-soft text-brand-ink border-transparent",
  data: "bg-data-soft text-data border-transparent",
  warn: "bg-warn-soft text-warn border-transparent",
  bad: "bg-bad-soft text-bad border-transparent",
  sim: "bg-sim-soft text-sim border-transparent",
};

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-semibold ${TONE[tone]}`}>
      {children}
    </span>
  );
}

export function SimTag() {
  return (
    <Badge tone="sim" title="Dado do simulador de hardware: não entra nos indicadores reais">
      <FlaskConical size={12} aria-hidden /> SIMULADO
    </Badge>
  );
}

const TRIP_TONE: Record<TripStatus, Tone> = { planejada: "neutral", em_andamento: "data", finalizada: "brand", cancelada: "neutral" };
export function TripStatusBadge({ status }: { status: TripStatus }) {
  return <Badge tone={TRIP_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}

const SEV: Record<Severity, [Tone, string]> = { info: ["data", "Informativo"], atencao: ["warn", "Atenção"], critico: ["bad", "Crítico"] };
export function SeverityBadge({ severity }: { severity: Severity }) {
  const [tone, label] = SEV[severity];
  return <Badge tone={tone}>{label}</Badge>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-serif text-[28px] leading-tight font-semibold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Section({ title, aside, children, className = "" }: { title: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card p-5 flex flex-col gap-4 min-w-0 ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold">{title}</h2>
        {aside && <div className="text-xs text-muted">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

export function Kpi({ label, value, unit, note, tone = "ink", icon }: { label: string; value: ReactNode; unit?: string; note?: ReactNode; tone?: "ink" | "brand" | "data" | "warn" | "bad"; icon?: ReactNode }) {
  const color = { ink: "text-ink", brand: "text-brand", data: "text-data", warn: "text-warn", bad: "text-bad" }[tone];
  return (
    <article className="card p-4 flex flex-col gap-2 min-h-[118px]">
      <div className="flex items-center justify-between gap-2 text-[13px] font-medium text-muted">
        <span>{label}</span>
        {icon && <span aria-hidden className="text-muted/70">{icon}</span>}
      </div>
      <div className={`num text-[28px] font-semibold leading-none tracking-tight ${color}`}>
        {value}
        {unit && <span className="ml-1 text-sm font-medium text-muted">{unit}</span>}
      </div>
      {note && <div className="text-xs text-muted">{note}</div>}
    </article>
  );
}

export function Loading({ label = "Carregando…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 justify-center text-sm text-muted" role="status">
      <Loader2 className="animate-spin" size={16} aria-hidden /> {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-bad/30 bg-bad-soft px-4 py-3 text-sm text-bad">
      <AlertTriangle size={16} aria-hidden />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <button className="btn-ghost h-8" onClick={onRetry}>
          Tentar de novo
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted">
      <Inbox size={22} aria-hidden />
      {children}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between gap-3 pt-2 text-sm text-muted">
      <span>
        {total === 0 ? "Nenhum registro" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} de ${total}`}
      </span>
      <div className="flex items-center gap-1">
        <button className="btn-ghost h-9 w-9 px-0" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Página anterior">
          <ChevronLeft size={16} />
        </button>
        <span className="num px-2">
          {page}/{pages}
        </span>
        <button className="btn-ghost h-9 w-9 px-0" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Próxima página">
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => d?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className={`card p-0 text-ink backdrop:bg-black/40 w-[calc(100%-32px)] ${wide ? "max-w-3xl" : "max-w-lg"}`}
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="text-base font-semibold">{title}</h2>
        <button className="btn-ghost h-9 w-9 px-0" onClick={onClose} aria-label="Fechar">
          <X size={16} />
        </button>
      </div>
      <div className="max-h-[75vh] overflow-y-auto px-5 py-4">{children}</div>
    </dialog>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="label">
      {label}
      {children}
      {hint && <span className="font-normal text-muted">{hint}</span>}
    </label>
  );
}

export function SimBanner() {
  return (
    <div role="note" className="flex items-center gap-2 rounded-lg border border-sim/30 bg-sim-soft px-4 py-2.5 text-sm text-sim">
      <FlaskConical size={16} aria-hidden />
      <span>
        <strong>Incluindo dados SIMULADOS.</strong> Os números abaixo misturam leituras do simulador de hardware e não representam a operação real.
      </span>
    </div>
  );
}
