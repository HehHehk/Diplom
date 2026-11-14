import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { Role, User } from "./api/types";

interface RegisterData {
  email: string;
  password: string;
  full_name: string;
  role: Exclude<Role, "admin">;
}

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    const token = localStorage.getItem("token");
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get<User>("/auth/me");
      setUser(data);
    } catch {
      localStorage.removeItem("token");
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUser();
  }, [loadUser]);

  const login = useCallback(async (email: string, password: string) => {
    const body = new URLSearchParams({ username: email, password });
    const { data } = await api.post<{ access_token: string }>("/auth/login", body, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    localStorage.setItem("token", data.access_token);
    const me = await api.get<User>("/auth/me");
    setUser(me.data);
  }, []);

  const register = useCallback(
    async (payload: RegisterData) => {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      await api.post("/auth/register", { ...payload, timezone });
      await login(payload.email, payload.password);
    },
    [login],
  );

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
