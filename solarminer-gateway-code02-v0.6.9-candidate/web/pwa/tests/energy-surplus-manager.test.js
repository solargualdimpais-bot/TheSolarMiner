import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");

test("Energy exposes the surplus manager as a navigable submenu and standalone demo", () => {
  assert.match(app, /gestao-excedentes/);
  assert.match(app, /function renderSurplusManager\(\)/);
  assert.match(app, /DEMO · SEM COMANDOS/);
  assert.match(app, /surplus-demo-run/);
  assert.match(app, /A demonstração não comunica com equipamentos/);
  assert.match(html, /data-page="energia"/);
});

test("surplus manager saves Owner policy and states physical integration limits", () => {
  assert.match(app, /saveGatewayEnergyEngineConfig\(\{surplus_manager:manager,automation\}\)/);
  assert.match(app, /manual_override:resume\?false:Boolean\(oldManager\.manual_override\)/);
  assert.match(app, /Tesla ainda sem controlo de carregamento/);
});

test("surplus manager separates state, existing loads, device links, priorities and rules", () => {
  assert.match(app, /const tabs=\[\["status","Estado"\],\["loads","Cargas"\],\["links","Ligações e mapas"\],\["priority","Prioridades"\],\["rules","Regras"\]\]/);
  assert.match(app, /data-surplus-tab="\$\{id\}"/);
  assert.match(app, /loads=\(config\.loads\|\|\[\]\)\.filter/);
  assert.match(app, /data-surplus-panel="links"/);
  assert.match(app, /PROTOCOLOS E MAPAS/);
  assert.match(app, /ORDEM APLICADA PELO GATEWAY/);
});

test("surplus manager saves per-load priorities and offers a manual ordering profile", () => {
  assert.match(app, /data-load-priority=/);
  assert.match(app, /id="surplus-save-priorities"/);
  assert.match(app, /value="custom"[\s\S]*?Personalizada · usar os números abaixo/);
  assert.match(app, /saveGatewayEnergyEngineConfig\(\{loads,surplus_manager:surplusManager\}\)/);
});
