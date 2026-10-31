import test from "node:test";
import assert from "node:assert/strict";
import { DEMO_CONTROL_CONFIG, createDemoControlState, updateDemoControl, toggleDemoControl } from "../demo-mode.js";
import { readFile } from "node:fs/promises";

test("the demo exposes exactly the six required areas and local controls",()=>{
  assert.deepEqual(Object.keys(DEMO_CONTROL_CONFIG),["inversores","baterias","mineradoras","ev","aqs","soalho-radiante"]);
  const state=createDemoControlState();
  assert.equal(state.evEnabled,false);
  assert.equal(state.batteryReserve,20);
  assert.equal(state.floorTarget,21.5);
});
test("numeric demo controls change only local state when mode is SIMULATED",()=>{
  const state=createDemoControlState();
  assert.equal(updateDemoControl("SIMULATED",state,"batteryReserve",45),true);
  assert.equal(state.batteryReserve,45);
  assert.equal(updateDemoControl("SIMULATED",state,"aqsTarget",54),true);
  assert.equal(state.aqsTarget,54);
  assert.equal(updateDemoControl("SIMULATED",state,"solarLimit",50),false);
  assert.equal(state.solarLimit,5);
});
test("demo controls reject real mode, invalid keys, non-finite values and invalid steps",()=>{
  const state=createDemoControlState();
  assert.equal(updateDemoControl("REAL",state,"batteryReserve",50),false);
  assert.equal(updateDemoControl("REAL_UNAVAILABLE",state,"batteryReserve",50),false);
  assert.equal(updateDemoControl("SIMULATED",state,"unknown",1),false);
  assert.equal(updateDemoControl("SIMULATED",state,"minerLoad",NaN),false);
  assert.equal(updateDemoControl("SIMULATED",state,"minerLoad",32),false);
  assert.equal(updateDemoControl("SIMULATED",state,"evEnabled",1),false);
  assert.equal(state.minerLoad,70);
});
test("EV demo toggle is local-only and cannot change outside SIMULATED",()=>{
  const state=createDemoControlState();
  assert.equal(toggleDemoControl("REAL",state,"evEnabled"),false);
  assert.equal(state.evEnabled,false);
  assert.equal(toggleDemoControl("SIMULATED",state,"evEnabled"),true);
  assert.equal(state.evEnabled,true);
  assert.equal(toggleDemoControl("SIMULATED",state,"evEnabled"),true);
  assert.equal(state.evEnabled,false);
});
test("demo module has no network, Gateway or physical-command dependencies",async()=>{
  const source=await readFile(new URL("../demo-mode.js",import.meta.url),"utf8");
  assert.doesNotMatch(source,/fetch\s*\(|XMLHttpRequest|WebSocket|GatewayApiClient|pairDevice|loginDevice|Modbus|\/api\/v1\//i);
});
test("demo UI labels controls as local and does not expose command endpoints",async()=>{
  const app=await readFile(new URL("../app.js",import.meta.url),"utf8");
  assert.match(app,/state\.mode!=="SIMULATED"/);
  assert.match(app,/DEMO · NÃO É UM COMANDO REAL/);
  assert.doesNotMatch(app,/\/api\/v1\/commands|\/api\/v1\/control|writeRegister|writeCoil/i);
});
test("property image comes from the Gateway and is only changed by the Owner",async()=>{
  const app=await readFile(new URL("../app.js",import.meta.url),"utf8");
  assert.match(app,/function readAndCompressImage/);
  assert.match(app,/saveGatewaySiteProfile\(payload\)/);
  assert.match(app,/state\.siteProfile\?\.photo_data_url \|\| ""/);
  assert.match(app,/Só o Owner pode alterar os dados partilhados da propriedade/);
  assert.doesNotMatch(app,/function readStoredPhoto/);
  assert.match(app,/canvas\.toBlob\(done,'image\/jpeg',quality\)/);
  assert.match(app,/maxDimension=Math\.round\(maxDimension\*\.8\)/);
  assert.match(app,/URL\.createObjectURL\(file\)/);
  assert.match(app,/photo_opacity/);
});
test("static cache includes demo module but never caches API responses",async()=>{
  const sw=await readFile(new URL("../service-worker.js",import.meta.url),"utf8");
  assert.match(sw,/demo-mode\.js/);
  assert.match(sw,/url\.pathname\.includes\("\/api\/v1\/"\)/);
});
