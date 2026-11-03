import { useState } from "react";
import { Empty, ErrorBox, Loading, PageHeader, Pagination } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api, qs } from "../services/api";
import type { Page, Sample } from "../types/api";
import { SamplesTable } from "./TripDetail";

export default function Samples() {
  const [page, setPage] = useState(1);
  const [sim, setSim] = useState(false);
  const { data, error, loading, reload } = useAsync(() => api.get<Page<Sample>>(`/api/v1/samples${qs({ page, page_size: 25, include_simulated: sim })}`), [page, sim]);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Coletas"
        subtitle="Acidez Dornic, densidade, litragem e decisão de aceite registradas pelo coletor. Para registrar, abra a viagem."
        actions={
          <label className="flex h-10 items-center gap-2 text-sm">
            <input type="checkbox" className="h-[18px] w-[18px]" checked={sim} onChange={(e) => { setSim(e.target.checked); setPage(1); }} /> Incluir simuladas
          </label>
        }
      />
      {error && <ErrorBox message={error} onRetry={reload} />}
      <div className="card p-2">
        {!data && loading && <Loading />}
        {data && data.items.length === 0 && <Empty>Nenhuma coleta registrada.</Empty>}
        {data && data.items.length > 0 && (
          <>
            <SamplesTable samples={data.items} showTrip />
            <div className="px-2">
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
            </div>
          </>
        )}
      </div>
      <p className="text-xs text-muted">Valores em vermelho estão fora da faixa de referência vigente na data da coleta.</p>
    </div>
  );
}
