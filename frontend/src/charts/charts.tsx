import { useEffect, useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { day, num, time } from "../services/format";

/** Lê as cores do tema atual (variáveis CSS) e acompanha a troca claro/escuro. */
export function useColors() {
  const read = () => {
    const s = getComputedStyle(document.documentElement);
    const c = (n: string) => `rgb(${s.getPropertyValue(`--${n}`).trim().split(" ").join(",")})`;
    return { ink: c("ink"), muted: c("muted"), line: c("line"), brand: c("brand"), brandSoft: c("brand-soft"), data: c("data"), dataSoft: c("data-soft"), warn: c("warn"), bad: c("bad"), badSoft: c("bad-soft"), surface: c("surface"), sim: c("sim") };
  };
  const [colors, setColors] = useState(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setColors(read()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return colors;
}

const axis = (muted: string) => ({ tick: { fill: muted, fontSize: 11, fontFamily: "IBM Plex Mono" }, tickLine: false, axisLine: false });

function TooltipBox({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="card px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-semibold">{title}</div>
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4">
          <span className="text-muted">{k}</span>
          <span className="num">{v}</span>
        </div>
      ))}
    </div>
  );
}

export interface TimePoint {
  t: string;
  avg: number | null;
  min?: number | null;
  max?: number | null;
}

/**
 * Série no tempo com a faixa de referência (verde) ou o limite (linha vermelha).
 * Mostra média e, quando houver, a faixa mínimo–máximo de cada intervalo.
 */
export function TimeChart({
  points,
  unit,
  limits,
  color = "data",
  bucket = "minute",
  digits = 1,
  height = 220,
  domain,
}: {
  points: TimePoint[];
  unit: string;
  limits?: { min: number | null; max: number | null } | null;
  color?: "data" | "brand";
  bucket?: "minute" | "hour" | "day";
  digits?: number;
  height?: number;
  domain?: [number, number];
}) {
  const c = useColors();
  const stroke = color === "data" ? c.data : c.brand;
  const data = points.map((p) => ({ ...p, band: p.min != null && p.max != null ? [p.min, p.max] : null }));
  const fmtT = (t: string) => (bucket === "day" ? day(t) : time(t));
  const hasBand = limits && limits.min != null && limits.max != null;
  const showMinMax = data.some((p) => p.band && p.band[0] !== p.band[1]);
  return (
    <div className="flex flex-col gap-2">
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={c.line} vertical={false} />
        <XAxis dataKey="t" tickFormatter={fmtT} minTickGap={40} {...axis(c.muted)} />
        <YAxis domain={domain ?? ["auto", "auto"]} tickFormatter={(v) => num(v, digits)} width={48} {...axis(c.muted)} />
        {hasBand && <ReferenceArea y1={limits!.min!} y2={limits!.max!} fill={c.brandSoft} fillOpacity={0.9} ifOverflow="extendDomain" />}
        {limits && !hasBand && limits.max != null && (
          <ReferenceLine y={limits.max} stroke={c.bad} strokeDasharray="6 4" ifOverflow="extendDomain" label={{ value: `limite ${num(limits.max, digits)} ${unit}`, fill: c.bad, fontSize: 11, position: "insideTopRight" }} />
        )}
        {limits && !hasBand && limits.min != null && <ReferenceLine y={limits.min} stroke={c.bad} strokeDasharray="6 4" ifOverflow="extendDomain" />}
        <Area dataKey="band" stroke="none" fill={c.muted} fillOpacity={0.14} isAnimationActive={false} connectNulls />
        <Line dataKey="avg" stroke={stroke} strokeWidth={2.2} dot={false} isAnimationActive={false} connectNulls />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as TimePoint;
            const rows: [string, string][] = [["média", `${num(p.avg, digits)} ${unit}`]];
            if (p.min != null && p.max != null && p.min !== p.max) rows.push(["mín–máx", `${num(p.min, digits)} – ${num(p.max, digits)}`]);
            return <TooltipBox title={bucket === "day" ? day(p.t) : `${day(p.t)} ${time(p.t)}`} rows={rows} />;
          }}
        />
      </ComposedChart>
    </ResponsiveContainer>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 rounded" style={{ background: stroke }} />média</span>
        {showMinMax && <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-3 rounded-sm bg-muted/20" />mínimo–máximo do intervalo</span>}
        {hasBand && <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-3 rounded-sm bg-brand-soft ring-1 ring-brand/30" />faixa de referência</span>}
        {limits && !hasBand && limits.max != null && <span className="inline-flex items-center gap-1.5"><span className="h-0 w-4 border-t-2 border-dashed border-bad" />limite</span>}
      </div>
    </div>
  );
}

export function BarsChart({
  data,
  unit,
  digits = 0,
  height = 200,
  band,
  highlight,
}: {
  data: { label: string; value: number; title?: string; flag?: boolean }[];
  unit: string;
  digits?: number;
  height?: number;
  band?: { min: number | null; max: number | null } | null;
  highlight?: "data" | "brand";
}) {
  const c = useColors();
  const base = highlight === "brand" ? c.brand : c.data;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 16, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={c.line} vertical={false} />
        <XAxis dataKey="label" interval="preserveStartEnd" {...axis(c.muted)} />
        <YAxis tickFormatter={(v) => (v >= 1000 ? `${num(v / 1000, v % 1000 ? 1 : 0)} mil` : num(v, digits))} width={56} {...axis(c.muted)} />
        {band && band.min != null && band.max != null && <ReferenceArea y1={band.min} y2={band.max} fill={c.brandSoft} fillOpacity={0.9} ifOverflow="extendDomain" />}
        <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.flag ? c.bad : base} />
          ))}
        </Bar>
        <Tooltip
          cursor={{ fill: c.line, fillOpacity: 0.4 }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as { label: string; value: number; title?: string };
            return <TooltipBox title={p.title ?? p.label} rows={[["valor", `${num(p.value, digits)} ${unit}`]]} />;
          }}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Mini-gráfico sem eixos para os cartões de tempo real. */
export function Sparkline({ values, limit, color = "data", height = 56 }: { values: (number | null)[]; limit?: { min?: number | null; max?: number | null }; color?: "data" | "brand"; height?: number }) {
  const c = useColors();
  const data = values.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 4, right: 0, bottom: 4, left: 0 }}>
        <YAxis hide domain={["dataMin - 0.3", "dataMax + 0.3"]} />
        {limit?.min != null && limit?.max != null && <ReferenceArea y1={limit.min} y2={limit.max} fill={c.brandSoft} fillOpacity={0.9} ifOverflow="extendDomain" />}
        {limit?.max != null && limit?.min == null && <ReferenceLine y={limit.max} stroke={c.bad} strokeDasharray="4 3" ifOverflow="extendDomain" />}
        <Line dataKey="v" stroke={color === "data" ? c.data : c.brand} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
