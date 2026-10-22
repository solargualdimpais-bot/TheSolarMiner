import test from 'node:test';
import assert from 'node:assert/strict';
import { CONNECTION_STATES, GatewayConnectionManager, PRESENCE_API_STATUS, classifyEndpoint, inferHostedGatewayEndpoint, parsePairingQr, probeGateway, validateGatewayUrl } from '../gateway-connection.js';

const makeQr = (code = `pair-${cryptoRandom()}` , expiresAt = Math.floor(Date.now()/1000)+300) => JSON.stringify({type:'solarminer-pairing',version:1,gateway_url:'https://solarminer-gw.example',pairing_code:code.padEnd(40,'x'),expires_at:expiresAt,single_use:true});
let seed=0; function cryptoRandom(){ seed++; return `unique-${seed}-${Date.now()}`; }
const jsonResponse = (body,status=200) => ({ok:status>=200&&status<300,status,json:async()=>body});
const fakeFetch = (health={status:'ok',version:'0.6.5',bootstrap_state:'READY'},info={product:'SolarMiner Gateway',version:'0.6.5'}) => async (url,init) => { assert.equal(init.method,'GET');assert.equal(init.credentials,'omit');assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');return url.endsWith('/api/v1/health')?jsonResponse(health):jsonResponse(info); };

test('1. demo mode stays explicitly simulated and disconnected',()=>{const m=new GatewayConnectionManager();assert.equal(m.state.state,CONNECTION_STATES.DEMO);assert.equal(m.state.simulated,true);assert.equal(m.state.reachable,false);});
test('Gateway-hosted PWA infers its LAN or Tailscale same-origin endpoint',()=>{
  assert.equal(inferHostedGatewayEndpoint({protocol:'https:',hostname:'192.168.8.168',port:'8443',origin:'https://192.168.8.168:8443'}),'https://192.168.8.168:8443');
  assert.equal(inferHostedGatewayEndpoint({protocol:'https:',hostname:'solarminer.tailnet.ts.net',port:'',origin:'https://solarminer.tailnet.ts.net'}),'https://solarminer.tailnet.ts.net');
  assert.equal(inferHostedGatewayEndpoint({protocol:'https:',hostname:'solargualdimpais-bot.github.io',port:'',origin:'https://solargualdimpais-bot.github.io'}),'');
  assert.equal(inferHostedGatewayEndpoint({protocol:'http:',hostname:'192.168.8.168',port:'8443',origin:'http://192.168.8.168:8443'}),'');
});
test('2. remote user without an associated Gateway is clearly unassociated',()=>{const m=new GatewayConnectionManager();assert.equal(m.clear().state,CONNECTION_STATES.UNASSOCIATED);});
test('3. valid local pairing QR is parsed as a candidate, not automatically paired',()=>{const q=parsePairingQr(makeQr());assert.equal(q.identityValidated,false);assert.equal(q.gatewayUrl,'https://solarminer-gw.example');assert.equal(q.singleUse,true);});
test('4. expired pairing QR is rejected',()=>assert.throws(()=>parsePairingQr(makeQr(undefined,Math.floor(Date.now()/1000)-1)),/expirou/i));
test('5. re-reading the same QR in one session is rejected locally',()=>{const qr=makeQr();parsePairingQr(qr);assert.throws(()=>parsePairingQr(qr),/já foi lido/i);});
test('6. unavailable Gateway is not treated as connected',async()=>{const r=await probeGateway('https://gw.example',{fetchImpl:async()=>{throw new Error('offline')}});assert.equal(r.state,CONNECTION_STATES.UNAVAILABLE);assert.equal(r.reachable,false);});
test('7. a valid HTTP response does not validate Gateway cryptographic identity',async()=>{const r=await probeGateway('https://gw.example',{fetchImpl:fakeFetch()});assert.equal(r.reachable,true);assert.equal(r.identityValidated,false);assert.equal(r.state,CONNECTION_STATES.RESPONDING_UNVERIFIED);});
test('8. HTTP 401 means authentication is required, not connected',async()=>{const r=await probeGateway('https://gw.example',{fetchImpl:async()=>jsonResponse({detail:'unauthorized'},401)});assert.equal(r.state,CONNECTION_STATES.AUTH_REQUIRED);assert.equal(r.identityValidated,false);});
test('9. expired-session status is not inferred without an authenticated API response',()=>{assert.equal(CONNECTION_STATES.SESSION_EXPIRED,'SESSÃO EXPIRADA');});
test('10. private IP endpoint is only a LAN candidate, not confirmed LAN',()=>{assert.equal(classifyEndpoint('https://192.168.1.20'),'CANDIDATE_LAN');});
test('11. public hostname endpoint is not automatically classified as remote',()=>{assert.equal(classifyEndpoint('https://gw.example'),'CANDIDATE_UNCLASSIFIED');});
test('12. loss of connection resets reachability and does not delete prior state silently',async()=>{let calls=0;const m=new GatewayConnectionManager({probe:async()=>({reachable:++calls===1,state:'ok',identityValidated:false})});await m.check('https://gw.example');await m.check('https://gw.example');assert.equal(m.state.reachable,false);assert.equal(m.endpoint,'https://gw.example');});
test('13. browser does not need or pretend to read SSID',()=>{assert.equal('ssid' in globalThis,false);});
test('14. retry backoff is bounded and progresses after failures',async()=>{const m=new GatewayConnectionManager({probe:async()=>({reachable:false,state:CONNECTION_STATES.UNAVAILABLE})});for(let i=0;i<12;i++) await m.check('https://gw.example');assert.equal(m.nextRetryDelay(),16000);});
test('15. presence heartbeat is explicitly scoped to authenticated sessions',()=>{assert.equal(PRESENCE_API_STATUS.available,true);assert.equal(PRESENCE_API_STATUS.endpoint,'/api/v1/presence/heartbeat');});
test('16. no presence expiry is falsely claimed by the client',()=>{assert.equal(PRESENCE_API_STATUS.physicalPresenceSupported,false);});
test('17. presence does not claim physical presence or LAN/remote path',()=>{assert.match(PRESENCE_API_STATUS.reason,/não prova presença física/i);assert.equal(PRESENCE_API_STATUS.physicalPresenceSupported,false);});
test('18. presence API has a defined endpoint but requires bearer authentication',()=>{assert.equal(PRESENCE_API_STATUS.readEndpoint,'/api/v1/presence/me');assert.match(PRESENCE_API_STATUS.reason,/sessão autenticada/i);});
test('19. user identity cannot be supplied as a presence target by this module',()=>assert.equal('reportPresence' in new GatewayConnectionManager(),false));
test('20. connection module contains no physical command routes or writes',async()=>{const fs=await import('node:fs');const source=fs.readFileSync(new URL('../gateway-connection.js',import.meta.url),'utf8');assert.doesNotMatch(source,/writeRegister|writeCoil|\/api\/v1\/devices\/discover|\/api\/v1\/use\b/i);});
test('21. TLS failure is reported as unavailable; no insecure fallback is attempted',async()=>{let calls=0;const r=await probeGateway('https://gw.example',{fetchImpl:async(url)=>{calls++;if(url.startsWith('http:'))throw new Error('unexpected_http');throw new TypeError('certificate error')}});assert.equal(r.state,CONNECTION_STATES.UNAVAILABLE);assert.equal(calls,1);});
test('22. URL validation requires HTTPS and rejects embedded credentials',()=>{assert.throws(()=>validateGatewayUrl('http://192.168.1.2'),/HTTPS/i);assert.throws(()=>validateGatewayUrl('https://user:pass@gw.example'),/credenciais/i);});

test('identity validation cannot be inferred from product name or version alone',async()=>{const r=await probeGateway('https://gw.example',{fetchImpl:fakeFetch()});assert.equal(r.identityValidated,false);assert.match(r.note,/identidade criptográfica/i);});
test('probe refuses an unexpected product response',async()=>{const r=await probeGateway('https://gw.example',{fetchImpl:fakeFetch(undefined,{product:'Other Gateway',version:'1'})});assert.equal(r.state,CONNECTION_STATES.UNAVAILABLE);});
test('QR parser rejects malformed or oversized payloads',()=>{assert.throws(()=>parsePairingQr('not json'));assert.throws(()=>parsePairingQr('x'.repeat(5000)));});
test('QR parser refuses non-HTTPS arbitrary endpoints',()=>{const qr=JSON.stringify({type:'solarminer-pairing',version:1,gateway_url:'http://192.168.1.2',pairing_code:'a'.repeat(40),expires_at:Math.floor(Date.now()/1000)+300,single_use:true});assert.throws(()=>parsePairingQr(qr),/HTTPS/i);});
test('manager coalesces concurrent checks to one probe',async()=>{let count=0;let release;const probe=()=>{count++;return new Promise(resolve=>{release=()=>resolve({state:CONNECTION_STATES.RESPONDING_UNVERIFIED,reachable:true,identityValidated:false})})};const m=new GatewayConnectionManager({probe});const a=m.check('https://gw.example');const b=m.check('https://gw.example');assert.equal(count,1);release();await Promise.all([a,b]);});

test("v0.6.7 invite QR requires full fingerprint and HTTPS", async () => {
  const { parseInviteQr } = await import("../gateway-connection.js");
  const payload = JSON.stringify({v:1,url:"https://gateway.example.test",token:"x".repeat(43),fp:"a".repeat(64),exp:Math.floor(Date.now()/1000)+3600});
  const parsed = parseInviteQr(payload);
  assert.equal(parsed.fingerprint, "a".repeat(64));
  assert.equal(parsed.identityValidated, false);
  assert.throws(() => parseInviteQr(JSON.stringify({...JSON.parse(payload), fp:"aabbccdd"})), /Fingerprint/);
  assert.throws(() => parseInviteQr(JSON.stringify({...JSON.parse(payload), url:"http://gateway.example.test"})), /HTTPS/);
});

test("v0.6.7 Gateway identity challenge verifies fingerprint and Ed25519 proof", async () => {
  const { verifyGatewayIdentityChallenge } = await import("../gateway-connection.js");
  const pair = await crypto.subtle.generateKey({name:"Ed25519"}, true, ["sign", "verify"]);
  const der = new Uint8Array(await crypto.subtle.exportKey("spki", pair.publicKey));
  const b64 = btoa(String.fromCharCode(...der));
  const pem = `-----BEGIN PUBLIC KEY-----\n${b64.match(/.{1,64}/g).join("\n")}\n-----END PUBLIC KEY-----`;
  const fingerprint = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", der)), b => b.toString(16).padStart(2,"0")).join("");
  const timestamp = Math.floor(Date.now()/1000), nonce = "test-gateway-identity-nonce";
  const canonical = new TextEncoder().encode(`GET\n/api/v1/gateway/identity\n${timestamp}\n${nonce}`);
  const signature = Array.from(new Uint8Array(await crypto.subtle.sign({name:"Ed25519"}, pair.privateKey, canonical)), b=>b.toString(16).padStart(2,"0")).join("");
  const invite = {fingerprint};
  const challenge = {public_key_pem:pem, fingerprint_sha256:fingerprint, timestamp, nonce, signature, signature_algorithm:"Ed25519"};
  assert.equal((await verifyGatewayIdentityChallenge(invite, challenge)).identityValidated, true);
  await assert.rejects(() => verifyGatewayIdentityChallenge({...invite, fingerprint:"b".repeat(64)}, challenge), /fingerprint/i);
});
