import http from 'node:http';
import { lstat, mkdir, open, readFile, stat } from 'node:fs/promises';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { installOpenClaudeErrorHook, setIntelligenceDiagnosticContext, writeIntelligenceDiagnostic,
  sanitizeSdkError } from './sdk-diagnostics.mjs';

const sdkPath = process.env.SOLARMINER_OPENCLAUDE_SDK || '/opt/solarminer/intelligence/app/node_modules/@twigpine/openclaude/dist/sdk.mjs';
const { query } = await import(pathToFileURL(sdkPath).href);
installOpenClaudeErrorHook();

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
const requestDiagnostics = new Map();

function updateRequestDiagnostic(requestId, { stage, state = 'in_progress', errorType = null, errorCode = null,
  errorMessage = null, providerHttpStatus = null } = {}) {
  if (typeof requestId !== 'string' || !/^[0-9a-f-]{36}$/i.test(requestId)) return;
  const now = Date.now();
  for (const [key, value] of requestDiagnostics) {
    if (now - value.updatedAt > 10 * 60 * 1000) requestDiagnostics.delete(key);
  }
  let entry = requestDiagnostics.get(requestId);
  if (!entry) {
    entry = { request_id: requestId, state: 'in_progress', stage: 'agent_received', startedAt: now,
      stageStartedAt: now, updatedAt: now, steps: [], mcp_tool_calls: 0, mcp_tool_results: 0,
      mcp_tool_failures: 0, sdk_messages: 0, sdk_assistant_messages: 0, sdk_assistant_text_blocks: 0,
      sdk_assistant_text_chars: 0, sdk_non_assistant_text_blocks: 0 };
    requestDiagnostics.set(requestId, entry);
  }
  if (stage && stage !== entry.stage) {
    entry.steps.push({ stage: entry.stage,
      duration_ms: Math.max(0, now - entry.stageStartedAt) });
    entry.stage = stage;
    entry.stageStartedAt = now;
  }
  entry.state = state;
  if (errorType) entry.error_type = String(errorType).slice(0, 64);
  if (errorCode && /^[A-Z0-9_]{1,32}$/.test(errorCode)) entry.error_code = errorCode;
  if (typeof errorMessage === 'string' && errorMessage) entry.error_message = sanitizeSdkError(errorMessage).message;
  if (Number.isInteger(providerHttpStatus) && providerHttpStatus >= 400 && providerHttpStatus <= 599) {
    entry.provider_http_status = providerHttpStatus;
  }
  entry.updatedAt = now;
  setIntelligenceDiagnosticContext({ diagnosticId: requestId, stage: entry.stage, startedAt: entry.startedAt });
  while (requestDiagnostics.size > 64) {
    const oldest = [...requestDiagnostics.entries()].reduce((a, b) => a[1].startedAt <= b[1].startedAt ? a : b)[0];
    requestDiagnostics.delete(oldest);
  }
}

function requestDiagnosticSnapshot(requestId) {
  const entry = requestDiagnostics.get(requestId);
  if (!entry) return { state: 'not_seen', request_id: requestId };
  const now = Date.now();
  return { request_id: entry.request_id, state: entry.state, stage: entry.stage,
    error_type: entry.error_type || null, error_code: entry.error_code || null,
    error_message: entry.error_message || null,
    provider_http_status: entry.provider_http_status || null,
    mcp_tool_calls: entry.mcp_tool_calls, mcp_tool_results: entry.mcp_tool_results,
    mcp_tool_failures: entry.mcp_tool_failures, sdk_messages: entry.sdk_messages,
    sdk_assistant_messages: entry.sdk_assistant_messages,
    sdk_assistant_text_blocks: entry.sdk_assistant_text_blocks,
    sdk_assistant_text_chars: entry.sdk_assistant_text_chars,
    sdk_non_assistant_text_blocks: entry.sdk_non_assistant_text_blocks,
    total_elapsed_ms: Math.max(0, now - entry.startedAt),
    stage_elapsed_ms: Math.max(0, now - entry.stageStartedAt), steps: entry.steps.slice(-12) };
}

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

function inferenceConfig(provider) {
  if (provider === 'ollama') {
    const model = process.env.SOLARMINER_OLLAMA_MODEL || 'qwen3.5:9b-q4_K_M';
    return {
      model,
      env: {
        CLAUDE_CODE_USE_OPENAI: '1',
        OPENAI_BASE_URL: process.env.SOLARMINER_OLLAMA_BASE_URL || 'http://127.0.0.1:11434/v1',
        // Ollama's OpenAI-compatible endpoint ignores the key; keep a fixed
        // local sentinel rather than forwarding any cloud credential.
        OPENAI_API_KEY: 'ollama-local',
        OPENAI_MODEL: model,
      },
    };
  }
  if (provider === 'openai') {
    if (!process.env.OPENAI_API_KEY) throw new Error('openai_credential_not_configured');
    if (!process.env.OPENAI_MODEL) throw new Error('openai_model_not_configured');
    return {
      model: process.env.OPENAI_MODEL,
      env: {
        CLAUDE_CODE_USE_OPENAI: '1',
        OPENAI_BASE_URL: 'https://api.openai.com/v1',
        OPENAI_API_KEY: process.env.OPENAI_API_KEY,
        OPENAI_MODEL: process.env.OPENAI_MODEL,
      },
    };
  }
  throw new Error('provider_invalid');
}

async function localModelStatus() {
  const model = process.env.SOLARMINER_OLLAMA_MODEL || 'qwen3.5:9b-q4_K_M';
  const baseUrl = (process.env.SOLARMINER_OLLAMA_BASE_URL || 'http://127.0.0.1:11434/v1').replace(/\/v1\/?$/, '');
  try {
    const [tagsResponse, psResponse] = await Promise.all([
      fetch(`${baseUrl}/api/tags`, { signal: AbortSignal.timeout(2000) }),
      fetch(`${baseUrl}/api/ps`, { signal: AbortSignal.timeout(2000) }),
    ]);
    if (!tagsResponse.ok) throw new Error('ollama_runtime_unavailable');
    const tags = await tagsResponse.json();
    const ps = psResponse.ok ? await psResponse.json() : {};
    const matches = item => item?.name === model || item?.model === model;
    return {
      runtime: 'available', model,
      installed: Array.isArray(tags.models) && tags.models.some(matches),
      loaded: Array.isArray(ps.models) && ps.models.some(matches),
      working: active,
    };
  } catch {
    return { runtime: 'unavailable', model, installed: false, loaded: false, working: active };
  }
}

async function runAnalysis(prompt, { development = false, provider = 'ollama', diagnosticId = null } = {}) {
  const analysisStartedAt = Date.now();
  setIntelligenceDiagnosticContext({ diagnosticId, stage: 'provider_precheck', startedAt: analysisStartedAt });
  updateRequestDiagnostic(diagnosticId, { stage: 'provider_precheck' });
  const inference = inferenceConfig(provider);
  if (provider === 'ollama') {
    const local = await localModelStatus();
    if (local.runtime !== 'available') throw new Error('ollama_runtime_unavailable');
    if (!local.installed) throw new Error('ollama_model_not_installed');
  }
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
  // The 9B local model can take several minutes on CPU. The PWA, Gateway and
  // Nginx use slightly longer deadlines so the model's own timeout is decisive.
  const timeout = setTimeout(() => abortController.abort(), development ? 20 * 60 * 1000 : 300000);
  try {
    updateRequestDiagnostic(diagnosticId, { stage: 'sdk_query_start' });
    const agentQuery = query({
      prompt,
      options: {
        cwd: development ? developmentWorkspace : cwd,
        sessionId: development ? await persistentSessionId(true) : process.env.SOLARMINER_INTELLIGENCE_SESSION_ID || await persistentSessionId(),
        permissionMode: 'default',
        model: inference.model,
        env: inference.env,
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
    updateRequestDiagnostic(diagnosticId, { stage: 'sdk_stream_wait' });
    for await (const message of agentQuery) {
      if (message?.type === 'result' && Array.isArray(message.errors) && message.errors.length) {
        const errors = message.errors.slice(0, 20);
        const summaries = errors.map(error => sanitizeSdkError(error).message).filter(Boolean);
        for (const error of errors) writeIntelligenceDiagnostic({ diagnosticId, stage: `sdk_result_${message.subtype || 'error'}`,
          durationMs: Date.now() - analysisStartedAt, source: 'openclaude_sdk_result_error', error });
        if (summaries.length) updateRequestDiagnostic(diagnosticId, { errorType: message.subtype || 'OpenClaudeResultError',
          errorMessage: summaries.join(' | ') });
      }
      const blocks = Array.isArray(message?.message?.content) ? message.message.content : [];
      const messageType = typeof message?.type === 'string' ? message.type : '';
      const toolUses = blocks.filter(item => item?.type === 'tool_use').length;
      const toolResultBlocks = blocks.filter(item => item?.type === 'tool_result');
      const toolResults = toolResultBlocks.length;
      const toolFailures = toolResultBlocks.filter(item => item.is_error === true).length;
      const textBlocks = blocks.filter(item => item?.type === 'text' && typeof item.text === 'string');
      const entry = typeof diagnosticId === 'string' ? requestDiagnostics.get(diagnosticId) : null;
      if (entry) {
        entry.sdk_messages += 1;
        if (messageType === 'assistant') {
          entry.sdk_assistant_messages += 1;
          entry.sdk_assistant_text_blocks += textBlocks.length;
          entry.sdk_assistant_text_chars += textBlocks.reduce((sum, item) => sum + item.text.length, 0);
        } else {
          entry.sdk_non_assistant_text_blocks += textBlocks.length;
        }
      }
      if (entry && toolUses) entry.mcp_tool_calls += toolUses;
      if (entry && toolResults) entry.mcp_tool_results += toolResults;
      if (entry && toolFailures) entry.mcp_tool_failures += toolFailures;
      if (toolResults) updateRequestDiagnostic(diagnosticId, { stage: 'mcp_tool_result' });
      else if (toolUses) updateRequestDiagnostic(diagnosticId, { stage: 'mcp_tool_call' });
      else if (messageType === 'assistant' && textBlocks.some(item => item.text.trim())) {
        updateRequestDiagnostic(diagnosticId, { stage: 'sdk_assistant_text_received' });
      }
      if (messageType === 'assistant') {
        for (const item of textBlocks) text.push(item.text);
      }
    }
    const answer = text.join('\n').trim().slice(0, 16000);
    if (!answer) {
      const entry = typeof diagnosticId === 'string' ? requestDiagnostics.get(diagnosticId) : null;
      const stage = entry?.sdk_assistant_text_blocks
        ? 'sdk_assistant_text_empty' : 'sdk_stream_complete_no_assistant_text';
      updateRequestDiagnostic(diagnosticId, { stage, state: 'failed', errorType: 'EmptyAssistantResponse' });
      throw new Error('analysis_returned_no_text');
    }
    updateRequestDiagnostic(diagnosticId, { stage: 'sdk_completed', state: 'completed' });
    return { status: 'ok', answer, provider };
  } catch (error) {
    const current = typeof diagnosticId === 'string' ? requestDiagnostics.get(diagnosticId) : null;
    const safeError = sanitizeSdkError(error);
    writeIntelligenceDiagnostic({ diagnosticId, stage: current?.stage || 'sdk_query_exception',
      durationMs: Date.now() - analysisStartedAt, source: 'openclaude_query_exception', error });
    updateRequestDiagnostic(diagnosticId, { state: 'failed', errorType: safeError.name || 'Error',
      errorCode: typeof error?.code === 'string' ? error.code : null, errorMessage: safeError.message });
    throw error;
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
    const local = await localModelStatus();
    return send(response, 200, {
      status: 'ok', agent: 'OpenClaude', default_provider: 'ollama',
      ollama: local,
      openai_configured: Boolean(process.env.OPENAI_API_KEY && process.env.OPENAI_MODEL),
      configured: Boolean(process.env.SOLARMINER_INTELLIGENCE_TOKEN && local.runtime === 'available' && local.installed),
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
  const diagnosticMatch = request.method === 'GET' && request.url.match(/^\/v1\/diagnostics\/([0-9a-f-]{36})$/i);
  if (diagnosticMatch) {
    const expected = process.env.SOLARMINER_INTELLIGENCE_LOCAL_TOKEN || '';
    const supplied = request.headers.authorization?.startsWith('Bearer ') ? request.headers.authorization.slice(7) : '';
    if (!expected || supplied !== expected) return send(response, 401, { error: 'unauthorized' });
    return send(response, 200, requestDiagnosticSnapshot(diagnosticMatch[1]));
  }
  if (request.method !== 'POST' || !['/v1/analyze', '/v1/develop'].includes(request.url)) return send(response, 404, { error: 'not_found' });
  const development = request.url === '/v1/develop';
  const rawDiagnosticId = request.headers['x-solarminer-diagnostic-id'];
  const diagnosticId = typeof rawDiagnosticId === 'string' && /^[0-9a-f-]{36}$/i.test(rawDiagnosticId)
    ? rawDiagnosticId : null;
  updateRequestDiagnostic(diagnosticId, { stage: 'agent_received' });
  const expected = process.env.SOLARMINER_INTELLIGENCE_LOCAL_TOKEN || '';
  const supplied = request.headers.authorization?.startsWith('Bearer ') ? request.headers.authorization.slice(7) : '';
  if (!expected || supplied !== expected) {
    updateRequestDiagnostic(diagnosticId, { stage: 'agent_authentication', state: 'failed', errorType: 'AuthenticationError' });
    return send(response, 401, { error: 'unauthorized' });
  }
  updateRequestDiagnostic(diagnosticId, { stage: 'agent_authenticated' });
  try {
    updateRequestDiagnostic(diagnosticId, { stage: 'agent_reading_prompt' });
    const body = await readBody(request);
    const prompt = body?.prompt;
    if (typeof prompt !== 'string' || !prompt.trim() || prompt.length > 8000) {
      updateRequestDiagnostic(diagnosticId, { stage: 'agent_prompt_validation', state: 'failed', errorType: 'ValidationError' });
      return send(response, 422, { error: 'prompt_must_be_1_to_8000_characters' });
    }
    const provider = development ? 'ollama' : (body?.provider === undefined ? 'ollama' : body.provider);
    updateRequestDiagnostic(diagnosticId, { stage: 'agent_prompt_received' });
    const result = await runAnalysis(prompt.trim(), { development, provider, diagnosticId });
    updateRequestDiagnostic(diagnosticId, { stage: 'agent_response_ready', state: 'completed' });
    return send(response, 200, result);
  } catch (error) {
    const known = new Set([
      'openai_credential_not_configured', 'openai_model_not_configured', 'solarminer_service_credential_not_configured', 'provider_invalid',
      'ollama_runtime_unavailable', 'ollama_model_not_installed',
      'analysis_busy', 'analysis_hourly_limit_reached', 'request_too_large',
      'analysis_returned_no_text', 'analysis_timeout', 'resident_session_id_invalid', 'development_workspace_unavailable',
    ]);
    const timedOut = error?.name === 'AbortError' || error?.code === 'ABORT_ERR';
    const raw = timedOut ? 'analysis_timeout' : String(error?.message || 'analysis_failed');
    const errorType = raw === 'analysis_returned_no_text' ? 'EmptyAssistantResponse'
      : typeof error?.name === 'string' && /^[A-Za-z][A-Za-z0-9]{0,63}$/.test(error.name)
        ? error.name : 'Error';
    const errorCode = typeof error?.code === 'string' && /^[A-Z0-9_]{1,32}$/.test(error.code)
      ? error.code : null;
    const permissionDenied = errorType === 'PermissionError' || errorCode === 'EACCES' || errorCode === 'EPERM';
    const message = permissionDenied ? 'intelligence_permission_denied'
      : known.has(raw) ? raw : 'provider_or_agent_request_failed';
    const providerHttpStatus = Number.isInteger(error?.status) && error.status >= 400 && error.status <= 599
      ? error.status : null;
    updateRequestDiagnostic(diagnosticId, { state: 'failed', errorType,
      errorCode: permissionDenied ? errorCode : null, providerHttpStatus });
    // Keep the diagnosis useful without logging prompts, paths, environment,
    // credentials or raw SDK exception text.
    console.error(JSON.stringify({ event: 'intelligence_analysis_failed', stage: 'openclaude_query',
      error_type: errorType, error_code: permissionDenied ? errorCode : null, reason: message }));
    const status = message === 'openai_credential_not_configured' || message === 'openai_model_not_configured' ||
      message === 'ollama_runtime_unavailable' || message === 'ollama_model_not_installed' ||
      message === 'solarminer_service_credential_not_configured' || message === 'intelligence_permission_denied' ? 503
      : message === 'analysis_timeout' ? 504
      : message === 'analysis_busy' || message === 'analysis_hourly_limit_reached' ? 429
      : message === 'request_too_large' ? 413 : 502;
    return send(response, status, { error: message.slice(0, 120), error_type: errorType,
      ...(permissionDenied && errorCode ? { error_code: errorCode } : {}) });
  }
});

server.requestTimeout = 130000;
server.headersTimeout = 5000;
server.listen(port, host);
scheduleDailyReview();
