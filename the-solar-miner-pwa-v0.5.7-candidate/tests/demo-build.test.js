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

test('property image is empty until the Owner uploads it to the Gateway', () => {
  const app = read('app.js');
  assert.ok(app.includes('saveGatewaySiteProfile(payload)'));
  assert.ok(app.includes('const photo = state.siteProfile?.photo_data_url || ""'));
  assert.ok(app.includes('id="hero-photo-settings"'));
  assert.ok(app.includes('sessionInfo().user?.role===\'owner\''));
  assert.ok(!app.includes('function readStoredPhoto'));
  assert.ok(!app.includes('workspace.house.photo=compressed'));
  assert.ok(!app.includes('Ambiente demonstrativo ativo.'));
  assert.ok(app.includes('maxDimension=1400'));
  assert.ok(app.includes('photoTransparency'));
  assert.ok(app.includes('photo_opacity'));
  assert.ok(!read('index.html').includes('id="property-photo-file"'));
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
  for (const id of ['weather-dialog','production-dialog','property-hero-host']) assert.ok(html.includes(id), id);
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

test('live Home uses compact square weather and production cards with a lighter house title', () => {
  const css = read('styles.css');
  assert.match(css, /\.home-weather-row\{[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /\.home-weather-card,\.home-production-card\{[^}]*aspect-ratio:1\/1/);
  assert.match(css, /\.live-property-hero \.home-property-name\{[^}]*font-weight:300/);
  assert.match(css, /\.live-property-hero\{[^}]*border-radius:0!important/);
  assert.match(css, /\.live-property-hero \.hero-shade\{[^}]*radial-gradient\(ellipse at center/);
  assert.match(css, /\.home-weather-values strong,\.home-production-value\{[^}]*font-size:clamp\(24px,2\.3vw,32px\)/);
  assert.match(css, /\.main-content \.home-weather-card,\.main-content \.home-production-card\{aspect-ratio:1\/1/);
  assert.match(css, /\.main-content \.home-weather-row\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /\.main-content \.live-property-hero\.has-property-photo::before[^}]*opacity:var\(--property-photo-opacity/);
});

test('Owner photo editor stores framing and weather card renders a condition icon', () => {
  const app=read('app.js'),html=read('index.html'),css=read('styles.css');
  for(const field of ['photo_position_x','photo_position_y','photo_zoom','photo_vignette']) assert.ok(app.includes(field),field);
  assert.match(app,/pointermove/);
  assert.match(app,/weather-condition-icon/);
  assert.match(app,/home-weather-condition/);
  assert.match(html,/context-editor-preview-vignette/);
  assert.match(css,/\.weather-condition-icon\{[^}]*width:25px/);
});

test('live history chart uses consumption bars and solid or dotted production/potential lines',()=>{
  const app=read('app.js');
  assert.match(app,/solar-window-chart/);
  assert.match(app,/stroke-dasharray="3 6"/);
  assert.match(app,/Produção/);
  assert.match(app,/Produção potencial/);
  assert.match(app,/data-load=/);
  assert.match(app,/Produção efetiva:/);
  assert.match(app,/kW/);
  assert.doesNotMatch(app,/FV medida \/ prevista|Consumo medido \/ previsto|Potencial FV pela meteorologia/);
});
