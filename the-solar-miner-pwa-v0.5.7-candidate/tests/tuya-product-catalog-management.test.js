import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const gatewayAuth = readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
const gatewayApp = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/app.py", import.meta.url), "utf8");

test("Owner Tuya Device has nested cloud, devices, Product IDs and DPS sections", () => {
  for (const label of ["Conta cloud", "Dispositivos", "Product IDs", "DPS"]) assert.ok(app.includes(`\"${label}\"`));
  assert.match(app, /setupTuyaManagementSections\(\)/);
  assert.match(app, /tuya-product-catalog-list/);
  assert.match(app, /tuya-product-dps-list/);
  assert.match(app, /\.xlsx/);
  assert.match(app, /tuya-product-url-preview/);
});

test("Product catalog imports preview before applying and preserve selected conflicts", () => {
  assert.match(app, /previewGatewayTuyaProductImport\(source\)/);
  assert.match(app, /applyGatewayTuyaProductImport\(result\.profiles,excluded\)/);
  assert.match(app, /data-import-exclude/);
  assert.match(app, /Assinala as linhas com incongruências para as preservar como estão/);
  assert.match(gatewayAuth, /product-catalog\/preview/);
  assert.match(gatewayAuth, /product-catalog\/apply/);
  assert.match(gatewayApp, /"persisted": False/);
});

test("Imports are bounded and do not fetch private-network URLs or follow redirects", () => {
  assert.match(gatewayApp, /2_000_000/);
  assert.match(gatewayApp, /ipaddress\.ip_address\(address\)\.is_global/);
  assert.match(gatewayApp, /product_import_url_redirect_not_supported/);
  assert.match(gatewayApp, /product_import_no_supported_product_schemas/);
});
