import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';

const [sdk036Path, sdk037Path, agentServicePath] = process.argv.slice(2);
assert.ok(sdk036Path && sdk037Path && agentServicePath,
  'pass installed SDK 0.36.0, SDK 0.37.0, and agent-service.mjs paths');

const model = 'qwen3.5:9b-q4_K_M';
const localToken = 'sdk-comparison-local-token-1234567890';
const prompt = 'Hello World. Reply with exactly: SolarMiner SDK comparison passed.';
const answer = 'SolarMiner SDK comparison passed.';
const ollamaRequests = [];
const ollamaHttpObservations = [];
const ollamaServer = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const rawBody = Buffer.concat(chunks).toString('utf8');
  ollamaHttpObservations.push({ method: request.method, path: request.url,
    body_chars: rawBody.length, body_sha256: createHash('sha256').update(rawBody).digest('hex') });
  if (request.method === 'GET' && request.url === '/api/version') {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ version: '0.13.0-comparison-fixture' }));
    return;
  }
  if (request.method === 'GET' && ['/api/tags', '/api/ps'].includes(request.url)) {
    const entry = { name: model, model, size: 1,
      details: { family: 'qwen', families: ['qwen'], parameter_size: '9B', quantization_level: 'Q4_K_M' } };
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ models: [entry] }));
    return;
  }
  if (request.url === '/api/show') {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ modelfile: '', parameters: '', template: '',
      details: { family: 'qwen', parameter_size: '9B' },
      thinking: { values: [true, false], default: true } }));
    return;
  }
  if (request.method !== 'POST' || !['/api/chat', '/v1/chat/completions'].includes(request.url)) {
    response.writeHead(404, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ error: 'fixture_route_not_found' }));
    return;
  }

  const body = JSON.parse(rawBody);
  const requestRecord = { route: request.url, body, rows: [] };
  ollamaRequests.push(requestRecord);
  const openAiCompatible = request.url === '/v1/chat/completions';
  if (body.messages.some(message => typeof message.content === 'string' && message.content.includes('[fixture:upstream-500]'))) {
    requestRecord.fixture_response = 'http_500_json';
    response.writeHead(500, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ error: { message: 'synthetic Ollama provider failure', type: 'api_error' } }));
    return;
  }
  response.writeHead(200, { 'content-type': openAiCompatible ? 'text/event-stream' : 'application/x-ndjson',
    'cache-control': 'no-cache', 'connection': 'keep-alive', 'transfer-encoding': 'chunked' });
  const writeRow = async row => {
    requestRecord.rows.push(row);
    response.write(openAiCompatible ? `data: ${JSON.stringify(row)}\n\n` : `${JSON.stringify(row)}\n`);
    await new Promise(resolve => setTimeout(resolve, 8));
  };
  if (openAiCompatible) {
    // Ollama's OpenAI-compatible stream carries reasoning separately from
    // visible content; only content may become the final assistant answer.
    if (body.think !== false) {
      await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
        choices: [{ index: 0, delta: { reasoning: 'fixture reasoning chunk one' }, finish_reason: null }] });
      await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
        choices: [{ index: 0, delta: { reasoning: 'fixture reasoning chunk two' }, finish_reason: null }] });
    }
    await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
      choices: [{ index: 0, delta: { role: 'assistant', content: 'SolarMiner SDK ' }, finish_reason: null }] });
    await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
      choices: [{ index: 0, delta: { content: 'comparison passed.' }, finish_reason: null }] });
    await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
      choices: [{ index: 0, delta: {}, finish_reason: 'stop' }] });
    response.write('data: [DONE]\n\n');
  } else {
    if (body.think !== false) {
      await writeRow({ model, message: { role: 'assistant', thinking: 'fixture reasoning chunk one', content: '' }, done: false });
      await writeRow({ model, message: { role: 'assistant', thinking: 'fixture reasoning chunk two', content: '' }, done: false });
    }
    await writeRow({ model, message: { role: 'assistant', content: 'SolarMiner SDK ' }, done: false });
    await writeRow({ model, message: { role: 'assistant', content: 'comparison passed.' }, done: false });
    await writeRow({ model, message: { role: 'assistant', content: '' }, done: true, done_reason: 'stop',
      prompt_eval_count: 15, eval_count: 5 });
  }
  response.end();
});

async function listen(server) {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return server.address().port;
}

async function unusedPort() {
  const probe = net.createServer();
  const port = await listen(probe);
  await new Promise(resolve => probe.close(resolve));
  return port;
}

async function waitForAgent(port, child, stderr) {
  const deadline = Date.now() + 12000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`Agent exited before health (${child.exitCode}): ${stderr()}`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`, { signal: AbortSignal.timeout(1000) });
      if (response.ok) return;
    } catch { /* wait for listener */ }
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw new Error(`Agent health did not become ready: ${stderr()}`);
}

const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-openclaude-compare-'));
const ollamaPort = await listen(ollamaServer);
const mcpStubPath = path.join(temp, 'read-only-mcp-fixture.mjs');
await writeFile(mcpStubPath, `
let buffer = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  buffer += chunk;
  for (;;) {
    const newline = buffer.indexOf('\\n');
    if (newline < 0) break;
    const line = buffer.slice(0, newline).trim();
    buffer = buffer.slice(newline + 1);
    if (!line) continue;
    const message = JSON.parse(line);
    if (message.id === undefined) continue;
    let result = {};
    if (message.method === 'initialize') result = {
      protocolVersion: message.params?.protocolVersion || '2025-03-26',
      capabilities: { tools: {} }, serverInfo: { name: 'solarminer-comparison-fixture', version: '1.0.0' },
    };
    else if (message.method === 'tools/list') result = { tools: [{ name: 'solarminer_snapshot',
      description: 'Read one fixed synthetic Gateway snapshot for the SDK compatibility test.',
      inputSchema: { type: 'object', properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false } }] };
    else if (message.method === 'tools/call') result = { content: [{ type: 'text', text: 'fixture snapshot: battery=charging' }], isError: false };
    process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: message.id, result }) + '\\n');
  }
});
`);

async function runVersion(version, sdkPath) {
  const port = await unusedPort();
  const statePath = path.join(temp, `state-${version}`);
  const env = {
    ...process.env,
    HOME: path.join(temp, `home-${version}`),
    SOLARMINER_OPENCLAUDE_SDK: sdkPath,
    SOLARMINER_NODE: process.execPath,
    SOLARMINER_MCP_SERVER: mcpStubPath,
    SOLARMINER_INTELLIGENCE_PORT: String(port),
    SOLARMINER_INTELLIGENCE_STATE: statePath,
    SOLARMINER_INTELLIGENCE_LOCAL_TOKEN: localToken,
    SOLARMINER_INTELLIGENCE_TOKEN: localToken,
    SOLARMINER_INTELLIGENCE_URL: 'https://127.0.0.1:1/api/v1/intelligence',
    SOLARMINER_GATEWAY_CA: path.join(temp, 'unused-gateway-ca.crt'),
    SOLARMINER_OLLAMA_BASE_URL: `http://127.0.0.1:${ollamaPort}/v1`,
    SOLARMINER_OLLAMA_MODEL: model,
    SOLARMINER_INTELLIGENCE_REVIEW_HOUR: 'not-scheduled-in-contract-test',
  };
  const child = spawn(process.execPath, [agentServicePath], { env, stdio: ['ignore', 'ignore', 'pipe'] });
  let stderrText = '';
  child.stderr.on('data', chunk => { stderrText += chunk.toString(); });
  const stderr = () => stderrText.slice(-3000);
  try {
    await waitForAgent(port, child, stderr);
    const diagnosticId = version === '0.36.0'
      ? '36036036-0360-4036-8036-360360360360'
      : '37037037-0370-4037-8037-370370370370';
    const firstRequestIndex = ollamaRequests.length;
    const response = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
      method: 'POST',
      headers: { authorization: `Bearer ${localToken}`, 'content-type': 'application/json',
        'X-SolarMiner-Diagnostic-ID': diagnosticId },
      body: JSON.stringify({ prompt, provider: 'ollama' }),
      signal: AbortSignal.timeout(90000),
    });
    const raw = await response.text();
    assert.equal(response.status, 200, `SDK ${version} Intelligence returned ${response.status}: ${raw}; ${stderr()}`);
    const result = JSON.parse(raw);
    const traceResponse = await fetch(`http://127.0.0.1:${port}/v1/diagnostics/${diagnosticId}`, {
      headers: { authorization: `Bearer ${localToken}` },
    });
    assert.equal(traceResponse.status, 200);
    const trace = await traceResponse.json();
    const requests = ollamaRequests.slice(firstRequestIndex);
    assert.equal(requests.length, 1,
      `SDK ${version} must make one streaming Ollama request for the simple Hello World prompt; observations=${JSON.stringify(ollamaHttpObservations.slice(-12))}`);
    const request = requests[0];
    assert.ok(request, `SDK ${version} did not call Ollama`);
    assert.equal(request.route, '/v1/chat/completions', `SDK ${version} used an unexpected provider protocol`);
    assert.ok(request.body.messages.some(message => typeof message.content === 'string' && message.content.includes(prompt)),
      `SDK ${version} did not forward the exact Hello World prompt in its provider messages`);
    assert.equal(request.body.model, model);
    assert.equal(request.body.stream, true);
    assert.equal(request.body.think, undefined,
      `SDK ${version} sent an unexpected think option on the configured /v1/chat/completions route`);
    assert.equal(result.answer, answer);
    assert.equal(trace.state, 'completed');
    assert.ok(trace.sdk_event_types?.assistant > 0, `SDK ${version} emitted no assistant events`);
    assert.ok(trace.sdk_event_shapes?.some(event => event.type === 'assistant' && event.content_block_types?.includes('text')),
      `SDK ${version} emitted no assistant event with a text content block`);
    assert.ok(trace.sdk_assistant_text_blocks > 0, `SDK ${version} emitted no text blocks`);
    assert.equal(trace.sdk_assistant_text_chars, answer.length);
    assert.equal(trace.mcp_tool_calls, 0, 'Hello World should not invoke MCP');
    assert.equal(trace.mcp_tool_results, 0, 'Hello World should not return MCP results');

    const errorDiagnosticId = version === '0.36.0'
      ? '36036036-0360-4036-8036-360360360361'
      : '37037037-0370-4037-8037-370370370371';
    const beforeErrorRequest = ollamaRequests.length;
    const providerErrorResponse = await fetch(`http://127.0.0.1:${port}/v1/analyze`, {
      method: 'POST', headers: { authorization: `Bearer ${localToken}`, 'content-type': 'application/json',
        'X-SolarMiner-Diagnostic-ID': errorDiagnosticId },
      body: JSON.stringify({ prompt: '[fixture:upstream-500]', provider: 'ollama' }),
      signal: AbortSignal.timeout(30000),
    });
    const providerErrorBody = await providerErrorResponse.text();
    assert.ok(providerErrorResponse.status >= 500 && providerErrorResponse.status <= 599,
      `SDK ${version} did not surface the simulated upstream 500 as a server error: ${providerErrorBody}`);
    const errorTraceResponse = await fetch(`http://127.0.0.1:${port}/v1/diagnostics/${errorDiagnosticId}`, {
      headers: { authorization: `Bearer ${localToken}` },
    });
    const errorTrace = await errorTraceResponse.json();
    assert.equal(errorTraceResponse.status, 200);
    const errorRequests = ollamaRequests.slice(beforeErrorRequest);
    assert.ok(errorRequests.some(item => item.fixture_response === 'http_500_json'),
      `SDK ${version} never sent the simulated error prompt to the provider`);

    const report = {
      sdk_version: version,
      query_prompt_sha256: createHash('sha256').update(prompt).digest('hex'),
      http_requests: requests.map(item => ({
        route: item.route,
        body: {
          model: item.body.model,
          stream: item.body.stream,
          think: Object.hasOwn(item.body, 'think') ? item.body.think : '(field omitted)',
          parameter_fields: Object.fromEntries(['think', 'reasoning_effort', 'temperature', 'max_tokens', 'stream_options']
            .filter(key => Object.hasOwn(item.body, key)).map(key => [key, item.body[key]])),
          options: item.body.options || {},
          messages: item.body.messages.map(message => {
            const content = typeof message.content === 'string' ? message.content : JSON.stringify(message.content ?? '');
            return { role: message.role, content_chars: content.length,
              content_sha256: createHash('sha256').update(content).digest('hex'),
              tool_call_names: (message.tool_calls || []).map(call => call.function?.name).filter(Boolean) };
          }),
          tool_names: (item.body.tools || []).map(tool => tool.function?.name || tool.name).filter(Boolean),
        },
          ollama_stream: item.rows.map(row => ({
          reasoning_chars: row.choices?.[0]?.delta?.reasoning?.length || row.message?.thinking?.length || 0,
          content_chars: row.choices?.[0]?.delta?.content?.length || row.message?.content?.length || 0,
          tool_call_names: (row.choices?.[0]?.delta?.tool_calls || row.message?.tool_calls || [])
            .map(call => call.function?.name).filter(Boolean),
          finish_reason: row.choices?.[0]?.finish_reason || row.done_reason || null,
          done: row.done === true,
        })),
      })),
      sdk_events_received: trace.sdk_event_types,
      sdk_event_shapes: trace.sdk_event_shapes,
      assistant_messages: trace.sdk_assistant_messages,
      text_blocks: trace.sdk_assistant_text_blocks,
      extracted_text_chars: trace.sdk_assistant_text_chars,
      mcp_tool_calls: trace.mcp_tool_calls,
      mcp_tool_results: trace.mcp_tool_results,
      intelligence_http_status: response.status,
      intelligence_result: result.answer,
      provider_http_500_experiment: {
        provider_request_route: errorRequests.find(item => item.fixture_response === 'http_500_json')?.route || null,
        agent_http_status: providerErrorResponse.status,
        agent_error_type: JSON.parse(providerErrorBody).error_type || null,
        diagnostic_error_type: errorTrace.error_type,
        diagnostic_provider_http_status: errorTrace.provider_http_status,
        diagnostic_stage: errorTrace.stage,
      },
    };
    return { report, request, result };
  } finally {
    child.kill('SIGTERM');
    await Promise.race([once(child, 'exit').catch(() => {}), new Promise(resolve => setTimeout(resolve, 3000))]);
  }
}

try {
  const oldVersion = await runVersion('0.36.0', sdk036Path);
  const newVersion = await runVersion('0.37.0', sdk037Path);

  assert.equal(oldVersion.result.answer, newVersion.result.answer,
    'the agent extraction must return the same final text for both SDK versions');

  console.log(JSON.stringify({ comparison: [oldVersion.report, newVersion.report],
    conclusion: 'Both SDK versions received the same query prompt, processed the OpenAI-compatible SSE reasoning/content stream and delivered final assistant text through the production agent-service extractor. The SDK adds its own prompt/tool context around the user text, which is reported using message lengths and hashes. Neither provider request included a think field on the configured /v1 route. Hello World made no MCP calls. This validates SDK-to-agent conversion for the fixture, not the Lenovo response or its HTTP 500.' }, null, 2));
} finally {
  await new Promise(resolve => ollamaServer.close(resolve));
  ollamaServer.closeAllConnections();
  await rm(temp, { recursive: true, force: true });
}
