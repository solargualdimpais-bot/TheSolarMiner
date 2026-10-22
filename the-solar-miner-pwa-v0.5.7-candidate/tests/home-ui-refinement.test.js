import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
const features = readFileSync(new URL("../features-v053.js", import.meta.url), "utf8");

test("Home production button opens a focused dialog with only the four KPI cards and detailed graph", () => {
  assert.match(app, /if\(e\.target\.closest\(\"#open-production\"\)\) openProductionDialog\(\)/);
  assert.match(app, /querySelector\(\'.ws-kpi-grid\'\)/);
  assert.match(app, /querySelector\(\'.feature-panel\'\)/);
  assert.match(app, /dialog\.showModal\(\)/);
  assert.match(features, /Produção real acumulada/);
  assert.match(features, /Potencial diário estimado/);
  assert.match(features, /Potencial restante/);
  assert.match(features, /Confiança/);
});

test("Profile font selector applies live scale on input and change", () => {
  assert.match(app, /function applyLiveFontScale\(\)/);
  assert.match(app, /applyLiveFontScale\(\);/);
  assert.match(css, /html\[data-font=\"xlarge\"\]/);
});

test("Home favorites expose local device controls and responsive typography", () => {
  assert.match(app, /data-favorite-toggle/);
  assert.match(app, /function toggleFavoriteDevice\(id\)/);
  assert.match(app, /saveDemoWorkspace\(\);render\(\)/);
  assert.match(css, /favorite-device-info strong\{font-size:clamp/);
  assert.match(css, /property-hero \.hero-content h1\{font-family:Georgia/);
});

test("Shared property photograph and menu title render above every PWA page", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const auth = readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
  assert.match(html, /id="property-hero-host"/);
  assert.match(app, /propertyHost\.innerHTML=renderHomePhotoHero/);
  assert.match(app, /function renderHomePhotoHero\(menuTitle = "Home"\)/);
  assert.match(app, /sessionInfo\(\)\.authenticated && sessionInfo\(\)\.user\?\.role === "owner"/);
  assert.match(auth, /gatewayApi\("\/api\/v1\/site\/profile"\)/);
  assert.match(auth, /saveGatewaySiteProfile/);
});

test("Live house structure is Gateway-backed and editing controls are Owner-only", () => {
  const gateway = readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/src/solarminer_gateway/app.py", import.meta.url), "utf8");
  assert.match(app, /function renderGatewayHousePage\(\)/);
  assert.match(app, /data-site-action="add-floor"/);
  assert.match(app, /data-site-action="add-room"/);
  assert.match(app, /sessionInfo\(\)\.user\?\.role!=="owner"\)return/);
  assert.match(app, /saveGatewaySiteProfile\(\{\.\.\.current,floors\}\)/);
  assert.match(gateway, /site\.profile\.configure/);
});

test("Any authenticated PWA can manage its favorites and choose registered Gateway equipment", () => {
  assert.match(app, /const canUsePwa=sessionInfo\(\)\.authenticated/);
  assert.match(app, /const canControl=canUsePwa&&sessionInfo\(\)\.user\?\.role==="owner"/);
  assert.match(app, /favoriteDeviceIds=favorites\.filter\(id=>all\.some\(item=>item\.id===id\)\)/);
  assert.match(app, /state\.equipment\|\|\[\]/);
  assert.match(app, /Adicionar aos meus favoritos/);
  assert.match(app, /const owner=sessionInfo\(\)\.authenticated&&sessionInfo\(\)\.user\?\.role==="owner"/);
  assert.match(app, /Só o Owner pode registar ou configurar dispositivos no Gateway/);
});
