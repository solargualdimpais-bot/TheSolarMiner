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
  assert.match(auth, /\/api\/v1\/energy\/engine\?history_hours=24/);
  assert.match(auth, /\/api\/v1\/energy\/engine\/config/);
  assert.match(app, /SOC da bateria/);
  assert.match(app, /Energia acima do SOC mínimo/);
  assert.match(app, /Autonomia até ao corte/);
  assert.match(app, /Autonomia da bateria até ao corte/);
  assert.match(app, /battery-flow-kpi \$\{batteryFlowClass\}/);
  assert.match(app, /batteryFlowClass==="charge"\?"A carregar":batteryFlowClass==="discharge"\?"A descarregar"/);
  assert.match(read(root, "styles.css"), /battery-flow-kpi\.charge strong\{color:var\(--blue\)\}/);
  assert.match(read(root, "styles.css"), /battery-flow-kpi\.discharge strong\{color:var\(--red\)\}/);
  assert.match(app, /battery_soc_source/);
  assert.match(app, /gateway_energy_integrated/);
  assert.match(app, /page==="baterias"\?`<article class="ws-kpi battery-autonomy-card"/);
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
