import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const auth = readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
const gateway = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/app.py", import.meta.url), "utf8");
const scanner = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/network_scanner.py", import.meta.url), "utf8");

test("LAN result rows open editable MAC-keyed device details", () => {
  assert.match(app, /data-network-device-row="\$\{index\}"/);
  assert.match(app, /#device-add-results \[data-network-device-row\]/);
  assert.match(app, /openLocalNetworkDeviceDetails\(Number\(row\.dataset\.networkDeviceRow\)\)/);
  assert.match(html, /id="network-device-detail-dialog"/);
  assert.match(html, /id="network-device-detail-ip"/);
  assert.match(html, /id="network-device-detail-mac"/);
  assert.match(html, /id="network-device-detail-mac-source"/);
  assert.match(html, /id="network-device-detail-manufacturer"/);
  assert.match(html, /id="network-device-detail-model"/);
  assert.match(html, /id="network-device-detail-name"/);
  assert.match(html, /id="network-device-detail-type"/);
});

test("saved LAN names enter the shared Gateway inventory and appear in Devices pending", () => {
  assert.match(gateway, /CREATE TABLE IF NOT EXISTS gateway_device_inventory/);
  assert.match(gateway, /@app\.get\("\/api\/v1\/device-inventory"\)/);
  assert.match(gateway, /_sync_gateway_device_inventory\(conn, config\)/);
  assert.match(gateway, /name_source="owner"/);
  assert.match(app, /readGatewayDeviceInventory\(\)/);
  assert.match(app, /confirmation_status==="pending"&&item\.source_provider==="network"/);
  assert.match(app, /Devices/);
  assert.match(app, /Por confirmar · descoberto na rede/);
});

test("saving LAN device details validates a fresh MAC sighting and blocks ambiguous IP updates", () => {
  assert.match(auth, /saveGatewayLocalNetworkDevice\(\{ mac, ip = "", name, device_type, manufacturer = "", model = "", product_id = "" \}\)/);
  assert.match(auth, /\/api\/v1\/network\/devices\/save/);
  assert.match(gateway, /@app\.post\("\/api\/v1\/network\/devices\/save"\)/);
  assert.match(gateway, /network_device_not_seen_in_current_scan/);
  assert.match(gateway, /ambiguous_ip/);
  assert.match(gateway, /network_device_inventory/);
  assert.match(scanner, /neighbor_table/);
  assert.match(scanner, /not set\(response\["methods"\]\)\.intersection\(\{"tcp", "icmp"\}\)/);
});
