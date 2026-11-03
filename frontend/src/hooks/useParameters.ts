import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { QualityParameter } from "../types/api";

export type Limits = { min: number | null; max: number | null; unit: string; source: string } | null;

/** Parâmetros de qualidade vigentes, por grandeza e contexto. */
export function useParameters() {
  const [params, setParams] = useState<QualityParameter[]>([]);
  useEffect(() => {
    api.get<QualityParameter[]>("/api/v1/quality-parameters").then(setParams).catch(() => {});
  }, []);
  return (parameter: string, context: string): Limits => {
    const p = params.find((x) => x.parameter === parameter && x.context === context);
    if (!p) return null;
    return {
      min: p.minimum_value != null ? Number(p.minimum_value) : null,
      max: p.maximum_value != null ? Number(p.maximum_value) : null,
      unit: p.unit,
      source: p.source_reference,
    };
  };
}

export function isOut(v: number | null | undefined, l: Limits) {
  if (v == null || !l) return false;
  return (l.min != null && v < l.min) || (l.max != null && v > l.max);
}
