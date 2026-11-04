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
