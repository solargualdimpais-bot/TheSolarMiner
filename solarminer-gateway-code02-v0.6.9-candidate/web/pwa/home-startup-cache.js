const DB_NAME = "solarminer-owner-home-cache-v1";
const STORE_NAME = "snapshots";
const VERSION = 1;
const MAX_PHOTO_CHARS = 2_600_000;

let dbPromise;
function openDb() {
  if (typeof indexedDB === "undefined") return Promise.reject(new Error("IndexedDB indisponível"));
  if (!dbPromise) dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) db.createObjectStore(STORE_NAME, { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Não foi possível abrir a cache da Home"));
  });
  return dbPromise;
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error || new Error("Falha na cache da Home"));
  });
}

export function homeCacheKey(session) {
  if (!session?.authenticated || !session.gatewayUrl || !session.user) return "";
  try {
    const gateway = new URL(session.gatewayUrl).origin.toLowerCase();
    const identity = String(session.user.id || session.user.username || "").trim().toLowerCase();
    if (!identity) return "";
    return `${gateway}::${identity}`;
  } catch { return ""; }
}

export async function readHomeDisplayCache(key) {
  if (!key) return null;
  try {
    const db = await openDb();
    const record = await requestResult(db.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(key));
    if (!record?.snapshot || Date.now() - Number(record.savedAt || 0) > 90 * 24 * 60 * 60 * 1000) return null;
    return { ...record.snapshot, savedAt: record.savedAt };
  } catch { return null; }
}

export async function writeHomeDisplayCache(key, snapshot) {
  if (!key || !snapshot || typeof snapshot !== "object") return false;
  const photo = typeof snapshot.site?.photo_data_url === "string" ? snapshot.site.photo_data_url : "";
  if (photo.length > MAX_PHOTO_CHARS || (photo && !/^data:image\/(?:jpeg|png|webp);base64,/i.test(photo))) {
    snapshot = { ...snapshot, site: { ...snapshot.site, photo_data_url: "" } };
  }
  try {
    const db = await openDb();
    const store = db.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME);
    const previous = await requestResult(store.get(key));
    const payload = JSON.stringify(snapshot);
    if (previous && JSON.stringify(previous.snapshot) === payload) return true;
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put({ key, snapshot, savedAt: Date.now() });
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error || new Error("Falha ao atualizar a cache da Home"));
      tx.onabort = () => reject(tx.error || new Error("Atualização da cache da Home cancelada"));
    });
    return true;
  } catch { return false; }
}

export async function clearHomeDisplayCache(key) {
  if (!key) return;
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(key);
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  } catch { /* Cache cleanup must not interrupt logout. */ }
}
