import { buildApiUrl } from "./app-core-legacy.js";

export class AuthFlowError extends Error {
  constructor(message, status = 0, code = "auth_error") { super(message); this.name = "AuthFlowError"; this.status = status; this.code = code; }
}

const encoder = new TextEncoder();
const subtle = () => {
  if (!globalThis.crypto?.subtle) throw new AuthFlowError("Este navegador não disponibiliza Web Crypto API.", 0, "webcrypto_unavailable");
  return globalThis.crypto.subtle;
};
const bytesToHex = bytes => Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, "0")).join("");
const bytesToBase64 = bytes => {
  let binary = "";
  for (const byte of new Uint8Array(bytes)) binary += String.fromCharCode(byte);
  return btoa(binary);
};
const randomNonce = () => {
  const bytes = new Uint8Array(24);
  globalThis.crypto.getRandomValues(bytes);
  return bytesToHex(bytes);
};
const timestampNow = () => Math.floor(Date.now() / 1000);
const pemEncode = der => `-----BEGIN PUBLIC KEY-----\n${bytesToBase64(der).match(/.{1,64}/g).join("\n")}\n-----END PUBLIC KEY-----`;

export async function generateDeviceIdentity() {
  let keyPair;
  try {
    // The private key is generated non-exportable and is never sent to the Gateway.
    keyPair = await subtle().generateKey({ name: "Ed25519" }, false, ["sign", "verify"]);
  } catch (error) {
    throw new AuthFlowError("Este browser não suporta geração de chaves Ed25519 não exportáveis. Atualiza o browser; não será usado um algoritmo alternativo silencioso.", 0, "ed25519_unavailable");
  }
  const publicDer = await subtle().exportKey("spki", keyPair.publicKey);
  const publicKeyPem = pemEncode(publicDer);
  const publicKeyDigest = bytesToHex(await subtle().digest("SHA-256", publicDer));
  return { privateKey: keyPair.privateKey, publicKeyPem, publicKeyDigest };
}

export async function signText(privateKey, canonicalText) {
  const signature = await subtle().sign({ name: "Ed25519" }, privateKey, encoder.encode(canonicalText));
  return bytesToHex(signature);
}

async function jsonRequest({ baseUrl, path, method = "POST", body, token = "", fetchImpl = globalThis.fetch, timeoutMs = 7000 }) {
  const url = buildApiUrl(baseUrl, path);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = { Accept: "application/json", "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetchImpl(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, cache: "no-store", credentials: "omit", redirect: "error" });
    let data;
    try { data = await response.json(); } catch { throw new AuthFlowError("Resposta inválida do Gateway.", response.status, "invalid_json"); }
    if (!response.ok) {
      const code = typeof data?.detail === "string" ? data.detail : (typeof data?.error === "string" ? data.error : "http_error");
      const message = ({ pairing_code_invalid_expired_or_used: "Código de emparelhamento inválido, expirado ou já utilizado.", device_signature_invalid: "Assinatura do dispositivo inválida.", timestamp_out_of_window: "Relógio do dispositivo fora da janela permitida.", nonce_replayed: "Pedido repetido detetado pelo Gateway.", invalid_credentials_or_device: "Credenciais ou dispositivo inválidos.", device_not_associated: "Este dispositivo não está associado a este utilizador.", session_invalid_or_expired: "Sessão expirada ou revogada.", permission_denied: "Não tens autorização para esta operação.", active_target_user_not_found: "O utilizador de destino não existe ou está inativo." })[code] || `O Gateway respondeu com HTTP ${response.status} (${code}).`;
      throw new AuthFlowError(message, response.status, code);
    }
    return data;
  } catch (error) {
    if (error instanceof AuthFlowError) throw error;
    if (error?.name === "AbortError") throw new AuthFlowError("Timeout ao contactar o Gateway.", 0, "timeout");
    throw new AuthFlowError("Gateway indisponível ou erro de rede.", 0, "network_error");
  } finally { clearTimeout(timer); }
}

export async function pairDevice({ baseUrl, pairingCode, mac, fetchImpl = globalThis.fetch, identity = null }) {
  if (!pairingCode || pairingCode.length < 32) throw new AuthFlowError("É necessário um código de emparelhamento válido.", 0, "pairing_code_required");
  const normalizedMac = String(mac || "").trim().toUpperCase();
  if (!/^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(normalizedMac)) throw new AuthFlowError("Indica um endereço MAC válido (declaração; não verificado fisicamente).", 0, "invalid_mac");
  const deviceIdentity = identity || await generateDeviceIdentity();
  const timestamp = timestampNow();
  const nonce = randomNonce();
  const canonical = `PAIR\n${pairingCode}\n${deviceIdentity.publicKeyDigest}\n${normalizedMac}\n${timestamp}\n${nonce}`;
  const signature = await signText(deviceIdentity.privateKey, canonical);
  const result = await jsonRequest({ baseUrl, path: "/api/v1/devices/pair", fetchImpl, body: { pairing_code: pairingCode, mac: normalizedMac, public_key_pem: deviceIdentity.publicKeyPem, timestamp, nonce, signature } });
  return { ...deviceIdentity, deviceId: result.device_id, username: result.username, gatewayOrigin: new URL(baseUrl).origin, pairedAt: new Date().toISOString() };
}

export async function loginDevice({ baseUrl, username, password, identity, fetchImpl = globalThis.fetch }) {
  if (!identity?.privateKey || !identity?.deviceId) throw new AuthFlowError("Este browser ainda não tem um dispositivo emparelhado com este Gateway.", 0, "device_not_paired");
  const timestamp = timestampNow();
  const nonce = randomNonce();
  const canonical = `LOGIN\n${username}\n${identity.deviceId}\n${timestamp}\n${nonce}`;
  const signature = await signText(identity.privateKey, canonical);
  return jsonRequest({ baseUrl, path: "/api/v1/auth/login", fetchImpl, body: { username, password, device_id: identity.deviceId, timestamp, nonce, signature } });
}

export async function issuePairingCode({ baseUrl, token, username, expiresIn = 300, fetchImpl = globalThis.fetch }) {
  if (!token) throw new AuthFlowError("É necessária uma sessão administrativa válida.", 401, "authentication_required");
  return jsonRequest({ baseUrl, path: "/api/v1/devices/pairing-codes", token, fetchImpl, body: { username, expires_in: expiresIn } });
}

export async function logoutDevice({ baseUrl, token, fetchImpl = globalThis.fetch }) {
  if (!token) return { status: "already_logged_out" };
  return jsonRequest({ baseUrl, path: "/api/v1/auth/logout", token, fetchImpl, body: {} });
}

export class IndexedDbIdentityStore {
  constructor({ indexedDBImpl = globalThis.indexedDB } = {}) { this.indexedDBImpl = indexedDBImpl; this.dbPromise = null; }
  open() {
    if (!this.indexedDBImpl) return Promise.reject(new AuthFlowError("IndexedDB indisponível; a chave privada não será guardada em armazenamento menos seguro.", 0, "indexeddb_unavailable"));
    if (!this.dbPromise) this.dbPromise = new Promise((resolve, reject) => {
      const request = this.indexedDBImpl.open("the-solar-miner-identities", 1);
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains("identities")) request.result.createObjectStore("identities", { keyPath: "gatewayOrigin" }); };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(new AuthFlowError("Não foi possível abrir o armazenamento de identidade do browser.", 0, "indexeddb_open_failed"));
    });
    return this.dbPromise;
  }
  async get(gatewayOrigin) {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const request = db.transaction("identities", "readonly").objectStore("identities").get(gatewayOrigin);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(new AuthFlowError("Não foi possível ler a identidade deste Gateway.", 0, "identity_read_failed"));
    });
  }
  async save(identity) {
    if (!identity?.privateKey || identity.privateKey.extractable !== false) throw new AuthFlowError("Recusada a persistência de uma chave privada exportável.", 0, "exportable_private_key_refused");
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const request = db.transaction("identities", "readwrite").objectStore("identities").put(identity);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(new AuthFlowError("Não foi possível guardar a identidade emparelhada.", 0, "identity_save_failed"));
    });
  }
  async delete(gatewayOrigin) {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const request = db.transaction("identities", "readwrite").objectStore("identities").delete(gatewayOrigin);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(new AuthFlowError("Não foi possível apagar a identidade local.", 0, "identity_delete_failed"));
    });
  }
}
