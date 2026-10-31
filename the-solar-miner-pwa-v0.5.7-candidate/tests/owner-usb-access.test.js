import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseOwnerRecoveryFile } from "../gateway-auth.js";

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
  assert.match(app, /battery_output_power/);
  assert.match(app, /miner_hashrate_5s_ghs/);
  assert.match(app, /miner_power_limit_w/);
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

test("the recovery key can be downloaded only from the first-owner one-time display", () => {
  assert.match(html, /gateway-download-recovery-key/);
  assert.match(html, /gateway-owner-recovery-form/);
  assert.match(html, /gateway-recovery-file/);
  assert.match(html, /apresentada uma única vez/);
  assert.match(app, /solarminer-owner-recovery-key\.txt/);
  assert.match(app, /recoverGatewayOwner\(/);
  assert.match(app, /Gateway Ed25519 fingerprint:/);
  assert.match(app, /const key = \$\("#gateway-bootstrap-recovery-key"\)\.value/);
  assert.match(app, /if \(!key\) return/);
});

test("Owner recovery file parser accepts a generated key and rejects malformed/oversized files", () => {
  const key = `SMR1-${Array(13).fill("ABCD").join("-")}`;
  const fingerprint = "ab".repeat(32);
  assert.deepEqual(parseOwnerRecoveryFile(`Gateway Ed25519 fingerprint: ${fingerprint}\n${key}\n`), { key, fingerprint });
  assert.throws(() => parseOwnerRecoveryFile("ordinary text without a recovery key"), /não contém/);
  assert.throws(() => parseOwnerRecoveryFile("x".repeat(4097)), /demasiado grande/);
});

test("new PWA static cache version is changed and USB limitations are documented", () => {
  assert.match(serviceWorker, /the-solar-miner-static-v0\.5\.65-surplus-manager/);
  assert.match(manifest, /v0\.5\.65/);
  assert.equal(packageJson.version, "0.5.65");
  assert.doesNotMatch(html, /gateway-update-refresh|Atualizar estado/);
  assert.doesNotMatch(app, /gateway-update-refresh/);
  const docs = read("OWNER_USB_AND_ACCESS.md");
  assert.match(docs, /texto simples/);
  assert.match(docs, /não valida certificados TLS/);
  assert.match(docs, /chave privada de assinatura nunca deve ser incluída/);
  assert.match(docs, /edição manual do SQLite.*não é suportada/s);
});

test("the Gateway-embedded PWA contains the Owner access controls and the package is version-aligned", () => {
  const embedded = name => readFileSync(new URL(`../../solarminer-gateway-code02-v0.6.9-candidate/web/pwa/${name}`, import.meta.url), "utf8");
  const embeddedHtml = embedded("index.html");
  const embeddedApp = embedded("app.js");
  const embeddedAuth = embedded("gateway-auth.js");
  const embeddedWorker = embedded("service-worker.js");
  const embeddedCss = embedded("styles.css");
  const embeddedManifest = embedded("manifest.webmanifest");
  const embeddedPhotoFormat = embedded("photo-format.js");
  const control = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/packaging/control", import.meta.url), "utf8");
  const installer = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/packaging/install-from-usb.sh", import.meta.url), "utf8");
  assert.match(embeddedHtml, /gateway-user-management/);
  assert.match(embeddedHtml, /gateway-download-recovery-key/);
  assert.match(embeddedHtml, /gateway-owner-recovery-form/);
  assert.match(embeddedHtml, /gateway-tailscale-management/);
  assert.match(embeddedHtml, /gateway-tailscale-endpoint/);
  assert.match(embeddedHtml, /gateway-tailscale-connect/);
  assert.match(embeddedApp, /updateGatewayUserRole/);
  assert.match(embeddedApp, /recoverGatewayOwner\(/);
  assert.match(embeddedApp, /solarminer-gateway-tailscale-endpoint-v1/);
  assert.match(embeddedAuth, /\/api\/v1\/users/);
  assert.match(embeddedAuth, /\/api\/v1\/system\/tailscale/);
  assert.match(embeddedAuth, /\/api\/v1\/system\/tailscale\/connect/);
  assert.match(embeddedApp, /startGatewayTailscale/);
  assert.match(embeddedApp, /liveHomeMetric\("Painéis"/);
  assert.match(embeddedApp, /liveMinerHomeMetric\(\)/);
  assert.match(embeddedWorker, /static-v0\.5\.65-surplus-manager/);
  assert.match(embeddedHtml, /data-owner-tab="gateway"/);
  assert.doesNotMatch(embeddedHtml, /data-owner-panel="console"/);
  assert.match(embeddedHtml, /Carrega em .Atualizar consola. para consultar os dados mais recentes/);
  assert.match(embeddedHtml, /id="gateway-console-output"/);
  assert.match(embeddedHtml, /gateway-console-services/);
  assert.match(embeddedHtml, /gateway-console-resources/);
  assert.match(embeddedApp, /readGatewayConsole/);
  assert.match(embeddedApp, /gatewayConsoleServiceLabels/);
  assert.match(embeddedApp, /gatewayConsoleBytes/);
  assert.match(embeddedAuth, /\/api\/v1\/system\/console/);
  assert.match(embeddedHtml, /id="gateway-diagnostics-upload-token"/);
  assert.match(embeddedApp, /saveGatewayDiagnosticsUploadToken/);
  assert.match(embeddedAuth, /\/api\/v1\/system\/diagnostics-upload/);
  assert.match(embeddedApp, /activeOwnerTab = name/);
  assert.doesNotMatch(embeddedApp, /refreshGatewayConsole\(\{ silent: true \}\)/);
  assert.doesNotMatch(embeddedHtml, /gateway-console-update-check/);
  assert.doesNotMatch(embeddedHtml, /gateway-console-command/);
  assert.match(embeddedWorker, /password-device-login/);
  assert.match(embeddedHtml, /OWNER PWA 0\.5\.65/);
  assert.match(embeddedHtml, /gateway-password-login-form/);
  assert.match(control, /^Version: 0\.6\.106$/m);
  assert.match(installer, /solarminer-gateway_0\.6\.106_amd64.deb/);
  assert.match(embeddedApp, /RECOVERY_BLOCKED/);
  assert.match(embeddedApp, /rollbackFailure/);
  assert.match(installer, /install-tailscale\.sh/);
  assert.equal(embeddedHtml, html);
  assert.equal(embeddedApp, app);
  assert.equal(embeddedWorker, serviceWorker);
  assert.equal(embeddedCss, read("styles.css"));
  assert.equal(embeddedManifest, manifest);
  assert.equal(embeddedPhotoFormat, read("photo-format.js"));
});

test("Tuya devices expose a local editor with channel names and Gateway-only persistence", () => {
  assert.match(app, /data-edit-tuya-device/);
  assert.match(app, /function openTuyaDeviceEditor/);
  assert.match(app, /data-tuya-capability-label/);
  assert.match(app, /name_source:"local"/);
  assert.match(app, /saveGatewayHardwareIntegrationConfig\(\{tuya:\{devices:next\}\}\)/);
  assert.match(app, /Dispositivo e canal Tuya/);
  assert.match(app, /device\.channel_labels\?\./);
});
