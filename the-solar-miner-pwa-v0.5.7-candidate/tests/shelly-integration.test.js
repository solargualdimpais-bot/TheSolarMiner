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

test("Shelly controls go through authenticated Gateway APIs and confirm observed state", () => {
  assert.match(api, /\/api\/v1\/integrations\/shelly\/\$\{encodeURIComponent\(deviceId\)\}\/switch/);
  assert.match(app, /result\.command_confirmed/);
  assert.match(app, /confirmas que queres \$\{on\?/i);
});

test("AP onboarding remains explicitly unimplemented in this LAN delivery", () => {
  assert.match(app, /configuração inicial pela rede Wi-Fi própria do dispositivo ainda não está disponível/);
  assert.doesNotMatch(app, /fetch\(["']http:\/\/192\.168\.33\.1/);
});

test("BLU bridge compatibility is only reported after the Gateway probes the model-specific API", () => {
  assert.match(app, /deteção de sensores Bluetooth sem IP ainda não está concluída/);
  assert.match(app, /o procedimento de descoberta deste modelo ainda precisa de validação/);
  assert.match(backend, /def inspect_bluetooth_bridge/);
  assert.doesNotMatch(backend, /BTHome\.StartDeviceDiscovery/);
});
