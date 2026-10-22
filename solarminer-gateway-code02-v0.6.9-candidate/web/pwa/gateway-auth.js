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
    const message = ({
      bootstrap_origin_not_allowed: "A origem desta PWA não está autorizada pelo Gateway.",
      bootstrap_token_invalid_or_expired: "O token de bootstrap expirou ou é inválido. No Gateway, renova-o localmente como root.",
      bootstrap_password_invalid: "A palavra-passe não corresponde à que foi definida na consola do Gateway durante a instalação.",
      bootstrap_attempts_limited: "Demasiadas tentativas. Aguarda 15 minutos antes de tentar novamente.",
      bootstrap_unavailable: "O Gateway já não permite criar o primeiro Owner."
    })[detail] || detail;
    const error = new Error(message);
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
      if (error.status === 401 && currentGateway) {
        try { await loginGateway({ gatewayUrl: currentGateway }); }
        catch { if (heartbeatTimer) clearInterval(heartbeatTimer); heartbeatTimer = null; }
      }
    }
  };
  await send();
  heartbeatTimer = setInterval(send, 60_000);
}
export function presenceInfo() { return { ...lastPresence }; }

export async function readGatewayBootstrapStatus(gatewayUrl) {
  return gatewayRequest(gatewayUrl, "/api/v1/bootstrap/status");
}

export async function bootstrapGatewayOwner({ gatewayUrl, username, password }) {
  const base = validateGatewayUrl(gatewayUrl, { allowLocalHttp: ["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, "")) }).origin;
  const bootstrapStatus = await readGatewayBootstrapStatus(base);
  if (!["BOOTSTRAP_PENDING", "OWNER_SETUP_REQUIRED"].includes(bootstrapStatus.state)) throw new Error("O Gateway não está à espera da criação inicial do Owner.");
  const ts = Math.floor(Date.now() / 1000), challengeNonce = nonce();
  const challenge = await gatewayRequest(base, `/api/v1/gateway/identity?timestamp=${ts}&nonce=${challengeNonce}`);
  const identity = await createDeviceIdentity(base, challenge.fingerprint_sha256);
  const normalizedUsername = username.trim();
  const timestamp = Math.floor(Date.now() / 1000), requestNonce = nonce();
  const canonical = new TextEncoder().encode(`BOOTSTRAP\n${normalizedUsername}\n${timestamp}\n${requestNonce}`);
  const signatureBytes = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, identity.privateKey, canonical));
  const signature = Array.from(signatureBytes, b => b.toString(16).padStart(2, "0")).join("");
  const result = await gatewayRequest(base, "/api/v1/bootstrap/owner", { method: "POST", body: {
    username: normalizedUsername, password,
    public_key_pem: identity.publicKeyPem, signature, timestamp, nonce: requestNonce
  } });
  identity.deviceId = result.device_id;
  identity.userId = result.user_id;
  await identityDbRequest("readwrite", store => store.put(identity));
  const login = await loginGateway({ gatewayUrl: base });
  return { ...result, login, gatewayUrl: base, identityValidated: true, gatewayFingerprint: challenge.fingerprint_sha256 };
}

export async function recoverGatewayOwner({ gatewayUrl, username, recoveryKey, newPassword, mac, expectedGatewayFingerprint }) {
  const base = validateGatewayUrl(gatewayUrl, { allowLocalHttp: ["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, "")) }).origin;
  const existingIdentity = await loadDeviceIdentity(base).catch(() => null);
  const pinnedFingerprint = String(expectedGatewayFingerprint || existingIdentity?.gatewayFingerprint || "").trim().replaceAll(":", "").toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(pinnedFingerprint)) throw new Error("Confirma a fingerprint SHA-256 Ed25519 do Gateway, apresentada no terminal local.");
  if (!recoveryKey || recoveryKey.length < 20) throw new Error("Chave de recuperação inválida ou ausente.");

  const identityTimestamp = Math.floor(Date.now() / 1000), identityNonce = nonce();
  const gatewayChallenge = await gatewayRequest(base, `/api/v1/gateway/identity?timestamp=${identityTimestamp}&nonce=${identityNonce}`);
  await verifyGatewayIdentityChallenge({ fingerprint: pinnedFingerprint }, gatewayChallenge);
  const challenge = await gatewayRequest(base, "/api/v1/owner/recovery/challenge", {
    method: "POST", body: { username: username.trim() }
  });
  const identity = await createDeviceIdentity(base, pinnedFingerprint);
  const proofMessage = new TextEncoder().encode(
    `SOLARMINER-GATEWAY-DEVICE-PROOF-V1\nrecovery\n${challenge.owner_id}\n${challenge.challenge}`
  );
  const signatureBytes = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, identity.privateKey, proofMessage));
  const signature = Array.from(signatureBytes, b => b.toString(16).padStart(2, "0")).join("");
  const result = await gatewayRequest(base, "/api/v1/owner/recovery", { method: "POST", body: {
    username: username.trim(), recovery_key: recoveryKey.trim(), new_password: newPassword,
    mac: mac.trim().toUpperCase(), public_key_pem: identity.publicKeyPem,
    challenge: challenge.challenge, signature
  } });
  identity.deviceId = result.device_id;
  identity.userId = challenge.owner_id;
  await identityDbRequest("readwrite", store => store.put(identity));
  const login = await loginGateway({ gatewayUrl: base });
  return { ...result, login, gatewayUrl: base, identityValidated: true, gatewayFingerprint: pinnedFingerprint };
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
  identity.userId = result.user?.id;
  await identityDbRequest("readwrite", store => store.put(identity));
  bearerToken = result.access_token;
  currentUser = result.user;
  currentGateway = invite.gatewayUrl;
  await startPresenceHeartbeat();
  return { ...result, gatewayUrl: invite.gatewayUrl, identityValidated: true, presence: presenceInfo() };
}
export async function loginGateway({ gatewayUrl }) {
  const base = validateGatewayUrl(gatewayUrl, { allowLocalHttp: ["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, "")) }).origin;
  const identity = await loadDeviceIdentity(base);
  if (!identity?.privateKey || !identity?.deviceId || !identity?.publicKeyPem || !identity?.gatewayFingerprint) throw new Error("Este dispositivo ainda não foi registado neste Gateway. A configuração inicial deve ser feita no primeiro dispositivo.");
  const identityTimestamp = Math.floor(Date.now() / 1000), identityNonce = nonce();
  const challenge = await gatewayRequest(base, `/api/v1/gateway/identity?timestamp=${identityTimestamp}&nonce=${identityNonce}`);
  await verifyGatewayIdentityChallenge({ fingerprint: identity.gatewayFingerprint }, challenge);
  const timestamp = Math.floor(Date.now() / 1000), requestNonce = nonce();
  const canonical = new TextEncoder().encode(identity.userId
    ? `DEVICE-LOGIN\n${identity.userId}\n${identity.deviceId}\n${timestamp}\n${requestNonce}`
    : `DEVICE-LOGIN\n${identity.deviceId}\n${timestamp}\n${requestNonce}`);
  const signatureBytes = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, identity.privateKey, canonical));
  const signature = Array.from(signatureBytes, b => b.toString(16).padStart(2, "0")).join("");
  const result = await gatewayRequest(base, "/api/v1/auth/device-login", { method: "POST", body: { ...(identity.userId ? { user_id: identity.userId } : {}), device_id: identity.deviceId, timestamp, nonce: requestNonce, signature } });
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
export async function readGatewayUpdateSource() {
  return gatewayApi("/api/v1/system/update/source");
}
export async function checkGatewayUpdate(repositoryUrl) {
  if (typeof repositoryUrl !== "string" || !repositoryUrl.trim()) throw new Error("Indica o URL do repositório GitHub.");
  return gatewayApi("/api/v1/system/update/check", { method: "POST", body: { repository_url: repositoryUrl.trim() } });
}
export async function readGatewayUpdateStatus() {
  return gatewayApi("/api/v1/system/update/status");
}
export function parseOwnerRecoveryFile(contents) {
  if (typeof contents !== "string" || contents.length > 4096) throw new Error("O ficheiro de recuperação é inválido ou demasiado grande.");
  const key = contents.match(/\bSMR1(?:-[A-Z2-7]{4}){13}\b/i)?.[0];
  if (!key) throw new Error("O ficheiro não contém uma chave SolarMiner reconhecida.");
  const fingerprint = contents.match(/Gateway Ed25519 fingerprint:\s*([0-9a-f]{64})\b/i)?.[1] || "";
  return { key: key.toUpperCase(), fingerprint: fingerprint.toLowerCase() };
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
export async function listGatewayUsers() { return gatewayApi("/api/v1/users"); }
export async function updateGatewayUserRole(userId, role, currentPassword) {
  if (!/^[0-9a-f-]{36}$/i.test(userId)) throw new Error("Identificador de utilizador inválido.");
  if (!['owner', 'admin', 'operator', 'viewer'].includes(role)) throw new Error("Papel inválido.");
  if (typeof currentPassword !== "string" || !currentPassword) throw new Error("Introduz a palavra-passe atual do Owner.");
  return gatewayApi(`/api/v1/users/${encodeURIComponent(userId)}/role`, { method: "PATCH", body: { role, current_password: currentPassword } });
}
export async function updateGatewayUserStatus(userId, status, currentPassword) {
  if (!/^[0-9a-f-]{36}$/i.test(userId)) throw new Error("Identificador de utilizador inválido.");
  if (!['active', 'revoked'].includes(status)) throw new Error("Estado inválido.");
  if (typeof currentPassword !== "string" || !currentPassword) throw new Error("Introduz a palavra-passe atual do Owner.");
  return gatewayApi(`/api/v1/users/${encodeURIComponent(userId)}/status`, { method: "PATCH", body: { status, current_password: currentPassword } });
}
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
