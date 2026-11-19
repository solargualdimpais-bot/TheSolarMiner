import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = name => readFileSync(new URL(`../${name}`, import.meta.url), "utf8");
const auth = read("gateway-auth.js");
const app = read("app.js");
const html = read("index.html");
const manifest = read("manifest.webmanifest");
  const packageJson = JSON.parse(read("package.json"));
const serviceWorker = read("service-worker.js");

test("Owner user management uses authenticated Gateway endpoints with reauthentication", () => {
  assert.match(auth, /gatewayApi\("\/api\/v1\/users"\)/);
  assert.match(auth, /\/api\/v1\/users\/\$\{encodeURIComponent\(userId\)\}\/role/);
  assert.match(auth, /\/api\/v1\/users\/\$\{encodeURIComponent\(userId\)\}\/status/);
  assert.match(auth, /current_password: currentPassword/);
  assert.match(app, /userPanel\.hidden = info\.user\.role !== "owner"/);
  assert.match(app, /gatewayResult\("Acesso atualizado no Gateway e registado na auditoria\."\)/);
  assert.match(app, /window\.prompt\("Confirma a palavra-passe atual do Owner/);
});

test("Gateway administration is on an Owner-only page and live Home uses Gateway readings", () => {
  const home = app.match(/function renderOverview\(\) \{([\s\S]*?)\r?\n\}\r?\nfunction renderCategory/);
  assert.ok(home, "renderOverview must remain a distinct dashboard renderer");
  assert.match(home[1], /liveSolarHomeMetric\(\)/);
  assert.match(home[1], /liveBatteryHomeMetric\(\)/);
  assert.match(home[1], /liveMinerHomeMetric\(\)/);
  assert.match(app, /liveHomeMetric\("Painéis"/);
  assert.match(app, /function liveSolarHomeMetric\(\) \{[\s\S]*?state\.energyEngine\?\.current[\s\S]*?current\.pv_power_w/);
  assert.match(app, /function liveBatteryHomeMetric\(\) \{[\s\S]*?current\.battery_power_w/);
  assert.match(app, /Date\.now\(\)-lastRefresh>=10_000/);
  assert.match(app, /battery_output_power/);
  assert.match(app, /miner_hashrate_5s_ghs/);
  assert.match(app, /miner_power_limit_w/);
  assert.match(app, /data-miner-breaker-save/);
  assert.match(app, /Disjuntor · potência agregada/);
  assert.match(app, /Disjuntor · potência medida/);
  assert.match(app, /provider === "deye" \|\| provider === "antminer"/);
  assert.doesNotMatch(home[1], /Gestão do Gateway|gateway-update-management|gateway-tailscale-management/);
  assert.match(html, /id="gateway-owner-page" class="owner-admin-page" hidden/);
  assert.match(html, /id="owner-nav-item" class="nav-item" data-page="owner" hidden/);
  assert.match(app, /if \(page === "owner" && \(!sessionInfo\(\)\.authenticated \|\| sessionInfo\(\)\.user\.role !== "owner"\)\) return/);
});

test("Gateway console summarizes detected errors and filters logs to affected services", () => {
  assert.match(html, /id="gateway-console-errors"/);
  assert.match(html, /option value="errors">Só serviços com erros</);
  assert.match(app, /function renderGatewayConsoleErrors\(\)/);
  assert.match(app, /gatewayConsoleErrorPattern/);
  assert.match(app, /gatewayConsoleDetectedErrorServices/);
  assert.match(app, /Serviços marcados como falhados/);
  assert.match(app, /gatewayConsoleServicePatterns\[service\]/);
  assert.match(html, /id="gateway-console-send-report"/);
  assert.match(app, /sendGatewayDiagnosticsReport\(\)/);
  assert.match(app, /gateway_watchdog: "Watchdog"/);
  assert.match(app, /setGatewayWatchdogEnabled\(enable\)/);
});

test("Owner PWA checks for Gateway updates automatically every minute while active", () => {
  assert.match(app, /setInterval\(\(\) => \{[\s\S]*?runGatewayUpdateCheck\(\{automatic:true\}\)[\s\S]*?\},60_000\)/);
  assert.match(app, /document\.visibilityState!=="visible"/);
  assert.match(html, /id="gateway-update-banner"/);
});

test("automatic update checks never open a modal that blocks PWA navigation", () => {
  const prompt = app.indexOf('const prompt={title:"Atualização verificada"');
  const automaticStart = app.indexOf("if(automatic){", prompt);
  const manualStart = app.indexOf("} else {", automaticStart);
  assert.ok(prompt >= 0 && automaticStart > prompt && manualStart > automaticStart);
  assert.doesNotMatch(app.slice(automaticStart, manualStart), /showOperationDialog|renderOperationDialog/);
  const blocked = app.slice(app.indexOf('if (result.status === "verified_staged")'), app.indexOf('} else if (result.status === "current")'));
  assert.match(blocked, /if\(!automatic\)\{[\s\S]*?renderOperationDialog\(\{title:"Atualização bloqueada"/);
});

test("the recovery key is shown once, but owner recovery remains local-only", () => {
  assert.match(html, /gateway-download-recovery-key/);
  assert.match(html, /a chave offline não é aceite pela API nem pela PWA/);
  assert.doesNotMatch(html, /gateway-owner-recovery-form|gateway-recovery-file|open-owner-recovery/);
  assert.match(html, /apresentada uma única vez/);
  assert.match(app, /solarminer-owner-recovery-key\.txt/);
  assert.doesNotMatch(app, /recoverGatewayOwner|parseOwnerRecoveryFile|\/api\/v1\/owner\/recovery/);
  assert.doesNotMatch(auth, /\/api\/v1\/owner\/recovery/);
  assert.match(app, /Gateway Ed25519 fingerprint:/);
  assert.match(app, /const key = \$\("#gateway-bootstrap-recovery-key"\)\.value/);
  assert.match(app, /if \(!key\) return/);
});

test("battery tabs use fresh Deye banks and do not label one bank as the total SOC", () => {
  const css = read("styles.css");
  assert.match(app, /function renderDetectedBatteryArea\(items, engine, batteryFlowClass\)/);
  assert.match(app, /data-battery-bank-tab/);
  assert.match(app, /liveBanks\.length===1\?socs\[0\]:null/);
  assert.match(app, /SOC total indisponível: faltam capacidades individuais/);
  assert.match(app, /age > 120/);
  assert.match(app, /Potência total · \$\{esc\(flow\)\}/);
  assert.match(css, /\.battery-flow-kpi\.charge strong\{color:#fff\}/);
  assert.match(css, /\.battery-flow-kpi\.discharge strong\{color:#e5484d\}/);
});

test("Intelligence status explains malformed Ollama runtime responses", () => {
  assert.match(app, /ollama_tags_response_invalid: "resposta da lista de modelos Ollama inválida"/);
  assert.match(app, /ollama_version_http_error: "endpoint de versão Ollama devolveu erro HTTP"/);
  assert.match(app, /providerTrace\.error_reason/);
  assert.match(app, /providerTrace\.http_status/);
});

test("new PWA static cache version is changed and USB limitations are documented", () => {
  assert.match(serviceWorker, /the-solar-miner-static-v0\.5\.194-intelligence-request-diagnostics/);
  assert.match(serviceWorker, /\.\/favorite-list\.js/);
  assert.match(manifest, /v0\.5\.194/);
  assert.equal(packageJson.version, "0.5.194");
  assert.doesNotMatch(html, /gateway-update-refresh|Atualizar estado/);
  assert.doesNotMatch(app, /gateway-update-refresh/);
  const docs = read("OWNER_USB_AND_ACCESS.md");
  assert.match(docs, /texto simples/);
  assert.match(docs, /não é aceite por nenhum endpoint HTTP/);
  assert.match(docs, /recuperação exige acesso local ao Gateway/);
  assert.match(docs, /chave privada de assinatura nunca deve ser incluída/);
  assert.match(docs, /edição manual do SQLite.*não é suportada/s);
});
