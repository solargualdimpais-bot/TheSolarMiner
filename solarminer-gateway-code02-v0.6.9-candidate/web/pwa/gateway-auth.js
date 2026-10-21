import { parseInviteQr, verifyGatewayIdentityChallenge, signInviteRedemption, validateGatewayUrl } from "./gateway-connection.js";

let bearerToken = null;
let currentUser = null;
let currentGateway = null;
let heartbeatTimer = null;
let lastPresence = { state: "unknown", reason: "not_authenticated" };
const DB_NAME = "solarminer-device-identity-v1";
const STORE_NAME = "identities";

function nonce() {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
}
function toBase64(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}
function pem(label, bytes) {
  const encoded = toBase64(bytes).match(/.{1,64}/g)?.join("\n") || "";
  return `-----BEGIN ${label}-----\n${encoded}\n-----END ${label}-----`;
}
function openIdentityDb() {
  if (!globalThis.indexedDB) throw new Error("Este browser não permite armazenamento seguro de identidade do dispositivo.");
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME, { keyPath: "gatewayUrl" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error("Não foi possível abrir o armazenamento da identidade."));
  });
}
async function identityDbRequest(mode, operation) {
  const db = await openIdentityDb();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode);
      const store = tx.objectStore(STORE_NAME);
      const request = operation(store);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(new Error("A operação de identidade não foi concluída."));
      tx.onabort = () => reject(new Error("O browser abortou a gravação da identidade."));
    });
  } finally { db.close(); }
}
async function createDeviceIdentity(gatewayUrl, gatewayFingerprint) {
  // Exportability is used only to derive the public key. The persisted private key
  // is immediately re-imported as non-extractable; the exported PKCS#8 buffer is zeroed.
  const generated = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
  const publicDer = new Uint8Array(await crypto.subtle.exportKey("spki", generated.publicKey));
  const privateDer = new Uint8Array(await crypto.subtle.exportKey("pkcs8", generated.privateKey));
  let privateKey;
  try { privateKey = await crypto.subtle.importKey("pkcs8", privateDer, { name: "Ed25519" }, false, ["sign"]); }
  finally { privateDer.fill(0); }
  return { gatewayUrl, gatewayFingerprint, publicKeyPem: pem("PUBLIC KEY", publicDer), privateKey, deviceId: null, createdAt: new Date().toISOString() };
}
export async function loadDeviceIdentity(gatewayUrl) {
  const normalized = validateGatewayUrl(gatewayUrl, { allowLocalHttp: ["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, "")) }).origin;
  return identityDbRequest("readonly", store => store.get(normalized));
}
async function gatewayRequest(baseUrl, path, { method = "GET", body, authenticated = false, token = bearerToken } = {}) {
  const base = validateGatewayUrl(baseUrl, { allowLocalHttp: ["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, "")) });
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (authenticated) {
    if (!token) throw new Error("É necessária uma sessão autenticada do Gateway.");
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(new URL(path, base.origin), {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "omit", cache: "no-store", redirect: "error",
  });
  let data = null;
  try { data = await response.json(); } catch { /* HTTP error body may be empty or non-JSON. */ }
  if (response.status === 401 && authenticated) {
    bearerToken = null; currentUser = null; lastPresence = { state: "unknown", reason: "session_expired" };
    if (heartbeatTimer) clearInterval(heartbeatTimer); heartbeatTimer = null;
  }
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : `HTTP_${response.status}`;
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return data;
}
async function startPresenceHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  const send = async () => {
    if (!bearerToken || !currentGateway) return;
    try {
      lastPresence = await gatewayRequest(currentGateway, "/api/v1/presence/heartbeat", { method: "POST", body: {}, authenticated: true });
    } catch (error) {
      lastPresence = { state: "unknown", reason: error.status === 401 ? "session_expired" : "heartbeat_failed" };
      if (error.status === 401 && heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
    }
  };
  await send();
  heartbeatTimer = setInterval(send, 60_000);
}
export function presenceInfo() { return { ...lastPresence }; }

export async function bootstrapGatewayOwner({ gatewayUrl, bootstrapToken, username, password, mac }) {
  const base = validateGatewayUrl(gatewayUrl, { allowLocalHttp: ["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, "")) }).origin;
  const host = new URL(base).hostname.replace(/^\[|\]$/g, "");
  if (!["localhost", "127.0.0.1", "::1"].includes(host)) throw new Error("A criação inicial do Owner só é permitida num browser local no próprio Gateway; o servidor rejeita pedidos remotos de bootstrap.");
  if (!bootstrapToken || bootstrapToken.length < 32) throw new Error("Token de bootstrap local inválido ou ausente.");
  const ts = Math.floor(Date.now() / 1000), challengeNonce = nonce();
  const challenge = await gatewayRequest(base, `/api/v1/gateway/identity?timestamp=${ts}&nonce=${challengeNonce}`);
  await verifyGatewayIdentityChallenge({ fingerprint: challenge.fingerprint_sha256 }, challenge);
  const identity = await createDeviceIdentity(base, challenge.fingerprint_sha256);
  const timestamp = Math.floor(Date.now() / 1000), requestNonce = nonce(), normalizedMac = mac.toUpperCase();
  const canonical = new TextEncoder().encode(`BOOTSTRAP\n${username}\n${normalizedMac}\n${timestamp}\n${requestNonce}`);
  const signatureBytes = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, identity.privateKey, canonical));
  const signature = Array.from(signatureBytes, b => b.toString(16).padStart(2, "0")).join("");
  const result = await gatewayRequest(base, "/api/v1/bootstrap/owner", { method: "POST", body: {
    bootstrap_token: bootstrapToken, username, password, mac: normalizedMac,
    public_key_pem: identity.publicKeyPem, signature, timestamp, nonce: requestNonce
  } });
  identity.deviceId = result.device_id;
  await identityDbRequest("readwrite", store => store.put(identity));
  const login = await loginGateway({ gatewayUrl: base, username, password });
  return { ...result, login, gatewayUrl: base };
}

export async function redeemGatewayInvite({ qrText, username, password, mac }) {
  const invite = parseInviteQr(qrText, { allowLocalHttp: ["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, "")) });
  const timestamp = Math.floor(Date.now() / 1000), challengeNonce = nonce();
  const challenge = await gatewayRequest(invite.gatewayUrl, `/api/v1/gateway/identity?timestamp=${timestamp}&nonce=${challengeNonce}`);
  await verifyGatewayIdentityChallenge(invite, challenge);
  const identity = await createDeviceIdentity(invite.gatewayUrl, invite.fingerprint);
  const payload = await signInviteRedemption({ privateKey: identity.privateKey, token: invite.token,
    username, password, mac, publicKeyPem: identity.publicKeyPem, timestamp: Math.floor(Date.now() / 1000), nonce: nonce() });
  const result = await gatewayRequest(invite.gatewayUrl, "/api/v1/invites/redeem", { method: "POST", body: payload, authenticated: false });
  identity.deviceId = result.device_id;
  await identityDbRequest("readwrite", store => store.put(identity));
  bearerToken = result.access_token;
  currentUser = result.user;
  currentGateway = invite.gatewayUrl;
  await startPresenceHeartbeat();
  return { ...result, gatewayUrl: invite.gatewayUrl, identityValidated: true, presence: presenceInfo() };
}
export async function loginGateway({ gatewayUrl, username, password }) {
  const base = validateGatewayUrl(gatewayUrl, { allowLocalHttp: ["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, "")) }).origin;
  const identity = await loadDeviceIdentity(base);
  if (!identity?.privateKey || !identity?.deviceId || !identity?.publicKeyPem || !identity?.gatewayFingerprint) throw new Error("Este browser ainda não tem uma identidade associada e verificada para este Gateway. Usa primeiro um convite QR válido.");
  const identityTimestamp = Math.floor(Date.now() / 1000), identityNonce = nonce();
  const challenge = await gatewayRequest(base, `/api/v1/gateway/identity?timestamp=${identityTimestamp}&nonce=${identityNonce}`);
  await verifyGatewayIdentityChallenge({ fingerprint: identity.gatewayFingerprint }, challenge);
  const timestamp = Math.floor(Date.now() / 1000), requestNonce = nonce();
  const canonical = new TextEncoder().encode(`LOGIN\n${username}\n${identity.deviceId}\n${timestamp}\n${requestNonce}`);
  const signatureBytes = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, identity.privateKey, canonical));
  const signature = Array.from(signatureBytes, b => b.toString(16).padStart(2, "0")).join("");
  const result = await gatewayRequest(base, "/api/v1/auth/login", { method: "POST", body: { username, password, device_id: identity.deviceId, timestamp, nonce: requestNonce, signature } });
  bearerToken = result.access_token;
  currentUser = result.user;
  currentGateway = base;
  await startPresenceHeartbeat();
  return { ...result, gatewayUrl: base, presence: presenceInfo() };
}
export function sessionInfo() { return currentUser ? { user: { ...currentUser }, gatewayUrl: currentGateway, authenticated: Boolean(bearerToken) } : { authenticated: false }; }
export async function gatewayApi(path, options = {}) {
  if (!currentGateway) throw new Error("Não existe Gateway autenticado nesta sessão.");
  return gatewayRequest(currentGateway, path, { ...options, authenticated: true });
}
export async function checkGatewayUpdate(repositoryUrl) {
  if (typeof repositoryUrl !== "string" || !repositoryUrl.trim()) throw new Error("Indica o URL do repositório GitHub.");
  return gatewayApi("/api/v1/system/update/check", { method: "POST", body: { repository_url: repositoryUrl.trim() } });
}
export async function readGatewayUpdateStatus() {
  return gatewayApi("/api/v1/system/update/status");
}
export async function applyGatewayUpdate(version) {
  if (typeof version !== "string" || !version) throw new Error("Versão de atualização inválida.");
  return gatewayApi("/api/v1/system/update/apply", { method: "POST", body: { version, confirm: true } });
}
export async function createGatewayInvite({ role, label }) {
  const result = await gatewayApi("/api/v1/invites", { method: "POST", body: { role, label } });
  return result;
}
export async function listGatewayInvites() { return gatewayApi("/api/v1/invites"); }
export async function readGatewayEnergy() {
  const [status, categories, equipment] = await Promise.all([
    gatewayApi("/api/v1/status"), gatewayApi("/api/v1/energy/categories"), gatewayApi("/api/v1/energy/equipment")
  ]);
  return { status, categories: categories.categories || [], equipment: equipment.equipment || [], fetchedAt: new Date().toISOString() };
}
export async function revokeGatewayInvite(inviteId) {
  if (!/^[0-9a-f-]{36}$/i.test(inviteId)) throw new Error("Identificador de convite inválido.");
  return gatewayApi(`/api/v1/invites/${encodeURIComponent(inviteId)}/revoke`, { method: "POST", body: {} });
}
export async function logoutGateway() {
  try { if (bearerToken && currentGateway) await gatewayRequest(currentGateway, "/api/v1/auth/logout", { method: "POST", body: {}, authenticated: true }); }
  finally { bearerToken = null; currentUser = null; currentGateway = null; lastPresence = { state: "unknown", reason: "logged_out" }; if (heartbeatTimer) clearInterval(heartbeatTimer); heartbeatTimer = null; }
}
export function clearGatewaySession() { bearerToken = null; currentUser = null; currentGateway = null; lastPresence = { state: "unknown", reason: "session_cleared" }; if (heartbeatTimer) clearInterval(heartbeatTimer); heartbeatTimer = null; }
