import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseOwnerRecoveryFile } from "../gateway-auth.js";

const read = name => readFileSync(new URL(`../${name}`, import.meta.url), "utf8");
const auth = read("gateway-auth.js");
const app = read("app.js");
const html = read("index.html");
const manifest = read("manifest.webmanifest");
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
  assert.match(serviceWorker, /the-solar-miner-static-v0\.5\.8-/);
  assert.match(manifest, /v0\.5\.8/);
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
  assert.match(embeddedWorker, /owner-pwa-v0\.6\.23/);
  assert.match(embeddedWorker, /password-device-login/);
  assert.match(embeddedHtml, /OWNER PWA 0\.6\.23/);
  assert.match(embeddedHtml, /gateway-password-login-form/);
  assert.match(control, /^Version: 0\.6\.23$/m);
  assert.match(installer, /solarminer-gateway_0\.6\.23_amd64\.deb/);
  assert.match(installer, /install-tailscale\.sh/);
});
