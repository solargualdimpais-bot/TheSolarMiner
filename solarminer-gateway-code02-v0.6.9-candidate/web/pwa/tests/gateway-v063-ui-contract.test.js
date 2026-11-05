import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const gatewayApp = readFileSync(new URL("../../../src/solarminer_gateway/app.py", import.meta.url), "utf8");
const energyEngine = readFileSync(new URL("../../../src/solarminer_gateway/energy_engine.py", import.meta.url), "utf8");
const gatewayBuild = readFileSync(new URL("../../../packaging/build-deb.sh", import.meta.url), "utf8");
const workflow = readFileSync(new URL("../../../../.github/workflows/gateway-release.yml", import.meta.url), "utf8");

test("Tuya LAN report exposes the saved target and key presence without the key", () => {
  assert.match(gatewayApp, /"local_ip": item\.get\("local_ip", ""\)/);
  assert.match(gatewayApp, /"local_key_configured": bool\(item\.get\("local_key"\)\)/);
  assert.match(gatewayApp, /"ip_refreshed_by_mac": any\(row\.get\("ip_refreshed_by_mac"\) for row in rows\)/);
  assert.match(gatewayApp, /"ip_cleared_missing_mac": any\(row\.get\("ip_cleared_missing_mac"\) for row in rows\)/);
  assert.match(app, /IP guardado/);
  assert.match(app, /Atualizado pelo MAC/);
  assert.match(app, /Removido: MAC ausente/);
  assert.match(app, /local_key_configured\?"Configurada":"Em falta"/);
});

test("Tuya LAN recovery requires an exact unique MAC match and refreshes only after a failed read", () => {
  const integrations = readFileSync(new URL("../../../src/solarminer_gateway/integrations.py", import.meta.url), "utf8");
  assert.match(integrations, /failed_indexes[\s\S]*_tuya_scan_local_ips_by_mac\(refresh=True\)/);
  assert.match(integrations, /by_mac = \{mac: next\(iter\(ips\)\) for mac, ips in candidates\.items\(\) if len\(ips\) == 1\}/);
  assert.match(integrations, /tuya_local_ip_not_found_for_mac/);
  assert.match(integrations, /device\.pop\("local_ip", None\)/);
});

test("Modem tab hosts the local LAN scanner without restoring modem APIs", () => {
  assert.match(html, /data-owner-tab="modem"[^>]*>Modem<\/button>/);
  assert.match(html, /data-owner-panel="modem" id="gateway-modem-management"/);
  const tuyaPanel = html.match(/<fieldset class="device-card" data-device-panel="tuya"[\s\S]*?<\/fieldset>/)?.[0] || "";
  const modemPanel = html.match(/<section class="panel gateway-auth-panel owner-tab-panel" data-owner-panel="modem"[\s\S]*?<\/section>/)?.[0] || "";
  assert.ok(tuyaPanel);
  assert.ok(modemPanel);
  assert.doesNotMatch(tuyaPanel, /huawei|modem/i);
  assert.match(modemPanel, /id="local-network-scan"/);
  assert.doesNotMatch(modemPanel, /local-network-apply|Guardar IPs dos devices reconhecidos/);
  assert.match(modemPanel, /id="local-network-results"/);
  assert.doesNotMatch(`${modemPanel}\n${app}`, /huawei|Pesquisar modem/i);
  assert.doesNotMatch(gatewayApp, /@app\.post\("\/api\/v1\/integrations\/huawei\/(?:clients|probe|client-label)/);
  assert.match(gatewayApp, /@app\.post\("\/api\/v1\/network\/scan"\)/);
  assert.match(gatewayApp, /@app\.post\("\/api\/v1\/network\/scan\/apply"\)/);
  assert.match(app, /configured_ip_update_count/);
  assert.match(app, /dispositivos que responderam/);
  assert.match(app, /Router de saída indicado pela rota/);
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

test("Tesla Fleet credentials live under Owner equipment while EV shows reads and local presence", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.match(html, /data-owner-device="tesla"[^>]*>Tesla Fleet/);
  assert.match(html, /data-device-panel="tesla"[\s\S]*?id="ev-tesla-refresh-token"/);
  assert.match(html, /id="ev-tesla-fleet-save"/);
  assert.match(html, /id="ev-tesla-local-mac"/);
  assert.match(app, /function renderEvSection\(config,isOwner\)/);
  assert.match(app, /Owner → Equipamentos → Tesla Fleet/);
  for (const id of ["ev-tesla-read", "ev-tesla-presence", "ev-tesla-read-status"]) assert.ok(app.includes('id="' + id + '"'), 'missing ' + id);
  assert.match(app, /page==="ev"\?renderEvSection\(config,isOwner\)/);
});

test("Tesla Fleet save is handled by the static Owner panel, reports outcomes, and refreshes MAC inventory", () => {
  assert.match(app, /document\.querySelector\("#gateway-hardware-management"\)\?\.addEventListener\("click"/);
  assert.match(app, /event\.target\.closest\("#ev-tesla-fleet-save"\)/);
  assert.match(app, /A guardar a configuração Fleet e a associar o MAC ao inventário/);
  assert.match(app, /Não foi possível guardar a ligação Tesla Fleet/);
  assert.match(app, /Configuração guardada, mas o teste Fleet falhou/);
  assert.match(app, /readGatewayDeviceInventory\(\)/);
  assert.match(app, /readGatewayTeslaEvCharging\(\)/);
  assert.match(app, /MAC foi guardado/);
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
  assert.match(app, /if\(enteringDevices&&sessionInfo\(\)\.user\?\.role==="owner"\)\{refreshGatewayReadings\(\);void refreshTuyaInventoryStatus\(\);void refreshShellyInventoryStatus\(\{quiet:true\}\);void refreshSmartProductCatalog\(\);\}/);
  assert.match(app, /window\.scrollTo\(\{top:0,behavior:"auto"\}\)/);
  assert.match(app, /if\(changed&&\["devices","inicio"\]\.includes\(state\.page\)\)changedSet\.forEach\(deviceId=>\{updateVisibleTuyaCard\(deviceId\);updateOpenTuyaDeviceDialog\(deviceId\);\}\)/);
  assert.match(app, /current\.replaceWith\(updated\)/);
  assert.match(app, /favoriteControlPending\.delete\(deviceId\);document\.querySelectorAll\(`\[data-favorite-toggle=/);
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
  assert.match(app, /if\(observed!==pending\.value\)[\s\S]*?Falha ao confirmar a ordem/);
  assert.match(app, /async function sendTuyaSwitchCommand\(device,code,desired\)\{[\s\S]*?pendingTuyaSwitchStates\.set\([\s\S]*?updateVisibleTuyaCard\(device\.device_id\);updateOpenTuyaDeviceDialog\(device\.device_id\);[\s\S]*?await controlGatewayTuyaSwitch/);
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

test("Gateway release package embeds the PWA and optional Tesla relay environment", () => {
  const service = readFileSync(new URL("../../../packaging/solarminer-gateway.service", import.meta.url), "utf8");
  assert.ok(service.includes('EnvironmentFile=-/etc/solarminer/tesla-relay.env'));
  assert.ok(gatewayBuild.includes('cp -R "$ROOT/web/pwa/." "$STAGE/usr/share/solarminer/pwa/'));
});

test("USB release rollback verification includes prior Gateway releases", () => {
  const rollbackLoops = [...workflow.matchAll(/for VERSION in([\s\S]*?); do/g)]
    .map(match => match[0].replace(/\\\s*\n\s*/g, " "));
  assert.equal(rollbackLoops.length, 2);
  for (const loop of rollbackLoops) {
    assert.match(loop, /0\.6\.112 0\.6\.113 0\.6\.114 0\.6\.115 0\.6\.116 0\.6\.117 0\.6\.118 0\.6\.119 0\.6\.120 0\.6\.121 0\.6\.122 0\.6\.123 0\.6\.124 0\.6\.125 0\.6\.126 0\.6\.127 0\.6\.128 0\.6\.129 0\.6\.130 0\.6\.131 0\.6\.132 0\.6\.133 0\.6\.134 0\.6\.135/);
  assert.match(loop, /0\.6\.139 0\.6\.140 0\.6\.141 0\.6\.142 0\.6\.143 0\.6\.145 0\.6\.146 0\.6\.147 0\.6\.148 0\.6\.149 0\.6\.150 0\.6\.151 0\.6\.152 0\.6\.153 0\.6\.154 0\.6\.155 0\.6\.156 0\.6\.157 0\.6\.158 0\.6\.159 0\.6\.160 0\.6\.161 0\.6\.162 0\.6\.163 0\.6\.164 0\.6\.165 0\.6\.166 0\.6\.169 0\.6\.171 0\.6\.172 0\.6\.173 0\.6\.174 0\.6\.175 0\.6\.176 0\.6\.177 0\.6\.188 0\.6\.189; do/);
  }
});
