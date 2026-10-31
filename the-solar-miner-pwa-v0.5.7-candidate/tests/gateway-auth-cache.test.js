import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const auth = readFileSync(new URL("../gateway-auth.js", import.meta.url), "utf8");
const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const sw = readFileSync(new URL("../service-worker.js", import.meta.url), "utf8");
const connection = readFileSync(new URL("../gateway-connection.js", import.meta.url), "utf8");

test("device private key is re-imported non-extractable and bearer is memory-only", () => {
  assert.match(auth, /importKey\("pkcs8", privateDer, \{ name: "Ed25519" \}, false, \["sign"\]\)/);
  assert.match(auth, /privateDer\.fill\(0\)/);
  assert.match(auth, /let bearerToken = null/);
  assert.doesNotMatch(auth, /localStorage\.setItem\([^\n]*(?:token|bearer|authorization)/i);
  assert.match(auth, /cache: "no-store"/);
  assert.match(auth, /credentials: "omit"/);
});

test("first Owner uses the local install password and later sessions use the device key", () => {
  assert.match(auth, /verifyGatewayIdentityChallenge\(invite, challenge\)/);
  assert.match(auth, /bootstrapGatewayOwner/);
  assert.match(auth, /bootstrap_password_invalid/);
  assert.match(auth, /\/api\/v1\/auth\/device-login/);
  assert.match(auth, /DEVICE-LOGIN/);
  assert.match(auth, /\/api\/v1\/invites\/redeem/);
  assert.match(app, /gateway-create-invite-form/);
  assert.match(app, /refreshInviteList/);
  assert.match(app, /revokeGatewayInvite/);
  assert.match(html, /id="gateway-bootstrap-dialog"/);
  assert.match(html, /id="gateway-bootstrap-form"/);
  assert.match(html, /id="gateway-endpoint"/);
  assert.doesNotMatch(html, /gateway-login-form|gateway-redeem-form|gateway-bootstrap-token|gateway-bootstrap-fingerprint/);
  assert.match(connection, /signGatewayLogin/);
});

test("new browser sign-in sends password only to the HTTPS Gateway and stores device key, not credentials", () => {
  assert.match(auth, /\/api\/v1\/auth\/password-device-login/);
  assert.match(auth, /PASSWORD-DEVICE-LOGIN/);
  assert.match(auth, /identityDbRequest\("readwrite", store => store\.put\(identity\)\)/);
  assert.doesNotMatch(auth, /localStorage\.setItem\([^\n]*(?:password|username)/i);
  assert.match(app, /loginGatewayWithPassword/);
  assert.match(app, /loginGateway\(\{ gatewayUrl: endpoint\.origin \}\)/);
  assert.match(app, /gateway-password-login-form/);
  assert.match(html, /id="gateway-login-username"/);
  assert.match(html, /id="gateway-login-password"/);
  assert.match(app, /password\.value = ""/);
  assert.match(sw, /password-device-login/);
});

test("invite QR is generated in the PWA and opens its one-time account activation form", () => {
  assert.match(app, /buildInviteLandingUrl\(/);
  assert.match(app, /tailscale\?\.https_ready !== true/);
  assert.match(app, /const gateways = \[tailscale\.endpoint\]/);
  const inviteHandler = app.split('$("#gateway-create-invite-form")')[1].split('$("#gateway-invite-list")')[0];
  assert.doesNotMatch(inviteHandler, /localStorage|gateway-lan-endpoint/);
  assert.match(app, /globalThis\.qrcode\(0, "M"\)/);
  assert.match(app, /redeemGatewayInvite\(/);
  assert.match(app, /readInviteLandingHash\(location\.hash\)/);
  assert.match(html, /id="gateway-invite-activation-form"/);
  assert.match(html, /id="gateway-invite-password"/);
  assert.match(sw, /qrcode-generator\.js/);
  assert.match(auth, /invite\.gatewayUrls/);
});

test("terminal WebSocket honors the confirmed Tailscale HTTPS route", () => {
  assert.match(auth, /const access = await readGatewayTailscale\(\)/);
  assert.match(auth, /access\?\.https_ready === true/);
  assert.match(auth, /socketBase = validateGatewayUrl\(access\.endpoint\)\.origin/);
  assert.match(auth, /new URL\("\/api\/v1\/system\/terminal\/ws", socketBase\)/);
});

test("service worker only caches allowlisted static resources and versions cache explicitly", () => {
  assert.match(sw, /the-solar-miner-static-v0\.5\.77-device-inventory-normalization/);
  assert.match(sw, /\.\/favorite-list\.js/);
  assert.match(sw, /url\.pathname\.includes\("\/api\/v1\/"\)/);
  assert.match(sw, /request\.headers\.has\("Authorization"\)/);
  assert.match(sw, /request\.headers\.has\("Cookie"\)/);
  assert.match(sw, /!STATIC_PATHS\.has\(url\.pathname\)/);
  assert.match(sw, /CACHE_PREFIXES/);
  assert.match(sw, /503/);
  assert.doesNotMatch(sw, /caches\.match\("\.\/index\.html"\)/);
});

test("completed Gateway update reports the target version and distinguishes the previous version", () => {
  assert.match(app, /status==="COMMITTED"[\s\S]{0,220}result\?\.target_version\|\|result\?\.details\?\.pipeline\?\.target_version/);
  assert.match(app, /versão \$\{previous&&previous!==version\?`\$\{previous\} → `:""\}\$\{version\}/);
});

test("real API failure states do not relabel demo readings as LIVE", () => {
  assert.match(app, /mode: "SIMULATED"/);
  assert.match(app, /Dados de demonstração · não são leituras reais/);
  assert.match(app, /A identidade não foi validada|Identidade não validada/);
});

