import {
  Activity,
  Bell,
  ClipboardList,
  Cpu,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Search,
  Settings2,
  ShieldCheck,
  Sun,
  Triangle,
  Truck,
  UserRound,
  Users,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ROLE_LABEL, useAuth } from "../hooks/auth";
import { useLive } from "../hooks/live";
import { api } from "../services/api";
import type { Alert, Page, Role } from "../types/api";

const NAV: { group: string; items: { to: string; label: string; icon: typeof Activity; min?: Role }[] }[] = [
  {
    group: "Operação",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard },
      { to: "/tempo-real", label: "Tempo real", icon: Activity },
      { to: "/viagens", label: "Viagens", icon: Truck },
      { to: "/coletas", label: "Coletas", icon: ClipboardList },
      { to: "/alertas", label: "Alertas", icon: Triangle },
      { to: "/relatorios", label: "Relatórios", icon: FileText },
    ],
  },
  {
    group: "Cadastros",
    items: [
      { to: "/veiculos", label: "Veículos", icon: Truck },
      { to: "/motoristas", label: "Motoristas", icon: UserRound },
      { to: "/dispositivos", label: "Dispositivos", icon: Cpu },
      { to: "/parametros", label: "Parâmetros de qualidade", icon: Settings2 },
      { to: "/usuarios", label: "Usuários", icon: Users, min: "admin" },
      { to: "/auditoria", label: "Auditoria", icon: ShieldCheck, min: "admin" },
    ],
  },
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("loglacto-theme", dark ? "dark" : "light");
    } catch {
      /* sem armazenamento */
    }
  }, [dark]);
  return [dark, setDark] as const;
}

export default function AppLayout() {
  const { user, logout, can } = useAuth();
  const [dark, setDark] = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [bellOpen, setBellOpen] = useState(false);
  const [q, setQ] = useState("");
  const nav = useNavigate();
  const loc = useLocation();

  const loadAlerts = () =>
    api
      .get<Page<Alert>>("/api/v1/alerts?status=aberto&page_size=8")
      .then((p) => setAlerts(p.items))
      .catch(() => {});

  useEffect(() => {
    loadAlerts();
  }, []);
  useEffect(() => setMenuOpen(false), [loc.pathname]);

  const connected = useLive((m) => {
    if (m.type === "event" && String(m.event ?? m.topic ?? "").startsWith("alerta")) loadAlerts();
  });

  const search = (e: FormEvent) => {
    e.preventDefault();
    nav(`/viagens?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <div className="min-h-full flex flex-wrap items-stretch">
      {/* Menu lateral */}
      <nav
        aria-label="Menu principal"
        className={`bg-nav text-nav-ink flex-[1_1_236px] max-w-full lg:max-w-[260px] flex flex-col gap-6 px-4 py-5 ${menuOpen ? "" : "max-lg:h-[68px] max-lg:overflow-hidden"}`}
      >
        <div className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 px-2 text-white no-underline">
            <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
              <rect width="32" height="32" rx="8" fill="#1E7A55" />
              <path d="M10 21c0-5.5 6-12 6-12s6 6.5 6 12a6 6 0 0 1-12 0z" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
            </svg>
            <span className="flex flex-col leading-tight">
              <span className="font-serif text-lg font-semibold">LogLacto</span>
              <span className="text-[10px] uppercase tracking-[0.14em] text-nav-ink/70">Smart Milk Logistics</span>
            </span>
          </Link>
          <button className="lg:hidden btn h-10 w-10 px-0 text-white hover:bg-nav-active" onClick={() => setMenuOpen((v) => !v)} aria-label="Abrir menu" aria-expanded={menuOpen}>
            <Menu size={20} />
          </button>
        </div>
        {NAV.map((g) => (
          <div key={g.group} className="flex flex-col gap-0.5">
            <span className="px-3 pb-2 text-[11px] uppercase tracking-[0.12em] text-nav-ink/60">{g.group}</span>
            {g.items
              .filter((i) => !i.min || can(i.min))
              .map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm no-underline ${isActive ? "bg-nav-active text-white font-semibold" : "text-nav-ink hover:bg-nav-active/60"}`
                  }
                >
                  <Icon size={17} aria-hidden />
                  <span className="flex-1">{label}</span>
                  {to === "/alertas" && alerts.length > 0 && (
                    <span className="num rounded-full bg-bad px-2 text-xs font-semibold text-white">{alerts.length}</span>
                  )}
                </NavLink>
              ))}
          </div>
        ))}
        <div className="mt-auto border-t border-white/10 px-2 pt-4 text-xs text-nav-ink/80 flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-[#5FD3A0]" : "bg-[#F2B755]"}`} aria-hidden />
          {connected ? "Tempo real conectado" : "Tempo real reconectando…"}
        </div>
      </nav>

      {/* Conteúdo */}
      <div className="flex-[999_1_560px] min-w-0 flex flex-col">
        <header className="sticky top-0 z-[500] flex flex-wrap items-center gap-3 border-b border-line bg-surface/95 px-4 py-3 backdrop-blur sm:px-8">
          <form onSubmit={search} role="search" className="flex flex-1 min-w-[200px] items-center gap-2 rounded-lg border border-line bg-surface px-3 h-10">
            <Search size={16} className="text-muted" aria-hidden />
            <label htmlFor="busca" className="sr-only">
              Pesquisar viagens
            </label>
            <input id="busca" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Pesquisar viagem, placa, motorista…" className="w-full bg-transparent text-sm outline-none placeholder:text-muted" />
          </form>
          <div className="relative">
            <button className="btn-ghost h-10 w-10 px-0 relative" aria-label={`Notificações: ${alerts.length} alertas abertos`} aria-expanded={bellOpen} onClick={() => setBellOpen((v) => !v)}>
              <Bell size={18} />
              {alerts.length > 0 && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-bad" />}
            </button>
            {bellOpen && (
              <div className="card absolute right-0 top-12 z-[600] w-[min(360px,calc(100vw-32px))] p-2 shadow-xl">
                <div className="px-2 py-1.5 text-xs font-semibold text-muted">Alertas abertos</div>
                {alerts.length === 0 && <div className="px-2 py-3 text-sm text-muted">Nenhum alerta aberto.</div>}
                {alerts.map((a) => (
                  <Link key={a.id} to="/alertas" onClick={() => setBellOpen(false)} className="block rounded-lg px-2 py-2 text-sm no-underline text-ink hover:bg-sunken">
                    <span className={`mr-2 inline-block h-2 w-2 rounded-full ${a.severity === "critico" ? "bg-bad" : a.severity === "atencao" ? "bg-warn" : "bg-data"}`} />
                    {a.title}
                    <span className="block pl-4 text-xs text-muted">
                      {a.trip_code ?? a.device_id ?? ""} {a.is_simulated ? "· simulado" : ""}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>
          <button className="btn-ghost h-10 w-10 px-0" onClick={() => setDark((v) => !v)} aria-label={dark ? "Usar modo claro" : "Usar modo escuro"}>
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <div className="flex items-center gap-3 pl-1">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-brand-soft text-sm font-bold text-brand-ink" aria-hidden>
              {user?.name
                .split(" ")
                .map((p) => p[0])
                .slice(0, 2)
                .join("")
                .toUpperCase()}
            </span>
            <div className="hidden sm:flex flex-col leading-tight">
              <span className="text-sm font-semibold">{user?.name}</span>
              <span className="text-xs text-muted">{user ? ROLE_LABEL[user.role] : ""}</span>
            </div>
            <button className="btn-ghost h-10 w-10 px-0" onClick={logout} aria-label="Sair">
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <main className="flex-1 px-4 py-6 sm:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
