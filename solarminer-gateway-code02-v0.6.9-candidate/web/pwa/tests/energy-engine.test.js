import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const gatewayPwa = resolve(root, "../solarminer-gateway-code02-v0.6.9-candidate/web/pwa");
const read = (base, file) => readFileSync(resolve(base, file), "utf8");

test("Owner PWA reads Gateway engine history and stores battery settings on Gateway", () => {
  const auth = read(root, "gateway-auth.js");
  const app = read(root, "app.js");
  assert.match(auth, /readGatewayEnergy\(historyHours = 24, historyUntil = null\)/);
  assert.match(auth, /history_hours: String\(historyHours\)/);
  assert.match(auth, /params\.set\("history_until", historyUntil\)/);
  assert.match(auth, /\/api\/v1\/energy\/engine\/config/);
  assert.match(app, /SOC da bateria/);
  assert.match(app, /Energia acima do SOC mínimo/);
  assert.match(app, /Autonomia até ao corte · sem solar/);
  assert.match(app, /perfil \$\{esc\(autonomy\.history_days_used\?\?0\)\} dias \+ consumo atual/);
  assert.match(app, /battery-flow-kpi \$\{batteryFlowClass\}/);
  assert.match(app, /batteryFlowClass==="charge"\?"A carregar":batteryFlowClass==="discharge"\?"A descarregar"/);
  assert.match(read(root, "styles.css"), /battery-flow-kpi\.charge strong\{color:var\(--blue\)\}/);
  assert.match(read(root, "styles.css"), /battery-flow-kpi\.discharge strong\{color:var\(--red\)\}/);
  assert.match(app, /battery_autonomy_forecast/);
  assert.match(app, /<h2>Até ao fim do dia<\/h2>/);
  assert.match(app, /<small>Solar restante<\/small>/);
  assert.match(app, /<small>Potencial restante<\/small>/);
  assert.match(app, /<small>Saldo após consumo<\/small>/);
  assert.match(app, /Previsão do dia comparada com a produção medida/);
  assert.match(app, /data-engine-history-day="-1"/);
  assert.match(app, /class="engine-history-arrow left" data-engine-history-day="-1"/);
  assert.match(app, /class="engine-history-arrow right" data-engine-history-day="1"/);
  assert.match(app, /dayKey>=todayKey\|\|loading\?/);
  assert.match(read(root, "styles.css"), /\.engine-history-arrow\.left\{left:0\}/);
  assert.match(app, /FV medido acumulado/);
  assert.match(app, /bank\.active!==false/);
  assert.match(app, /Potência FV estimada \+1 h/);
  assert.match(app, /Consumo estimado \+1 h/);
  assert.match(app, /SOC estimado \+1 h/);
  assert.match(app, /Guardar bateria/);
  assert.match(app, /LIVE_UNVERIFIED/);
  assert.match(app, /CARGAS FLEXÍVEIS/);
  assert.match(app, /underfloor_heating/);
  assert.match(app, /engine-load-tuya-device/);
  assert.match(app, /Relé de alimentação mineradora/);
  assert.match(auth, /controlGatewayTuyaSwitch/);
  assert.match(auth, /\/api\/v1\/integrations\/tuya\/switch/);
});

test("Gateway-served PWA assets match the GitHub Pages PWA", () => {
  for (const file of ["app.js", "gateway-auth.js", "index.html", "service-worker.js"]) {
    assert.equal(read(gatewayPwa, file), read(root, file), `${file} must stay in sync`);
  }
});
