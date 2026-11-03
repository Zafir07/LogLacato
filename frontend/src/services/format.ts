// Formatação no padrão brasileiro e no fuso de Brasília.

const TZ = "America/Sao_Paulo";

export function num(v: unknown, digits = 1): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function int(v: unknown): string {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("pt-BR", { maximumFractionDigits: 0 }) : "—";
}

export function dateTime(v: string | null | undefined): string {
  if (!v) return "—";
  return new Date(v).toLocaleString("pt-BR", { timeZone: TZ, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function time(v: string | null | undefined, seconds = false): string {
  if (!v) return "—";
  return new Date(v).toLocaleTimeString("pt-BR", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: seconds ? "2-digit" : undefined });
}

export function day(v: string): string {
  const d = v.length === 10 ? new Date(`${v}T12:00:00`) : new Date(v);
  return d.toLocaleDateString("pt-BR", { timeZone: TZ, day: "2-digit", month: "2-digit" });
}

export function ago(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "sem leitura";
  if (seconds < 60) return `há ${Math.max(0, Math.round(seconds))} s`;
  if (seconds < 3600) return `há ${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `há ${Math.round(seconds / 3600)} h`;
  return `há ${Math.round(seconds / 86400)} d`;
}

export function agoFrom(iso: string | null | undefined): string {
  if (!iso) return "nunca";
  return ago((Date.now() - new Date(iso).getTime()) / 1000);
}

/** Valor para <input type="datetime-local"> no fuso local do navegador. */
export function toLocalInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function fromLocalInput(v: string): string | null {
  return v ? new Date(v).toISOString() : null;
}

export const PARAM_LABEL: Record<string, string> = {
  ph: "pH",
  milk_temperature: "Temperatura do leite",
  acidity_dornic: "Acidez titulável",
  density: "Densidade",
};

export const CONTEXT_LABEL: Record<string, string> = { coleta: "Coleta", transporte: "Transporte", recepcao: "Recepção" };

export const STATUS_LABEL: Record<string, string> = {
  planejada: "Planejada",
  em_andamento: "Em andamento",
  finalizada: "Finalizada",
  cancelada: "Cancelada",
};

export const ALERT_TYPE_LABEL: Record<string, string> = {
  qualidade: "Qualidade",
  sem_leitura: "Ausência de leitura",
  dispositivo_offline: "Sem comunicação",
  dados_invalidos: "Dados inválidos",
  atraso: "Viagem com atraso",
  sensor: "Falha de sensor",
};
