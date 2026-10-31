import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const auth = readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
const worker = readFileSync(new URL("../service-worker.js", import.meta.url), "utf8");

test("property photo save is isolated from the full profile and requires Gateway confirmation", () => {
  assert.match(app, /saveGatewaySitePhoto\(\{kind:'house',floorId:'',roomId:'',photoDataUrl:editorPhoto\|\|null\}\)/);
  assert.match(app, /if\(\(savedProfile\.photo_data_url\|\|null\)!==\(editorPhoto\|\|null\)\)throw new Error\('site_photo_not_confirmed'\)/);
  assert.match(app, /let savedProfile=profileFieldsChanged\?await saveGatewaySiteProfile\(payload\):current/);
  assert.match(auth, /new Set\(\["house", "floor", "plan", "room"\]\)/);
  assert.match(worker, /"\.\/photo-format\.js"/);
});

test("photo failures are explained without closing the property editor", () => {
  assert.match(app, /site_photo_not_confirmed/);
  assert.match(app, /invalid_site_photo_size_or_format/);
  assert.match(app, /error\?\.status===413/);
  assert.match(app, /\$\('#context-editor-status'\)\.textContent=userFacingSaveError\(error\)/);
});
