import { Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Loading } from "./components/ui";
import { AuthProvider, useAuth } from "./hooks/auth";
import { LiveProvider } from "./hooks/live";
import AppLayout from "./layouts/AppLayout";
import { Audit, Parameters, Users } from "./pages/Admin";
import Alerts from "./pages/Alerts";
import Dashboard from "./pages/Dashboard";
import { Devices, Drivers, VehicleDetail, Vehicles } from "./pages/Fleet";
import Live from "./pages/Live";
import Login from "./pages/Login";
import Reports from "./pages/Reports";
import Samples from "./pages/Samples";
import TripDetail from "./pages/TripDetail";
import Trips from "./pages/Trips";


function AdminOnly({ children }: { children: ReactNode }) {
  const { can } = useAuth();
  return can("admin") ? <>{children}</> : <Navigate to="/" replace />;
}

function Shell() {
  const { user, loading } = useAuth();
  if (loading) return <Loading label="Abrindo…" />;
  if (!user) return <Login />;
  return (
    <LiveProvider enabled>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="tempo-real" element={<Live />} />
            <Route path="viagens" element={<Trips />} />
            <Route path="viagens/:id" element={<TripDetail />} />
            <Route path="coletas" element={<Samples />} />
            <Route path="alertas" element={<Alerts />} />
            <Route path="relatorios" element={<Reports />} />
            <Route path="veiculos" element={<Vehicles />} />
            <Route path="veiculos/:id" element={<VehicleDetail />} />
            <Route path="motoristas" element={<Drivers />} />
            <Route path="dispositivos" element={<Devices />} />
            <Route path="parametros" element={<Parameters />} />
            <Route path="usuarios" element={<AdminOnly><Users /></AdminOnly>} />
            <Route path="auditoria" element={<AdminOnly><Audit /></AdminOnly>} />
            <Route path="*" element={<div className="py-16 text-center text-muted">Página não encontrada.</div>} />
          </Route>
        </Routes>
      </Suspense>
    </LiveProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </BrowserRouter>
  );
}
