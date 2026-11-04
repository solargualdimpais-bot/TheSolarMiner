import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const app = fs.readFileSync(new URL("../app.js", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
const backend = fs.readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/shelly_integration.py", import.meta.url), "utf8");

test("Devices has one manufacturer-neutral network discovery flow", () => {
  assert.match(app, /id="device-add-scan"/);
  assert.match(app, /Procurar equipamentos/);
  assert.match(app, /scanGatewayLocalNetwork\(\)/);
  assert.match(app, /openLocalNetworkDeviceDetails\(Number\(addScanRow\.dataset\.networkDeviceRow\)\)/);
  assert.match(app, /MAC \$\{saved\.device\.mac\}/);
  assert.match(api, /\/api\/v1\/integrations\/shelly\/register/);
});

test("LAN result dialog tolerates double-clicks and reports save status in Devices onboarding", () => {
  assert.match(app, /if\(dialog\.open\)return;/);
  assert.match(app, /statusSelector=\$\("#local-network-status"\)\?"#local-network-status":"#device-add-status"/);
});

test("Shelly controls go through authenticated Gateway APIs and confirm observed state", () => {
  assert.match(api, /\/api\/v1\/integrations\/shelly\/\$\{encodeURIComponent\(deviceId\)\}\/switch/);
  assert.match(app, /result\.command_confirmed/);
  assert.doesNotMatch(app, /confirmas que queres \$\{on\?/i);
});

test("AP onboarding remains explicitly unimplemented in this LAN delivery", () => {
  assert.match(app, /configuração inicial pela rede Wi-Fi própria do dispositivo ainda não está disponível/);
  assert.doesNotMatch(app, /fetch\(["']http:\/\/192\.168\.33\.1/);
});

test("BLU sensors are discovered and registered through a Shelly bridge by the Gateway", () => {
  assert.match(app, /report\.blu_devices/);
  assert.match(app, /openBluDeviceDetails/);
  assert.match(api, /\/api\/v1\/integrations\/shelly\/blu\/register/);
  assert.match(backend, /def inspect_bluetooth_bridge/);
  assert.match(backend, /BLE\.Scanner\.start/);
  assert.match(backend, /Script\.Create/);
  assert.match(backend, /Script\.Delete/);
  assert.match(backend, /def discover_bluetooth_devices/);
  assert.match(app, /data-shelly-light-on/);
  assert.match(app, /bthome_values/);
  assert.doesNotMatch(backend, /BTHome\.StartDeviceDiscovery/);
  assert.match(app, /data-shelly-blu-discover/);
  assert.match(app, /discoverGatewayShellyBluDevices\(bridge\.device_id\)/);
  assert.match(api, /\/api\/v1\/integrations\/shelly\/\$\{encodeURIComponent\(deviceId\)\}\/blu\/discover/);
  assert.match(app, /openBluDeviceDetails\(Number\(blu\.dataset\.bluDeviceRow\)\)/);
  assert.doesNotMatch(app, /openBluDeviceDetails\(index\)[\s\S]{0,900}dialog\.showModal\(\);[\s\S]{0,300}dialog\.showModal\(\)/);
});

test("Shelly Vintage card opens details and local light control is exposed", () => {
  assert.match(app, /function openShellyDeviceDetails\(deviceId\)/);
  assert.match(app, /openShellyDeviceDetails\(smartShellyCard\.dataset\.smartDevice\)/);
  assert.match(app, /data-shelly-light-on/);
  assert.match(backend, /endpoint = f"\/light\/\{channel\}"/);
  assert.match(app, /data-shelly-expand/);
  assert.match(app, /data-shelly-settings/);
  assert.match(app, /data-shelly-brightness-value/);
  assert.match(api, /readGatewayShellyProductProfiles/);
  const cardRenderer=app.match(/const shellyCards=list=>list\.map\(device=>\{[\s\S]*?\}\)\.join\(""\);/)?.[0]||"";
  assert.doesNotMatch(cardRenderer, /range|data-shelly-apply-brightness|Procurar sensores BLU/);
});

test("Shelly detail uses the shared device dialog layout used by Tuya", () => {
  const detail = app.match(/function openShellyDeviceDetails\(deviceId\)\{[\s\S]*?\n\}/)?.[0] || "";
  assert.match(detail, /class="dialog-body"/);
  assert.match(detail, /class="dialog-header"/);
  assert.match(detail, /class="device-detail-grid"/);
  assert.match(detail, /class="dialog-actions"/);
  assert.match(detail, /data-shelly-light-on/);
  assert.match(detail, /data-shelly-brightness/);
  assert.doesNotMatch(detail, /device\.protocol|device\.model\}\s*·/);
});

test("Shelly inventory cards use the same compact layout and live only model-confirmed toggles", () => {
  assert.match(app, /data-shelly-card-state/);
  assert.match(app, /favorite-expand.*data-shelly-expand/);
  assert.match(app, /shelly_blu_gateway_gwf_kz01/);
  assert.match(app, /shelly_vintage_gen1/);
});
