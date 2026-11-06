import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = path => readFileSync(new URL(path, import.meta.url), "utf8");

test("Owner hardware setup includes the Tesla Fleet configuration beside Deye, Antminer and Tuya", () => {
  const html = read("../index.html");
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  for (const id of ["gateway-hardware-management", "hardware-deye-host", "hardware-antminer-host", "hardware-antminer-password", "hardware-antminer-rest-port", "hardware-tuya-client-secret", "hardware-tuya-uid", "deye-save", "deye-read", "antminer-save", "tuya-save", "tuya-sync", "tuya-device-list", "owner-open-gateway"]) assert.match(html, new RegExp(`id="${id}"`));
  for (const id of ["antminer-management-panel", "antminer-refresh-management", "antminer-management-output", "antminer-management-status", "antminer-management-diagnosis", "antminer-management-operation", "antminer-management-submit"]) assert.match(app, new RegExp(`id="${id}"`));
  assert.match(app, /antminerReadOperations=\[\[/);
  for (const operation of ["api_version", "details", "errors", "hashboards", "stats", "configuration", "constraints", "cooling", "network_details", "tuner", "performance_mode", "target_profiles", "efficiency_profile", "pools", "advanced_settings", "advanced_schema", "network", "auto_upgrade", "license", "locate_state"]) assert.match(app, new RegExp(String.raw`\["${operation}",`));
  assert.doesNotMatch(app.match(/const antminerReadOperations=\[\[([\s\S]*?)\];/)?.[0]||"", /\["power_target"/);
  assert.match(app, /const antminerReadCategories=\[\[[\s\S]*?\["Potência","ϟ",\["tuner"\]\]/);
  assert.match(app, /if\(operation==="tuner"\)\{[\s\S]*?Alvo do perfil[\s\S]*?Alvo ativo agora[\s\S]*?Hashrate médio[\s\S]*?Consumo estimado pelo tuner[\s\S]*?id="antminer-section-apply-watt"/);
  assert.match(app, /antminerWriteOperations=\[\[/);
  for (const operation of ["set_power_target", "power_target_default", "power_target_increment", "power_target_decrement", "power_target_relative", "set_hashrate_target", "hashrate_target_default", "hashrate_target_increment", "hashrate_target_decrement", "hashrate_target_relative", "performance_mode", "dps", "quick_ramping", "quick_ramping_default", "reset_tuned_profiles", "cooling_mode", "advanced_settings", "network", "hashboards", "auto_upgrade", "pools_batch", "create_pool_group", "update_pool_group", "delete_pool_group", "locate"]) assert.match(app, new RegExp(String.raw`\["${operation}",`));
  for (const operation of ["start", "resume", "pause", "stop", "restart", "reboot"]) assert.ok(app.includes(`data-antminer-write="${operation}"`));
  for (const operation of ["create_pool_group", "update_pool_group", "delete_pool_group"]) assert.ok(app.includes(`\["${operation}"`));
  assert.match(html, /data-page="mineradoras"/);
  assert.doesNotMatch(html, /id="antminer-(?:power-target|pause|stop|start|read|control-test)"/);
  assert.doesNotMatch(html, /antminer-control-test|Testar controlo sem alterar potência/);
  assert.doesNotMatch(html, /hardware-antminer-username/);
  assert.doesNotMatch(app, /hardware-antminer-username/);
  assert.match(app, /saveHardwareProvider\("antminer", \{ enabled: Boolean\(host\), host,/);
  for (const tab of ["access", "updates", "tailscale", "gateway", "equipment", "modem"]) assert.match(html, new RegExp(`data-owner-tab="${tab}"`));
  const modemPanel = html.match(/<section class="panel gateway-auth-panel owner-tab-panel" data-owner-panel="modem"[\s\S]*?<\/section>/)?.[0] || "";
  assert.match(modemPanel, /local-network-scan/);
  assert.match(modemPanel, /local-network-results/);
  assert.match(app, /interface_discovery_failed/);
  assert.match(app, /active_arp_unavailable/);
  assert.match(app, /ARP ativo/);
  assert.match(app, /SSDP\/UPnP/);
  assert.match(app, /mDNS\/DNS-SD/);
  assert.doesNotMatch(`${html}\n${app}\n${auth}`, /huawei|Pesquisar modem|integrations\/huawei/i);
  for (const tab of ["deye", "antminer", "tuya", "tesla"]) assert.match(html, new RegExp(`data-owner-device="${tab}"`));
  const workspace = read("../workspace-ui.js");
  for (const id of ["ev-tesla-refresh-token", "ev-tesla-vehicle-id", "ev-tesla-local-mac", "ev-tesla-save", "ev-tesla-presence", "ev-tesla-fleet-save", "ev-tesla-read"]) assert.match(workspace, new RegExp(`id="${id}"`));
  assert.match(app, /info\.user\.role !== "owner"/);
  assert.match(app, /saveGatewayHardwareIntegrationConfig/);
  assert.match(app, /readGatewayHardwareProvider/);
  assert.match(app, /telemetria confirmada em /i);
  assert.match(app, /hashing reportado/);
  assert.match(auth, /antminer_control_credentials_required/);
  assert.match(auth, /O teste de ligação é independente do controlo/);
  assert.match(app, /saveGatewayHardwareIntegrationConfig\(\{ \[provider\]: payload \}\)/);
  assert.match(app, /hardware-tuya-client-secret"\)\.value = ""/);
  assert.match(auth, /\/api\/v1\/integrations\/hardware\/\$\{provider\}\/read/);
  assert.match(auth, /\/api\/v1\/integrations\/antminer\/control/);
  assert.match(auth, /\/api\/v1\/integrations\/antminer\/management/);
  assert.match(app, /readGatewayAntminerManagement/);
  assert.match(app, /writeGatewayAntminerManagement/);
  assert.match(app, /testGatewayAntminerControl\(\)/);
  assert.match(app, /accepted_shares/);
  assert.match(app, /não reporta shares aceites/);
  assert.match(app, /Ler estado completo/);
  assert.match(auth, /\/api\/v1\/integrations\/tuya\/level/);
  assert.match(auth, /\/api\/v1\/integrations\/tuya\/sync/);
  assert.match(app, /syncGatewayTuyaDevices/);
  assert.match(app, /controlGatewayTuyaLevel/);
  assert.match(app, /data-favorite-level/);
  assert.match(auth, /"set_power_target", "pause", "stop", "start"/);
  assert.match(app, /confirmAntminerAction\(/);
  assert.match(app, /runAntminerAction\(/);
  assert.match(app, /A enviar o comando através do Gateway e a aguardar a resposta da Braiins OS/);
  assert.ok(app.includes("updateOperationDialog({title:`${title} · falhou`"));
  assert.match(auth, /\/api\/v1\/energy\/ev\/tesla\/read/);
  assert.match(auth, /\/api\/v1\/energy\/ev\/tesla\/presence/);
  assert.match(auth, /\/api\/v1\/energy\/ev\/tesla\/oauth\/complete/);
  assert.match(auth, /saveGatewayTeslaRelay/);
  assert.match(auth, /\/api\/v1\/energy\/ev\/tesla\/relay/);
  assert.match(app, /completeGatewayTeslaOAuth/);
  assert.match(app, /Relay ligado e autenticado/);
  assert.match(app, /#ev-tesla-relay-key/);
  assert.match(app, /flow\.relay_mode/);
  assert.match(app, /config\.oauth_redirect_uri/);
  assert.match(app, /readGatewayTeslaLocalPresence/);
  assert.doesNotMatch(app, /hardware-tesla-(?:region|client-id|refresh-token|vehicles)/);
  assert.doesNotMatch(auth, /tuya.*localStorage/i);
});

test("Saving a Tuya device resolves missing LAN identity, then confirms first-time DPS; verified edits do not retest", () => {
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  const gateway = read("../../../src/solarminer_gateway/app.py");
  const integrations = read("../../../src/solarminer_gateway/integrations.py");
  assert.match(app, /async function testTuyaLanReachability\(deviceId\)[\s\S]*?testGatewayTuyaLanReachability\(deviceId\)/);
  assert.match(app, /if\(!requestedIp\|\|!requestedMac\)\{[\s\S]*?discoverGatewayTuyaLanDevices\(\)/);
  assert.match(app, /saveGatewayHardwareIntegrationConfig\(\{tuya:\{devices:next\}\}\)[\s\S]*?if\(previouslyVerified\)\{/);
  assert.match(app, /const report=await runGatewayTuyaLanDiagnostics\(1,device\.device_id\)/);
  assert.match(app, /Alterações guardadas\. A ligação local já estava confirmada; não repeti os testes\./);
  assert.match(auth, /\/api\/v1\/integrations\/tuya\/lan-reachability/);
  assert.match(gateway, /@app\.post\(\"\/api\/v1\/integrations\/tuya\/lan-reachability\"\)/);
  assert.match(gateway, /status_read\": False, \"dps_read\": False, \"cloud_requested\": False/);
  assert.match(integrations, /probe_tuya_lan_reachability\(host: str, timeout: float = 1\.0\)/);
  assert.match(integrations, /socket\.create_connection\(\(address, 6668\), timeout=timeout\)/);
});

test("Antminer power target prefers the active tuner target over the saved profile target", () => {
  const app = read("../app.js");
  const helper = app.match(/function antminerCurrentPowerTarget\(data\)\{[\s\S]*?\n\}/)?.[0];
  assert.ok(helper, "current-target parser exists");
  const parseTarget = new Function(`${helper}; return antminerCurrentPowerTarget;`)();
  assert.deepEqual(parseTarget({mode_state:{power_target_mode_state:{
    current_target:{watt:2500}, profile:{target:{watt:1900}},
  }}}), {current:2500, profile:1900});
  assert.deepEqual(parseTarget({modeState:{powerTargetModeState:{
    currentTarget:{watt:2400}, profile:{target:{watt:1900}},
  }}}), {current:2400, profile:1900});
});

test("Antminer power command result exposes Braiins-applied watts, including a clamp", () => {
  const app = read("../app.js");
  const helper = app.match(/function antminerSetPowerResponseWatt\(result\)\{[\s\S]*?\n\}/)?.[0];
  assert.ok(helper, "power-response parser exists");
  const parseWatt = new Function(`${helper}; return antminerSetPowerResponseWatt;`)();
  assert.equal(parseWatt({operation:"set_power_target", data:{watt:2000}}), 2000);
  assert.equal(parseWatt({operation:"set_power_target", data:{watt:2500}}), 2500);
  assert.equal(parseWatt({operation:"set_power_target", data:{watt:"not-a-wattage"}}), null);
});

test("periodic Gateway refresh preserves unrelated dialogs and patches Tuya control cards in place", () => {
  const app = read("../app.js");
  assert.match(app, /function renderAfterLiveRefresh\(\)\s*\{\s*const now=Date\.now\(\),recentIds=new Set/);
  assert.match(app, /if\(\(recentIds\.size\|\|activeDialog\)&&\["inicio","devices"\]\.includes\(state\.page\)\)/);
  assert.match(app, /if \(document\.querySelector\("dialog\[open\]"\)\) \{ state\.pendingLiveRender = true;/);
  assert.match(app, /document\.addEventListener\("close", \(\) => \{\s*if \(state\.pendingLiveRender && !document\.querySelector\("dialog\[open\]"\)\)/);
  assert.equal((app.match(/renderAfterLiveRefresh\(\);/g) || []).length, 2);
});

test("Deye Cloud history connection is configured by the Owner and runs only on explicit actions", () => {
  const html = read("../index.html");
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  for (const id of ["deye-cloud-center", "deye-cloud-app-id", "deye-cloud-app-secret", "deye-cloud-email", "deye-cloud-password", "deye-cloud-save", "deye-cloud-stations", "deye-cloud-station", "deye-cloud-import"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /id="deye-cloud-progress"[\s\S]*?<progress[^>]+Progresso da importação do histórico Deye/);
  assert.match(app, /if\(progress\)progress\.hidden=false/);
  assert.match(app, /if\(progress\)progress\.hidden=true/);
  assert.match(app, /A importação pode demorar alguns minutos/);
  assert.match(app, /\$\("#deye-cloud-save"\)\.addEventListener\("click"/);
  assert.match(app, /\$\("#deye-cloud-stations"\)\.addEventListener\("click"/);
  assert.match(app, /\$\("#deye-cloud-import"\)\.addEventListener\("click"/);
  assert.match(app, /\$\("#deye-cloud-app-secret"\)\.value="";\$\("#deye-cloud-password"\)\.value=""/);
  assert.match(auth, /\/api\/v1\/integrations\/deye-cloud\/stations/);
  assert.match(auth, /\/api\/v1\/integrations\/deye-cloud\/history\/import/);
  assert.match(auth, /async function importGatewayDeyeCloudHistory\(stationId, onProgress/);
  assert.match(auth, /history\/import\/\$\{encodeURIComponent\(job\.job_id\)\}/);
  assert.match(auth, /current\.status === "completed"/);
  assert.match(auth, /current\.status === "failed"/);
  assert.match(app, /importGatewayDeyeCloudHistory\(stationId,job=>\{if\(progressBar\)progressBar\.value=Number\(job\.progress\)\|\|0/);
  assert.match(html, /Importar histórico de 90 dias/);
});

test("Gateway terminal waits for server authentication and explains WebSocket failures", () => {
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  assert.match(auth, /\/api\/v1\/system\/terminal\/diagnostics/);
  assert.match(auth, /message\?\.type === "ready"/);
  assert.match(auth, /websocket_handshake_failed/);
  assert.match(app, /HTTPS do Tailscale não está pronto/);
  assert.match(app, /handshake WebSocket falhou/);
  assert.match(app, /appendGatewayTerminalOutput\(`\\r\\n\[Diagnóstico\]/);
});

test("Gateway terminal enables its input after authenticated readiness", () => {
  const app = read("../app.js");
  assert.match(app, /const socket = await openGatewayTerminalSocket\(\);\s*gatewayTerminalSocket = socket;[\s\S]{0,360}setGatewayTerminalConnected\(true\);\s*status\.textContent = "Terminal ligado ao Gateway\."/);
});

test("Owner DPS editor sends normalized characteristic, unit, and divisor to the Product ID map", () => {
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  assert.match(app, /Característica normalizada/);
  assert.match(app, /daily_accumulated_energy/);
  assert.match(app, /Informação descritiva · sem cálculo/);
  assert.match(app, /standardDpsLabels/);
  assert.match(app, /device\.product_profile\?\.normalized_characteristics/);
  assert.match(app, /updateCharacteristicUnits/);
  assert.match(app, /saveGatewayTuyaProductDpsDescription\(device\.device_id,dpsId,form\.elements\.description\.value,mapping\)/);
  assert.match(auth, /saveGatewayTuyaProductDpsDescription\(deviceId, dpsId, description, mapping = \{\}\)/);
  assert.match(auth, /body\.semantic_code = mapping\.semantic_code/);
  assert.match(auth, /body\.unit = mapping\.unit/);
  assert.match(auth, /body\.scale = mapping\.scale/);
});

test("Deye Cloud import explains HTTP 504 as a Gateway or proxy timeout", () => {
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  assert.match(app, /error\.status===504\?"O Gateway\/proxy expirou à espera da resposta da importação de 90 dias/);
  assert.match(auth, /deye_cloud_upstream_timeout:/);
});

test("live navigation renders Gateway data without the demo renderer overriding operational pages", () => {
  const app = read("../app.js");
  assert.match(app, /state\.mode!=="SIMULATED"&&liveAreaPages\.includes/);
  assert.match(app, /state\.mode!=="SIMULATED"&&liveUtilityPages\.includes/);
  assert.match(app, /state\.mode === "SIMULATED" && state\.page === "automatismos"/);
  assert.match(app, /state\.mode === "SIMULATED" && state\.page === "producao"/);
  assert.match(app, /state\.mode === "SIMULATED" && state\.page === "profile"/);
  assert.match(app, /Gateway ainda não forneceu equipamentos ou leituras/);
});

test("Gateway package embeds the source PWA assets used by the release build", () => {
  const build = read("../../../packaging/build-deb.sh");
  assert.match(build, /cp -R "\$ROOT\/web\/pwa\/\." "\$STAGE\/usr\/share\/solarminer\/pwa\/"/);
});
