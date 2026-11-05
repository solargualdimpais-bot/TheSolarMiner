import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const gatewayAuth = readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
const gatewayApp = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/app.py", import.meta.url), "utf8");

test("Tuya Owner has nested cloud, devices, Product IDs and DPS sections", () => {
  for (const label of ["Conta cloud", "Dispositivos", "Product IDs", "DPS"]) assert.ok(app.includes(`\"${label}\"`));
  assert.match(app, /tuya-product-catalog-list/);
  assert.match(app, /tuya-product-dps-list/);
  assert.match(app, /\.xlsx/);
});

test("Product import previews first and applies only non-excluded rows", () => {
  assert.match(gatewayAuth, /product-catalog\/preview/);
  assert.match(gatewayAuth, /product-catalog\/apply/);
  assert.match(app, /data-import-exclude/);
  assert.match(gatewayApp, /"persisted": False/);
  assert.match(gatewayApp, /product-catalog\/apply/);
});
