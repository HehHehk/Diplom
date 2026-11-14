import axios from "axios";

export const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && localStorage.getItem("token")) {
      localStorage.removeItem("token");
    }
    return Promise.reject(error);
  },
);

export function apiError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (Array.isArray(record)) {
      return record
        .map((entry) => (entry as { msg?: string }).msg ?? "")
        .filter(Boolean)
        .join("; ");
    }
  }
  return "Не удалось выполнить запрос";
}
