import test from 'node:test';
import assert from 'node:assert/strict';
import { renderWorkspacePage, workspace } from '../workspace-ui.js';

test('v0.5.0 exposes seven independent energy areas',()=>{
  const summary=renderWorkspacePage('energia');
  for(const id of ['inversores','baterias','paineis-solares','ev','aqs','mineradoras','soalho-radiante']) assert.ok(summary.includes(`data-page="${id}"`),id);
});
test('initial photovoltaic configuration matches 8.94 kWp without claiming live production',()=>{
  const html=renderWorkspacePage('paineis-solares');
  assert.match(html,/8,94/);
  assert.match(html,/12 × 445 W \+ 6 × 600 W/);
  assert.match(html,/INDISPONÍVEL/);
});
test('battery view distinguishes configuration from unavailable telemetry',()=>{
  const html=renderWorkspacePage('baterias');
  assert.match(html,/SOC observado/);
  assert.match(html,/INDISPONÍVEL/);
  assert.match(html,/não é calculada energia utilizável/i);
});
test('house has a configurable floor-room-device hierarchy and simulated states',()=>{
  workspace.house.activeFloor='floor-ground';
  const html=renderWorkspacePage('casa');
  assert.match(html,/Rés do chão/);
  assert.match(html,/Sala de estar/);
  assert.match(html,/ILUSTRAÇÃO DEMO/);
  assert.match(html,/simulados/i);
  assert.ok(workspace.house.floors.every(f=>Array.isArray(f.rooms)));
});
test('profile keeps role and administration unconfirmed without Gateway support',()=>{
  const html=renderWorkspacePage('profile');
  assert.match(html,/PAPEL: DESCONHECIDO/);
  assert.match(html,/não define listagem\/criação de utilizadores/i);
  assert.match(html,/Guardar preferências/);
});
test('Engine offers distinct X/Y/Z scenarios but no real Gateway claims',()=>{
  const html=renderWorkspacePage('engine');
  for(const strategy of ['EXCEDENTE SOLAR','SOLAR + OBJETIVO AO PÔR DO SOL','URGÊNCIA + SOC MÍNIMO']) assert.ok(html.includes(strategy),strategy);
  assert.match(html,/INDISPONÍVEL/);
  assert.match(html,/não aplicada ao Gateway/);
});
test('workspace module contains no network, auth or physical command implementation',async()=>{
  const fs=await import('node:fs');const source=fs.readFileSync(new URL('../workspace-ui.js',import.meta.url),'utf8');
  assert.doesNotMatch(source,/fetch\s*\(|XMLHttpRequest|WebSocket|\/api\/v1\/|writeRegister|writeCoil|GatewayApiClient|loginDevice|pairDevice/i);
});
