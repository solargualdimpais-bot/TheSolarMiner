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

test("Tuya model selector uses protocol identity and refreshes the catalog after opening", () => {
  assert.match(app, /const isTuyaProtocol=\["Tuya","MOES"\]\.includes\(manufacturer\)/);
  assert.match(app, /isTuyaProtocol\?String\(item\.protocol\|\|""\)\.toLowerCase\(\)==="tuya"/);
  assert.match(app, /refreshSmartProductCatalog\(\)\.then\(ok=>\{if\(ok&&dialog\.open\)updateProductChoices\(\);\}\)/);
  assert.match(app, /products\.map\(item=>`<option value="\$\{esc\(item\.product_code\)\}"/);
});

test("network-pending cards hide LAN identifiers and open their detail view", () => {
  const pendingCard=app.match(/networkPending\.map\(item=>`<article[\s\S]*?`\)\.join\(""\)/)?.[0]||"";
  assert.match(pendingCard, /data-network-inventory-device=/);
  assert.match(pendingCard, /Por confirmar · descoberto na rede/);
  assert.doesNotMatch(pendingCard, /last_ip|item\.mac|item\.model|item\.manufacturer/);
  assert.match(app, /openNetworkInventoryDeviceDetails\(networkInventoryCard\.dataset\.networkInventoryDevice\)/);
});

test("Deye inverter card opens shared device information and hides model metadata from the card", () => {
  assert.match(app, /data-energy-equipment="\$\{esc\(item\.id\)\}"/);
  assert.match(app, /openFavoriteDeviceDetails\(energyEquipmentCard\.dataset\.energyEquipment,"equipment"\)/);
  assert.match(app, /page==="inversores"\?"INVERSOR":"EQUIPAMENTO"/);
  assert.doesNotMatch(app, /item\.manufacturer\|\|"EQUIPAMENTO"\)\}\$\{item\.model/);
});

test("saved LAN names enter the shared Gateway inventory and appear in the matching confirmation tab", () => {
  assert.match(gateway, /CREATE TABLE IF NOT EXISTS gateway_device_inventory/);
  assert.match(gateway, /@app\.get\("\/api\/v1\/device-inventory"\)/);
  assert.match(gateway, /_sync_gateway_device_inventory\(conn, config\)/);
  assert.match(gateway, /name_source="owner"/);
  assert.match(app, /readGatewayDeviceInventory\(\)/);
  assert.match(app, /item\.source_provider==="network"\),networkPending=networkInventory\.filter\(item=>item\.confirmation_status!=="confirmed"\),networkIdentified=networkInventory\.filter\(item=>item\.confirmation_status==="confirmed"\)/);
  assert.match(app, /networkIdentified\.map\(item=>`<article/);
  assert.match(app, /Devices/);
  assert.match(app, /Por confirmar · descoberto na rede/);
});

test("freshly scanned unique IP/MAC is confirmed as network identity separately from control readiness", () => {
  assert.match(gateway, /status="confirmed" if current_ip and not ambiguous_ip else "pending"/);
  assert.match(gateway, /probe_tuya_lan_reachability\(current_ip\)/);
  assert.match(app, /Identificado na rede · ligação de controlo por verificar/);
  assert.match(app, /confirmedDevices\.length\+networkIdentified\.length/);
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
