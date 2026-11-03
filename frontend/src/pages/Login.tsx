import { useState, type FormEvent } from "react";
import { ErrorBox } from "../components/ui";
import { useAuth } from "../hooks/auth";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <div className="hidden flex-col justify-between bg-nav p-12 text-nav-ink lg:flex">
        <span className="eyebrow text-nav-ink/70">Projeto de monitoramento</span>
        <div>
          <h1 className="font-serif text-5xl leading-[1.08] text-white">
            Monitorar para preservar:
            <br />
            logística inteligente do leite
          </h1>
          <p className="mt-5 max-w-md text-nav-ink/80">pH, temperatura, acidez e litragem acompanhados da coleta ao laticínio, com alerta enquanto o caminhão ainda está na estrada.</p>
        </div>
        <span className="eyebrow text-nav-ink/60">Bernardo · Francisco · Matheus · Nicolas · Zafir</span>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="card flex w-full max-w-sm flex-col gap-4 p-7">
          <div className="flex items-center gap-2.5">
            <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden>
              <rect width="32" height="32" rx="8" fill="#1E7A55" />
              <path d="M10 21c0-5.5 6-12 6-12s6 6.5 6 12a6 6 0 0 1-12 0z" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
            </svg>
            <div>
              <div className="font-serif text-xl font-semibold">LogLacto</div>
              <div className="text-xs text-muted">Entre com sua conta</div>
            </div>
          </div>
          <label className="label">
            E-mail
            <input className="input" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="label">
            Senha
            <input className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && <ErrorBox message={error} />}
          <button className="btn-primary" disabled={busy}>
            {busy ? "Entrando…" : "Entrar"}
          </button>
          <p className="text-xs text-muted">O primeiro administrador é criado a partir de ADMIN_EMAIL e ADMIN_PASSWORD do arquivo .env.</p>
        </form>
      </div>
    </div>
  );
}
