import { buildApiUrl } from "./app-core-legacy.js";

export class GatewayApiError extends Error {
  constructor(message, status = 0, code = "network_error") { super(message); this.name = "GatewayApiError"; this.status = status; this.code = code; }
}

export class GatewayApiClient {
  constructor({ baseUrl, token = "", fetchImpl = globalThis.fetch, timeoutMs = 5000 }) {
    this.baseUrl = baseUrl;
    this.token = token;
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  async request(path, { method = "GET", body = undefined } = {}) {
    const url = buildApiUrl(this.baseUrl, path);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const headers = { Accept: "application/json" };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (this.token) headers.Authorization = `Bearer ${this.token}`;
      const response = await this.fetchImpl(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, cache: "no-store", credentials: "omit", redirect: "error" });
      if (response.status === 401) throw new GatewayApiError("Sessão expirada ou não autorizada.", 401, "session_expired");
      if (response.status === 403) throw new GatewayApiError("O utilizador não tem permissão de leitura.", 403, "forbidden");
      if (!response.ok) throw new GatewayApiError(`O Gateway respondeu com HTTP ${response.status}.`, response.status, "http_error");
      return await response.json();
    } catch (error) {
      if (error instanceof GatewayApiError) throw error;
      if (error?.name === "AbortError") throw new GatewayApiError("Timeout ao contactar o Gateway.", 0, "timeout");
      throw new GatewayApiError("Gateway indisponível ou erro de rede.", 0, "network_error");
    } finally { clearTimeout(timeout); }
  }

  postJson(path, body) { return this.request(path, { method: "POST", body }); }
  health() { return this.request("/api/v1/health"); }
  categories() { return this.request("/api/v1/energy/categories"); }
  equipment(category) { return this.request(`/api/v1/energy/equipment${category ? `?category=${encodeURIComponent(category)}` : ""}`); }
  status() { return this.request("/api/v1/status"); }
  logout() { return this.postJson("/api/v1/auth/logout", {}); }
}
