import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const gatewayApp = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/app.py", import.meta.url), "utf8");
const energyEngine = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/energy_engine.py", import.meta.url), "utf8");
const workflow = readFileSync(new URL("../../.github/workflows/gateway-release.yml", import.meta.url), "utf8");

test("Tuya LAN report exposes the saved target and key presence without the key", () => {
  assert.match(gatewayApp, /"local_ip": item\.get\("local_ip", ""\)/);
  assert.match(gatewayApp, /"local_key_configured": bool\(item\.get\("local_key"\)\)/);
  assert.match(app, /IP guardado/);
  assert.match(app, /local_key_configured\?"Configurada":"Em falta"/);
});

test("Huawei modem tools live in their own Owner tab, outside Tuya settings", () => {
  assert.match(html, /data-owner-tab="modem"[^>]*>Modem<\/button>/);
  assert.match(html, /data-owner-panel="modem" id="gateway-modem-management"/);
  const tuyaPanel = html.match(/<fieldset class="device-card" data-device-panel="tuya"[\s\S]*?<\/fieldset>/)?.[0] || "";
  const modemPanel = html.match(/<section class="panel gateway-auth-panel owner-tab-panel" data-owner-panel="modem"[\s\S]*?<\/section>/)?.[0] || "";
  assert.ok(tuyaPanel);
  assert.ok(modemPanel);
  assert.doesNotMatch(tuyaPanel, /huawei-router-(?:host|password|save|read|status)/);
  assert.match(modemPanel, /huawei-router-(?:host|password|save|read|status)/);
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

test("Favorite commands use the cached state and never trigger a LAN read", () => {
  assert.match(app, /const live=state\.tuyaReadings\.find\(item=>item\.device_id===deviceId\),current=device\?tuyaSwitchState\(device,live,code\):undefined/);
  assert.match(app, /sendTuyaSwitchCommand\(device,code,!current\)/);
  assert.doesNotMatch(app, /beforeProbe=await testTuyaLanDevice/);
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

test("Devices inventory uses the latest Gateway reading instead of stale LAN probes and places power before voltage", () => {
  assert.match(app, /async function refreshTuyaInventoryStatus\(\)/);
  assert.match(app, /setInterval\(\(\) => \{ void refreshTuyaInventoryStatus\(\); \},1_500\)/);
  assert.match(app, /!\[\"devices\",\"inicio\"\]\.includes\(state\.page\)/);
  assert.match(app, /function tuyaCachedReadings\(devices\)/);
  assert.match(app, /function tuyaReadingsFromConfig\(devices\)\{[\s\S]*?return tuyaCachedReadings\(devices\);/);
  assert.doesNotMatch(app, /tuyaReadingsFromConfig\(devices\)\{[^}]*lan_probe/);
  assert.match(app, /state\.tuyaReadings=readings/);
  assert.match(app, /const changed=changedSet\.size>0/);
  assert.match(app, /function tuyaDeviceState\(device,reading\)\{[\s\S]*?if\(typeof value==="boolean"\)return value\?"Ligado":"Desligado";[\s\S]*?if\(reading\?\.connection_state==="failed"\)/);
  assert.match(app, /current_connection_state===\"local_responded\"&&device\.local_control_state===\"ready\"/);
  assert.match(app, /metrics\.find\(metric=>metric\.label===\"Potência\"\),voltage=metrics\.find\(metric=>metric\.label===\"Tensão\"\)/);
  assert.match(app, /class="inventory-device-metrics"><span>/);
  assert.match(app, /if\(reading\?\.connection_state!==\"local_responded\"\)return \[\]/);
});

test("The per-device LAN button only checks TCP reachability and never reads DPS", () => {
  const handler = app.match(/if \(read\) \{([\s\S]*?)\} else if \(toggle\)/)?.[1] || "";
  assert.match(handler, /testTuyaLanReachability\(id\)/);
  assert.doesNotMatch(handler, /testTuyaLanDevice\(id\)|runGatewayTuyaLanDiagnostics/);
  assert.match(handler, /sem leitura DPS/);
  assert.match(app, /data-tuya-detail-read-status[\s\S]*?testTuyaLanDevice\(deviceId\)/);
});

test("PV string and AQS dialogs intercept native form submits before the browser can reset the page", () => {
  assert.match(app, /pvStringForm\?\.addEventListener\("submit",event=>\{event\.preventDefault\(\);event\.stopImmediatePropagation\(\);void savePvStringForm\(pvStringForm\);\}\)/);
  assert.match(app, /aqsForm\?\.addEventListener\("submit",event=>\{event\.preventDefault\(\);event\.stopImmediatePropagation\(\);void saveAqsForm\(aqsForm\);\}\)/);
  assert.doesNotMatch(app, /e\.target\.id === "pv-string-form"/);
  assert.doesNotMatch(app, /e\.target\.id === "aqs-form"/);
});

test("Devices navigation is immediate and background inventory refreshes patch only changed device cards", () => {
  assert.match(app, /enteringDevices=page==="devices"&&state\.page!=="devices"/);
  assert.match(app, /if\(enteringDevices&&sessionInfo\(\)\.user\?\.role==="owner"\)void refreshTuyaInventoryStatus\(\)/);
  assert.match(app, /window\.scrollTo\(\{top:0,behavior:"auto"\}\)/);
  assert.match(app, /if\(changed&&\["devices","inicio"\]\.includes\(state\.page\)\)changedSet\.forEach\(deviceId=>\{updateVisibleTuyaCard\(deviceId\);updateOpenTuyaDeviceDialog\(deviceId\);\}\)/);
  assert.match(app, /current\.replaceWith\(updated\)/);
  assert.match(app, /favoriteControlPending\.delete\(deviceId\);updateVisibleTuyaCard\(deviceId\)/);
  assert.doesNotMatch(app, /state\.page==="energia"\s*\|\|\s*!Number\.isFinite\(lastRefresh\)/);
  assert.match(app, /const readingByDevice=new Map\(readings\.map\(reading=>\[reading\.device_id,reading\]\)\)/);
  assert.match(app, /catch \(error\) \{\s*console\.error\(`Could not render SolarMiner page: \$\{state\.page\}`/);
  assert.match(app, /<h2>Não foi possível abrir esta área<\/h2>/);
});

test("Devices inventory waits to distinguish a single card click from a double click on the name", () => {
  assert.match(app, /let inventoryCardClickTimer = null/);
  assert.match(app, /inventoryCardClickTimer=setTimeout\(\(\)=>\{inventoryCardClickTimer=null;openFavoriteDeviceDetails\(deviceId,"tuya"\);\},280\)/);
  assert.match(app, /addEventListener\("dblclick",event=>\{const card=event\.target\.closest\("\[data-inventory-device\]"\);if\(!card\|\|!event\.target\.closest\("\.favorite-device-info"\)\)return/);
});

test("Favorite card render retains the switch code list for its controls", () => {
  assert.match(app, /return \{id,kind,device,details,status,codes,channels,isLevel,percent\}/);
  assert.match(app, /rows\.map\(\(\{id,kind,device,details,status,codes,channels,isLevel,percent,reading\}\)=>/);
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

test("Tuya LAN reachability stays distinct from DPS reads and unknown switches remain actionable", () => {
  assert.match(app, /status_read:false,dps_read:false,cloud_requested:false/);
  assert.match(app, /data-tuya-detail-read-status>Ler estado DPS local/);
  assert.match(app, /estado por confirmar no varrimento/);
  assert.match(app, /data-tuya-quick-toggle=.*?sessionInfo\(\)\.user\?\.role!=="owner"\?"disabled":""/);
  assert.match(app, /if\(typeof current!=="boolean"\)throw new Error\("Ainda não há estado ON\/OFF confirmado pelo varrimento independente\."\)/);
});

test("Tuya cards mirror the Home layout and expose schema-driven quick controls", () => {
  assert.match(app, /data-favorite-expand=/);
  assert.match(app, /data-inventory-expand=/);
  assert.match(app, /function openTuyaQuickControls\(device\)/);
  assert.match(app, /function tuyaSwitchCodes\(device\)/);
  assert.match(app, /data-tuya-setting=/);
  assert.match(app, /data-tuya-channel-label=/);
});

test("Tuya state uses the product DPS catalog and breaker menu tolerates optional controls", () => {
  assert.match(app, /function tuyaSpecDpsId\(device,spec\)[\s\S]*?device\?\.product_profile\?\.dps/);
  assert.match(app, /status\.find\(item=>Number\(item\?\.dps_id\?\?item\?\.dp_id\)===dpId/);
  assert.ok(app.includes("const quickEditable=breaker?[...(breakerCountdown?[breakerCountdown]:[]),...breakerLocks]"));
  assert.match(app, /data-inventory-expand/);
});

test("Tuya engine readings update open device popups without a page refresh", () => {
  assert.match(app, /changedSet\.forEach\(deviceId=>\{updateVisibleTuyaCard\(deviceId\);updateOpenTuyaDeviceDialog\(deviceId\);\}\)/);
  assert.match(app, /function updateOpenTuyaDeviceDialog\(deviceId\)[\s\S]*?tuyaSwitchState\(device,reading,code\)/);
  assert.match(app, /dialog\.dataset\.tuyaDeviceId=device\.device_id/);
  assert.match(app, /currentReading=state\.tuyaReadings\.find\(item=>item\.device_id===device\.device_id\)/);
  assert.match(app, /pendingTuyaSwitchStates\.set\(/);
  assert.match(app, /function settlePendingTuyaSwitchStates\(devices,readings\)/);
  assert.match(app, /typeof observed==="boolean"&&observed===pending\.value/);
  assert.match(app, /tuyaSwitchState\(device,reading,code\)[\s\S]*?if\(pending\)return pending\.value/);
});

test("Devices inventory tolerates missing optional Tuya arrays", () => {
  assert.match(app, /function normalizeTuyaInventoryDevice\(device\)/);
  assert.match(app, /function normalizeTuyaInventory\(devices\)/);
  assert.match(app, /function normalizeTuyaReading\(reading\)/);
  assert.match(app, /devices=normalizeTuyaInventory\(state\.tuyaDevices\)/);
  assert.match(app, /map\(normalizeTuyaReading\)\.filter\(Boolean\)/);
  assert.match(app, /normalizeTuyaInventory\(hardware\.tuya\?\.devices\)/);
  assert.match(app, /functions:objectRows\(device\.functions\),status_spec:objectRows\(device\.status_spec\),current_status:objectRows\(device\.current_status\)/);
  assert.match(app, /Array\.isArray\(state\.tuyaReadings\)\?state\.tuyaReadings:\[\]/);
  assert.match(app, /Array\.isArray\(device\?\.functions\)/);
  assert.match(app, /Array\.isArray\(reading\?\.status\)/);
  assert.match(app, /status\.filter\(item=>item&&typeof item==="object"\)/);
  assert.match(app, /\.filter\(item=>item&&\["bool","boolean"\]/);
});

test("Tuya commands do not trigger reads before or after writing", () => {
  assert.match(app, /async function sendTuyaSwitchCommand\(device,code,desired\)\{[\s\S]*?controlGatewayTuyaSwitch\(device\.device_id,desired,code\)/);
  assert.doesNotMatch(app, /async function sendTuyaSwitchCommand\(device,code,desired\)\{[^}]*testTuyaLanDevice/);
  assert.match(app, /inventoryToggle[\s\S]*?live=state\.tuyaReadings\.find\(item=>item\.device_id===device\.device_id\)[\s\S]*?sendTuyaSwitchCommand\(device,code,!observed\)/);
  assert.doesNotMatch(app, /inventoryToggle[\s\S]*?testTuyaLanDevice\(device\.device_id\)/);
  assert.match(app, /Ordem enviada\. O estado será atualizado pelo próximo varrimento LAN\./);
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
for (const loop of rollbackLoops) assert.match(loop, /0\.6\.112 0\.6\.113 0\.6\.114 0\.6\.115 0\.6\.116 0\.6\.117 0\.6\.118 0\.6\.119 0\.6\.120 0\.6\.121 0\.6\.122 0\.6\.123 0\.6\.124 0\.6\.125 0\.6\.126 0\.6\.127 0\.6\.128 0\.6\.129 0\.6\.130 0\.6\.131 0\.6\.132 0\.6\.133 0\.6\.134 0\.6\.135; do/);
});

