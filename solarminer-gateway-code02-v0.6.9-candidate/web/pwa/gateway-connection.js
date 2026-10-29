/**
 * SolarMiner PWA v0.5.7 Gateway connection, invite parsing, and identity verification.
 * This module validates endpoint input and Gateway identity proofs; session
 * authentication and bearer-token handling live in gateway-auth.js.
 */
export const CONNECTION_STATES = Object.freeze({
  DEMO: "DEMONSTRAÇÃO — SEM LIGAÇÃO AO GATEWAY",
  SEARCHING: "A PROCURAR GATEWAY",
  UNASSOCIATED: "GATEWAY AINDA NÃO ASSOCIADO",
  RESPONDING_UNVERIFIED: "GATEWAY RESPONDE — IDENTIDADE NÃO VALIDADA",
  UNAVAILABLE: "GATEWAY INDISPONÍVEL",
  AUTH_REQUIRED: "AUTENTICAÇÃO NECESSÁRIA",
  SESSION_EXPIRED: "SESSÃO EXPIRADA",
  STALE: "DADOS DESATUALIZADOS",
  LOST: "LIGAÇÃO PERDIDA",
});

const MAX_QR_CHARS = 4096;
const seenPairingCodesThisSession = new Set();
const PRIVATE_IPV4 = /^(10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.(?:\d{1,3}\.)\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3})$/;

export function validateGatewayUrl(value, { allowLocalHttp = false } = {}) {
  if (typeof value !== "string" || !value.trim() || value.length > 2048) throw new Error("Introduz um endereço HTTPS válido do Gateway.");
  let url;
  try { url = new URL(value.trim()); } catch { throw new Error("O endereço do Gateway não é válido."); }
  if (url.username || url.password || url.search || url.hash) throw new Error("O endereço não pode conter credenciais, parâmetros ou fragmentos.");
  const hostname = url.hostname.toLowerCase().replaceAll("[", "").replaceAll("]", "");
  const local = ["localhost", "127.0.0.1", "::1"].includes(hostname);
  if (url.protocol !== "https:" && !(allowLocalHttp && local && url.protocol === "http:")) throw new Error("É obrigatório HTTPS. A validação TLS nunca é desativada.");
  if (url.port && !/^\d{1,5}$/.test(url.port)) throw new Error("Porta inválida.");
  url.pathname = url.pathname.replace(/\/$/, "");
  return url;
}

export function parsePairingQr(raw, options = {}) {
  if (typeof raw !== "string" || raw.length > MAX_QR_CHARS) throw new Error("QR Code inválido ou demasiado grande.");
  let data;
  try { data = JSON.parse(raw); } catch { throw new Error("O QR Code não contém um convite SolarMiner reconhecido."); }
  if (!data || data.type !== "solarminer-pairing" || data.version !== 1) throw new Error("Formato de QR Code não reconhecido.");
  const endpoint = validateGatewayUrl(data.gateway_url, options);
  if (typeof data.pairing_code !== "string" || data.pairing_code.length < 32 || data.pairing_code.length > 256) throw new Error("O QR Code não contém um código de emparelhamento válido.");
  if (typeof data.expires_at !== "number" || !Number.isFinite(data.expires_at)) throw new Error("O QR Code não contém uma expiração válida.");
  if (data.expires_at <= Math.floor(Date.now() / 1000)) throw new Error("Este QR Code expirou. Gera um novo código no Gateway.");
  if (data.single_use !== true) throw new Error("O convite tem de ser de utilização única.");
  if (seenPairingCodesThisSession.has(data.pairing_code)) throw new Error("Este código já foi lido nesta sessão. Gera um novo QR Code para evitar reutilização.");
  seenPairingCodesThisSession.add(data.pairing_code);
  // Only return a candidate. Do not call the endpoint or consume the pairing code.
  return { gatewayUrl: endpoint.origin, pairingCode: data.pairing_code, expiresAt: data.expires_at, singleUse: true, identityValidated: false };
}

export function classifyEndpoint(urlValue) {
  const url = validateGatewayUrl(urlValue, { allowLocalHttp: true });
  const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (PRIVATE_IPV4.test(host) || host.endsWith(".local") || host === "localhost" || host === "127.0.0.1" || host === "::1") return "CANDIDATE_LAN";
  // Hostname alone cannot prove a remote path (including Tailscale).
  return "CANDIDATE_UNCLASSIFIED";
}

/** Return the same-origin Gateway endpoint when this PWA is hosted by a Gateway. */
export function inferHostedGatewayEndpoint(locationLike = globalThis.location) {
  if (!locationLike || locationLike.protocol !== "https:") return "";
  const hostname = String(locationLike.hostname || "").toLowerCase();
  if (locationLike.port === "8443" || hostname.endsWith(".ts.net")) return locationLike.origin || "";
  return "";
}

export async function probeGateway(urlValue, { fetchImpl = globalThis.fetch, timeoutMs = 3500, allowLocalHttp = false } = {}) {
  const base = validateGatewayUrl(urlValue, { allowLocalHttp });
  const startedAt = Date.now();
  const getJson = async path => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(new URL(path, base.origin).toString(), {
        method: "GET", headers: { Accept: "application/json" }, cache: "no-store",
        credentials: "omit", redirect: "error", signal: controller.signal,
      });
      if (response.status === 401) return { authRequired: true };
      if (response.status === 403) return { forbidden: true };
      if (!response.ok) throw new Error(`HTTP_${response.status}`);
      const body = await response.json();
      if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("INVALID_RESPONSE");
      return body;
    } finally { clearTimeout(timer); }
  };
  try {
    const health = await getJson("/api/v1/health");
    if (health.authRequired) return { state: CONNECTION_STATES.AUTH_REQUIRED, reachable: true, identityValidated: false };
    if (health.forbidden) return { state: CONNECTION_STATES.AUTH_REQUIRED, reachable: true, identityValidated: false };
    if (health.status !== "ok" || typeof health.version !== "string") throw new Error("INVALID_HEALTH");
    const info = await getJson("/api/v1/info");
    if (info.authRequired || info.forbidden) return { state: CONNECTION_STATES.AUTH_REQUIRED, reachable: true, identityValidated: false };
    if (info.product !== "SolarMiner Gateway" || typeof info.version !== "string") throw new Error("UNEXPECTED_PRODUCT");
    return {
      state: CONNECTION_STATES.RESPONDING_UNVERIFIED,
      reachable: true,
      identityValidated: false,
      gatewayProduct: info.product,
      reportedVersion: info.version,
      endpointKind: classifyEndpoint(base.toString()),
      lastCommunicationAt: new Date().toISOString(),
      elapsedMs: Date.now() - startedAt,
      note: "A API respondeu, mas o contrato v0.6.5 não expõe uma identidade criptográfica do Gateway para validação independente.",
    };
  } catch (error) {
    const code = error?.name === "AbortError" ? "timeout" : (error?.message || "network_error");
    return { state: CONNECTION_STATES.UNAVAILABLE, reachable: false, identityValidated: false, errorCode: code };
  }
}

export class GatewayConnectionManager {
  constructor({ probe = probeGateway, onState = () => {}, retryDelays = [1000, 2000, 4000, 8000, 16000] } = {}) {
    this.probe = probe; this.onState = onState; this.retryDelays = [...retryDelays];
    this.state = { state: CONNECTION_STATES.DEMO, reachable: false, identityValidated: false, simulated: true };
    this.inFlight = null; this.retryIndex = 0; this.endpoint = null;
  }
  setState(next) { this.state = { ...next }; this.onState(this.state); return this.state; }
  async check(url) {
    if (this.inFlight) return this.inFlight;
    this.endpoint = url;
    this.setState({ state: CONNECTION_STATES.SEARCHING, reachable: false, identityValidated: false, simulated: false });
    this.inFlight = (async () => {
      const result = await this.probe(url);
      this.retryIndex = result.reachable ? 0 : Math.min(this.retryIndex + 1, this.retryDelays.length - 1);
      return this.setState({ ...result, simulated: false });
    })();
    try { return await this.inFlight; } finally { this.inFlight = null; }
  }
  nextRetryDelay() { return this.retryDelays[this.retryIndex] ?? this.retryDelays.at(-1) ?? 16000; }
  useDemo() { this.endpoint = null; this.retryIndex = 0; return this.setState({ state: CONNECTION_STATES.DEMO, reachable: false, identityValidated: false, simulated: true }); }
  clear() { this.endpoint = null; this.retryIndex = 0; return this.setState({ state: CONNECTION_STATES.UNASSOCIATED, reachable: false, identityValidated: false, simulated: false }); }
}

export const PRESENCE_API_STATUS = Object.freeze({ available: true, endpoint: "/api/v1/presence/heartbeat", readEndpoint: "/api/v1/presence/me", reason: "A API de presença exige sessão autenticada e só declara atividade recente desta sessão; não prova presença física nem método LAN/REMOTO.", physicalPresenceSupported: false, connectionMethod: "unknown" });

function encodeInviteFragment(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/g, "");
}

/** Build a PWA deep link. The one-time code is in the URL fragment, never sent to the static host. */
export function buildInviteLandingUrl({ pwaUrl, gatewayUrls, token, fingerprint, expiresAt }) {
  const page = new URL(pwaUrl);
  if (page.protocol !== "https:") throw new Error("A página de ativação tem de usar HTTPS.");
  const urls = [...new Set((gatewayUrls || []).map(value => validateGatewayUrl(value).origin))];
  if (!urls.length) throw new Error("Não há um endereço HTTPS válido para o Gateway.");
  const fp = String(fingerprint || "").toLowerCase().replaceAll(":", "");
  if (!/^[0-9a-f]{64}$/.test(fp)) throw new Error("Fingerprint completa SHA-256 inválida.");
  if (typeof token !== "string" || token.length < 32 || token.length > 256) throw new Error("Código de acesso inválido.");
  if (!Number.isSafeInteger(expiresAt) || expiresAt <= Math.floor(Date.now() / 1000)) throw new Error("O convite expirou.");
  page.hash = `invite=${encodeInviteFragment({ v: 2, urls, token, fp, exp: expiresAt })}`;
  return page.href;
}

export function readInviteLandingHash(hash) {
  const raw = String(hash || "").replace(/^#/, "");
  const params = new URLSearchParams(raw);
  const encoded = params.get("invite");
  if (!encoded) return null;
  if (encoded.length > 4096 || !/^[A-Za-z0-9_-]+$/.test(encoded)) throw new Error("Link de convite inválido.");
  const base64 = encoded.replaceAll("-", "+").replaceAll("_", "/").padEnd(Math.ceil(encoded.length / 4) * 4, "=");
  let data;
  try {
    const binary = atob(base64);
    const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
    data = JSON.parse(new TextDecoder().decode(bytes));
  } catch { throw new Error("Não foi possível ler o convite deste link."); }
  return JSON.stringify(data);
}

/** Parse the invite payload used by PWA activation links. Parsing alone does not establish trust. */
export function parseInviteQr(raw, options = {}) {
  if (typeof raw !== "string" || raw.length > MAX_QR_CHARS) throw new Error("Convite QR inválido ou demasiado grande.");
  let data;
  try { data = JSON.parse(raw); } catch { throw new Error("O QR não contém JSON válido."); }
  if (!data || ![1, 2].includes(data.v) || typeof data.token !== "string" ||
      typeof data.fp !== "string" || typeof data.exp !== "number") throw new Error("Formato de convite v0.6.7 inválido.");
  const urls = data.v === 2 ? data.urls : [data.url];
  if (!Array.isArray(urls) || urls.length < 1 || urls.length > 4 || urls.some(url => typeof url !== "string")) throw new Error("O convite não contém endereços do Gateway válidos.");
  const endpoints = [...new Set(urls.map(url => validateGatewayUrl(url, options).origin))];
  const fp = data.fp.toLowerCase().replaceAll(":", "");
  if (!/^[0-9a-f]{64}$/.test(fp)) throw new Error("Fingerprint completa SHA-256 inválida.");
  if (data.token.length < 32 || data.token.length > 256) throw new Error("Token do convite inválido.");
  if (!Number.isSafeInteger(data.exp) || data.exp <= Math.floor(Date.now() / 1000)) throw new Error("O convite expirou.");
  return { version: data.v, gatewayUrl: endpoints[0], gatewayUrls: endpoints, token: data.token, fingerprint: fp, expiresAt: data.exp, identityValidated: false };
}

/** Verify possession of the Gateway identity private key and match its full QR fingerprint. */
export async function verifyGatewayIdentityChallenge(invite, challenge, { now = Math.floor(Date.now() / 1000) } = {}) {
  if (!invite || !challenge || challenge.signature_algorithm !== "Ed25519" ||
      challenge.nonce == null || challenge.timestamp == null || typeof challenge.public_key_pem !== "string") {
    throw new Error("Desafio de identidade do Gateway incompleto.");
  }
  if (Math.abs(now - challenge.timestamp) > 300) throw new Error("Desafio de identidade fora da janela temporal.");
  if (challenge.nonce.length < 16) throw new Error("Nonce do Gateway inválido.");
  const b64 = challenge.public_key_pem.replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s/g, "");
  const der = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", der));
  const fp = Array.from(digest, b => b.toString(16).padStart(2, "0")).join("");
  if (fp !== invite.fingerprint || fp !== String(challenge.fingerprint_sha256).toLowerCase()) throw new Error("A identidade do Gateway não corresponde à fingerprint completa do QR.");
  const key = await crypto.subtle.importKey("spki", der, { name: "Ed25519" }, false, ["verify"]);
  const canonical = new TextEncoder().encode(`GET\n/api/v1/gateway/identity\n${challenge.timestamp}\n${challenge.nonce}`);
  const signature = Uint8Array.from(challenge.signature.match(/.{1,2}/g) || [], h => parseInt(h, 16));
  const valid = await crypto.subtle.verify({ name: "Ed25519" }, key, signature, canonical);
  if (!valid) throw new Error("Assinatura do desafio de identidade do Gateway inválida.");
  return { identityValidated: true, fingerprint: fp, timestamp: challenge.timestamp };
}

/** Canonical request bytes expected by POST /api/v1/auth/login. */
export async function signGatewayLogin({ privateKey, username, deviceId, timestamp = Math.floor(Date.now() / 1000), nonce }) {
  if (!privateKey || !username || !deviceId || !nonce) throw new Error("Dados de autenticação incompletos.");
  const canonical = new TextEncoder().encode(`LOGIN\n${username}\n${deviceId}\n${timestamp}\n${nonce}`);
  const bytes = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, privateKey, canonical));
  return { username, device_id: deviceId, timestamp, nonce, signature: Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("") };
}

/** Canonical request bytes expected by POST /api/v1/invites/redeem. */
export async function signInviteRedemption({ privateKey, token, username, password, mac, publicKeyPem, timestamp = Math.floor(Date.now() / 1000), nonce }) {
  if (!privateKey || !token || !username || !password || !mac || !publicKeyPem || !nonce) throw new Error("Dados de resgate incompletos.");
  const digestHex = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
  const encoder = new TextEncoder();
  const tokenHash = await digestHex(encoder.encode(token));
  const passwordHash = await digestHex(encoder.encode(password));
  const der = Uint8Array.from(atob(publicKeyPem.replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s/g, "")), c => c.charCodeAt(0));
  const publicKeyHash = await digestHex(der);
  const normalizedMac = mac.toUpperCase();
  const canonical = `POST\n/api/v1/invites/redeem\n${timestamp}\n${nonce}\n${tokenHash}\n${username}\n${passwordHash}\n${normalizedMac}\n${publicKeyHash}`;
  const signature = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, privateKey, encoder.encode(canonical)));
  return { invite_token: token, username, password, mac: normalizedMac, client_pubkey_pem: publicKeyPem, timestamp, nonce,
    signature: Array.from(signature, b => b.toString(16).padStart(2, "0")).join("") };
}
