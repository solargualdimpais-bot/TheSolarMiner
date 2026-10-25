import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const gatewayApp = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/app.py", import.meta.url), "utf8");
const energyEngine = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/energy_engine.py", import.meta.url), "utf8");
const workflow = readFileSync(new URL("../../.github/workflows/gateway-release.yml", import.meta.url), "utf8");

test("Tuya LAN report exposes the saved target and key presence without the key", () => {
  assert.match(gatewayApp, /"local_ip": item\.get\("local_ip", ""\)/);
  assert.match(gatewayApp, /"local_key_configured": bool\(item\.get\("local_key"\)\)/);
  assert.match(app, /IP guardado/);
  assert.match(app, /local_key_configured\?"Configurada":"Em falta"/);
});

test("Panels separate MPPT readings from inverter output and AQS records retain user fields", () => {
  assert.match(app, /const deyeReadings=page==="inversores"/);
  assert.match(app, /page==="paineis-solares"\?`\$\{panelReadings/);
  assert.match(app, /manufacturer,volume_l:volume/);
  assert.match(energyEngine, /"manufacturer", "volume_l"/);
  assert.match(energyEngine, /"pv_strings": normalized_pv_strings/);
});

test("PV string editor captures module details and derives total nominal power", () => {
  assert.match(app, /name="manufacturer"/);
  assert.match(app, /name="panel_count"/);
  assert.match(app, /name="panel_power_w"/);
  assert.match(app, /MPPT 1/);
  assert.match(app, /MPPT 2/);
  assert.match(app, /panelCount\*panelPower\/1000/);
  assert.match(app, /name="active" type="checkbox" checked> String online/);
  assert.match(app, /String “\$\{name\}” guardada no Gateway\./);
  assert.match(app, /Não foi possível guardar a string “\$\{name\}”: \$\{error\.message\}/);
  assert.match(app, /state\.page=pageBeforeSave;\s*render\(\);window\.scrollTo\(\{top:scrollBeforeSave,behavior:"auto"\}\)/);
  assert.match(energyEngine, /"panel_count"/);
  assert.match(energyEngine, /"panel_power_w"/);
  assert.match(app, /const saved=await saveGatewayEnergyEngineConfig\(\{pv_strings:strings\}\)/);
  assert.match(app, /const savedStrings=Array\.isArray\(saved\?\.pv_strings\)/);
  assert.match(energyEngine, /"pv_strings": normalized_pv_strings/);
  assert.match(gatewayApp, /@app\.get\("\/api\/v1\/energy\/engine\/config"\)/);
});

test("LAN discovery tries the local neighbor cache after broadcast errors", () => {
  assert.match(gatewayApp, /trying neighbor cache/);
  assert.match(gatewayApp, /neighbor_cache_empty/);
  assert.match(workflow, /0\.6\.58 0\.6\.59 0\.6\.60 0\.6\.61 0\.6\.62/);
});
