import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import AdminPage from "./pages/AdminPage";
import CatalogPage from "./pages/CatalogPage";
import EquipmentPage from "./pages/EquipmentPage";
import LoginPage from "./pages/LoginPage";
import MyBookingsPage from "./pages/MyBookingsPage";
import OwnerPage from "./pages/OwnerPage";
import RegisterPage from "./pages/RegisterPage";
import { useAuth } from "./auth";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

function RoleRoute({ roles, children }: { roles: string[]; children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return roles.includes(user.role) ? <>{children}</> : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<CatalogPage />} />
        <Route path="equipment/:id" element={<EquipmentPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route
          path="my"
          element={
            <PrivateRoute>
              <MyBookingsPage />
            </PrivateRoute>
          }
        />
        <Route
          path="owner"
          element={
            <RoleRoute roles={["owner", "admin"]}>
              <OwnerPage />
            </RoleRoute>
          }
        />
        <Route
          path="admin"
          element={
            <RoleRoute roles={["admin"]}>
              <AdminPage />
            </RoleRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
