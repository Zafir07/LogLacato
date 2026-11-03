import { FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import Filters, { defaultFilters, filterParams, type FilterState } from "../components/Filters";
import { ErrorBox, PageHeader, Section, SimBanner } from "../components/ui";
import { download, qs } from "../services/api";

export default function Reports() {
  const [f, setF] = useState<FilterState>(defaultFilters);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const params = qs(filterParams(f));
  const stamp = new Date().toISOString().slice(0, 10);

  const get = async (key: string, path: string, name: string) => {
    setBusy(key);
    setError(null);
    try {
      await download(path, name);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const items = [
    { key: "trips", title: "Viagens, volume e comparação", text: "Uma planilha com as viagens do período lado a lado (volume, pH médio, temperatura máxima do leite, acidez, alertas, última posição GPS) e uma aba com o volume por dia. Filtre por veículo ou motorista para o relatório por veículo.", path: `/api/v1/reports/trips.xlsx${params}`, file: `viagens-${stamp}.xlsx` },
    { key: "alerts", title: "Histórico de alertas", text: "Todos os alertas do período, com classificação, valores medidos, referência, reconhecimento e encerramento.", path: `/api/v1/reports/alerts.xlsx${params}`, file: `alertas-${stamp}.xlsx` },
  ];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Relatórios" subtitle="Exportação em Excel com os filtros abaixo. O relatório em PDF de uma viagem e as leituras de temperatura e pH ficam na página de cada viagem." />
      <Filters value={f} onChange={setF} />
      {f.include_simulated && <SimBanner />}
      {error && <ErrorBox message={error} />}
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr))]">
        {items.map((it) => (
          <Section key={it.key} title={it.title}>
            <p className="text-sm text-muted">{it.text}</p>
            <button className="btn-primary self-start" disabled={busy === it.key} onClick={() => get(it.key, it.path, it.file)}>
              <FileSpreadsheet size={16} /> {busy === it.key ? "Gerando…" : "Baixar Excel"}
            </button>
          </Section>
        ))}
        <Section title="Relatório de uma viagem (PDF)">
          <p className="text-sm text-muted">Informações logísticas, resumo, temperatura, pH, coletas e alertas. Abra a viagem em Viagens e use o botão PDF.</p>
          <span className="inline-flex items-center gap-2 text-sm text-muted">
            <FileText size={16} /> Viagens → (viagem) → PDF
          </span>
        </Section>
      </div>
    </div>
  );
}
