import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm, writeFile, chmod } from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const server = fileURLToPath(new URL('./server.mjs', import.meta.url));

async function run(messages, env = {}) {
  const child = spawn(process.execPath, [server], { env: { ...process.env, ...env }, stdio: ['pipe', 'pipe', 'pipe'] });
  const chunks = [];
  child.stdout.on('data', data => chunks.push(data));
  child.stdin.write(messages.map(message => JSON.stringify(message)).join('\n') + '\n');
  child.stdin.end();
  await once(child, 'close');
  return Buffer.concat(chunks).toString('utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
}

test('MCP initialization identifies the SolarMiner Intelligence server', async () => {
  const responses = await run([
    { jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2024-11-05' } },
  ]);
  assert.equal(responses[0].result.serverInfo.name, 'solarminer-intelligence');
});

test('MCP lists read-only SolarMiner, diagnostics and private GitHub report tools without a Gateway connection', async () => {
  const responses = await run([{ jsonrpc: '2.0', id: 2, method: 'tools/list' }]);
  assert.deepEqual(responses[0].result.tools.map(tool => tool.name), [
    'solarminer_snapshot', 'solarminer_device_readings', 'solarminer_energy_status', 'solarminer_recent_events',
    'solarminer_gateway_diagnostics', 'solarminer_github_diagnostics', 'solarminer_equipment_inventory',
    'solarminer_dps_assessment', 'solarminer_energy_forecast_evaluation', 'solarminer_update_outcomes',
    'solarminer_device_response_history', 'solarminer_validate_intelligence_workspace',
  ]);
});

test('workspace validation accepts only a fixed suite and delegates execution to the isolated root broker', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-workspace-validation-'));
  const tokenFile = path.join(temp, 'service.token');
  const token = 'b'.repeat(72);
  const auditRequests = [];
  const auditServer = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    assert.equal(request.headers.authorization, `Bearer ${token}`);
    auditRequests.push({ method: request.method, url: request.url, body: JSON.parse(Buffer.concat(chunks).toString('utf8')) });
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ status: 'passed', suite: 'intelligence', exit_code: 0,
      isolation: 'separate_uid_private_network_read_only_snapshot', output: 'tests 2\npass 2\nfail 0' }));
  });
  auditServer.listen(0, '127.0.0.1');
  await once(auditServer, 'listening');
  await writeFile(tokenFile, `SOLARMINER_INTELLIGENCE_TOKEN=${token}\n`, { mode: 0o600 });
  await chmod(tokenFile, 0o600);
  t.after(async () => { auditServer.close(); await rm(temp, { recursive: true, force: true }); });
  const responses = await run([
    { jsonrpc: '2.0', id: 10, method: 'tools/call', params: {
      name: 'solarminer_validate_intelligence_workspace', arguments: { suite: 'intelligence' },
    } },
    { jsonrpc: '2.0', id: 11, method: 'tools/call', params: {
      name: 'solarminer_validate_intelligence_workspace', arguments: { suite: 'arbitrary', command: 'whoami' },
    } },
  ], { SOLARMINER_INTELLIGENCE_TOKEN_FILE: tokenFile,
    SOLARMINER_INTELLIGENCE_URL: `http://127.0.0.1:${auditServer.address().port}/api/v1/intelligence` });
  assert.equal(responses[0].result.structuredContent.status, 'passed');
  assert.equal(responses[0].result.structuredContent.isolation, 'separate_uid_private_network_read_only_snapshot');
  assert.match(responses[0].result.structuredContent.output, /tests 2/);
  assert.equal(responses[1].result.isError, true);
  assert.equal(responses[1].result.content[0].text, 'validation_suite_not_allowed');
  assert.deepEqual(auditRequests, [{ method: 'POST', url: '/api/v1/intelligence/workspace-tests', body: { suite: 'intelligence' } }]);
});

test('MCP tool call fails closed when the service credential is missing', async () => {
  const responses = await run([{ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'solarminer_snapshot', arguments: {} } }], {
    SOLARMINER_INTELLIGENCE_TOKEN: '',
  });
  assert.equal(responses[0].result.isError, true);
  assert.equal(responses[0].result.content[0].text, 'intelligence_service_credential_missing');
});

test('MCP reads its service credential from a protected file and never from environment or argv',
  { skip: Boolean(process.getuid && process.getuid() !== 0) }, async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-mcp-'));
  const tokenFile = path.join(temp, 'service.token');
  const token = 'a'.repeat(72);
  await writeFile(tokenFile, `SOLARMINER_INTELLIGENCE_TOKEN=${token}\n`, { mode: 0o600 });
  await chmod(tokenFile, 0o600);
  const server = http.createServer((request, response) => {
    assert.equal(request.headers.authorization, `Bearer ${token}`);
    assert.equal(request.url, '/api/v1/intelligence/snapshot?history_hours=24');
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end('{"gateway":{"status":"ok"}}');
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(async () => { server.close(); await rm(temp, { recursive: true, force: true }); });
  const port = server.address().port;
  const child = spawn(process.execPath, [serverFileForTest()], {
    env: { ...process.env, SOLARMINER_INTELLIGENCE_TOKEN: '', SOLARMINER_INTELLIGENCE_TOKEN_FILE: tokenFile,
      SOLARMINER_INTELLIGENCE_URL: `http://127.0.0.1:${port}/api/v1/intelligence` },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const chunks = [];
  child.stdout.on('data', data => chunks.push(data));
  child.stdin.end(`${JSON.stringify({ jsonrpc: '2.0', id: 7, method: 'tools/call', params: { name: 'solarminer_snapshot', arguments: {} } })}\n`);
  await once(child, 'close');
  const response = JSON.parse(Buffer.concat(chunks).toString('utf8').trim());
  assert.equal(response.result?.structuredContent?.gateway?.status, 'ok', JSON.stringify(response));
});

function serverFileForTest() {
  return fileURLToPath(new URL('./server.mjs', import.meta.url));
}
