import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
const auth = readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
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

test("Home favorite controls use a centered plus-only add button and the open-ring power symbol", () => {
  assert.match(app, /class="favorite-add-button" id="home-favorite-plus"/);
  assert.match(css, /\.home-favorites \.favorite-manage\{flex-direction:column;justify-content:center/);
  assert.match(css, /\.home-favorites \.favorite-add-button\{display:grid;place-items:center;width:40px;height:40px;padding:0;border:0;border-radius:0/);
  assert.match(app, /const powerGlyph=`<svg viewBox="0 0 28 28"[^`]*M19\.25 4\.9a10\.5 10\.5 0 1 1-10\.5 0/);
  assert.match(css, /\.home-favorites \.favorite-state-symbol\.on\{border:0;background:transparent;color:var\(--gold\)/);
  assert.match(css, /\.home-favorites \.favorite-state-symbol\{width:40px;height:40px;flex-basis:40px;border:0;border-radius:0/);
});

test("Casa reuses the exact shared property photo hero used by every operational menu", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const auth = readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
  assert.match(html, /id="property-hero-host"/);
  assert.match(app, /propertyHost\.innerHTML=renderHomePhotoHero\(state\.page==="inicio"\?"Home":pageLabel\(state\.page\)\)/);
  assert.match(app, /function renderHomePhotoHero\(menuTitle = "Home"\)/);
  assert.match(app, /class="property-hero \$\{photoStyle\} live-property-hero shared-property-hero/);
  assert.match(app, /gateway-house-floor-nav/);
  assert.doesNotMatch(app, /class="property-hero \$\{photoStyle\} live-property-hero shared-property-hero gateway-house-hero/);
  assert.match(app, /property-hero-image" src=/);
  assert.match(app, /photo_opacity/);
  assert.match(app, /photo_vignette/);
  assert.match(app, /sessionInfo\(\)\.authenticated && sessionInfo\(\)\.user\?\.role === "owner"/);
  assert.match(auth, /gatewayApi\("\/api\/v1\/site\/profile"\)/);
  assert.match(auth, /saveGatewaySiteProfile/);
});

test("Gateway Casa provides floor and room navigation with Gateway-persisted floor plans and room photos", () => {
  assert.doesNotMatch(app, /CASA · GUARDADA NO GATEWAY|Pisos, divisões e plantas partilhados com as tuas sessões\.|data-action="edit-house">Editar casa/);
  assert.match(app, /data-house-general="true"/);
  assert.match(app, /data-house-select-floor=.*data-house-view="overview"/);
  assert.match(app, /data-house-room-floor=/);
  assert.doesNotMatch(app, /aria-label="Secções da casa"/);
  assert.doesNotMatch(app, /gateway-house-summary/);
  assert.doesNotMatch(app, /gateway-house-quick-grid/);
  assert.match(app, /if\(houseGeneral\)\{houseView\.floorId=null;houseView\.roomId=null;houseView\.tab="overview"/);
  assert.match(app, /data-site-action="upload-plan"/);
  assert.match(app, /data-site-action="upload-room-photo"/);
  assert.match(app, /floor\.plan_data_url=photo/);
  assert.match(app, /room\.photo_data_url=photo/);
  assert.match(app, /data-site-plan-zoom/);
  assert.match(css, /\.gateway-house-plan-tiles/);
  assert.match(css, /\.gateway-house-floor-tabs/);
  assert.match(css, /main-content \.live-property-hero \.property-hero-image\{[^}]*border-radius:inherit/);
  assert.match(css, /\.main-content \.live-property-hero\{border-radius:24px!important\}/);
  assert.match(css, /\.main-content \.live-property-hero \.hero-shade\{background:radial-gradient[\s\S]*linear-gradient\(0deg/);
});

test("Casa floor buttons have a restrained lifted shadow and tactile press state", () => {
  assert.match(css, /\.gateway-house-floor-chip\{box-shadow:0 2px 5px rgba\(0,0,0,\.24\),inset 0 1px 0/);
  assert.match(css, /\.gateway-house-floor-chip\.active\{box-shadow:0 3px 8px/);
  assert.match(css, /\.gateway-house-floor-chip:hover\{transform:translateY\(-1px\)/);
  assert.match(css, /\.gateway-house-floor-chip:active\{transform:translateY\(0\)/);
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
  assert.match(app, /const canUsePwa=sessionInfo\(\)\.authenticated,canControl=canUsePwa&&sessionInfo\(\)\.user\?\.role==="owner"/);
  assert.match(app, /favoriteDeviceIds=favorites\.filter\(id=>all\.some\(item=>item\.id===id\)\)/);
  assert.match(app, /state\.equipment\|\|\[\]/);
  assert.match(app, /Adicionar aos meus favoritos/);
  assert.match(app, /const owner=sessionInfo\(\)\.authenticated&&sessionInfo\(\)\.user\?\.role==="owner"/);
  assert.match(app, /Só o Owner pode registar ou configurar dispositivos no Gateway/);
});

test("Tuya device editor opens a Gateway event log for state, availability and automated actions", () => {
  assert.match(auth, /readGatewayTuyaDeviceEvents/);
  assert.match(app, /data-tuya-events=/);
  assert.match(app, /data-tuya-event-list=/);
  assert.match(app, /automation_action/);
  assert.match(app, /Dispositivo indisponível na LAN/);
  assert.match(app, /A carregar registo local do Gateway/);
  assert.match(auth, /discoverGatewayTuyaLanDevices/);
  assert.match(app, /tuya-lan-discovery/);
  assert.match(app, /esc\(item\.ip\)/);
});

test("Energy page shows Gateway daily solar estimate and battery energy above cut-off", () => {
  assert.match(app, /engine\.forecast\?\.solar_day/);
  assert.match(app, /Produção solar prevista até ao fim do dia/);
  assert.match(app, /battery_energy_available_kwh_above_minimum/);
  assert.match(app, /Energia disponível até ao corte/);
  assert.doesNotMatch(app, /battery_energy_consumed_since_maximum_kwh/);
});
