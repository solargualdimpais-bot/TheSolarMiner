import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { renderWorkspacePage, workspace } from '../workspace-ui.js';

const source = fs.readFileSync(new URL('../workspace-ui.js', import.meta.url), 'utf8');
const app = fs.readFileSync(new URL('../app.js', import.meta.url), 'utf8');

test('v0.5.2 CASA shows all configured rooms in Todos os pisos, with their own room identifiers and images', () => {
  workspace.house.activeFloor = null; workspace.house.activeRoom = null; workspace.house.activeDevice = null;
  const html = renderWorkspacePage('casa');
  assert.equal((html.match(/data-ws-editable="room"/g) || []).length, workspace.house.floors.reduce((n, f) => n + f.rooms.length, 0));
  for (const room of workspace.house.floors.flatMap(f => f.rooms)) assert.ok(html.includes(`data-room="${room.id}"`));
  assert.match(html, /Todos os pisos/);
  assert.match(html, /simulados/i);
});

test('v0.5.2 ENERGY provides all seven horizontal tabs on summary and equipment pages', () => {
  const ids = ['inversores','baterias','paineis-solares','ev','aqs','mineradoras','soalho-radiante'];
  for (const page of ['energia', ...ids]) {
    const html = renderWorkspacePage(page);
    for (const id of ids) assert.ok(html.includes(`data-page="${id}"`), `${page} should include tab ${id}`);
    assert.match(html, /ws-horizontal-tabs/);
  }
});

test('v0.5.2 DEVICES is a compact horizontal room selector and equipment list', () => {
  const html = renderWorkspacePage('devices');
  assert.match(html, /ws-horizontal-tabs/);
  assert.match(html, /role="tablist"/);
  assert.match(html, /ws-device-list/);
  assert.doesNotMatch(html, /ws-room-grid/);
  assert.match(html, /data-ws-action="open-device"/);
  assert.match(html, /data-ws-action="edit-device"/);
});

test('v0.5.2 contextual editor has one local-save path for house, room and device', () => {
  assert.match(source, /export function getEditableEntity/);
  assert.match(source, /export function saveEditableEntity/);
  assert.match(app, /setTimeout\(\(\)=>\{const context=editTargetFrom\(holdTarget\);/);
  assert.match(app, /},2000\)/);
  assert.match(app, /pointermove/);
  assert.match(app, /context-editor-preview/);
  assert.match(app, /As alterações ficam apenas neste browser\/instalação PWA/);
  assert.match(app, /saveGatewaySiteProfile\(payload\)/);
});

test('workspace editor stays local while authenticated Gateway settings use explicit API operations', () => {
  assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|WebSocket|\/api\/v1\/|writeRegister|writeCoil|GatewayApiClient/i);
  assert.match(source, /DEMO · dados de exemplo/);
  assert.match(app, /Nome e fotografia guardados no Gateway e partilhados com as outras PWA/);
  assert.match(app, /saveGatewayEnergyEngineConfig/);
  assert.match(app, /controlGatewayTuyaLevel/);
});
