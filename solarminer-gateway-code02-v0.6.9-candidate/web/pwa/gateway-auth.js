import { parseInviteQr, verifyGatewayIdentityChallenge, signInviteRedemption, signGatewayLogin, validateGatewayUrl } from "./gateway-connection.js";

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
async function gatewayRequest(baseUrl, path, { method = "GET", body, authenticated = false, token = bearerToken, signal } = {}) {
  const base = validateGatewayUrl(baseUrl, { allowLocalHttp: ["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, "")) });
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (authenticated) {
    if (!token) throw new Error("É necessária uma sessão autenticada do Gateway.");
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(new URL(path, base.origin), {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "omit", cache: "no-store", redirect: "error", signal,
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
      login_attempts_limited: "Demasiadas tentativas de início de sessão. Aguarda alguns minutos antes de tentar novamente.",
      bootstrap_unavailable: "O Gateway já não permite criar o primeiro Owner.",
      invalid_credentials_or_device: "Utilizador ou palavra-passe incorretos, ou este dispositivo não está associado à conta.",
      device_not_associated: "Este dispositivo ainda não está associado a essa conta. Confirma as credenciais ou remove a identidade antiga deste browser.",
      ev_tesla_not_configured: "Configura primeiro a ligação Tesla em Energia → Carregador EV.",
      ev_tesla_read_failed: "O Gateway não conseguiu ler o estado de carga Tesla. Confirma a região, a autorização Fleet e o veículo selecionado.",
      invalid_tesla_vehicle_ids: "Seleciona apenas um veículo Tesla para o carregamento.",
      deye_cloud_auth_rejected: "A Deye Cloud recusou a autenticação. Confirma App ID, App Secret, e-mail, palavra-passe e centro de dados.",
      deye_cloud_permission_denied: "A Deye Cloud autenticou o pedido, mas recusou o acesso a esta conta ou estação.",
      deye_cloud_endpoint_not_found: "A Deye Cloud não reconheceu o endpoint para este centro de dados. Confirma a região selecionada.",
      deye_cloud_rate_limited: "A Deye Cloud limitou os pedidos. Aguarda antes de tentar importar novamente.",
      deye_cloud_upstream_timeout: "A Deye Cloud demorou demasiado a responder ao pedido de histórico.",
      deye_cloud_connection_failed: "O Gateway não conseguiu estabelecer ligação à Deye Cloud.",
      deye_cloud_invalid_response: "A Deye Cloud devolveu uma resposta que o Gateway não conseguiu interpretar.",
      antminer_control_credentials_required: "O teste de ligação é independente do controlo. Para enviar comandos Braiins OS, configura e guarda o utilizador e a palavra-passe próprios do minerador."
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
export async function loginGatewayWithPassword({ gatewayUrl, username, password }) {
  const base = validateGatewayUrl(gatewayUrl).origin;
  const normalizedUsername = String(username || "").trim();
  if (!normalizedUsername || !password) throw new Error("Introduz o utilizador e a palavra-passe do Gateway.");
  const timestamp = Math.floor(Date.now() / 1000), challengeNonce = nonce();
  const challenge = await gatewayRequest(base, `/api/v1/gateway/identity?timestamp=${timestamp}&nonce=${challengeNonce}`);
  let identity = await loadDeviceIdentity(base);
  if (identity && identity.gatewayFingerprint !== challenge.fingerprint_sha256) {
    throw new Error("A identidade Ed25519 do Gateway mudou. A ligação foi interrompida para proteger a conta.");
  }
  if (identity?.privateKey && identity?.deviceId && identity?.publicKeyPem) {
    const loginTimestamp = Math.floor(Date.now() / 1000), loginNonce = nonce();
    const payload = await signGatewayLogin({ privateKey: identity.privateKey, username: normalizedUsername,
      deviceId: identity.deviceId, timestamp: loginTimestamp, nonce: loginNonce });
    payload.password = password;
    const result = await gatewayRequest(base, "/api/v1/auth/login", { method: "POST", body: payload });
    bearerToken = result.access_token; currentUser = result.user; currentGateway = base;
    await startPresenceHeartbeat();
    return { ...result, gatewayUrl: base, presence: presenceInfo() };
  }
  if (!identity) identity = await createDeviceIdentity(base, challenge.fingerprint_sha256);
  const digestHex = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
  const publicDer = Uint8Array.from(atob(identity.publicKeyPem.replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s/g, "")), c => c.charCodeAt(0));
  const passwordHash = await digestHex(new TextEncoder().encode(password));
  const publicHash = await digestHex(publicDer);
  const loginTime = Math.floor(Date.now() / 1000), loginNonce = nonce();
  const canonical = `PASSWORD-DEVICE-LOGIN\n${normalizedUsername}\n${loginTime}\n${loginNonce}\n${passwordHash}\n${publicHash}`;
  const signatureBytes = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, identity.privateKey, new TextEncoder().encode(canonical)));
  const signature = Array.from(signatureBytes, b => b.toString(16).padStart(2, "0")).join("");
  const result = await gatewayRequest(base, "/api/v1/auth/password-device-login", { method: "POST", body: {
    username: normalizedUsername, password, public_key_pem: identity.publicKeyPem,
    timestamp: loginTime, nonce: loginNonce, signature
  } });
  identity.deviceId = result.device_id; identity.userId = result.user.id;
  await identityDbRequest("readwrite", store => store.put(identity));
  bearerToken = result.access_token; currentUser = result.user; currentGateway = base;
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
export async function readGatewayTailscale() {
  return gatewayApi("/api/v1/system/tailscale");
}
export async function readGatewayConsole() {
  return gatewayApi("/api/v1/system/console");
}
export async function readGatewayTerminalDiagnostics() {
  return gatewayApi("/api/v1/system/terminal/diagnostics");
}
export async function openGatewayTerminalSocket() {
  if (!currentGateway || !bearerToken || currentUser?.role !== "owner") throw new Error("Inicia sessão como Owner para abrir o terminal.");
  // The saved Tailscale HTTPS endpoint is an explicit route choice for the
  // terminal too; otherwise an Owner session authenticated on another Gateway
  // origin keeps opening its WebSocket against that old origin.
  let socketBase = currentGateway;
  try {
    const access = await readGatewayTailscale();
    if (access?.https_ready === true && typeof access.endpoint === "string") {
      socketBase = validateGatewayUrl(access.endpoint).origin;
    }
  } catch { /* Keep the authenticated session endpoint if route lookup fails. */ }
  const socketUrl = new URL("/api/v1/system/terminal/ws", socketBase);
  socketUrl.protocol = socketUrl.protocol === "https:" ? "wss:" : "ws:";
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(socketUrl.toString());
    let settled = false;
    const timer = setTimeout(() => fail("O Gateway aceitou a ligação, mas não confirmou a sessão do terminal dentro do tempo esperado.", "timeout"), 10000);
    const cleanup = () => {
      clearTimeout(timer);
      socket.removeEventListener("open", onOpen);
      socket.removeEventListener("message", onMessage);
      socket.removeEventListener("close", onClose);
      socket.removeEventListener("error", onError);
    };
    const fail = (message, code) => {
      if (settled) return;
      settled = true;
      cleanup();
      const error = new Error(message);
      error.code = code;
      reject(error);
      socket.close();
    };
    const onOpen = () => {
      try { socket.send(JSON.stringify({ type: "authenticate", token: bearerToken })); }
      catch { fail("A ligação abriu, mas não foi possível enviar a autenticação ao Gateway.", "send_failed"); }
    };
    const onMessage = event => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message?.type === "ready") {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(socket);
      } else if (message?.type === "error") {
        fail(typeof message.data === "string" ? message.data : "O serviço de terminal recusou a ligação.", "gateway_error");
      }
    };
    const onClose = event => {
      const reasons = {
        4401: ["A sessão Owner expirou ou não foi aceite pelo Gateway. Termina sessão e volta a entrar.", "unauthorized"],
        4403: ["O Gateway recusou o acesso Owner ou a origem da PWA para o terminal.", "forbidden"],
        1011: ["O Gateway aceitou a ligação, mas não conseguiu iniciar o terminal. A verificação de compatibilidade pode indicar a causa.", "gateway_failure"],
      };
      const [text, code] = reasons[event.code] || ["O WebSocket foi fechado antes de o Gateway confirmar o terminal.", `close_${event.code || 0}`];
      fail(text, code);
    };
    const onError = () => fail("O navegador não conseguiu concluir o handshake WebSocket com o Gateway.", "websocket_handshake_failed");
    socket.addEventListener("open", onOpen);
    socket.addEventListener("message", onMessage);
    socket.addEventListener("close", onClose);
    socket.addEventListener("error", onError);
  });
}
export async function configureGatewayTailscale(endpoint) {
  if (endpoint !== null && (typeof endpoint !== "string" || !endpoint.trim())) throw new Error("Indica um endereço Tailscale HTTPS ou deixa o campo vazio para deteção automática.");
  return gatewayApi("/api/v1/system/tailscale", { method: "PUT", body: { endpoint: endpoint === null ? null : endpoint.trim() } });
}
export async function startGatewayTailscale() {
  return gatewayApi("/api/v1/system/tailscale/connect", { method: "POST", body: {} });
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
export async function readGatewayEnergy(historyHours = 24, historyUntil = null) {
  const params = new URLSearchParams({ history_hours: String(historyHours) });
  if (historyUntil) params.set("history_until", historyUntil);
  const isOwner = sessionInfo().user?.role === "owner";
  const [status, categories, equipment, engine, siteProfile, configuration] = await Promise.all([
    gatewayApi("/api/v1/status"), gatewayApi("/api/v1/energy/categories"), gatewayApi("/api/v1/energy/equipment"),
    gatewayApi(`/api/v1/energy/engine?${params.toString()}`), gatewayApi("/api/v1/site/profile"),
    isOwner ? gatewayApi("/api/v1/energy/engine/config") : Promise.resolve(null)
  ]);
  const liveReadings = engine?.latest_readings || {};
  const liveEquipment = (equipment.equipment || []).map(item => {
    const isDeyeInverter = item.id?.startsWith("deye-inverter-");
    const isDeyeBattery = item.id?.startsWith("deye-battery-");
    if (!isDeyeInverter && !isDeyeBattery) return item;
    const fields = new Set(Object.entries(liveReadings)
      .filter(([, reading]) => reading && ((isDeyeInverter && !reading.field.startsWith("battery_")) || (isDeyeBattery && reading.field.startsWith("battery_"))))
      .map(([field]) => field));
    if (!fields.size) return item;
    const historical = (item.readings || []).filter(reading => !fields.has(reading.field));
    const current = [...fields].map(field => ({ ...liveReadings[field], id: `live-${field}` }));
    return { ...item, readings: [...historical, ...current], last_communication_at: engine.updated_at || item.last_communication_at };
  });
  if (isOwner && configuration) engine.configuration = configuration;
  return { status, categories: categories.categories || [], equipment: liveEquipment, engine, siteProfile, fetchedAt: new Date().toISOString() };
}
export async function readGatewaySiteProfile() {
  return gatewayApi("/api/v1/site/profile");
}
export async function saveGatewaySiteProfile(profile) {
  if (!profile || typeof profile !== "object") throw new Error("Perfil da propriedade inválido.");
  return gatewayApi("/api/v1/site/profile", { method: "PUT", body: profile });
}
export async function saveGatewaySitePhoto({ kind, floorId, roomId = "", photoDataUrl }) {
  if (!new Set(["floor", "plan", "room"]).has(kind) || !floorId || typeof photoDataUrl !== "string") throw new Error("Fotografia do piso inválida.");
  return gatewayApi("/api/v1/site/profile/photo", { method: "PUT", body: { kind, floor_id: floorId, room_id: roomId, photo_data_url: photoDataUrl } });
}
export async function saveGatewayEnergyEngineConfig(config) {
  if (!config || typeof config !== "object") throw new Error("Configuração energética inválida.");
  return gatewayApi("/api/v1/energy/engine/config", { method: "PUT", body: config });
}
export async function readGatewayHardwareIntegrationConfig() {
  return gatewayApi("/api/v1/integrations/hardware");
}
export async function saveGatewayHardwareIntegrationConfig(config) {
  if (!config || typeof config !== "object") throw new Error("Configuração de equipamentos inválida.");
  return gatewayApi("/api/v1/integrations/hardware", { method: "PUT", body: config });
}
export async function readGatewayDeyeCloudStations() {
  return gatewayApi("/api/v1/integrations/deye-cloud/stations", { method: "POST", body: {} });
}
export async function importGatewayDeyeCloudHistory(stationId, onProgress = () => {}) {
  if (!/^\d{1,32}$/.test(String(stationId ?? ""))) throw new Error("Seleciona uma estação Deye válida.");
  const job = await gatewayApi("/api/v1/integrations/deye-cloud/history/import", { method: "POST", body: { station_id: String(stationId) } });
  if (!job?.job_id) throw new Error("O Gateway não iniciou a importação do histórico.");
  const startedAt = Date.now();
  let current = job;
  while (Date.now() - startedAt < 15 * 60 * 1000) {
    onProgress(current);
    if (current.status === "completed") return current.result;
    if (current.status === "failed") {
      const error = new Error(current.error?.message || "deye_cloud_history_import_failed");
      error.status = current.error?.status;
      throw error;
    }
    await new Promise(resolve => setTimeout(resolve, 1200));
    current = await gatewayApi(`/api/v1/integrations/deye-cloud/history/import/${encodeURIComponent(job.job_id)}`);
  }
  const error = new Error("O Gateway continua a processar a importação, mas a PWA deixou de aguardar. Verifica o histórico antes de repetir.");
  error.status = 504;
  throw error;
}
export async function syncGatewayTuyaDevices({ signal } = {}) {
  return gatewayApi("/api/v1/integrations/tuya/sync", { method: "POST", body: {}, signal });
}
export async function readGatewayHardwareIntegrations() {
  return gatewayApi("/api/v1/integrations/hardware/read", { method: "POST", body: {} });
}
export async function readGatewayHardwareProvider(provider, deviceId) {
  if (!["deye", "antminer", "tuya"].includes(provider)) throw new Error("Equipamento inválido.");
  const body = deviceId ? { device_id: deviceId } : {};
  return gatewayApi(`/api/v1/integrations/hardware/${provider}/read`, { method: "POST", body });
}
export async function controlGatewayAntminer(action, watt) {
  if (!["set_power_target", "pause", "stop", "start"].includes(action)) throw new Error("Ação Antminer inválida.");
  const body = { action };
  if (action === "set_power_target") {
    if (!Number.isInteger(watt) || watt < 1 || watt > 100000) throw new Error("O alvo tem de estar entre 1 e 100000 W.");
    body.watt = watt;
  }
  return gatewayApi("/api/v1/integrations/antminer/control", { method: "POST", body });
}
export async function testGatewayAntminerControl() {
  return gatewayApi("/api/v1/integrations/antminer/test-control", { method: "POST", body: {} });
}
export async function readGatewayAntminerManagement(operation) {
  if (typeof operation !== "string" || !/^[a-z_]{1,64}$/.test(operation)) throw new Error("Consulta da Mineradora inválida.");
  return gatewayApi("/api/v1/integrations/antminer/management", { method: "POST", body: { operation } });
}
export async function writeGatewayAntminerManagement(operation, payload = undefined, resourceId = undefined) {
  if (typeof operation !== "string" || !/^[a-z_]{1,64}$/.test(operation)) throw new Error("Operação da Mineradora inválida.");
  if (resourceId !== undefined && (typeof resourceId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(resourceId))) throw new Error("Identificador da configuração inválido.");
  return gatewayApi("/api/v1/integrations/antminer/management", { method: "POST", body: { operation, ...(payload !== undefined ? { payload } : {}), ...(resourceId ? { resource_id: resourceId } : {}) } });
}
export async function controlGatewayTuyaSwitch(deviceId, on, code = undefined) {
  if (typeof deviceId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(deviceId) || typeof on !== "boolean") throw new Error("Comando Tuya inválido.");
  if (code !== undefined && (typeof code !== "string" || !/^[A-Za-z0-9_-]{1,64}$/.test(code))) throw new Error("Canal Tuya inválido.");
  return gatewayApi("/api/v1/integrations/tuya/switch", { method: "POST", body: { device_id: deviceId, on, ...(code ? { code } : {}) } });
}
export async function controlGatewayTuyaLevel(deviceId, percent) {
  if (typeof deviceId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(deviceId) || !Number.isInteger(percent) || percent < 0 || percent > 100) throw new Error("Comando Tuya percentual inválido.");
  return gatewayApi("/api/v1/integrations/tuya/level", { method: "POST", body: { device_id: deviceId, percent } });
}
export async function readGatewayTuyaDeviceEvents(deviceId, limit = 100) {
  if (typeof deviceId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(deviceId) || !Number.isInteger(limit) || limit < 1 || limit > 500) throw new Error("Dispositivo inválido.");
  return gatewayApi(`/api/v1/integrations/tuya/${encodeURIComponent(deviceId)}/events?limit=${limit}`);
}
export async function runGatewayTuyaLanDiagnostics(rounds = 3) {
  if (!Number.isInteger(rounds) || rounds < 1 || rounds > 5) throw new Error("O diagnóstico aceita entre uma e cinco rondas.");
  return gatewayApi("/api/v1/integrations/tuya/lan-diagnostics", { method: "POST", body: { rounds } });
}
export async function discoverGatewayTuyaLanDevices() {
  return gatewayApi("/api/v1/integrations/tuya/lan-discovery", { method: "POST", body: {} });
}
export async function readGatewayHuaweiClients() {
  return gatewayApi("/api/v1/integrations/huawei/clients", { method: "POST", body: {} });
}
export async function readGatewayTeslaEvConfig() {
  return gatewayApi("/api/v1/energy/ev/tesla");
}
export async function saveGatewayTeslaEvConfig(config) {
  if (!config || typeof config !== "object") throw new Error("Configuração Tesla EV inválida.");
  return gatewayApi("/api/v1/energy/ev/tesla", { method: "PUT", body: config });
}
export async function readGatewayTeslaEvCharging() {
  return gatewayApi("/api/v1/energy/ev/tesla/read", { method: "POST", body: {} });
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
