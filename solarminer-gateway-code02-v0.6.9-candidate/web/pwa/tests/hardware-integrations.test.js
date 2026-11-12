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

test("Saving a Tuya device in either form runs only the selected LAN reachability test", () => {
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  const gateway = read("../../../src/solarminer_gateway/app.py");
  const integrations = read("../../../src/solarminer_gateway/integrations.py");
  assert.match(app, /async function testTuyaLanReachability\(deviceId\)[\s\S]*?testGatewayTuyaLanReachability\(deviceId\)/);
  assert.match(app, /saveGatewayHardwareIntegrationConfig\([\s\S]*?testTuyaLanReachability\(id\)/);
  assert.match(app, /saveGatewayHardwareIntegrationConfig\(\{tuya:\{devices:next\}\}\)[\s\S]*?runGatewayTuyaLanDiagnostics\(1,device\.device_id\)/);
  assert.match(auth, /\/api\/v1\/integrations\/tuya\/lan-reachability/);
  assert.match(gateway, /@app\.post\(\"\/api\/v1\/integrations\/tuya\/lan-reachability\"\)/);
  assert.match(gateway, /status_read\": False, \"dps_read\": False, \"cloud_requested\": False/);
  assert.match(integrations, /probe_tuya_lan_reachability\(host: str, timeout: float = 1\.0\)/);
  assert.match(integrations, /socket\.create_connection\(\(address, 6668\), timeout=timeout\)/);
});

test("Tuya PID DPS catalog separates cloud commands, readings, and observed LAN IDs", () => {
  const app = read("../app.js");
  const gateway = read("../../../src/solarminer_gateway/app.py");
  const integrations = read("../../../src/solarminer_gateway/integrations.py");
  assert.match(app, /Capacidades recebidas da cloud · ainda sem ID numérico/);
  assert.match(app, /Ordem · função/);
  assert.match(app, /Leitura · estado/);
  assert.match(app, /tuyaPidRows\(profile\)[\s\S]*?source_kind\|\|row\.source/);
  assert.match(app, /data-tuya-pid-read=[\s\S]*?Ler num equipamento/);
  assert.match(app, /runGatewayTuyaLanDiagnostics\(1,deviceId\)/);
  assert.match(app, /tuya-dps-compact-head/);
  assert.match(app, /data-edit-capability/);
  assert.match(app, /Último valor lido pela LAN/);
  assert.match(app, /Analisar texto e guardar/);
  assert.match(app, /Incongruência · confirmar associação/);
  assert.match(app, /tuya_pid_dps_cloud_code_mapped_more_than_once/);
  assert.match(gateway, /CREATE TABLE IF NOT EXISTS tuya_pid_capabilities/);
  assert.match(gateway, /_persist_tuya_pid_capabilities\(conn, tuya\.get\("product_schemas"\)\)/);
  assert.match(integrations, /_tuya_merge_pid_dps_rows\([\s\S]*?item\.get\("functions"[\s\S]*?item\.get\("status_spec"/);
  assert.match(integrations, /row\.update\(\{"dps_id": dps_id, "dp_id": dps_id, "code": item\["code"\]/);
});

test("Tuya PID map editor imports text, saves per DPS and highlights ambiguity", () => {
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  const css = read("../styles.css");
  const parser = app.match(/function parseTuyaPidDpsPaste\([\s\S]*?\n\}/)?.[0];
  assert.ok(parser, "text import parser exists");
  const parse = new Function(`${parser}; return parseTuyaPidDpsPaste;`)();
  const profile = {
    functions: [{code:"countdown_1", type:"Integer", values:{unit:"s",min:0,max:86400,step:1}}],
    status_spec: [{code:"cur_voltage", type:"Integer", values:{unit:"V",scale:0.1}}]
  };
  const rows = [{dps_id:20,code:"",source:"unknown",label_pt:"Por identificar"},{dps_id:9,code:"",source:"unknown",label_pt:"Por identificar"}];
  const result = parse("DPS 20 | Tensão | cur_voltage | V | 0.1\nDPS 9 | Temporizador | countdown_1 | s | 1", profile, rows);
  assert.deepEqual(result.mapped, [20,9]);
  assert.equal(result.rows.find(row=>row.dps_id===20).code, "cur_voltage");
  assert.equal(result.rows.find(row=>row.dps_id===9).source, "function");
  const inferred = parse("DPS 20 | Tensão medida | V | 0.1", profile, rows);
  assert.equal(inferred.rows.find(row=>row.dps_id===20).code, "cur_voltage", "known descriptions should link to the matching PID capability without requiring the AI to know its cloud code");
  const fullProfile = {
    functions: [{code:"switch",type:"Boolean"},{code:"countdown_1",type:"Integer",values:{unit:"s",min:0,max:86400,scale:0,step:1}}],
    status_spec: ["add_ele","cur_current","cur_power","cur_voltage","test_bit","voltage_coe","electric_coe","power_coe","electricity_coe","fault","relay_status","light_mode","child_lock","cycle_time","online_state"].map(code=>({code,type:code==="fault"?"Fault":code==="light_mode"||code==="relay_status"?"Enum":"Integer"}))
  };
  const pasted = [1,9,17,18,19,20,21,22,23,24,25,26,38,40,41,42,66].map(dps_id=>({dps_id,code:"",source:"unknown",label_pt:"Por identificar"}));
  const aiText = "DPS 1 | Interruptor | Ordem • Interruptor • switch | Por identificar | Booleano | — | 1\nDPS 9 | Contagem decrescente | Ordem • Contagem decrescente • countdown_1 | Por identificar | Valor numérico | s | 1\nDPS 17 | Energia acumulada | Leitura • Energia acumulada • add_ele | Por identificar | Valor numérico | kWh | 0.001\nDPS 18 | Corrente atual | Leitura • Corrente atual • cur_current | Por identificar | Valor numérico | A | 0.001\nDPS 19 | Potência atual | Leitura • Potência atual • cur_power | Por identificar | Valor numérico | W | 0.1\nDPS 20 | Tensão atual | Leitura • Tensão atual • cur_voltage | Por identificar | Valor numérico | V | 0.1\nDPS 21 | Função Tuya | Leitura • Função Tuya • test_bit | Por identificar | Desconhecido | — | 1\nDPS 22 | Tensão | Leitura • Tensão • voltage_coe | Por identificar | Valor numérico | — | 1\nDPS 23 | Corrente | Leitura • Corrente • electric_coe | Por identificar | Valor numérico | — | 1\nDPS 24 | Potência | Leitura • Potência • power_coe | Por identificar | Valor numérico | — | 1\nDPS 25 | Energia | Leitura • Energia • electricity_coe | Por identificar | Valor numérico | — | 1\nDPS 26 | Falha | Leitura • Falha • fault | Por identificar | Falha | — | 1\nDPS 38 | Estado do relé | Leitura • Estado do relé • relay_status | Por identificar | Booleano | — | 1\nDPS 40 | Luz | Leitura • Luz • light_mode | Por identificar | Enumeração | — | 1\nDPS 41 | Bloqueio infantil | Leitura • Bloqueio infantil • child_lock | Por identificar | Booleano | — | 1\nDPS 42 | Temporizador | Leitura • Temporizador • cycle_time | Por identificar | Valor numérico | s | 1\nDPS 66 | Estado | Leitura • Estado • online_state | Por identificar | Booleano | — | 1";
  const imported = parse(aiText, fullProfile, pasted);
  assert.equal(imported.mapped.length, pasted.length);
  assert.equal(imported.rows.find(row=>row.dps_id===1).data_type, "bool");
  assert.equal(imported.rows.find(row=>row.dps_id===9).scale, 1);
  assert.equal(imported.rows.find(row=>row.dps_id===9).source, "function");
  assert.equal(imported.rows.find(row=>row.dps_id===17).data_type, "value");
  assert.equal(imported.rows.find(row=>row.dps_id===40).data_type, "enum");
  const analyzer = app.match(/function analyzeTuyaPidDpsPaste\([\s\S]*?\n\}/)?.[0];
  assert.ok(analyzer, "DPS text review identifies invalid rows before saving");
  const analyze = new Function(`${parser}; ${analyzer}; return analyzeTuyaPidDpsPaste;`)();
  const reviewed = analyze(aiText, fullProfile, pasted);
  assert.equal(reviewed.records.length, pasted.length);
  assert.deepEqual(reviewed.records[0].issues, []);
  const invalidReview = analyze(aiText.replace("Booleano", "Tipo inventado"), fullProfile, pasted);
  assert.match(invalidReview.records[0].issues.join(" "), /Tipo de dado .* não reconhecido/);
  const jsonReview = analyze(JSON.stringify([{dps_id:1, label_pt:"Interruptor", source:"unknown", data_type:"Booleano", semantic_code:"switch"}]), fullProfile, pasted);
  assert.equal(jsonReview.records.length, 1);
  assert.equal(jsonReview.records[0].suggestion, jsonReview.records[0].original);
  assert.match(app, /Texto inserido<textarea data-review-original readonly/);
  assert.match(app, /Sugestão corrigida · pode editar/);
  assert.match(app, /data-review-prev/);
  assert.match(app, /data-review-next/);
  assert.match(app, /Gravar correções/);
  assert.match(css, /data-review-original\]\.has-error/);
  assert.match(app, /saveGatewayTuyaPidDpsMap\(productId,updates,\{partial:true\}\)/);
  assert.match(app, /A guardar apenas o DPS \$\{row\.dps_id\}/);
  assert.match(auth, /const acceptedFields = \["dps_id", "code", "label_pt", "source", "data_type", "unit", "scale", "details", "semantic_code", "write_supported"\]/);
  assert.match(auth, /"booleano":"bool"/);
  assert.match(auth, /const cleanRows = rows\.map\(row => Object\.fromEntries\(acceptedFields/);
  assert.match(app, /Código Tuya duplicado neste PID/);
  const errorFormatter = app.match(/function tuyaPidDpsSaveErrorText\([\s\S]*?\n\}/)?.[0];
  assert.ok(errorFormatter, "DPS save errors include row and field context");
  const formatError = new Function(`${errorFormatter}; return tuyaPidDpsSaveErrorText;`)();
  assert.equal(formatError(new Error("tuya_pid_dps_row_invalid|row=2|dps=20|field=data_type|reason=unsupported_value")), "Linha 2 da lista DPS (DPS 20), campo tipo de dado: valor não aceite.");
  assert.match(formatError(new Error("Load failed")), /não recebeu resposta do Gateway/);
  assert.match(app, /Erro no mapa DPS — \$\{tuyaPidDpsSaveErrorText\(error\)\}/);
  assert.match(css, /\.connection-result\.tuya-dps-error\{[^}]*background:#351d1c/);
  assert.match(css, /\.tuya-dps-compact-row\.is-ambiguous/);
  assert.match(css, /\.tuya-dps-compact-row\.is-conflict/);
});

test("runtime device-card layout scales item coordinates to the card width", () => {
  const app = read("../app.js");
  const css = read("../styles.css");
  assert.match(app, /left:\$\{x\/ canvasWidth\*100\}%/);
  assert.match(app, /aspect-ratio:\$\{canvasWidth\}\/\$\{canvasHeight\}/);
  assert.match(app, /container-type:inline-size/);
  assert.match(css, /\.device-card-runtime-item\{[^}]*position:absolute/);
  assert.match(css, /\.device-card-runtime-item\.favorite-device-info/);
});

test("mobile device-detail card clears the phone status area and keeps a visible outline", () => {
  const css = read("../styles.css");
  assert.match(css, /@media\(max-width:680px\)\{dialog\.favorite-device-details\[open\]\{[^}]*top:calc\(env\(safe-area-inset-top,0px\) \+ 12px\)/);
  assert.match(css, /dialog\.favorite-device-details\[open\]\{[^}]*border:1px solid #4b4638/);
});

test("Tuya PID map enriches every matching device card and its controls", () => {
  const app = read("../app.js");
  const helper = app.match(/function tuyaDeviceWithPidMap\(device\)\{[\s\S]*?\n\}/)?.[0];
  assert.ok(helper, "PID-to-device card mapping helper exists");
  const applyMap = new Function("state", `${helper}; return tuyaDeviceWithPidMap;`)({smartProductCatalog:[{
    product_id:"pid-a",dps:[
      {dps_id:1,code:"switch_1",source_kind:"function",data_type:"bool",semantic_code:"switch",write_supported:true},
      {dps_id:20,code:"cur_voltage",source_kind:"status",data_type:"value",unit:"V",scale:0.1},
      {dps_id:21,code:"countdown_1",source_kind:"function",data_type:"integer",unit:"s",values:{min:0,max:86400,step:1}}
    ]
  }]});
  const device=applyMap({device_id:"dev-a",product_id:"pid-a",functions:[{code:"switch_1",type:"bool"}],status_spec:[{code:"cur_voltage",type:"value"}],local_dps_map:{}});
  assert.equal(device.functions[0].dp_id,1);
  assert.equal(device.local_dps_map.switch_1,"1");
  assert.equal(device.status_spec[0].dp_id,20);
  assert.equal(device.dps_knowledge.dps.find(row=>row.dps_id===20).semantic_code,"voltage");
  assert.equal(device.dps_knowledge.dps.find(row=>row.dps_id===20).confidence,"SCHEMA_INFERRED");
  assert.equal(device.dps_knowledge.dps.find(row=>row.dps_id===21).semantic_code,"countdown");
  const other=applyMap({device_id:"dev-b",product_id:"pid-b",functions:[]});
  assert.equal(other.dps_knowledge,undefined,"a different PID must not inherit this mapping");
  assert.match(app,/state\.smartProductCatalog=Array\.isArray\(result\.tuya_profiles\)\?result\.tuya_profiles:\[\]/);
  assert.match(app,/normalizeTuyaInventory\(state\.tuyaDevices\)\.map\(tuyaDeviceWithPidMap\)/);
});

test("Tuya editor can resolve a missing local IP by unique MAC before LAN testing", () => {
  const app = read("../app.js");
  assert.match(app, /if\(!requestedIp&&!requestedMac\)/);
  assert.doesNotMatch(app, /if\(!form\.elements\.local_ip\.value\.trim\(\)\|\|!form\.elements\.local_mac\.value\.trim\(\)\)/);
  assert.match(app, /local_protocol:form\.elements\.local_protocol\.value/);
  assert.match(app, /if\(!requestedIp\|\|!requestedMac\)[\s\S]*?scanGatewayLocalNetwork\(\)[\s\S]*?candidateIps\.size!==1\|\|candidateMacs\.size!==1[\s\S]*?form\.elements\.local_ip\.value=requestedIp;form\.elements\.local_mac\.value=requestedMac[\s\S]*?saveGatewayHardwareIntegrationConfig/);
  assert.match(app, /requestedIp&&requestedMac\?"A guardar IP e MAC já indicados/);
  assert.match(app, /if\(!schemaInfo\.queried\)[\s\S]*?runGatewayTuyaLanDiagnostics\(1,device\.device_id\)/);
  assert.match(app, /mais de uma correspondência possível/);
  assert.match(app, /state\.tuyaDevices=normalizeTuyaInventory\(savedConfig\.tuya\?\.devices\|\|state\.tuyaDevices\)/);
  assert.match(app, /runGatewayTuyaLanDiagnostics\(1,device\.device_id\)[\s\S]*?local_responded[\s\S]*?state\.gatewayDeviceInventory=Array\.isArray\(inventory\.devices\)/);
  assert.match(app, /if\(!requestedIp\|\|!requestedMac\)[\s\S]*?scanGatewayLocalNetwork\(\)/);
  assert.match(app, /requestedIp&&requestedMac\?"A guardar IP e MAC já indicados/);
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
