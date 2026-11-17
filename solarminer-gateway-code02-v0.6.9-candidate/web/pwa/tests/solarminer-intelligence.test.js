import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = name => readFileSync(new URL(`../${name}`, import.meta.url), 'utf8');
const html = read('index.html');
const app = read('app.js');
const auth = read('gateway-auth.js');

test('Owner has an Intelligence panel with protected provider setup and read-only scope disclosure', () => {
  assert.match(html, /data-owner-tab="intelligence"/);
  assert.match(html, /data-owner-panel="intelligence"/);
  assert.match(html, /gateway-intelligence-api-key/);
  assert.match(html, /gateway-intelligence-model/);
  assert.match(html, /gateway-intelligence-question/);
  assert.match(html, /previsões e histórico do Energy Engine/i);
  assert.match(html, /Gera uma revisão diária com propostas baseadas em evidência/i);
  assert.match(html, /gateway-intelligence-reviews-refresh/);
  assert.match(html, /não envia comandos físicos/i);
});

test('PWA uses authenticated Gateway endpoints for provider setup, revocation and analysis', () => {
  assert.match(auth, /\/api\/v1\/intelligence\/provider/);
  assert.match(auth, /\/api\/v1\/intelligence\/ask/);
  assert.match(auth, /saveGatewayIntelligenceProvider\(apiKey, model\)/);
  assert.match(auth, /revokeGatewayIntelligenceProvider/);
  assert.match(auth, /askGatewayIntelligence/);
  assert.match(auth, /readGatewayIntelligenceReviews/);
  assert.match(app, /refreshGatewayIntelligenceProvider/);
  assert.match(app, /refreshGatewayIntelligenceReviews/);
  assert.match(app, /key\.value = ""/);
  assert.match(app, /answer\.textContent = result\.answer/);
  assert.doesNotMatch(app, /innerHTML\s*=\s*result\.answer/);
});
