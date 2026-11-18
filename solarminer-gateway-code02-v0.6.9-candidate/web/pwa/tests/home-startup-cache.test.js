import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const root = new URL("../", import.meta.url);
const read = name => readFileSync(new URL(name, root), "utf8");

test("Home startup cache stores the property header photo and safe device display metadata", () => {
  const app = read("app.js");
  const cache = read("home-startup-cache.js");
  assert.match(app, /function homeDisplaySnapshot\(\)/);
  assert.match(app, /photo_data_url:typeof profile\.photo_data_url===\"string\"\?profile\.photo_data_url:\(previous\.site\?\.photo_data_url\|\|\"\"\)/);
  assert.match(app, /function cachedHomeDevice\(raw,kind,id\)/);
  assert.match(app, /name:String\(raw\?\.name\|\|raw\?\.friendly_name\|\|raw\?\.model\|\|kind\)/);
  assert.match(app, /const displayProfile=state\.siteProfile\|\|\{\},cachedProfile=state\.startupHomeCache\?\.site\|\|\{\}/);
  assert.match(app, /const photo = displayProfile\.photo_data_url \|\| cachedProfile\.photo_data_url \|\| ""/);
  assert.match(cache, /indexedDB\.open\(DB_NAME, VERSION\)/);
  assert.match(cache, /90 \* 24 \* 60 \* 60 \* 1000/);
});

test("cached Home favorites are display-only and controls stay tied to live Gateway inventory", () => {
  const app = read("app.js");
  const snapshot = app.match(/function homeDisplaySnapshot\(\)\{([\s\S]*?)\n\}/)?.[1] || "";
  assert.match(snapshot, /state\.equipment/);
  assert.match(snapshot, /state\.tuyaDevices/);
  assert.match(snapshot, /state\.shellyDevices/);
  assert.doesNotMatch(snapshot, /readings|bearer|token|password|authorization/i);
  assert.match(app, /if\(state\.mode!==\"LIVE\"\)[\s\S]*favorite-device-cache/);
  assert.doesNotMatch(app, /Guardado · a atualizar/);
  assert.match(app, /data-favorite-toggle/);
  assert.match(app, /data-shelly-switch/);
  assert.match(app, /void hydrateHomeDisplayCache\(\)/);
});

test("the service worker versions and precaches the new Home cache module", () => {
  const sw = read("service-worker.js");
  assert.match(sw, /the-solar-miner-static-v0\.5\.191-intelligence-timeout/);
  assert.match(sw, /\.\/home-startup-cache\.js/);
});
