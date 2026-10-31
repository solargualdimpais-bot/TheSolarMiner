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
  assert.match(app, /const current=await readGatewayEnergyEngineConfig\(\);\s*const strings=Array\.isArray\(current\?\.pv_strings\)\?\[\.\.\.current\.pv_strings\]:\[\]/);
  assert.match(app, /const index=strings\.findIndex\(item=>item\.id===id\)/);
  assert.match(app, /const saved=await readGatewayEnergyEngineConfig\(\)/);
  assert.match(app, /const savedStrings=Array\.isArray\(saved\?\.pv_strings\)/);
  assert.match(app, /pvStringForm\?\.addEventListener\("submit",event=>\{event\.preventDefault\(\);event\.stopImmediatePropagation\(\);void savePvStringForm\(pvStringForm\);\}\)/);
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
  assert.match(app, /const beforeProbe=await testTuyaLanDevice\(deviceId\),before=beforeProbe\.reading/);
  assert.match(app, /controlGatewayTuyaSwitch\(deviceId,desired,code\)/);
  assert.match(app, /const afterProbe=await testTuyaLanDevice\(deviceId\),after=afterProbe\.reading/);
  assert.match(app, /openFavoriteDeviceDetails\(favoriteCard\.dataset\.favoriteDevice,favoriteCard\.dataset\.deviceKind\)/);
  assert.match(app, /function openFavoriteDeviceDetails\(deviceId,kind\)/);
  assert.match(app, /function tuyaSimpleReadings\(device,reading\)/);
  assert.match(app, /function favoriteReadingConfirmed\(item\)/);
  assert.match(app, /A testar apenas a resposta na LAN/);
  assert.match(app, /Configuração guardada, mas sem resposta LAN/);
  assert.match(app, /function renderTuyaDeviceCards\(devices\)/);
  assert.match(app, /tuya-read-state/);
  assert.match(app, /confirmed\?'Confirmado':'Por confirmar'/);
  assert.match(app, /const ordered=\[\.\.\.devices\]\.sort/);
  assert.match(app, /tuya-device-list[\s\S]*?addEventListener\("keydown"/);
});

test("Devices inventory preserves explicit LAN readings across cache refreshes and places power before voltage", () => {
  assert.match(app, /async function refreshTuyaInventoryStatus\(\)/);
  assert.match(app, /setInterval\(\(\) => \{ void refreshTuyaInventoryStatus\(\); \},10_000\)/);
  assert.match(app, /!\[\"devices\",\"inicio\"\]\.includes\(state\.page\)/);
  assert.match(app, /function tuyaCachedReadings\(devices\)/);
  assert.match(app, /function tuyaReadingsFromConfig\(devices\)[\s\S]*?lan_probe===true/);
  assert.match(app, /tuyaReadings=tuyaReadingsFromConfig\(state\.tuyaDevices\)/);
  assert.match(app, /const changed=signature!==state\.tuyaInventorySignature/);
  assert.match(app, /current_connection_state===\"local_responded\"&&device\.local_control_state===\"ready\"/);
  assert.match(app, /metrics\.find\(metric=>metric\.label===\"Potência\"\),voltage=metrics\.find\(metric=>metric\.label===\"Tensão\"\)/);
  assert.match(app, /class="inventory-device-metrics"><span>/);
  assert.match(app, /if\(reading\?\.connection_state!==\"local_responded\"\)return \[\]/);
});

test("PV string and AQS dialogs intercept native form submits before the browser can reset the page", () => {
  assert.match(app, /pvStringForm\?\.addEventListener\("submit",event=>\{event\.preventDefault\(\);event\.stopImmediatePropagation\(\);void savePvStringForm\(pvStringForm\);\}\)/);
  assert.match(app, /aqsForm\?\.addEventListener\("submit",event=>\{event\.preventDefault\(\);event\.stopImmediatePropagation\(\);void saveAqsForm\(aqsForm\);\}\)/);
  assert.doesNotMatch(app, /e\.target\.id === "pv-string-form"/);
  assert.doesNotMatch(app, /e\.target\.id === "aqs-form"/);
});

test("Devices navigation is immediate and background inventory refreshes do not redraw another page", () => {
  assert.match(app, /enteringDevices=page==="devices"&&state\.page!=="devices"/);
  assert.match(app, /if\(enteringDevices&&sessionInfo\(\)\.user\?\.role==="owner"\)void refreshTuyaInventoryStatus\(\)/);
  assert.match(app, /window\.scrollTo\(\{top:0,behavior:"auto"\}\)/);
  assert.match(app, /if\(changed&&\["devices","inicio"\]\.includes\(state\.page\)\)renderAfterLiveRefresh\(\)/);
  assert.doesNotMatch(app, /state\.page==="energia"\s*\|\|\s*!Number\.isFinite\(lastRefresh\)/);
  assert.match(app, /const readingByDevice=new Map\(readings\.map\(reading=>\[reading\.device_id,reading\]\)\)/);
});

test("Devices inventory waits to distinguish a single card click from a double click on the name", () => {
  assert.match(app, /let inventoryCardClickTimer = null/);
  assert.match(app, /inventoryCardClickTimer=setTimeout\(\(\)=>\{inventoryCardClickTimer=null;openFavoriteDeviceDetails\(deviceId,"tuya"\);\},280\)/);
  assert.match(app, /addEventListener\("dblclick",event=>\{const card=event\.target\.closest\("\[data-inventory-device\]"\);if\(!card\|\|!event\.target\.closest\("\.favorite-device-info"\)\)return/);
});

test("Favorite card render retains the switch code list for its controls", () => {
  assert.match(app, /return \{id,kind,device,details,status,codes,channels,isLevel,percent\}/);
  assert.match(app, /tuyaPrimarySwitchCode\(device,codes\)/);
  assert.match(app, /let probe;try\{probe=await testTuyaLanReachability\(deviceId\);\}catch\(error\)\{statusNode\.textContent=`Teste LAN falhou: \$\{error\.message\}`/);
  assert.match(app, /A resposta LAN foi recebida; houve uma falha ao atualizar o cartão/);
});

test("Tuya setting writes require a known local datapoint mapping", () => {
  assert.match(app, /localDpsMapped=Boolean\(device\.local_dps_map\?\.\[spec\.code\]\)/);
  assert.match(app, /tuyaUnmappedSettingChange\(editable,inputs\)/);
  assert.match(app, /Não foi enviado qualquer comando: a função \$\{unmapped\.code\} precisa do DPS local correto/);
});

test("Tuya editor distinguishes a confirmed save from a failed follow-up LAN test", () => {
  assert.match(app, /Falha ao guardar no Gateway: \$\{error\.message\}/);
  assert.match(app, /Configuração guardada, mas sem resposta LAN/);
  assert.match(app, /const \{reading,result\}=await testTuyaLanReachability\(device\.device_id\)/);
});

test("Tuya save and manual re-test use only basic LAN reachability, and closed Tuya ports stay unconfirmed", () => {
  assert.match(app, /async function testTuyaLanReachability\(deviceId\)[\s\S]*?cloud_requested:false/);
  assert.match(app, /data-tuya-detail-read/);
  assert.match(app, /testTuyaLanReachability\(deviceId\)/);
  assert.match(app, /tuyaReadingConfirmed\(reading\)\{return Boolean\(reading&&\["local_responded","lan_reachable"\]\.includes\(reading\.connection_state\)\);\}/);
  assert.doesNotMatch(app, /tuyaReadingConfirmed\(reading\)\{return Boolean\(reading&&\["local_responded","lan_reachable","lan_host_responded"\]/);
});

test("Tuya cards mirror the Home layout and expose schema-driven quick controls", () => {
  assert.match(app, /data-favorite-expand=/);
  assert.match(app, /data-inventory-expand=/);
  assert.match(app, /function openTuyaQuickControls\(device\)/);
  assert.match(app, /function tuyaSwitchCodes\(device\)/);
  assert.match(app, /data-tuya-setting=/);
  assert.match(app, /data-tuya-channel-label=/);
});

test("Devices inventory tolerates missing optional Tuya arrays", () => {
  assert.match(app, /devices=Array\.isArray\(state\.tuyaDevices\)/);
  assert.match(app, /readings=Array\.isArray\(state\.tuyaReadings\)/);
  assert.match(app, /Array\.isArray\(device\?\.functions\)/);
  assert.match(app, /Array\.isArray\(reading\?\.status\)/);
});

test("Tuya device switch is updated only after a fresh LAN status confirms the requested state", () => {
  assert.match(app, /const result = await controlGatewayTuyaSwitch\(deviceId, on\);[\s\S]*?const \{reading\}=await testTuyaLanDevice\(deviceId\);[\s\S]*?reading\.status\.find\(item=>item\.code===code\)\?\.value!==on/);
  assert.match(app, /inventoryToggle[\s\S]*?testTuyaLanDevice\(device\.device_id\)[\s\S]*?controlGatewayTuyaSwitch\(device\.device_id,!observed,code\)/);
  assert.match(app, /device-inventory-content home-favorites/);
});

test("LAN discovery tries the local neighbor cache after broadcast errors", () => {
  assert.match(gatewayApp, /trying neighbor cache/);
  assert.match(gatewayApp, /neighbor_cache_empty/);
  assert.match(workflow, /0\.6\.58 0\.6\.59 0\.6\.60 0\.6\.61 0\.6\.62/);
});

test("USB release rollback verification includes the installed Gateway release", () => {
  const rollbackLoops = workflow.match(/for VERSION in[^\n]+/g) || [];
  assert.equal(rollbackLoops.length, 2);
  for (const loop of rollbackLoops) assert.match(loop, /0\.6\.112 0\.6\.113 0\.6\.114 0\.6\.115 0\.6\.116; do/);
});

