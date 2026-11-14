import { lazy, Suspense } from "react";
import { Spin } from "antd";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import { useAuth } from "./auth";

const CatalogPage = lazy(() => import("./pages/CatalogPage"));
const EquipmentPage = lazy(() => import("./pages/EquipmentPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const MyBookingsPage = lazy(() => import("./pages/MyBookingsPage"));
const OwnerPage = lazy(() => import("./pages/OwnerPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const VerifyPage = lazy(() => import("./pages/VerifyPage"));

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
    <Suspense
      fallback={
        <div className="page-loader">
          <Spin size="large" />
        </div>
      }
    >
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<CatalogPage />} />
          <Route path="equipment/:id" element={<EquipmentPage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="register" element={<RegisterPage />} />
          <Route path="verify" element={<VerifyPage />} />
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
    </Suspense>
  );
}
