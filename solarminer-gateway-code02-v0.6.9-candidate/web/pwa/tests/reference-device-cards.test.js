import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const css = await readFile(new URL("../styles.css", import.meta.url), "utf8");

test("device-name detail opens the Shelly-reference Tuya card", () => {
  assert.match(app, /function openFavoriteDeviceDetails\([\s\S]*?if\(isTuya\)\{openTuyaReferenceDeviceCard\(deviceId\);return;\}/);
  assert.match(app, /\['bell','Notificações','notifications'\].*\['settings','Definições','settings'\]/);
  assert.match(app, /reference-rail.*Opções do dispositivo/);
});

test("reference cards include per-channel dimmer and ON/OFF layouts", () => {
  assert.match(app, /reference-dimmer-layout \$\{multi\?"is-multi":""\}/);
  assert.match(app, /reference-channel-grid \$\{channels\.length===2\?"is-two":""\}/);
  assert.match(app, /reference-group-action/);
  assert.match(app, /data-reference-brightness="\$\{esc\(dimmer\.code\)\}"/);
});

test("six-channel device popup keeps the 2-by-3 channel grid and group action", () => {
  assert.match(app, /channels\.map\(channelMarkup\)\.join\(""\)/);
  assert.match(app, /reference-channel-grid/);
  assert.match(app, /const groupAction=multi\?/);
  assert.match(css, /\.reference-channel-grid\{[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
});

test("breaker card shows the four requested readings without inventing zeroes", () => {
  assert.match(app, /\["Tensão","Corrente","Potência","Consumo diário"\]/);
  assert.match(app, /value!==null&&metric\.value!==undefined&&metric\.value!==""\?metric\.value:"Sem leitura"/);
});

test("Shelly dimmer uses a vertical slider, fades and locks while off", () => {
  assert.match(app, /shelly-slider-track \$\{lightIsOn\?"":"is-off"\}/);
  assert.match(app, /!connected\|\|!lightIsOn\?"disabled":""/);
  assert.match(css, /\.shelly-slider-track input\{[^}]*writing-mode:vertical-lr/);
});

test("reference cards use the specified palette and mobile-sized controls", () => {
  for (const token of ["#1a1a18", "#121211", "#3a3626", "#e3d3a6", "#9b9688"]) assert.ok(css.includes(token));
  assert.match(css, /\.reference-rail button\{[^}]*width:47px;height:48px/);
  assert.match(css, /\.reference-metric\{[^}]*border-radius:20px/);
});
