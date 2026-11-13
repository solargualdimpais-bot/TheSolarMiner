import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const root = new URL("../../solarminer-gateway-code02-v0.6.9-candidate/", import.meta.url);
const app = fs.readFileSync(new URL("web/pwa/app.js", root), "utf8");
const api = fs.readFileSync(new URL("web/pwa/gateway-auth.js", root), "utf8");
const worker = fs.readFileSync(new URL("web/pwa/service-worker.js", root), "utf8");
const backend = fs.readFileSync(new URL("src/solarminer_gateway/app.py", root), "utf8");
const engine = fs.readFileSync(new URL("src/solarminer_gateway/user_automation.py", root), "utf8");

test("live Automatismos is a persistent Gateway feature, separate from the surplus manager", () => {
  assert.match(app, /function renderUserAutomationPage\(\)/);
  assert.match(app, /Este motor é independente da Gestão de excedentes/);
  assert.match(app, /createGatewayUserAutomation\(payload\)/);
  assert.match(app, /updateGatewayUserAutomation\(userAutomationEditingId,payload\)/);
  assert.match(backend, /@app\.get\("\/api\/v1\/automations"\)/);
  assert.match(backend, /@app\.post\("\/api\/v1\/automations"\)/);
  assert.match(engine, /CREATE TABLE IF NOT EXISTS user_automation_rules/);
});

test("automation API supports edits, deletion, dry-run, and owner authorization", () => {
  for (const operation of ["readGatewayUserAutomations", "createGatewayUserAutomation", "updateGatewayUserAutomation", "deleteGatewayUserAutomation", "dryRunGatewayUserAutomation"]) {
    assert.ok(api.includes(`function ${operation}`) || api.includes(` ${operation}(`), `${operation} wrapper is present`);
  }
  assert.match(backend, /@app\.post\("\/api\/v1\/automations\/dry-run"\)/);
  assert.match(backend, /require_permission\("manage_gateway"\)/);
  assert.match(backend, /_require_owner\(session, conn\)/);
});

test("local engine rejects stale Tuya inputs and dispatches explicit, bounded actions", () => {
  assert.match(engine, /MAX_STALENESS_SECONDS = 60/);
  assert.match(engine, /MAX_RULES = 100/);
  assert.match(engine, /not 1 <= len\(actions\) <= 8/);
  assert.match(backend, /_user_automation_loop\(\)/);
  assert.match(backend, /asyncio\.sleep\(5\)/);
  assert.match(backend, /pending_action_payload/);
  assert.match(backend, /attempts >= 12/);
  assert.match(backend, /control_tuya_switch\(config, action\["device_id"\], action\["on"\]/);
  assert.match(backend, /control_switch\(host, int\(device\.get\("generation"\) or 0\)/);
});

test("Owner menu exposes rule simulation, ordered actions, and execution history", () => {
  assert.match(app, /Simular condição/);
  assert.match(app, /Então executar estas ações, por ordem/);
  assert.match(app, /Execuções recentes/);
  assert.match(app, /Nenhum comando foi enviado/);
});

test("automation prototype exposes navigable tap and Tuya status menus without saving", () => {
  assert.match(app, /data-automation-menu="create"/);
  assert.match(app, /TOCAR PARA EXECUTAR/);
  assert.match(app, /QUANDO O STATUS DO DISPOSITIVO MUDA/);
  assert.match(app, /status-functions:/);
  assert.match(app, /status-value:/);
  assert.match(app, /A Cloud declarou um valor booleano, mas não forneceu um range explícito/);
  assert.match(app, /automation-prototype-save" disabled/);
});

test("Tuya status selector uses Portuguese capability names and hides technical schema metadata", () => {
  const statusMenu = app.slice(app.indexOf('if(view.startsWith("status-functions:"))'), app.indexOf('if(view.startsWith("status-value:"))'));
  assert.match(statusMenu, /tuyaFriendlyCapabilityLabel\(/);
  assert.match(statusMenu, /return \{title:label,action:/);
  assert.doesNotMatch(statusMenu, /subtitle:/);
  assert.match(app, /online_state:"Estado online"/);
  assert.match(app, /light_mode:"Modo da luz"/);
  assert.match(app, /declaredRange\.map\(value=>\(\{title:tuyaEnumValuePt\(value\)\}\)\)/);
  const header = app.slice(app.indexOf("function automationMenuHeader("), app.indexOf("function automationMenuRows("));
  assert.match(header, /aria-label="Voltar"/);
  assert.doesNotMatch(header, />‹ Voltar</);
  const css = fs.readFileSync(new URL("../../solarminer-gateway-code02-v0.6.9-candidate/web/pwa/styles.css", import.meta.url), "utf8");
  assert.match(css, /automation-prototype-header h2\{width:100%[^}]*text-align:center/);
});

test("status-device selector filters favorites, configured divisions, then all devices without manufacturer tabs", () => {
  assert.match(app, /automation-filter-pills" aria-label="Filtrar dispositivos"/);
  assert.match(app, /allButton\("favorites","Favoritos"\)/);
  assert.match(app, /favoriteIds\.has\(device\.device_id\)/);
  assert.match(app, /divisionFor\(device\)/);
  assert.match(app, /allButton\("all","Todos os dispositivos"\)/);
  assert.match(app, /status-filter:/);
  assert.doesNotMatch(app, /<span>Tuya<\/span>/);
});

test("static cache is versioned for the automation menu release", () => {
  assert.match(worker, /the-solar-miner-static-v0\.5\.175-tuya-lan-responsive-readback/);
});
