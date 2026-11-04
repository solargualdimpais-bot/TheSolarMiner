import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");

test("miner configuration exposes breaker association and first-load setup", () => {
  assert.match(app, /data-miner-section="config"[\s\S]*?renderMinerBreakerAssociation\(\)/);
  assert.match(app, /renderLoadBuilder\("miner"\)/);
  assert.match(app, /Associar disjuntor e registar mineradora/);
  assert.match(app, /data-miner-breaker-save=/);
});

test("surplus manager can add a load and persists it through the Gateway API", () => {
  assert.match(app, /data-surplus-panel="loads"[\s\S]*?renderLoadBuilder\(\)/);
  assert.match(app, /saveGatewayEnergyEngineConfig\(\{loads:\[\.\.\.loads,load\]\}\)/);
  assert.match(app, /O Gateway não confirmou que a carga ficou guardada/);
});

test("Home labels measured miner power as coming from the associated breaker", () => {
  assert.match(app, /Disjuntor · potência medida/);
  assert.match(app, /Disjuntor · sem leitura recente/);
});

test("miner name and characteristics are saved as one canonical inventory identity", () => {
  assert.match(app, /data-miner-load-save=/);
  assert.match(app, /O Gateway não confirmou todas as alterações/);
  assert.match(app, /state\.equipment\|\|\[\]\)if\(item\.category==="mineradoras"/);
  assert.match(app, /linked\?\.device_key/);
  assert.match(app, /state\.energyConfigStatus=`\$\{name\}: nome e características guardados no dispositivo e no inventário\.`/);
});

test("periodic energy refresh does not redraw miner and load configuration pages", () => {
  assert.match(app, /!\["mineradoras","gestao-excedentes"\]\.includes\(state\.page\)/);
  assert.match(app, /antminerActiveSubmenu!=="config"\?"hidden":""/);
});

test("registered miners have individual named tabs and unsupported machines stay read-only", () => {
  assert.match(app, /registeredMiners\.length\?`<nav class="ws-horizontal-tabs miner-equipment-tabs"/);
  assert.match(app, /data-miner-equipment-select=/);
  assert.match(app, /data-miner-section="state"/);
  assert.match(app, /equipmentConnectionIsLive\(activeMiner\)/);
  assert.match(app, /não são apresentados comandos que poderiam atingir outra máquina/);
  assert.match(app, /activeMiner\?\.name/);
  assert.match(app, /<details class="miner-load-editor" open>/);
});

test("historical chart does not backfill future forecasts into missing past measurements", () => {
  assert.match(app, /return before\?\.value;\};/);
  assert.doesNotMatch(app, /return before\?\.value\?\?after\?\.value/);
});

test("miner page only shows the named miner tabs, and the situation power comes from its Tuya breaker", () => {
  assert.match(app, /const equipmentCards=page==="mineradoras"\?"":/);
  assert.match(app, /function minerAssociatedBreakerReading\(miner, loads, registeredMinerCount\)/);
  assert.match(app, /telemetry\[load\.id\].*load\.tuya_device_id/);
  assert.match(app, /Potência · disjuntor Tuya/);
  assert.match(app, /filter\(item=>!\["miner_power_w","miner_power"\]/);
});

test("miner commands submenu includes an authenticated power target action", () => {
  assert.match(app, /data-miner-section="commands"[^`]*Alvo de potência \(W\)/);
  assert.match(app, /id="antminer-section-apply-watt"/);
  assert.match(app, /writeGatewayAntminerManagement\("set_power_target",\{watt\}\)/);
});

test("Tuya toggle keeps Home and Devices in place through command confirmation", () => {
  assert.match(app, /const recentTuyaSwitchCommands=new Map\(\)/);
  assert.match(app, /recentTuyaSwitchCommands\.set\(device\.device_id,requestedAt\+5_000\)/);
  assert.match(app, /for\(const deviceId of deviceIds\)\{updateVisibleTuyaCard\(deviceId\);updateOpenTuyaDeviceDialog\(deviceId\);\}/);
  assert.match(app, /finally\{favoriteControlPending\.delete\(deviceId\);document\.querySelectorAll\(`\[data-favorite-toggle=/);
  assert.doesNotMatch(app, /finally\{favoriteControlPending\.delete\(deviceId\);updateVisibleTuyaCard\(deviceId\);\}/);
});
