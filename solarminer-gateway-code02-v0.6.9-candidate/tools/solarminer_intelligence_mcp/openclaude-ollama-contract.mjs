import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const sdkPath = process.argv[2];
assert.ok(sdkPath, 'pass the installed OpenClaude sdk.mjs path');

const root = await mkdtemp(join(tmpdir(), 'solarminer-openclaude-ollama-contract-'));
const portServer = createServer();
let observedRequest = null;
const assistantText = 'solarminer-openclaude-sdk-contract-ok';

portServer.on('request', async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  observedRequest = {
    method: request.method,
    url: request.url,
    body: JSON.parse(Buffer.concat(chunks).toString('utf8')),
  };
  response.writeHead(200, { 'content-type': 'application/x-ndjson' });
  response.end([
    JSON.stringify({ model: 'qwen3.5:9b-q4_K_M', message: { role: 'assistant', content: assistantText }, done: false }),
    JSON.stringify({ model: 'qwen3.5:9b-q4_K_M', message: { role: 'assistant', content: '' }, done: true, done_reason: 'stop' }),
    '',
  ].join('\n'));
});

try {
  await new Promise((resolve, reject) => {
    portServer.once('error', reject);
    portServer.listen(0, '127.0.0.1', resolve);
  });
  const address = portServer.address();
  const env = {
    HOME: root,
    CLAUDE_CODE_USE_OPENAI: '1',
    OPENAI_BASE_URL: `http://127.0.0.1:${address.port}/v1`,
    OPENAI_API_KEY: 'ollama-local',
    OPENAI_MODEL: 'qwen3.5:9b-q4_K_M',
  };
  process.env.HOME = root;
  const { query } = await import(pathToFileURL(sdkPath).href);
  const agent = query({
    prompt: 'Reply with exactly the fixture response.',
    options: {
      cwd: root,
      model: 'qwen3.5:9b-q4_K_M',
      permissionMode: 'default',
      settingSources: [],
      env,
      canUseTool: async () => ({ behavior: 'deny', message: 'contract test does not permit tools' }),
    },
  });

  let assistantContent = '';
  for await (const event of agent) {
    if (event?.type !== 'assistant') continue;
    const blocks = event.message?.content;
    if (Array.isArray(blocks)) {
      assistantContent += blocks.filter(block => block?.type === 'text' && typeof block.text === 'string')
        .map(block => block.text).join('');
    }
  }

  assert.equal(observedRequest?.method, 'POST');
  assert.equal(observedRequest?.url, '/api/chat');
  assert.equal(observedRequest?.body?.think, false,
    'OpenClaude must disable hybrid-model reasoning by default for Ollama');
  assert.equal(assistantContent, assistantText,
    'OpenClaude query() must yield Ollama assistant content to the host');
  console.log('PASS: real OpenClaude query() sent think=false to native Ollama chat and yielded assistant text.');
} finally {
  await new Promise(resolve => portServer.close(resolve));
  await rm(root, { recursive: true, force: true });
}
