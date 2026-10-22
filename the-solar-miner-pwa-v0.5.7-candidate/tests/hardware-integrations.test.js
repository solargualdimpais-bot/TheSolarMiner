import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = path => readFileSync(new URL(path, import.meta.url), "utf8");

test("Owner hardware setup exposes Deye, Antminer and Tuya; Tesla belongs to EV charging", () => {
  const html = read("../index.html");
  const app = read("../app.js");
  const auth = read("../gateway-auth.js");
  for (const id of ["gateway-hardware-management", "hardware-deye-host", "hardware-antminer-host", "hardware-antminer-username", "hardware-antminer-password", "hardware-antminer-rest-port", "antminer-power-target", "antminer-pause", "antminer-stop", "antminer-start", "hardware-tuya-client-secret", "hardware-integrations-read"]) assert.match(html, new RegExp(`id="${id}"`));
  const workspace = read("../workspace-ui.js");
  for (const id of ["ev-tesla-refresh-token", "ev-tesla-vehicle-id", "ev-tesla-save", "ev-tesla-read"]) assert.match(workspace, new RegExp(`id="${id}"`));
  assert.match(app, /info\.user\.role !== "owner"/);
  assert.match(app, /saveGatewayHardwareIntegrationConfig/);
  assert.match(app, /readGatewayHardwareIntegrations/);
  assert.match(app, /hardware-tuya-client-secret"\)\.value = ""/);
  assert.match(auth, /\/api\/v1\/integrations\/hardware\/read/);
  assert.match(auth, /\/api\/v1\/integrations\/antminer\/control/);
  assert.match(auth, /"set_power_target", "pause", "stop", "start"/);
  assert.match(app, /if \(!confirm\(prompt\)\) return/);
  assert.match(auth, /\/api\/v1\/energy\/ev\/tesla\/read/);
  assert.doesNotMatch(app, /hardware-tesla-(?:region|client-id|refresh-token|vehicles)/);
  assert.doesNotMatch(auth, /tuya.*localStorage/i);
});

test("Gateway embedded PWA has the exact same integration UI and client", () => {
  const root = new URL("../../solarminer-gateway-code02-v0.6.9-candidate/web/pwa/", import.meta.url);
  for (const file of ["index.html", "app.js", "gateway-auth.js", "styles.css", "service-worker.js"]) {
    assert.equal(readFileSync(new URL(`../${file}`, import.meta.url), "utf8"), readFileSync(new URL(file, root), "utf8"), `${file} should match embedded copy`);
  }
});
