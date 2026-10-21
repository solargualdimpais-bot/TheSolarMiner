export const CATEGORIES = [
  { id: "inversores", label: "Inversores", icon: "ϟ", description: "Produção solar e conversão de energia" },
  { id: "baterias", label: "Baterias", icon: "▤", description: "Armazenamento, carga e descarga" },
  { id: "mineradoras", label: "Mineradoras", icon: "▦", description: "Equipamento de computação e consumo" },
  { id: "ev", label: "EV", icon: "↗", description: "Veículos e carregamento elétrico" },
  { id: "aqs", label: "AQS", icon: "♨", description: "Água quente sanitária" },
  { id: "soalho-radiante", label: "Soalho Radiante", icon: "⌁", description: "Aquecimento e controlo térmico" },
];

export const DEMO_EQUIPMENT = [
  { id: "demo-inv-01", category: "inversores", name: "Inversor principal", manufacturer: "DEMO", model: "Perfil não validado", connection_state: "SIMULATED", status: "SIMULATED", readings: [{ field: "potencia_solar", value: 4.82, unit: "kW", trust: "SIMULATED", source: "DEMO_FIXTURE" }], last_communication_at: null, source: "SIMULATED" },
  { id: "demo-bat-01", category: "baterias", name: "Banco de baterias", manufacturer: "DEMO", model: "Perfil ilustrativo", connection_state: "SIMULATED", status: "SIMULATED", readings: [{ field: "soc", value: 78, unit: "%", trust: "SIMULATED", source: "DEMO_FIXTURE" }], last_communication_at: null, source: "SIMULATED" },
  { id: "demo-miner-01", category: "mineradoras", name: "Mineradora de exemplo", manufacturer: "DEMO", model: "Sem ligação física", connection_state: "SIMULATED", status: "SIMULATED", readings: [{ field: "potencia", value: 3.25, unit: "kW", trust: "SIMULATED", source: "DEMO_FIXTURE" }], last_communication_at: null, source: "SIMULATED" },
  { id: "demo-ev-01", category: "ev", name: "Carregador EV", manufacturer: "DEMO", model: "Sem ligação física", connection_state: "SIMULATED", status: "SIMULATED", readings: [{ field: "potencia", value: 0, unit: "kW", trust: "SIMULATED", source: "DEMO_FIXTURE" }], last_communication_at: null, source: "SIMULATED" },
  { id: "demo-aqs-01", category: "aqs", name: "Depósito AQS", manufacturer: "DEMO", model: "Sem sensor real", connection_state: "SIMULATED", status: "SIMULATED", readings: [{ field: "temperatura", value: 48, unit: "°C", trust: "SIMULATED", source: "DEMO_FIXTURE" }], last_communication_at: null, source: "SIMULATED" },
  { id: "demo-floor-01", category: "soalho-radiante", name: "Zona de conforto", manufacturer: "DEMO", model: "Sem termóstato real", connection_state: "SIMULATED", status: "SIMULATED", readings: [{ field: "temperatura", value: 21.5, unit: "°C", trust: "SIMULATED", source: "DEMO_FIXTURE" }], last_communication_at: null, source: "SIMULATED" },
];

export function isSimulated(item) {
  return item?.status === "SIMULATED" || item?.connection_state === "SIMULATED" || item?.source === "SIMULATED" || item?.readings?.some(r => r.trust === "SIMULATED" || r.source === "DEMO_FIXTURE");
}

export function formatReading(reading) {
  if (!reading || reading.value === null || reading.value === undefined) return { value: "—", unit: "", valid: false };
  const value = typeof reading.value === "number" ? new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 2 }).format(reading.value) : String(reading.value);
  return { value, unit: reading.unit || "", valid: true };
}

export function classifyEquipment(item) {
  if (isSimulated(item)) return "SIMULATED";
  const state = String(item?.connection_state || item?.status || "UNKNOWN").toUpperCase();
  if (["CONNECTED", "ONLINE", "OK", "ACTIVE"].includes(state)) return "CONNECTED";
  if (["UNAVAILABLE", "OFFLINE", "ERROR", "DISCONNECTED"].includes(state)) return "UNAVAILABLE";
  return "NOT_VALIDATED";
}

export function buildApiUrl(baseUrl, path) {
  const base = new URL(baseUrl);
  if (base.protocol !== "https:" && base.hostname !== "localhost" && base.hostname !== "127.0.0.1") throw new Error("HTTPS_REQUIRED_FOR_REAL_GATEWAY");
  if (!path.startsWith("/api/v1/")) throw new Error("API_PATH_NOT_ALLOWED");
  return new URL(path, base).toString();
}

export function summarizeDataState({ mode, lastUpdated, now = Date.now(), maxAgeMs = 60_000 }) {
  if (mode === "SIMULATED") return { label: "DEMONSTRAÇÃO · SIMULATED", stale: false, simulated: true };
  if (!lastUpdated) return { label: "SEM LEITURAS CONFIRMADAS", stale: true, simulated: false };
  const age = Math.max(0, now - new Date(lastUpdated).getTime());
  if (!Number.isFinite(age) || age > maxAgeMs) return { label: "DADOS DESATUALIZADOS", stale: true, simulated: false };
  return { label: "DADOS RECENTES", stale: false, simulated: false };
}

export function latestDataTimestamp(equipment) {
  const timestamps = [];
  for (const item of equipment || []) {
    if (item?.last_communication_at) timestamps.push(item.last_communication_at);
    for (const reading of item?.readings || []) if (reading?.observed_at) timestamps.push(reading.observed_at);
  }
  const valid = timestamps.map(value => ({value, ms: new Date(value).getTime()})).filter(x => Number.isFinite(x.ms));
  if (!valid.length) return null;
  return valid.reduce((latest, current) => current.ms > latest.ms ? current : latest).value;
}
