import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { RequireAdmin } from "./auth/RequireAdmin";
import { RedirectIfAuthenticated, RequireAuth } from "./auth/RequireAuth";
import { RequireOperatorOrAdmin } from "./auth/RequireOperatorOrAdmin";
import { NavShell } from "./components/NavShell";
import { AccountPage } from "./pages/AccountPage";
import { CatalogoDatosPage } from "./pages/CatalogoDatosPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { SchedulesPage } from "./pages/SchedulesPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";
import { AuditPage } from "./pages/administracion/AuditPage";
import { ConexionesApiPage } from "./pages/administracion/ConexionesApiPage";
import { ConfiguracionPage } from "./pages/administracion/ConfiguracionPage";
import { UsersPage } from "./pages/administracion/UsersPage";
import { HistoryPage } from "./pages/actividad/HistoryPage";
import { RunningTasksPage } from "./pages/actividad/RunningTasksPage";
import { BcExtractPage } from "./pages/ejecutar/BcExtractPage";
import { BcSyncPage } from "./pages/ejecutar/BcSyncPage";
import { BcUploadPage } from "./pages/ejecutar/BcUploadPage";
import { FactorialExtractPage } from "./pages/ejecutar/FactorialExtractPage";
import { FactorialSyncPage } from "./pages/ejecutar/FactorialSyncPage";
import { FactorialUploadPage } from "./pages/ejecutar/FactorialUploadPage";
import { HubspotExtractPage } from "./pages/ejecutar/HubspotExtractPage";
import { HubspotSyncPage } from "./pages/ejecutar/HubspotSyncPage";
import { HubspotUploadPage } from "./pages/ejecutar/HubspotUploadPage";
import { PipelinesPage } from "./pages/ejecutar/PipelinesPage";
import { CompararPage } from "./pages/sincronizacion/CompararPage";
import { MapeosPage } from "./pages/sincronizacion/MapeosPage";
import { SecretsPage } from "./pages/administracion/SecretsPage";

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route
            path="/login"
            element={
              <RedirectIfAuthenticated>
                <LoginPage />
              </RedirectIfAuthenticated>
            }
          />
          <Route element={<RequireAuth />}>
            <Route path="/change-password" element={<ChangePasswordPage />} />
            <Route element={<NavShell />}>
              <Route path="/" element={<HomePage />} />
              <Route element={<RequireOperatorOrAdmin />}>
                <Route path="/ejecutar/bc-extraer" element={<BcExtractPage />} />
                <Route path="/ejecutar/bc-subir" element={<BcUploadPage />} />
                <Route path="/ejecutar/bc-sync" element={<BcSyncPage />} />
                <Route path="/ejecutar/factorial-extraer" element={<FactorialExtractPage />} />
                <Route path="/ejecutar/factorial-subir" element={<FactorialUploadPage />} />
                <Route path="/ejecutar/factorial-sync" element={<FactorialSyncPage />} />
                <Route path="/ejecutar/hubspot-extraer" element={<HubspotExtractPage />} />
                <Route path="/ejecutar/hubspot-subir" element={<HubspotUploadPage />} />
                <Route path="/ejecutar/hubspot-sync" element={<HubspotSyncPage />} />
                <Route path="/ejecutar/pipelines" element={<PipelinesPage />} />
                <Route path="/flujos" element={<WorkflowsPage />} />
                <Route path="/catalogo-datos" element={<CatalogoDatosPage />} />
                <Route path="/sincronizacion/comparar" element={<CompararPage />} />
                <Route path="/programacion" element={<SchedulesPage />} />
                <Route path="/actividad/tareas-en-curso" element={<RunningTasksPage />} />
                <Route path="/actividad/historial" element={<HistoryPage />} />
              </Route>
              <Route element={<RequireAdmin />}>
                <Route path="/sincronizacion/mapeos" element={<MapeosPage />} />
                <Route path="/administracion/usuarios" element={<UsersPage />} />
                <Route path="/administracion/auditoria" element={<AuditPage />} />
                <Route path="/administracion/conexiones-api" element={<ConexionesApiPage />} />
                <Route path="/administracion/configuracion" element={<ConfiguracionPage />} />
                <Route path="/administracion/claves-de-servicio" element={<SecretsPage />} />
              </Route>
              <Route path="/cuenta" element={<AccountPage />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
