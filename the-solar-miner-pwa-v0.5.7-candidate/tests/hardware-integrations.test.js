import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = path => readFileSync(new URL(path, import.meta.url), "utf8");

test("Owner hardware setup exposes Deye, Antminer and Tuya; Tesla belongs to EV charging", () => {
  const html = read("../index.html");
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  for (const id of ["gateway-hardware-management", "hardware-deye-host", "hardware-antminer-host", "hardware-antminer-password", "hardware-antminer-rest-port", "antminer-power-target", "antminer-pause", "antminer-stop", "antminer-start", "hardware-tuya-client-secret", "hardware-tuya-uid", "deye-save", "deye-read", "antminer-save", "antminer-read", "tuya-save", "tuya-sync", "tuya-device-list", "owner-open-gateway"]) assert.match(html, new RegExp(`id="${id}"`));
  assert.doesNotMatch(html, /hardware-antminer-username/);
  assert.doesNotMatch(app, /hardware-antminer-username/);
  for (const tab of ["access", "updates", "tailscale", "gateway", "equipment"]) assert.match(html, new RegExp(`data-owner-tab="${tab}"`));
  for (const tab of ["deye", "antminer", "tuya"]) assert.match(html, new RegExp(`data-owner-device="${tab}"`));
  const workspace = read("../workspace-ui.js");
  for (const id of ["ev-tesla-refresh-token", "ev-tesla-vehicle-id", "ev-tesla-save", "ev-tesla-read"]) assert.match(workspace, new RegExp(`id="${id}"`));
  assert.match(app, /info\.user\.role !== "owner"/);
  assert.match(app, /saveGatewayHardwareIntegrationConfig/);
  assert.match(app, /readGatewayHardwareProvider/);
  assert.match(app, /leitura confirmada em /i);
  assert.match(app, /hashing reportado/);
  assert.match(auth, /antminer_control_credentials_required/);
  assert.match(auth, /O teste de ligação é independente do controlo/);
  assert.match(app, /saveGatewayHardwareIntegrationConfig\(\{ \[provider\]: payload \}\)/);
  assert.match(app, /hardware-tuya-client-secret"\)\.value = ""/);
  assert.match(auth, /\/api\/v1\/integrations\/hardware\/\$\{provider\}\/read/);
  assert.match(auth, /\/api\/v1\/integrations\/antminer\/control/);
  assert.match(auth, /\/api\/v1\/integrations\/tuya\/level/);
  assert.match(auth, /\/api\/v1\/integrations\/tuya\/sync/);
  assert.match(app, /syncGatewayTuyaDevices/);
  assert.match(app, /controlGatewayTuyaLevel/);
  assert.match(app, /data-favorite-level/);
  assert.match(auth, /"set_power_target", "pause", "stop", "start"/);
  assert.match(app, /if \(!confirm\(prompt\)\) return/);
  assert.match(auth, /\/api\/v1\/energy\/ev\/tesla\/read/);
  assert.doesNotMatch(app, /hardware-tesla-(?:region|client-id|refresh-token|vehicles)/);
  assert.doesNotMatch(auth, /tuya.*localStorage/i);
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

test("Huawei password-only CPE flow hides the username field and uses the protocol default", () => {
  const html = read("../index.html");
  const app = read("../app.js");
  assert.doesNotMatch(html, /id="huawei-router-username"/);
  assert.match(html, /Este modelo pede apenas a palavra-passe/);
  assert.match(app, /username="admin"/);
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

test("Gateway embedded PWA has the exact same integration UI and client", () => {
  const root = new URL("../../solarminer-gateway-code02-v0.6.9-candidate/web/pwa/", import.meta.url);
  for (const file of ["index.html", "app.js", "gateway-auth.js", "styles.css", "service-worker.js"]) {
    assert.equal(readFileSync(new URL(`../${file}`, import.meta.url), "utf8"), readFileSync(new URL(file, root), "utf8"), `${file} should match embedded copy`);
  }
});
