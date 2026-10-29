import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");

test("Energy exposes the surplus manager as a navigable submenu and standalone demo", () => {
  assert.match(app, /gestao-excedentes/);
  assert.match(app, /function renderSurplusManager\(\)/);
  assert.match(app, /DEMO · SEM GATEWAY/);
  assert.match(app, /surplus-demo-run/);
  assert.match(app, /Esta demonstração não envia comandos a equipamentos/);
  assert.match(html, /data-page="energia"/);
});

test("surplus manager saves Owner policy and states physical integration limits", () => {
  assert.match(app, /saveGatewayEnergyEngineConfig\(\{surplus_manager:manager,automation\}\)/);
  assert.match(app, /manual_override:resume\?false:Boolean\(oldManager\.manual_override\)/);
  assert.match(app, /telemetria real e dispositivos configurados continuam a limitar o comando/);
  assert.match(app, /API Tesla configurada neste software ainda é só de leitura/);
});
