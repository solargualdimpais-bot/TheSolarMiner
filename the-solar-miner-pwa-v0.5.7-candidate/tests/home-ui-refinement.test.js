import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
const features = readFileSync(new URL("../features-v053.js", import.meta.url), "utf8");

test("Home production button opens a focused dialog with only the four KPI cards and detailed graph", () => {
  assert.match(app, /if\(e\.target\.closest\(\"#open-production\"\)\) openProductionDialog\(\)/);
  assert.match(app, /querySelector\(\'.ws-kpi-grid\'\)/);
  assert.match(app, /querySelector\(\'.feature-panel\'\)/);
  assert.match(app, /dialog\.showModal\(\)/);
  assert.match(features, /Produção real acumulada/);
  assert.match(features, /Potencial diário estimado/);
  assert.match(features, /Potencial restante/);
  assert.match(features, /Confiança/);
});

test("Profile font selector applies live scale on input and change", () => {
  assert.match(app, /function applyLiveFontScale\(\)/);
  assert.match(app, /applyLiveFontScale\(\);/);
  assert.match(css, /html\[data-font=\"xlarge\"\]/);
});

test("Home favorites expose local device controls and responsive typography", () => {
  assert.match(app, /data-favorite-toggle/);
  assert.match(app, /function toggleFavoriteDevice\(id\)/);
  assert.match(app, /saveDemoWorkspace\(\);render\(\)/);
  assert.match(css, /favorite-device-info strong\{font-size:clamp/);
  assert.match(css, /property-hero \.hero-content h1\{font-family:Georgia/);
});
