import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const service = fileURLToPath(new URL('./agent-service.mjs', import.meta.url));
const sdkMock = `
import { appendFile } from 'node:fs/promises';
export async function* query({ prompt, options }) {
  const allowed = await options.canUseTool('mcp__solarminer__solarminer_energy_forecast_evaluation', {}, {});
  const denied = await options.canUseTool('Bash', {}, {});
  await appendFile(process.env.MOCK_REPORT, JSON.stringify({
    prompt, sessionId: options.sessionId, permissionMode: options.permissionMode, model: options.model,
    inferenceEnv: options.env,
    allowed, denied, mcpCommand: options.mcpServers.solarminer.command,
    mcpArgs: options.mcpServers.solarminer.args,
    mcpEnv: options.mcpServers.solarminer.env,
    mainKey: Boolean(process.env.OPENAI_API_KEY),
  }) + '\\n');
  yield { type: 'assistant', message: { content: [{ type: 'tool_use', name: 'mcp__solarminer__solarminer_snapshot' }] } };
  yield { type: 'user', message: { content: [
    { type: 'tool_result', content: 'snapshot' },
    { type: 'tool_result', content: 'unavailable', is_error: true },
  ] } };
  yield { type: 'assistant', message: { content: [{ type: 'text', text: 'Análise baseada na ponte SolarMiner.' }] } };
}
`;

async function unusedPort() {
  const probe = net.createServer();
  probe.listen(0, '127.0.0.1');
  await once(probe, 'listening');
  const { port } = probe.address();
  await new Promise(resolve => probe.close(resolve));
  return port;
}

async function startMockOllama(t, { installed = true } = {}) {
  const model = 'qwen3.5:9b-q4_K_M';
  const server = http.createServer((request, response) => {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify(request.url === '/api/ps' ? { models: [] } :
      { models: installed ? [{ name: model, model }] : [] }));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  return `http://127.0.0.1:${server.address().port}/v1`;
}

async function waitForHealth(port, child) {
  const until = Date.now() + 10000;
  while (Date.now() < until) {
    if (child.exitCode !== null) throw new Error(`agent exited before health: ${child.exitCode}; ${child.testStderr || ''}`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`);
      if (response.ok) return response.json();
    } catch { /* server is still starting */ }
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw new Error(`agent health timeout; ${child.testStderr || ''}`);
}

test('resident agent authenticates requests, persists sessions and only allows the SolarMiner MCP read tool', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-intelligence-'));
  const port = await unusedPort();
  const auditPort = await unusedPort();
  const mockPath = path.join(temp, 'mock-sdk.mjs');
  const reportPath = path.join(temp, 'agent-report.jsonl');
  const statePath = path.join(temp, 'state');
  const ollamaBase = await startMockOllama(t);
  const auditRequests = [];
  const auditServer = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    auditRequests.push({ method: request.method, url: request.url, authorization: request.headers.authorization,
      body: Buffer.concat(chunks).toString('utf8') });
    response.writeHead(201, { 'content-type': 'application/json' });
    response.end('{"status":"recorded"}');
  });
  auditServer.listen(auditPort, '127.0.0.1');
  await once(auditServer, 'listening');
  await writeFile(mockPath, sdkMock);
  const child = spawn(process.execPath, [service], {
    env: {
      ...process.env,
      SOLARMINER_OPENCLAUDE_SDK: mockPath,
      SOLARMINER_INTELLIGENCE_PORT: String(port),
      SOLARMINER_INTELLIGENCE_STATE: statePath,
      SOLARMINER_INTELLIGENCE_LOCAL_TOKEN: 'local-agent-test-token-12345678901234567890',
      SOLARMINER_INTELLIGENCE_TOKEN: 'gateway-service-test-token-12345678901234567890',
      SOLARMINER_INTELLIGENCE_URL: `http://127.0.0.1:${auditPort}/api/v1/intelligence`,
      SOLARMINER_GATEWAY_CA: '/test/gateway-ca.crt',
      SOLARMINER_OLLAMA_BASE_URL: ollamaBase,
      MOCK_REPORT: reportPath,
      OPENAI_API_KEY: 'sk-test-only-not-a-real-credential-123456789',
      OPENAI_MODEL: 'reasoning-model-test',
    },
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  let stderr = '';
  child.stderr.on('data', data => { stderr += data.toString(); });
  t.after(async () => {
    child.kill();
    if (child.exitCode === null && child.signalCode === null) await once(child, 'exit').catch(() => {});
    auditServer.close();
    await rm(temp, { recursive: true, force: true });
  });

  const health = await waitForHealth(port, child);
  assert.equal(health.agent, 'OpenClaude');
  assert.equal(health.configured, true);
  assert.equal(health.default_provider, 'ollama');
  assert.equal(health.ollama.installed, true);
  assert.equal(JSON.stringify(health).includes('sk-test'), false);

  const unauthorized = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ prompt: 'test' }),
  });
  assert.equal(unauthorized.status, 401);

  const headers = { authorization: 'Bearer local-agent-test-token-12345678901234567890', 'content-type': 'application/json' };
  const invalid = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
    method: 'POST', headers, body: JSON.stringify({ prompt: '' }),
  });
  assert.equal(invalid.status, 422);

  const diagnosticId = 'a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1';
  for (const [index, prompt] of ['Analisa os erros recentes.', 'Compara os dados atuais com o histórico.'].entries()) {
    const response = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
      method: 'POST', headers: { ...headers, ...(index === 0 ? { 'X-SolarMiner-Diagnostic-ID': diagnosticId } : {}) },
      body: JSON.stringify({ prompt }),
    });
    const result = await response.text();
    assert.equal(response.status, 200, result);
    assert.equal(JSON.parse(result).answer, 'Análise baseada na ponte SolarMiner.');
    assert.equal(JSON.parse(result).provider, 'ollama');
  }
  const traceResponse = await fetch(`http://127.0.0.1:${port}/v1/diagnostics/${diagnosticId}`, { headers });
  const trace = await traceResponse.json();
  assert.equal(traceResponse.status, 200);
  assert.equal(trace.state, 'completed');
  assert.equal(trace.stage, 'agent_response_ready');
  assert.equal(trace.mcp_tool_calls, 1);
  assert.equal(trace.mcp_tool_results, 2);
  assert.equal(trace.mcp_tool_failures, 1);
  assert.ok(trace.steps.some(step => step.stage === 'sdk_text_received'));
  const explicitCloud = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
    method: 'POST', headers, body: JSON.stringify({ prompt: 'Usa OpenAI apenas neste pedido.', provider: 'openai' }),
  });
  const explicitCloudBody = await explicitCloud.text();
  assert.equal(explicitCloud.status, 200, explicitCloudBody);
  assert.equal(JSON.parse(explicitCloudBody).provider, 'openai');

  const reports = (await readFile(reportPath, 'utf8')).trim().split('\n').map(line => JSON.parse(line));
  assert.equal(reports.length, 3);
  assert.equal(reports[0].sessionId, reports[1].sessionId);
  assert.equal(reports[0].permissionMode, 'default');
  assert.equal(reports[0].model, 'qwen3.5:9b-q4_K_M');
  assert.equal(reports[0].inferenceEnv.OPENAI_BASE_URL, ollamaBase);
  assert.equal(reports[0].inferenceEnv.OPENAI_API_KEY, 'ollama-local');
  assert.equal(reports[2].model, 'reasoning-model-test');
  assert.equal(reports[2].inferenceEnv.OPENAI_BASE_URL, 'https://api.openai.com/v1');
  assert.equal(reports[2].inferenceEnv.OPENAI_API_KEY, 'sk-test-only-not-a-real-credential-123456789');
  assert.deepEqual(reports[0].allowed, { behavior: 'allow' });
  assert.equal(reports[0].denied.behavior, 'deny');
  assert.equal(reports[0].mcpCommand, '/usr/bin/env');
  assert.equal(reports[0].mcpArgs[0], '-i');
  assert.deepEqual(reports[0].mcpEnv, {});
  assert.equal(reports[0].mainKey, true);
  assert.equal(stderr.includes('sk-test'), false);
  assert.equal(auditRequests.length, 3);
  assert.equal(auditRequests[0].method, 'POST');
  assert.equal(auditRequests[0].url, '/api/v1/intelligence/agent-events');
  assert.equal(auditRequests[0].authorization, 'Bearer gateway-service-test-token-12345678901234567890');
  assert.deepEqual(JSON.parse(auditRequests[0].body), { event: 'tool_denied', tool: 'Bash' });
  assert.equal(auditRequests[0].body.includes('sk-test'), false);
  assert.equal(reports[0].mcpArgs.join(' ').includes('sk-test'), false);
  assert.equal(reports[0].mcpArgs.join(' ').includes('gateway-service-test-token'), false);
});

test('resident agent returns an explicit 504 when the OpenClaude SDK aborts inference', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-intelligence-timeout-'));
  const port = await unusedPort();
  const mockPath = path.join(temp, 'timeout-sdk.mjs');
  const ollamaBase = await startMockOllama(t);
  await writeFile(mockPath, `export async function* query() { const error = new Error('aborted'); error.name = 'AbortError'; throw error; }\n`);
  const child = spawn(process.execPath, [service], {
    env: { ...process.env, SOLARMINER_OPENCLAUDE_SDK: mockPath,
      SOLARMINER_INTELLIGENCE_PORT: String(port), SOLARMINER_INTELLIGENCE_STATE: path.join(temp, 'state'),
      SOLARMINER_INTELLIGENCE_LOCAL_TOKEN: 'local-agent-test-token-12345678901234567890',
      SOLARMINER_INTELLIGENCE_TOKEN: 'gateway-service-test-token-12345678901234567890',
      SOLARMINER_OLLAMA_BASE_URL: ollamaBase },
    stdio: 'ignore',
  });
  t.after(async () => {
    child.kill();
    if (child.exitCode === null && child.signalCode === null) await once(child, 'exit').catch(() => {});
    await rm(temp, { recursive: true, force: true });
  });
  await waitForHealth(port, child);
  const response = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
    method: 'POST',
    headers: { authorization: 'Bearer local-agent-test-token-12345678901234567890', 'content-type': 'application/json' },
    body: JSON.stringify({ prompt: 'Teste de timeout.' }),
  });
  assert.equal(response.status, 504);
  assert.deepEqual(await response.json(), { error: 'analysis_timeout', error_type: 'AbortError' });
});

test('resident agent identifies permission failures without exposing paths or exception text', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-intelligence-permission-'));
  const port = await unusedPort();
  const mockPath = path.join(temp, 'permission-sdk.mjs');
  const ollamaBase = await startMockOllama(t);
  await writeFile(mockPath, `export async function* query() { const error = new Error('secret path /root/private'); error.code = 'EACCES'; throw error; }\n`);
  const child = spawn(process.execPath, [service], {
    env: { ...process.env, SOLARMINER_OPENCLAUDE_SDK: mockPath,
      SOLARMINER_INTELLIGENCE_PORT: String(port), SOLARMINER_INTELLIGENCE_STATE: path.join(temp, 'state'),
      SOLARMINER_INTELLIGENCE_LOCAL_TOKEN: 'local-agent-test-token-12345678901234567890',
      SOLARMINER_INTELLIGENCE_TOKEN: 'gateway-service-test-token-12345678901234567890',
      SOLARMINER_OLLAMA_BASE_URL: ollamaBase },
    stdio: 'ignore',
  });
  t.after(async () => {
    child.kill();
    if (child.exitCode === null && child.signalCode === null) await once(child, 'exit').catch(() => {});
    await rm(temp, { recursive: true, force: true });
  });
  await waitForHealth(port, child);
  const response = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
    method: 'POST',
    headers: { authorization: 'Bearer local-agent-test-token-12345678901234567890', 'content-type': 'application/json' },
    body: JSON.stringify({ prompt: 'Teste de permissões.' }),
  });
  assert.equal(response.status, 503);
  const result = await response.json();
  assert.equal(result.error, 'intelligence_permission_denied');
  assert.equal(result.error_code, 'EACCES');
  assert.equal(result.error_type, 'Error');
  assert.equal(JSON.stringify(result).includes('/root/private'), false);
});

test('resident agent defaults to local Ollama without OpenAI credentials and requires a key only for explicit cloud requests', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-intelligence-no-key-'));
  const port = await unusedPort();
  const mockPath = path.join(temp, 'unused-sdk.mjs');
  const ollamaBase = await startMockOllama(t);
  await writeFile(mockPath, 'export async function* query() {}\n');
  const child = spawn(process.execPath, [service], {
    env: {
      ...process.env,
      SOLARMINER_OPENCLAUDE_SDK: mockPath,
      SOLARMINER_INTELLIGENCE_PORT: String(port),
      SOLARMINER_INTELLIGENCE_STATE: path.join(temp, 'state'),
      SOLARMINER_INTELLIGENCE_LOCAL_TOKEN: 'local-agent-test-token-12345678901234567890',
      SOLARMINER_INTELLIGENCE_TOKEN: 'gateway-service-test-token-12345678901234567890',
      OPENAI_API_KEY: '',
      OPENAI_MODEL: 'reasoning-model-test',
      SOLARMINER_OLLAMA_BASE_URL: ollamaBase,
    },
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  child.testStderr = '';
  child.stderr.on('data', data => { child.testStderr += data.toString(); });
  t.after(async () => {
    child.kill();
    if (child.exitCode === null && child.signalCode === null) await once(child, 'exit').catch(() => {});
    await rm(temp, { recursive: true, force: true });
  });
  await waitForHealth(port, child);
  const headers = { authorization: 'Bearer local-agent-test-token-12345678901234567890', 'content-type': 'application/json' };
  const local = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
    method: 'POST', headers, body: JSON.stringify({ prompt: 'Test' }),
  });
  assert.equal(local.status, 502, 'the empty mock intentionally returns no answer, but provider resolution must remain local');
  const noKey = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
    method: 'POST', headers, body: JSON.stringify({ prompt: 'Test', provider: 'openai' }),
  });
  assert.equal(noKey.status, 503);
  assert.equal((await noKey.json()).error, 'openai_credential_not_configured');
  const oversized = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
    method: 'POST', headers, body: 'x'.repeat(13000),
  });
  assert.equal(oversized.status, 413);
});

test('development session confines source edits to its isolated checkout and still denies shell and protected files', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-intelligence-development-'));
  const port = await unusedPort();
  const auditPort = await unusedPort();
  const workspace = path.join(temp, 'workspace');
  await mkdir(path.join(workspace, 'src'), { recursive: true });
  await mkdir(path.join(workspace, 'tests'), { recursive: true });
  await writeFile(path.join(workspace, 'src', 'engine.py'), 'def calculate(): return 1\n');
  await writeFile(path.join(workspace, 'tests', 'test_existing.py'), 'def test_existing(): assert True\n');
  const mockPath = path.join(temp, 'mock-sdk.mjs');
  const reportPath = path.join(temp, 'tool-report.json');
  const ollamaBase = await startMockOllama(t);
  await writeFile(mockPath, `
import { writeFile } from 'node:fs/promises';
export async function* query({ options }) {
  const root = process.env.MOCK_WORKSPACE;
  const tools = {
    sourceEdit: await options.canUseTool('Edit', { file_path: root + '/src/engine.py' }),
    addRegressionTest: await options.canUseTool('Write', { file_path: root + '/tests/test_new.py' }),
    workspaceTests: await options.canUseTool('mcp__solarminer__solarminer_validate_intelligence_workspace', { suite: 'intelligence' }),
    existingTestEdit: await options.canUseTool('Edit', { file_path: root + '/tests/test_existing.py' }),
    traversal: await options.canUseTool('Edit', { file_path: root + '/../../outside.py' }),
    shell: await options.canUseTool('Bash', { command: 'echo unsafe' }),
    mcpRead: await options.canUseTool('mcp__solarminer__solarminer_snapshot', {}, {}),
    cwd: options.cwd,
  };
  await writeFile(process.env.MOCK_REPORT, JSON.stringify(tools));
  yield { type: 'assistant', message: { content: [{ type: 'text', text: 'Alteração isolada preparada.' }] } };
}
`);
  const auditRequests = [];
  const auditServer = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    auditRequests.push(JSON.parse(Buffer.concat(chunks).toString('utf8')));
    response.writeHead(201, { 'content-type': 'application/json' });
    response.end('{"status":"recorded"}');
  });
  auditServer.listen(auditPort, '127.0.0.1');
  await once(auditServer, 'listening');
  const child = spawn(process.execPath, [service], {
    env: {
      ...process.env,
      SOLARMINER_OPENCLAUDE_SDK: mockPath,
      SOLARMINER_INTELLIGENCE_PORT: String(port),
      SOLARMINER_INTELLIGENCE_STATE: path.join(temp, 'state'),
      SOLARMINER_INTELLIGENCE_DEV_WORKSPACE: workspace,
      SOLARMINER_INTELLIGENCE_LOCAL_TOKEN: 'local-agent-test-token-12345678901234567890',
      SOLARMINER_INTELLIGENCE_TOKEN: 'gateway-service-test-token-12345678901234567890',
      SOLARMINER_INTELLIGENCE_URL: `http://127.0.0.1:${auditPort}/api/v1/intelligence`,
      OPENAI_API_KEY: 'sk-test-only-not-a-real-credential-123456789', OPENAI_MODEL: 'reasoning-model-test',
      SOLARMINER_OLLAMA_BASE_URL: ollamaBase,
      MOCK_WORKSPACE: workspace, MOCK_REPORT: reportPath,
    },
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  child.testStderr = '';
  child.stderr.on('data', data => { child.testStderr += data.toString(); });
  t.after(async () => {
    child.kill();
    if (child.exitCode === null && child.signalCode === null) await once(child, 'exit').catch(() => {});
    auditServer.close();
    await rm(temp, { recursive: true, force: true });
  });
  await waitForHealth(port, child);
  const response = await fetch(`http://127.0.0.1:${port}/v1/develop`, {
    method: 'POST',
    headers: { authorization: 'Bearer local-agent-test-token-12345678901234567890', 'content-type': 'application/json' },
    body: JSON.stringify({ prompt: 'Corrige o erro confirmado e acrescenta teste.' }),
  });
  assert.equal(response.status, 200, await response.text());
  const report = JSON.parse(await readFile(reportPath, 'utf8'));
  assert.equal(report.cwd, workspace);
  assert.deepEqual(report.sourceEdit, { behavior: 'allow' });
  assert.deepEqual(report.addRegressionTest, { behavior: 'allow' });
  assert.deepEqual(report.workspaceTests, { behavior: 'allow' });
  assert.equal(report.existingTestEdit.behavior, 'deny');
  assert.equal(report.traversal.behavior, 'deny');
  assert.equal(report.shell.behavior, 'deny');
  assert.deepEqual(report.mcpRead, { behavior: 'allow' });
  assert.equal(auditRequests.length, 5);
  assert.deepEqual(auditRequests.map(item => item.tool), ['Edit', 'Write', 'Edit', 'Edit', 'Bash']);
  assert.deepEqual(auditRequests.map(item => item.event), [
    'workspace_file_edit', 'workspace_file_write', 'tool_denied', 'tool_denied', 'tool_denied',
  ]);
  assert.equal(auditRequests[0].path, 'src/engine.py');
});

test('scheduled daily review requires the local credential and stores a proposal-only report', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-intelligence-review-'));
  const port = await unusedPort();
  const auditPort = await unusedPort();
  const mockPath = path.join(temp, 'mock-sdk.mjs');
  const reportPath = path.join(temp, 'agent-report.jsonl');
  const ollamaBase = await startMockOllama(t);
  const requests = [];
  const auditServer = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    requests.push({ url: request.url, authorization: request.headers.authorization,
      body: Buffer.concat(chunks).toString('utf8') });
    response.writeHead(request.url.endsWith('/reviews') ? 201 : 201, { 'content-type': 'application/json' });
    response.end('{"status":"recorded"}');
  });
  auditServer.listen(auditPort, '127.0.0.1');
  await once(auditServer, 'listening');
  await writeFile(mockPath, sdkMock);
  const child = spawn(process.execPath, [service], {
    env: { ...process.env, SOLARMINER_OPENCLAUDE_SDK: mockPath,
      SOLARMINER_INTELLIGENCE_PORT: String(port), SOLARMINER_INTELLIGENCE_STATE: path.join(temp, 'state'),
      SOLARMINER_INTELLIGENCE_LOCAL_TOKEN: 'local-agent-test-token-12345678901234567890',
      SOLARMINER_INTELLIGENCE_TOKEN: 'gateway-service-test-token-12345678901234567890',
      SOLARMINER_INTELLIGENCE_URL: `http://127.0.0.1:${auditPort}/api/v1/intelligence`,
      OPENAI_API_KEY: 'sk-test-only-not-a-real-credential-123456789', OPENAI_MODEL: 'reasoning-model-test',
      SOLARMINER_OLLAMA_BASE_URL: ollamaBase,
      MOCK_REPORT: reportPath }, stdio: 'ignore',
  });
  t.after(async () => {
    child.kill();
    if (child.exitCode === null && child.signalCode === null) await once(child, 'exit').catch(() => {});
    auditServer.close(); await rm(temp, { recursive: true, force: true });
  });
  await waitForHealth(port, child);
  const denied = await fetch(`http://127.0.0.1:${port}/v1/review`, { method: 'POST' });
  assert.equal(denied.status, 401);
  const response = await fetch(`http://127.0.0.1:${port}/v1/review`, { method: 'POST',
    headers: { authorization: 'Bearer local-agent-test-token-12345678901234567890' } });
  assert.equal(response.status, 201, await response.text());
  const review = requests.find(request => request.url === '/api/v1/intelligence/reviews');
  assert.ok(review);
  assert.equal(review.authorization, 'Bearer gateway-service-test-token-12345678901234567890');
  assert.equal(JSON.parse(review.body).review_kind, 'daily_engine_review');
  assert.equal(JSON.parse(review.body).report_text, 'Análise baseada na ponte SolarMiner.');
  assert.equal(JSON.stringify(requests).includes('sk-test'), false);
});
