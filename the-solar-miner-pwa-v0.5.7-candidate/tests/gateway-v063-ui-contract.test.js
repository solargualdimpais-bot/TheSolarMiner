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
  assert.match(app, /dialog\.dataset\.returnPage=state\.page/);
  assert.match(app, /state\.page=returnPage;\s*render\(\);window\.scrollTo\(\{top:scrollBeforeSave,behavior:"auto"\}\)/);
  assert.doesNotMatch(app, /state\.page=pageBeforeSave==="paineis-solares"\?pageBeforeSave:"paineis-solares"/);
  assert.match(energyEngine, /"panel_count"/);
  assert.match(energyEngine, /"panel_power_w"/);
  assert.match(app, /await saveGatewayEnergyEngineConfig\(\{pv_strings:strings\}\)/);
  assert.match(app, /const saved=await readGatewayEnergyEngineConfig\(\)/);
  assert.match(app, /const savedStrings=Array\.isArray\(saved\?\.pv_strings\)/);
  assert.match(app, /e\.preventDefault\(\); e\.stopPropagation\(\); void savePvStringForm/);
  assert.match(readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8"), /export async function readGatewayEnergyEngineConfig\(\)/);
  assert.match(energyEngine, /"pv_strings": normalized_pv_strings/);
  assert.match(gatewayApp, /@app\.get\("\/api\/v1\/energy\/engine\/config"\)/);
});

test("AQS save waits for valid fields, confirms persistence, and stays in its area", () => {
  assert.match(app, /id="aqs-form"[\s\S]*?button type="submit" class="button primary" disabled>Guardar/);
  assert.match(app, /function updateAqsSaveButton\(form\)/);
  assert.match(app, /const saved=await readGatewayEnergyEngineConfig\(\),savedLoads=Array\.isArray\(saved\?\.loads\)\?saved\.loads:null/);
  assert.match(app, /dialog\.dataset\.returnPage=state\.page/);
  assert.match(app, /state\.page=returnPage;\s*render\(\);window\.scrollTo\(\{top:scrollBeforeSave,behavior:"auto"\}\)/);
  assert.doesNotMatch(app, /state\.page=pageBeforeSave==="aqs"\?pageBeforeSave:"aqs"/);
});

test("AQS breaker options show one Tuya device name and select its configured primary channel", () => {
  assert.match(app, /const devicesById=new Map\(\)/);
  assert.match(app, /if\(!device\?\.device_id\|\|devicesById\.has\(device\.device_id\)\)continue/);
  assert.match(app, /\$\{esc\(device\.name\)\}<\/option>/);
});

test("EV page renders the Tesla Fleet and local-presence controls used by its handlers", () => {
  assert.match(app, /function renderEvSection\(config,isOwner\)/);
  for (const id of ["ev-tesla-region", "ev-tesla-client-id", "ev-tesla-refresh-token", "ev-tesla-vehicle-id", "ev-tesla-fleet-save", "ev-tesla-read", "ev-tesla-local-mac", "ev-tesla-save", "ev-tesla-presence"]) {
    assert.ok(app.includes(`id="${id}"`), `missing ${id}`);
  }
  assert.match(app, /page==="ev"\?renderEvSection\(config,isOwner\)/);
  assert.match(app, /Esta ligação consulta a API Tesla para ler o estado do veículo\. Não envia comandos de carregamento\./);
});

test("Favorite controls refresh the target device before toggling and show a simple detail on tap", () => {
  assert.match(app, /readGatewayHardwareProvider\("tuya",deviceId\),before=/);
  assert.match(app, /controlGatewayTuyaSwitch\(deviceId,desired,code\)/);
  assert.match(app, /readGatewayHardwareProvider\("tuya",deviceId\),after=/);
  assert.match(app, /openFavoriteDeviceDetails\(favoriteCard\.dataset\.favoriteDevice,favoriteCard\.dataset\.deviceKind\)/);
  assert.match(app, /function openFavoriteDeviceDetails\(deviceId,kind\)/);
  assert.match(app, /function tuyaSimpleReadings\(device,reading\)/);
  assert.match(app, /function favoriteReadingConfirmed\(item\)/);
  assert.match(app, /A testar agora uma leitura real na LAN/);
  assert.match(app, /Configuração guardada, mas a leitura LAN falhou/);
  assert.match(app, /function renderTuyaDeviceCards\(devices\)/);
  assert.match(app, /tuya-read-state/);
  assert.match(app, /confirmed\?'Confirmado':'Por confirmar'/);
  assert.match(app, /const ordered=\[\.\.\.devices\]\.sort/);
  assert.match(app, /tuya-device-list[\s\S]*?addEventListener\("keydown"/);
});

test("Devices inventory refreshes cached live Tuya state each second and places power before voltage", () => {
  assert.match(app, /async function refreshTuyaInventoryStatus\(\)/);
  assert.match(app, /setInterval\(\(\) => \{ void refreshTuyaInventoryStatus\(\); \},1_000\)/);
  assert.match(app, /!\[\"devices\",\"inicio\"\]\.includes\(state\.page\)/);
  assert.match(app, /function tuyaCachedReadings\(devices\)/);
  assert.match(app, /const changed=signature!==state\.tuyaInventorySignature/);
  assert.match(app, /current_connection_state===\"local_responded\"&&device\.local_control_state===\"ready\"/);
  assert.match(app, /metrics\.find\(metric=>metric\.label===\"Potência\"\),voltage=metrics\.find\(metric=>metric\.label===\"Tensão\"\)/);
  assert.match(app, /class=\"inventory-device-metrics\"><span>\$\{power\?/);
  assert.match(app, /if\(reading\?\.connection_state!==\"local_responded\"\)return \[\]/);
});

test("Devices inventory waits to distinguish a single card click from a double click on the name", () => {
  assert.match(app, /let inventoryCardClickTimer = null/);
  assert.match(app, /inventoryCardClickTimer=setTimeout\(\(\)=>\{inventoryCardClickTimer=null;openFavoriteDeviceDetails\(deviceId,"tuya"\);\},280\)/);
  assert.match(app, /addEventListener\("dblclick",event=>\{const name=event\.target\.closest\("\[data-device-name\]"\);if\(!name\)return;clearTimeout\(inventoryCardClickTimer\);inventoryCardClickTimer=null/);
});

test("Tuya editor distinguishes a confirmed save from a failed follow-up LAN test", () => {
  assert.match(app, /Falha ao guardar no Gateway: \$\{error\.message\}/);
  assert.match(app, /Configuração guardada, mas a leitura LAN falhou/);
  assert.match(app, /const \{reading,result\}=await testTuyaLanDevice\(device\.device_id\)/);
});

test("Tuya connection test keeps the fresh status response and reports latency without assuming a switch", () => {
  const handler=app.match(/const inventoryRead=event\.target\.closest\("\[data-inventory-read\]"\);[\s\S]*?const inventoryToggle=/)?.[0]||"";
  assert.match(handler, /testTuyaLanDevice\(id\)/);
  assert.match(handler, /state\.tuyaReadings=.*reading/);
  assert.doesNotMatch(handler, /refreshHardwareIntegrationConfig/);
  assert.match(app, /Ligação LAN confirmada · \$\{result\.success_count\}\/\$\{result\.rounds\} respostas · média \$\{result\.average_latency_ms\} ms/);
  assert.match(app, /async function testTuyaLanDevice\(deviceId\)[\s\S]*?runGatewayTuyaLanDiagnostics\(3,deviceId\)/);
  assert.match(app, /Online na Tuya · sem resposta LAN/);
});

test("Tuya device switch is updated only after a fresh LAN status confirms the requested state", () => {
  assert.match(app, /const result = await controlGatewayTuyaSwitch\(deviceId, on\);[\s\S]*?const \{reading\}=await testTuyaLanDevice\(deviceId\);[\s\S]*?reading\.status\.find\(item=>item\.code===code\)\?\.value!==on/);
  assert.match(app, /inventoryToggle[\s\S]*?testTuyaLanDevice\(device\.device_id\)[\s\S]*?controlGatewayTuyaSwitch\(device\.device_id,!observed,code\)/);
  assert.match(app, /inventory-device-icon/);
});

test("LAN discovery tries the local neighbor cache after broadcast errors", () => {
  assert.match(gatewayApp, /trying neighbor cache/);
  assert.match(gatewayApp, /neighbor_cache_empty/);
  assert.match(workflow, /0\.6\.58 0\.6\.59 0\.6\.60 0\.6\.61 0\.6\.62/);
});

test("USB release rollback verification includes the installed Gateway release", () => {
  const rollbackLoops = workflow.match(/for VERSION in[^\n]+/g) || [];
  assert.equal(rollbackLoops.length, 2);
  for (const loop of rollbackLoops) assert.match(loop, /0\.6\.111 0\.6\.112; do/);
});
