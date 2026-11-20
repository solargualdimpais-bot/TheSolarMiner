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
const prompt = 'Use the read-only SolarMiner snapshot tool to retrieve the fixture data, then reply with exactly: SolarMiner SDK comparison passed.';
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
  const requestRecord = { body, rows: [] };
  ollamaRequests.push(requestRecord);
  const openAiCompatible = request.url === '/v1/chat/completions';
  response.writeHead(200, { 'content-type': openAiCompatible ? 'text/event-stream' : 'application/x-ndjson',
    'cache-control': 'no-cache', 'connection': 'keep-alive', 'transfer-encoding': 'chunked' });
  const writeRow = async row => {
    requestRecord.rows.push(row);
    response.write(openAiCompatible ? `data: ${JSON.stringify(row)}\n\n` : `${JSON.stringify(row)}\n`);
    await new Promise(resolve => setTimeout(resolve, 8));
  };
  const afterTool = body.messages.some(message => message.role === 'tool' || message.tool_call_id);
  if (!afterTool) {
    const tool = (body.tools || []).map(item => item.function || item).find(item =>
      typeof item?.name === 'string' && item.name.includes('solarminer_snapshot'));
    assert.ok(tool, `SDK did not send the read-only SolarMiner MCP tool in its provider request; body_keys=${Object.keys(body).join(',')}; tools=${JSON.stringify((body.tools || []).map(item => item.function?.name || item.name || item.type || 'unknown'))}`);
    if (openAiCompatible) {
      await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
        choices: [{ index: 0, delta: { role: 'assistant' }, finish_reason: null }] });
      // Ollama's OpenAI-compatible stream carries reasoning and visible answer
      // separately in delta.reasoning and delta.content.
      if (body.think !== false) {
        await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
          choices: [{ index: 0, delta: { reasoning: 'fixture reasoning chunk one' }, finish_reason: null }] });
        await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
          choices: [{ index: 0, delta: { reasoning: 'fixture reasoning chunk two' }, finish_reason: null }] });
      }
      await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
        choices: [{ index: 0, delta: { tool_calls: [{ index: 0, id: 'call-solarminer-snapshot', type: 'function',
          function: { name: tool.name, arguments: '{}' } }] }, finish_reason: null }] });
      await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
        choices: [{ index: 0, delta: {}, finish_reason: 'tool_calls' }] });
      response.write('data: [DONE]\n\n');
    } else {
      if (body.think !== false) {
        await writeRow({ model, message: { role: 'assistant', thinking: 'fixture reasoning chunk one', content: '' }, done: false });
        await writeRow({ model, message: { role: 'assistant', thinking: 'fixture reasoning chunk two', content: '' }, done: false });
      }
      await writeRow({ model, message: { role: 'assistant', content: '', tool_calls: [
        { function: { name: tool.name, arguments: {} } },
      ] }, done: true, done_reason: 'tool_calls', prompt_eval_count: 10, eval_count: 2 });
    }
  } else {
    if (openAiCompatible) {
      await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
        choices: [{ index: 0, delta: { role: 'assistant' }, finish_reason: null }] });
      await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
        choices: [{ index: 0, delta: { content: 'SolarMiner SDK ' }, finish_reason: null }] });
      await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
        choices: [{ index: 0, delta: { content: 'comparison passed.' }, finish_reason: null }] });
      await writeRow({ id: 'chatcmpl-fixture', object: 'chat.completion.chunk', model,
        choices: [{ index: 0, delta: {}, finish_reason: 'stop' }] });
      response.write('data: [DONE]\n\n');
    } else {
      await writeRow({ model, message: { role: 'assistant', content: 'SolarMiner SDK ' }, done: false });
      await writeRow({ model, message: { role: 'assistant', content: 'comparison passed.' }, done: false });
      await writeRow({ model, message: { role: 'assistant', content: '' }, done: true, done_reason: 'stop',
        prompt_eval_count: 15, eval_count: 5 });
    }
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

async function runVersion(version, sdkPath, expectedThink) {
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
    assert.equal(requests.length, 2,
      `SDK ${version} must perform one Ollama MCP tool-call round trip; observations=${JSON.stringify(ollamaHttpObservations.slice(-12))}`);
    const request = requests[0];
    assert.ok(request, `SDK ${version} did not call native Ollama /api/chat`);
    assert.equal(request.body.model, model);
    assert.equal(request.body.stream, true);
    assert.equal(request.body.think, expectedThink);
    assert.ok(request.body.tools?.some(tool => tool.function?.name === 'solarminer_snapshot'),
      `SDK ${version} did not pass the read-only tool definition to Ollama`);
    assert.ok(requests[1].body.messages.some(message => message.role === 'tool'),
      `SDK ${version} did not pass the MCP tool result back to Ollama`);
    const returnedToolContent = requests[1].body.messages.find(message => message.role === 'tool')?.content;
    assert.match(String(returnedToolContent), /fixture snapshot: battery=charging/,
      `SDK ${version} changed or lost the MCP tool result content`);
    assert.equal(result.answer, answer);
    assert.equal(trace.state, 'completed');
    assert.ok(trace.sdk_event_types?.assistant > 0, `SDK ${version} emitted no assistant events`);
    assert.ok(trace.sdk_event_shapes?.some(event => event.type === 'assistant' && event.content_block_types?.includes('text')),
      `SDK ${version} emitted no assistant event with a text content block`);
    assert.ok(trace.sdk_assistant_text_blocks > 0, `SDK ${version} emitted no text blocks`);
    assert.equal(trace.sdk_assistant_text_chars, answer.length);
    assert.equal(trace.mcp_tool_calls, 1, `SDK ${version} did not emit the MCP tool call to the agent`);
    assert.equal(trace.mcp_tool_results, 1, `SDK ${version} did not return the MCP result to the agent`);

    const report = {
      sdk_version: version,
      http_requests: requests.map(item => ({
        route: '/api/chat',
        body: {
          model: item.body.model,
          stream: item.body.stream,
          think: Object.hasOwn(item.body, 'think') ? item.body.think : '(field omitted)',
          options: item.body.options || {},
          messages: item.body.messages.map(message => {
            const content = typeof message.content === 'string' ? message.content : JSON.stringify(message.content ?? '');
            return { role: message.role, content_chars: content.length,
              content_sha256: createHash('sha256').update(content).digest('hex'),
              tool_call_names: (message.tool_calls || []).map(call => call.function?.name).filter(Boolean) };
          }),
          tool_names: (item.body.tools || []).map(tool => tool.function?.name).filter(Boolean),
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
    };
    return { report, request, result };
  } finally {
    child.kill('SIGTERM');
    await Promise.race([once(child, 'exit').catch(() => {}), new Promise(resolve => setTimeout(resolve, 3000))]);
  }
}

try {
  const oldVersion = await runVersion('0.36.0', sdk036Path, undefined);
  const newVersion = await runVersion('0.37.0', sdk037Path, false);

  assert.deepEqual(oldVersion.request.body.messages.map(({ role, content }) => ({ role, content })),
    newVersion.request.body.messages.map(({ role, content }) => ({ role, content })),
    'the SDK versions must receive the same prompt and conversation');
  assert.equal(oldVersion.result.answer, newVersion.result.answer,
    'the agent extraction must return the same final text for both SDK versions');

  console.log(JSON.stringify({ comparison: [oldVersion.report, newVersion.report],
    conclusion: 'Both SDK versions passed the same read-only MCP tool request/result round-trip and delivered final assistant text through the production agent-service extractor; 0.37.0 additionally disables Ollama thinking by default.' }, null, 2));
} finally {
  await new Promise(resolve => ollamaServer.close(resolve));
  ollamaServer.closeAllConnections();
  await rm(temp, { recursive: true, force: true });
}
