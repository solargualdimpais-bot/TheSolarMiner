import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const auth = readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
const gateway = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/app.py", import.meta.url), "utf8");

test("LAN result rows open editable MAC-keyed device details", () => {
  assert.match(app, /data-network-device-row="\$\{index\}"/);
  assert.match(app, /#local-network-results"\)\.addEventListener\("click"/);
  assert.match(app, /openLocalNetworkDeviceDetails\(Number\(row\.dataset\.networkDeviceRow\)\)/);
  assert.match(html, /id="network-device-detail-dialog"/);
  assert.match(html, /id="network-device-detail-ip"/);
  assert.match(html, /id="network-device-detail-mac"/);
  assert.match(html, /id="network-device-detail-manufacturer"/);
  assert.match(html, /id="network-device-detail-model"/);
  assert.match(html, /id="network-device-detail-name"/);
  assert.match(html, /id="network-device-detail-type"/);
});

test("saving LAN device details validates a fresh MAC sighting and blocks ambiguous IP updates", () => {
  assert.match(auth, /saveGatewayLocalNetworkDevice\(\{ mac, name, device_type \}\)/);
  assert.match(auth, /\/api\/v1\/network\/devices\/save/);
  assert.match(gateway, /@app\.post\("\/api\/v1\/network\/devices\/save"\)/);
  assert.match(gateway, /network_device_not_seen_in_current_scan/);
  assert.match(gateway, /ambiguous_ip/);
  assert.match(gateway, /network_device_inventory/);
});
