import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const root = new URL("../", import.meta.url);
const app = readFileSync(new URL("app.js", root), "utf8");
const html = readFileSync(new URL("index.html", root), "utf8");
const sw = readFileSync(new URL("service-worker.js", root), "utf8");
const pkg = JSON.parse(readFileSync(new URL("package.json", root), "utf8"));

test("first PWA visit opens secure Gateway setup and keeps Owner bootstrap behind endpoint validation", () => {
  const earlyHandler = app.indexOf('document.addEventListener("click",event=>');
  const laterButtonBinding = app.indexOf('$("#close-gateway-dialog").addEventListener');
  assert.ok(earlyHandler >= 0 && earlyHandler < laterButtonBinding);
  assert.match(app, /#mode-chip, #owner-open-gateway, #profile-open-gateway, #open-owner-management/);
  assert.match(app, /solarminer-first-connection-prompted-v1/);
  assert.match(app, /setTimeout\(openGatewayConnectionDialog,0\)/);
  assert.match(app, /if \(\["BOOTSTRAP_PENDING", "OWNER_SETUP_REQUIRED"\]\.includes\(bootstrap\.state\)\)/);
  assert.match(html, /Se o Gateway estiver à espera do primeiro Owner, abre-se então a janela/);
  assert.equal(pkg.version, "0.5.173");
  assert.match(sw, /the-solar-miner-static-v0\.5\.173-automation-status-device-filters/);
});
