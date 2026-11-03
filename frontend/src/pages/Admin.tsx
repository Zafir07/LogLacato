import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Badge, Empty, ErrorBox, Field, Loading, Modal, PageHeader, Pagination } from "../components/ui";
import { ROLE_LABEL, useAuth } from "../hooks/auth";
import { useAsync } from "../hooks/useAsync";
import { api, qs } from "../services/api";
import { CONTEXT_LABEL, dateTime, num, PARAM_LABEL } from "../services/format";
import type { Page, QualityParameter, Role, User } from "../types/api";

// ------------------------------------------------------------------ parâmetros
export function Parameters() {
  const { can } = useAuth();
  const [history, setHistory] = useState(false);
  const [edit, setEdit] = useState<QualityParameter | "new" | null>(null);
  const { data, error, loading, reload } = useAsync(() => api.get<QualityParameter[]>(`/api/v1/quality-parameters${history ? "?include_history=true" : ""}`), [history]);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Parâmetros de qualidade"
        subtitle="Faixas de referência usadas nos alertas e indicadores. Mudar um limite cria uma nova versão: leituras antigas continuam avaliadas pelo limite que valia na data delas."
        actions={
          <>
            <label className="flex h-10 items-center gap-2 text-sm">
              <input type="checkbox" className="h-[18px] w-[18px]" checked={history} onChange={(e) => setHistory(e.target.checked)} /> Mostrar histórico
            </label>
            {can("admin") && <button className="btn-primary" onClick={() => setEdit("new")}><Plus size={16} /> Nova versão</button>}
          </>
        }
      />
      {error && <ErrorBox message={error} onRetry={reload} />}
      <div className="card p-2">
        {!data && loading && <Loading />}
        {data && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px]">
              <thead>
                <tr>
                  <th className="th">Grandeza</th>
                  <th className="th">Contexto</th>
                  <th className="th text-right">Mínimo</th>
                  <th className="th text-right">Máximo</th>
                  <th className="th">Unidade</th>
                  <th className="th">Vigência</th>
                  <th className="th">Fonte técnica</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id} className={p.valid_to ? "opacity-60" : ""}>
                    <td className="td font-medium">{PARAM_LABEL[p.parameter]}</td>
                    <td className="td">{CONTEXT_LABEL[p.context]}</td>
                    <td className="td num text-right">{num(p.minimum_value, p.parameter === "density" ? 3 : 1)}</td>
                    <td className="td num text-right">{num(p.maximum_value, p.parameter === "density" ? 3 : 1)}</td>
                    <td className="td">{p.unit}</td>
                    <td className="td num text-xs">
                      {dateTime(p.valid_from)} → {p.valid_to ? dateTime(p.valid_to) : "atual"}
                    </td>
                    <td className="td text-xs">
                      {p.source_reference} {p.needs_review && <Badge tone="warn">a revisar</Badge>}
                    </td>
                    <td className="td text-right">{can("admin") && !p.valid_to && <button className="btn-ghost h-8" onClick={() => setEdit(p)}>Alterar</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {edit && <ParameterForm base={edit === "new" ? undefined : edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </div>
  );
}

function ParameterForm({ base, onClose, onSaved }: { base?: QualityParameter; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({
    parameter: base?.parameter ?? "ph",
    context: base?.context ?? "coleta",
    minimum_value: base?.minimum_value ?? "",
    maximum_value: base?.maximum_value ?? "",
    unit: base?.unit ?? "",
    source_reference: "",
    needs_review: false,
  });
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post("/api/v1/quality-parameters", {
        ...f,
        minimum_value: f.minimum_value === "" ? null : String(f.minimum_value).replace(",", "."),
        maximum_value: f.maximum_value === "" ? null : String(f.maximum_value).replace(",", "."),
      });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <Modal title="Nova versão do parâmetro" onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-2 gap-4">
        <Field label="Grandeza">
          <select className="input" value={f.parameter} disabled={!!base} onChange={(e) => setF({ ...f, parameter: e.target.value as QualityParameter["parameter"] })}>
            {Object.entries(PARAM_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Contexto">
          <select className="input" value={f.context} disabled={!!base} onChange={(e) => setF({ ...f, context: e.target.value as QualityParameter["context"] })}>
            {Object.entries(CONTEXT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Mínimo">
          <input className="input num" inputMode="decimal" value={f.minimum_value} onChange={(e) => setF({ ...f, minimum_value: e.target.value })} />
        </Field>
        <Field label="Máximo">
          <input className="input num" inputMode="decimal" value={f.maximum_value} onChange={(e) => setF({ ...f, maximum_value: e.target.value })} />
        </Field>
        <Field label="Unidade">
          <input className="input" required value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} />
        </Field>
        <div className="col-span-2">
          <Field label="Fonte técnica" hint="Norma, artigo ou laudo que justifica o valor (obrigatório)">
            <input className="input" required minLength={5} value={f.source_reference} onChange={(e) => setF({ ...f, source_reference: e.target.value })} placeholder="Ex.: IN MAPA nº 76/2018, art. 5º" />
          </Field>
        </div>
        <label className="col-span-2 flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-[18px] w-[18px]" checked={f.needs_review} onChange={(e) => setF({ ...f, needs_review: e.target.checked })} /> Ainda precisa ser conferido
        </label>
        {error && <div className="col-span-2"><ErrorBox message={error} /></div>}
        <div className="col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
          <button className="btn-primary">Salvar nova versão</button>
        </div>
      </form>
    </Modal>
  );
}

// ------------------------------------------------------------------ usuários
export function Users() {
  const [page, setPage] = useState(1);
  const [edit, setEdit] = useState<User | "new" | null>(null);
  const { data, error, loading, reload } = useAsync(() => api.get<Page<User>>(`/api/v1/users${qs({ page, page_size: 25 })}`), [page]);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Usuários"
        subtitle="Perfis: Leitura (só consulta) · Coletor (registra coletas) · Gestor (viagens, frota, alertas) · Administrador (tudo)"
        actions={<button className="btn-primary" onClick={() => setEdit("new")}><Plus size={16} /> Novo usuário</button>}
      />
      {error && <ErrorBox message={error} onRetry={reload} />}
      <div className="card p-2">
        {!data && loading && <Loading />}
        {data && data.items.length === 0 && <Empty>Nenhum usuário.</Empty>}
        {data && data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px]">
              <thead>
                <tr>
                  <th className="th">Nome</th>
                  <th className="th">E-mail</th>
                  <th className="th">Perfil</th>
                  <th className="th">Situação</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((u) => (
                  <tr key={u.id}>
                    <td className="td font-medium">{u.name}</td>
                    <td className="td">{u.email}</td>
                    <td className="td">{ROLE_LABEL[u.role]}</td>
                    <td className="td"><Badge tone={u.active ? "brand" : "neutral"}>{u.active ? "ativo" : "inativo"}</Badge></td>
                    <td className="td text-right"><button className="btn-ghost h-8" onClick={() => setEdit(u)}>Editar</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-2"><Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} /></div>
          </div>
        )}
      </div>
      {edit && <UserForm user={edit === "new" ? undefined : edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </div>
  );
}

function UserForm({ user, onClose, onSaved }: { user?: User; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ name: user?.name ?? "", email: user?.email ?? "", role: (user?.role ?? "leitura") as Role, active: user?.active ?? true, password: "" });
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      if (user) await api.patch(`/api/v1/users/${user.id}`, { name: f.name, role: f.role, active: f.active, password: f.password || undefined });
      else await api.post("/api/v1/users", { name: f.name, email: f.email, role: f.role, password: f.password });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <Modal title={user ? `Editar ${user.name}` : "Novo usuário"} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Nome"><input className="input" required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="E-mail"><input className="input" type="email" required disabled={!!user} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Perfil">
          <select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
            {(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
        </Field>
        <Field label={user ? "Nova senha (deixe em branco para manter)" : "Senha"} hint="Mínimo de 10 caracteres">
          <input className="input" type="password" autoComplete="new-password" minLength={10} required={!user} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        </Field>
        {user && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-[18px] w-[18px]" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Ativo
          </label>
        )}
        {error && <ErrorBox message={error} />}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
          <button className="btn-primary">Salvar</button>
        </div>
      </form>
    </Modal>
  );
}

// ------------------------------------------------------------------ auditoria
interface AuditRow { id: number; at: string; user_id: number | null; action: string; entity: string; entity_id: string | null; details: Record<string, unknown> | null; ip: string | null }

export function Audit() {
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useAsync(() => api.get<Page<AuditRow>>(`/api/v1/audit${qs({ page, page_size: 50 })}`), [page]);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Auditoria" subtitle="Quem fez o quê: logins, cadastros, coletas, reconhecimento de alertas e mudanças de limite." />
      {error && <ErrorBox message={error} onRetry={reload} />}
      <div className="card p-2">
        {!data && loading && <Loading />}
        {data && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead>
                <tr><th className="th">Quando</th><th className="th">Usuário</th><th className="th">Ação</th><th className="th">Registro</th><th className="th">Detalhes</th><th className="th">IP</th></tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id}>
                    <td className="td num">{dateTime(a.at)}</td>
                    <td className="td num">{a.user_id ?? "—"}</td>
                    <td className="td">{a.action}</td>
                    <td className="td num">{a.entity}{a.entity_id ? ` #${a.entity_id}` : ""}</td>
                    <td className="td max-w-[360px] truncate text-xs text-muted" title={a.details ? JSON.stringify(a.details) : ""}>{a.details ? JSON.stringify(a.details) : "—"}</td>
                    <td className="td num text-xs">{a.ip ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-2"><Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} /></div>
          </div>
        )}
      </div>
    </div>
  );
}
