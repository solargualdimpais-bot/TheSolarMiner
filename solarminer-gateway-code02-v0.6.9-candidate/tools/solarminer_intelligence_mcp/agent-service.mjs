import http from 'node:http';
import { lstat, mkdir, open, readFile, stat } from 'node:fs/promises';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';

const sdkPath = process.env.SOLARMINER_OPENCLAUDE_SDK || '/opt/solarminer/intelligence/app/node_modules/@twigpine/openclaude/dist/sdk.mjs';
const { query } = await import(pathToFileURL(sdkPath).href);

const host = '127.0.0.1';
const port = Number(process.env.SOLARMINER_INTELLIGENCE_PORT || 8765);
const cwd = process.env.SOLARMINER_INTELLIGENCE_STATE || '/var/lib/solarminer-intelligence/work';
const developmentWorkspace = resolve(process.env.SOLARMINER_INTELLIGENCE_DEV_WORKSPACE || join(cwd, 'source/solarminer-gateway-code02-v0.6.9-candidate'));
const base = process.env.SOLARMINER_INTELLIGENCE_URL || 'https://localhost:8443/api/v1/intelligence';
const allowedTools = new Set([
  'mcp__solarminer__solarminer_snapshot',
  'mcp__solarminer__solarminer_device_readings',
  'mcp__solarminer__solarminer_energy_status',
  'mcp__solarminer__solarminer_recent_events',
  'mcp__solarminer__solarminer_gateway_diagnostics',
  'mcp__solarminer__solarminer_github_diagnostics',
  'mcp__solarminer__solarminer_equipment_inventory',
  'mcp__solarminer__solarminer_dps_assessment',
  'mcp__solarminer__solarminer_energy_forecast_evaluation',
  'mcp__solarminer__solarminer_update_outcomes',
  'mcp__solarminer__solarminer_device_response_history',
]);
const developmentValidationTool = 'mcp__solarminer__solarminer_validate_intelligence_workspace';
const developmentFileTools = new Set(['Read', 'Edit', 'Write', 'Glob', 'Grep']);
let active = false;
let requestCount = 0;
let windowStartedAt = Date.now();

async function persistentSessionId(development = false) {
  await mkdir(cwd, { recursive: true, mode: 0o700 });
  const sessionPath = join(cwd, development ? 'development-session.id' : 'resident-session.id');
  try {
    const value = (await readFile(sessionPath, 'utf8')).trim();
    if (/^[0-9a-f-]{36}$/i.test(value)) return value;
    throw new Error('resident_session_id_invalid');
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error;
  }
  const value = randomUUID();
  try {
    const file = await open(sessionPath, 'wx', 0o600);
    try { await file.writeFile(`${value}\n`, 'utf8'); await file.sync(); }
    finally { await file.close(); }
    return value;
  } catch (error) {
    if (error?.code !== 'EEXIST') throw error;
    const raced = (await readFile(sessionPath, 'utf8')).trim();
    if (!/^[0-9a-f-]{36}$/i.test(raced)) throw new Error('resident_session_id_invalid');
    return raced;
  }
}

function workspaceRelativePath(rawPath) {
  if (typeof rawPath !== 'string' || !rawPath || rawPath.includes('\0')) return null;
  const target = resolve(developmentWorkspace, rawPath);
  const relativePath = relative(developmentWorkspace, target);
  if (!relativePath || relativePath === '.' || relativePath.startsWith(`..${sep}`) || relativePath === '..' || isAbsolute(relativePath)) return null;
  return { target, relativePath, auditPath: relativePath.split(sep).join('/') };
}

async function isWorkspaceToolAllowed(name, input) {
  if (!developmentFileTools.has(name) || !input || typeof input !== 'object') return false;
  const rawPath = ['Read', 'Edit', 'Write'].includes(name) ? input.file_path : input.path;
  if (name === 'Glob' || name === 'Grep') {
    const pattern = name === 'Glob' ? input.pattern : input.glob;
    if (typeof pattern === 'string' && pattern.split(/[\\/]/).includes('..')) return false;
    if (rawPath === undefined) return true;
  }
  if (typeof rawPath !== 'string') return false;
  const resolved = workspaceRelativePath(rawPath);
  if (!resolved) return false;
  const { target, relativePath } = resolved;
  const components = relativePath.split(sep);
  if (components.includes('.git') || components.some(part => part === '.github')) return false;
  let cursor = developmentWorkspace;
  try {
    const rootInfo = await lstat(developmentWorkspace);
    if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink()) return false;
    for (const component of components) {
      cursor = join(cursor, component);
      try {
        const info = await lstat(cursor);
        if (info.isSymbolicLink()) return false;
      } catch (error) {
        if (error?.code !== 'ENOENT') return false;
        break;
      }
    }
  } catch { return false; }
  if (components[0] === 'tests' && ['Edit', 'Write'].includes(name)) {
    try { await stat(target); return false; }
    catch (error) { if (error?.code !== 'ENOENT') return false; }
  }
  return true;
}

async function auditDeniedTool(name) {
  const tool = typeof name === 'string' && /^[A-Za-z0-9_.:-]{1,120}$/.test(name) ? name : 'unknown_tool';
  try {
    const response = await fetch(`${base}/agent-events`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.SOLARMINER_INTELLIGENCE_TOKEN}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ event: 'tool_denied', tool }),
      signal: AbortSignal.timeout(5000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

async function auditWorkspaceAction(event, tool, relativePath) {
  try {
    const response = await fetch(`${base}/agent-events`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.SOLARMINER_INTELLIGENCE_TOKEN}`,
        'Content-Type': 'application/json', Accept: 'application/json',
      },
      body: JSON.stringify({ event, tool, path: relativePath }),
      signal: AbortSignal.timeout(5000),
    });
    return response.ok;
  } catch { return false; }
}

function send(response, status, body) {
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  response.end(JSON.stringify(body));
}

async function readBody(request) {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > 12000) throw new Error('request_too_large');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

async function runAnalysis(prompt, { development = false } = {}) {
  if (!process.env.OPENAI_API_KEY) throw new Error('openai_credential_not_configured');
  if (!process.env.OPENAI_MODEL) throw new Error('openai_model_not_configured');
  if (!process.env.SOLARMINER_INTELLIGENCE_TOKEN) throw new Error('solarminer_service_credential_not_configured');
  if (development) {
    const workspace = await stat(developmentWorkspace).catch(() => null);
    if (!workspace?.isDirectory()) throw new Error('development_workspace_unavailable');
  }
  if (active) throw new Error('analysis_busy');
  if (Date.now() - windowStartedAt >= 60 * 60 * 1000) {
    requestCount = 0;
    windowStartedAt = Date.now();
  }
  if (requestCount >= 30) throw new Error('analysis_hourly_limit_reached');
  requestCount += 1;
  active = true;
  const abortController = new AbortController();
  const timeout = setTimeout(() => abortController.abort(), development ? 20 * 60 * 1000 : 120000);
  try {
    const agentQuery = query({
      prompt,
      options: {
        cwd: development ? developmentWorkspace : cwd,
        sessionId: development ? await persistentSessionId(true) : process.env.SOLARMINER_INTELLIGENCE_SESSION_ID || await persistentSessionId(),
        permissionMode: 'default',
        model: process.env.OPENAI_MODEL || undefined,
        abortController,
        systemPrompt: development
          ? 'You are SolarMiner Intelligence in an isolated source-development session. Use the read-only SolarMiner MCP tools to verify the reported problem, then make a focused code change in this checkout only when evidence supports it. Add new regression tests when useful, but do not edit existing test files, release workflows, Git metadata, signing material, or claim tests were run. After a source change, invoke solarminer_validate_intelligence_workspace with gateway-python for Gateway Python changes, intelligence for MCP/agent changes, or both when appropriate, and report the exact results. You have no shell or publication tools. Do not access or modify the live installation, database, settings, services, or devices. Report evidence, exact changed files, and validation still required. Essential energy and protection behavior must remain local and independent of the cloud model.'
          : 'You are SolarMiner Intelligence. Use only the read-only SolarMiner MCP tools. Never claim live device data when a tool marks it cached or unavailable. Compare all Gateway-reported equipment, energy-engine readings, production/consumption forecasts and history. Evaluate forecast error, bias, confidence and calibration using the Energy Engine evidence. Analyze update failures/rollbacks from persisted diagnostics. Compare device commands with later observed state, clearly distinguishing confirmed, unconfirmed and unavailable responses. Assess DPS mappings using exact product identity and source confidence; label unknowns and conflicts, never guess a physical meaning or unit. MAC/IP discovery is limited to cached inventory; do not scan the LAN. You may formulate concrete, testable software-change proposals for any engine, with evidence and regression tests, but never execute a device command, change active settings, edit production code, bypass tests/signatures/recovery, or claim a proposed algorithm is validated. Essential energy and protection behavior must remain local and independent of the cloud model.',
        // The MCP subprocess must not inherit the OpenAI credential. OpenClaude
        // merges its parent environment into stdio-server environments, so run
        // the trusted env utility in clean-environment mode and pass only the
        // Gateway endpoint, service token, CA bundle and Node runtime onward.
        mcpServers: {
          solarminer: {
            type: 'stdio',
            command: '/usr/bin/env',
            args: ['-i',
              `PATH=${process.env.PATH || '/usr/bin:/bin'}`,
              `SOLARMINER_INTELLIGENCE_URL=${base}`,
              `SOLARMINER_INTELLIGENCE_DEV_WORKSPACE=${developmentWorkspace}`,
              'SOLARMINER_INTELLIGENCE_TOKEN_FILE=/usr/share/solarminer/intelligence-mcp/service.token',
              `NODE_EXTRA_CA_CERTS=${process.env.SOLARMINER_GATEWAY_CA || '/usr/share/solarminer/intelligence-agent/gateway-ca.crt'}`,
              process.env.SOLARMINER_NODE || process.execPath,
              process.env.SOLARMINER_MCP_SERVER || '/usr/share/solarminer/intelligence-mcp/server.mjs'],
            env: {},
          },
        },
        canUseTool: async (name, input) => {
          if (allowedTools.has(name)) return { behavior: 'allow' };
          if (development && name === developmentValidationTool) return { behavior: 'allow' };
          if (development && await isWorkspaceToolAllowed(name, input)) {
            if (['Edit', 'Write'].includes(name)) {
              const target = workspaceRelativePath(input.file_path);
              const event = name === 'Edit' ? 'workspace_file_edit' : 'workspace_file_write';
              if (!target || !await auditWorkspaceAction(event, name, target.auditPath)) {
                await auditDeniedTool(name);
                return { behavior: 'deny', message: 'Workspace write denied because its audit record could not be stored.' };
              }
            }
            return { behavior: 'allow' };
          }
          // Record the denied action centrally before returning the denial. If
          // the audit endpoint is unavailable, the tool remains denied anyway.
          await auditDeniedTool(name);
          return { behavior: 'deny', message: development
            ? 'Only read-only SolarMiner MCP tools and file operations confined to the isolated source workspace are allowed.'
            : 'Only the read-only SolarMiner MCP tools are allowed.' };
        },
      },
    });
    const text = [];
    for await (const message of agentQuery) {
      if (message?.type !== 'assistant' || !Array.isArray(message.message?.content)) continue;
      for (const item of message.message.content) if (item?.type === 'text' && typeof item.text === 'string') text.push(item.text);
    }
    const answer = text.join('\n').trim().slice(0, 16000);
    if (!answer) throw new Error('analysis_returned_no_text');
    return { status: 'ok', answer };
  } finally {
    clearTimeout(timeout);
    active = false;
  }
}

async function runScheduledReview() {
  const report = await runAnalysis(
    'Faz a revisão diária dos dados recentes do SolarMiner. Usa as ferramentas disponíveis para inspecionar inventário e todos os equipamentos, falhas e atualizações, respostas observadas dos devices, atribuições DPS e previsões/histórico do Energy Engine. Compara valores previstos e medidos apenas quando existirem períodos comparáveis e dados válidos. Apresenta: evidência e timestamps; dados atuais, históricos e indisponíveis; anomalias e confiança; uma proposta concreta por oportunidade, com ficheiros/motor provável e testes de regressão ou backtest necessários. Não alteres nem afirmes que alteraste código, parâmetros, serviços ou equipamentos. Se os dados não justificarem uma alteração, regista explicitamente que não há proposta sustentada.'
  );
  const response = await fetch(`${base}/reviews`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.SOLARMINER_INTELLIGENCE_TOKEN}`,
      'Content-Type': 'application/json', Accept: 'application/json',
    },
    body: JSON.stringify({ review_kind: 'daily_engine_review', report_text: report.answer }),
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error(`review_store_failed_${response.status}`);
  return { status: 'recorded' };
}

function scheduleDailyReview() {
  const rawHour = Number(process.env.SOLARMINER_INTELLIGENCE_REVIEW_HOUR || 21);
  const hour = Number.isInteger(rawHour) && rawHour >= 0 && rawHour <= 23 ? rawHour : 21;
  const now = new Date();
  const next = new Date(now);
  next.setHours(hour, 0, 0, 0);
  if (next <= now) next.setDate(next.getDate() + 1);
  const timer = setTimeout(async () => {
    try { await runScheduledReview(); }
    catch (error) { console.error(`scheduled_review_failed:${String(error?.message || 'unknown').slice(0, 80)}`); }
    finally { scheduleDailyReview(); }
  }, next.getTime() - now.getTime());
  timer.unref();
}

const server = http.createServer(async (request, response) => {
  if (request.method === 'GET' && request.url === '/health') {
    return send(response, 200, {
      status: 'ok', agent: 'OpenClaude', provider: 'OpenAI',
      configured: Boolean(process.env.OPENAI_API_KEY && process.env.OPENAI_MODEL && process.env.SOLARMINER_INTELLIGENCE_TOKEN),
      busy: active,
    });
  }
  if (request.method === 'POST' && request.url === '/v1/review') {
    const expected = process.env.SOLARMINER_INTELLIGENCE_LOCAL_TOKEN || '';
    const supplied = request.headers.authorization?.startsWith('Bearer ') ? request.headers.authorization.slice(7) : '';
    if (!expected || supplied !== expected) return send(response, 401, { error: 'unauthorized' });
    try { return send(response, 201, await runScheduledReview()); }
    catch { return send(response, 503, { error: 'scheduled_review_failed' }); }
  }
  if (request.method !== 'POST' || !['/v1/analyze', '/v1/develop'].includes(request.url)) return send(response, 404, { error: 'not_found' });
  const development = request.url === '/v1/develop';
  const expected = process.env.SOLARMINER_INTELLIGENCE_LOCAL_TOKEN || '';
  const supplied = request.headers.authorization?.startsWith('Bearer ') ? request.headers.authorization.slice(7) : '';
  if (!expected || supplied !== expected) return send(response, 401, { error: 'unauthorized' });
  try {
    const body = await readBody(request);
    const prompt = body?.prompt;
    if (typeof prompt !== 'string' || !prompt.trim() || prompt.length > 8000) return send(response, 422, { error: 'prompt_must_be_1_to_8000_characters' });
    return send(response, 200, await runAnalysis(prompt.trim(), { development }));
  } catch (error) {
    const known = new Set([
      'openai_credential_not_configured', 'openai_model_not_configured', 'solarminer_service_credential_not_configured',
      'analysis_busy', 'analysis_hourly_limit_reached', 'request_too_large',
      'analysis_returned_no_text', 'resident_session_id_invalid', 'development_workspace_unavailable',
    ]);
    const raw = String(error?.message || 'analysis_failed');
    const message = known.has(raw) ? raw : 'provider_or_agent_request_failed';
    const status = message === 'openai_credential_not_configured' || message === 'openai_model_not_configured' ||
      message === 'solarminer_service_credential_not_configured' ? 503
      : message === 'analysis_busy' || message === 'analysis_hourly_limit_reached' ? 429
      : message === 'request_too_large' ? 413 : 502;
    return send(response, status, { error: message.slice(0, 120) });
  }
});

server.requestTimeout = 130000;
server.headersTimeout = 5000;
server.listen(port, host);
scheduleDailyReview();
