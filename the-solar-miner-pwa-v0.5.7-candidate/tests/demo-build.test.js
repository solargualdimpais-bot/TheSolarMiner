import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const read = name => readFileSync(join(root, name), 'utf8');

test('v0.5.1 includes read-only Gateway diagnostics but no authentication or pairing client', () => {
  assert.equal(existsSync(join(root, 'api-client.js')), false);
  assert.equal(existsSync(join(root, 'auth-client.js')), false);
  const runtime = ['index.html','app.js','app-core.js','demo-mode.js','gateway-connection.js'].map(read).join('\n');
  for (const forbidden of ['GatewayApiClient','IndexedDbIdentityStore','pairDevice(','loginDevice(','issuePairingCode(','logoutDevice(','XMLHttpRequest','WebSocket','writeRegister','writeCoil']) {
    assert.equal(runtime.includes(forbidden), false, `unexpected auth/physical primitive: ${forbidden}`);
  }
  assert.match(runtime, /\/api\/v1\/health/);
  assert.match(runtime, /redirect: \"error\"/);
  assert.match(runtime, /identityValidated: false/);
});

test('all six areas remain navigable in desktop and mobile navigation', () => {
  const html = read('index.html');
  for (const id of ['inversores','baterias','mineradoras','ev','aqs','soalho-radiante']) assert.ok(html.includes(`data-page="${id}"`), id);
  assert.ok(html.includes('id="mobile-nav"'));
  assert.ok(html.includes('data-action="devices"'));
  assert.ok(html.includes('data-action="automations"'));
  assert.ok(read('app.js').includes('action==="automations"'));
  assert.ok(read('app.js').includes('populateMore'));
  assert.ok(read('app.js').includes('data-page=\"${esc(c.id)}\"'));
});


test('v0.5.4 shows AUTOMATISMOS directly in mobile navigation and migrates old saved preferences', () => {
  const html = read('index.html');
  const ui = read('workspace-ui.js');
  const app = read('app.js');
  assert.match(html, /data-action="automations"[^>]*>\s*<span>⟳<\/span>Automatismos/);
  assert.match(ui, /automations:'automatismos'/);
  assert.match(ui, /Migrate older per-user preference records/);
  assert.ok(app.includes('else if(action==="automations"){navigate("automatismos");}'));
  assert.match(read('styles.css'), /grid-template-columns:repeat\(6,minmax\(0,1fr\)\)/);
});

test('v0.5.4 keeps image data out of localStorage and restores photos from IndexedDB', () => {
  const ui = read('workspace-ui.js');
  assert.match(ui, /indexedDB\.open\(PHOTO_DB,1\)/);
  assert.match(ui, /makePhotoSafe\(workspace\)/);
  assert.match(ui, /__solarPhotoRef/);
  assert.match(ui, /export async function hydrateWorkspacePhotos\(\)/);
  assert.match(ui, /putPhotos\(photos\)/);
  assert.match(read('app.js'), /hydrateWorkspacePhotos\(\)/);
});

test('DEMO mode and simulated fixtures are explicit', () => {
  const html = read('index.html');
  const app = read('app.js');
  const core = read('app-core.js');
  assert.match(app, /DEMO · SIMULATED/);
  assert.match(app, /mode: "SIMULATED"/);
  assert.match(app, /NÃO.*comandos|Nada é enviado para equipamentos físicos/s);
  assert.match(core, /DEMO_FIXTURE/);
  assert.ok(read('demo-mode.js').includes('mode !== "SIMULATED"'));
});

test('property image controls only use browser-local storage and are removable', () => {
  const app = read('app.js');
  assert.ok(app.includes('workspace.house.photo=compressed'));
  assert.ok(app.includes('saveDemoWorkspace()'));
  assert.ok(read('workspace-ui.js').includes('indexedDB.open(PHOTO_DB,1)'));
  assert.ok(read('workspace-ui.js').includes('makePhotoSafe(workspace)'));
  assert.ok(app.includes('hydrateWorkspacePhotos'));
  assert.ok(!app.includes('localStorage.setItem("solar-miner-demo-property-photo-v1"'));
  assert.ok(app.includes('1400/Math.max'));
  assert.ok(read('index.html').includes('id="property-photo-file"'));
});

test('responsive breakpoints and safe-area bottom navigation are present', () => {
  const css = read('styles.css');
  assert.ok(css.includes('@media(max-width:680px)'));
  assert.ok(css.includes('@media(min-width:681px) and (max-width:850px)'));
  assert.ok(css.includes('env(safe-area-inset-bottom)'));
  assert.ok(css.includes('.mobile-nav'));
});

test('service worker caches only static demo assets and excludes API paths', () => {
  const sw = read('service-worker.js');
  assert.ok(sw.includes('demo-mode.js'));
  assert.ok(sw.includes('url.pathname.includes("/api/v1/")'));
  assert.ok(!sw.includes('api-client.js'));
  assert.ok(!sw.includes('auth-client.js'));
  assert.ok(!sw.includes('api-client.js'));
  assert.ok(!sw.includes('auth-client.js'));
});

test('Meta reference visual elements and basic interactions are present', () => {
  const html = read('index.html');
  const app = read('app.js');
  const css = read('styles.css');
  for (const id of ['weather-dialog','production-dialog','property-photo-file']) assert.ok(html.includes(id), id);
  for (const id of ['open-weather','open-production']) assert.ok(app.includes(id), id);
  for (const token of ['favoriteDeviceCards','data-fav-toggle','data-fav-range','function setSky','function miniChart']) assert.ok(app.includes(token), token);
  for (const token of ['#060608','#dcc99c','.reference-home-grid','.weather-options','.favorite-device-grid']) assert.ok(css.includes(token), token);
  assert.match(html, /Home<\/button>[\s\S]*Profile<\/button>[\s\S]*Energy<\/button>[\s\S]*Casa<\/button>[\s\S]*Devices<\/button>/);
});

test('live Home uses Gateway weather, solar history and owner-controlled Tuya favorites', () => {
  const app = read('app.js');
  const html = read('index.html');
  const runtime = ['index.html','app.js','app-core.js','demo-mode.js'].map(read).join('\n');
  assert.match(app, /SIMULATED/);
  assert.match(app, /forecast\?\.weather/);
  assert.match(app, /engine\.history\?\.pv_total_power/);
  assert.match(app, /controlGatewayTuyaSwitch/);
  assert.match(app, /controlGatewayTuyaLevel/);
  assert.match(app, /sessionInfo\(\)\.user\?\.role!=="owner"/);
  assert.doesNotMatch(runtime, /cdn\.jsdelivr\.net|chart\.js/i);
  assert.match(runtime, /CONNECTION_STATES/);
  assert.match(app, /state\.mode!=="SIMULATED"&&liveAreaPages\.includes/);
});
