import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { AuthProvider } from "./auth/AuthContext";
import { RedirectIfAuthenticated, RequireAuth } from "./auth/RequireAuth";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";

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
            <Route element={<AppShell />}>
              <Route path="/" element={<HomePage />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
