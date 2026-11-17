#!/usr/bin/env node
// Read-only Gateway MCP tools plus a fixed test request delegated to the
// authenticated root broker. This process never talks to devices or runs tests.
import readline from 'node:readline';
import { constants as fsConstants, openSync, readFileSync, fstatSync, closeSync } from 'node:fs';

const apiBase = (process.env.SOLARMINER_INTELLIGENCE_URL || 'https://127.0.0.1:8443/api/v1/intelligence').replace(/\/$/, '');
const tokenFile = process.env.SOLARMINER_INTELLIGENCE_TOKEN_FILE || '/usr/share/solarminer/intelligence-mcp/service.token';
const protocolVersion = '2024-11-05';

function readServiceToken() {
  let fd;
  try {
    fd = openSync(tokenFile, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW || 0));
    const stat = fstatSync(fd);
    if (!stat.isFile() || process.platform !== 'win32' &&
        ((process.getuid && stat.uid !== 0 && stat.uid !== process.getuid()) || (stat.mode & 0o037) !== 0)) return '';
    const content = readFileSync(fd, { encoding: 'ascii' });
    const match = /^SOLARMINER_INTELLIGENCE_TOKEN=([A-Za-z0-9_-]{64,128})\n$/.exec(content);
    return match?.[1] || '';
  } catch {
    return '';
  } finally {
    if (fd !== undefined) closeSync(fd);
  }
}

const tools = [
  { name: 'solarminer_snapshot', description: 'Read the current SolarMiner Gateway, Device Engine and Energy Engine snapshot from cached Gateway data. No device communication or control.', inputSchema: { type: 'object', properties: { history_hours: { type: 'integer', minimum: 1, maximum: 168, default: 24 } } } },
  { name: 'solarminer_device_readings', description: 'Read cached Tuya and Shelly readings, communication latency and measurement validity from the Gateway Device Engine.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'solarminer_energy_status', description: 'Read the existing SolarMiner Energy Engine status and recent summary.', inputSchema: { type: 'object', properties: { history_hours: { type: 'integer', minimum: 1, maximum: 168, default: 24 } } } },
  { name: 'solarminer_recent_events', description: 'Read recent sanitized Gateway audit events and smart-device events.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'solarminer_gateway_diagnostics', description: 'Read bounded, sanitized application errors and allowlisted Gateway service journals. Does not run commands.', inputSchema: { type: 'object', properties: { limit: { type: 'integer', minimum: 1, maximum: 200, default: 100 } } } },
  { name: 'solarminer_github_diagnostics', description: 'Read recent sanitized issues from the already-configured private SolarMiner diagnostics repository. Never receives the GitHub token.', inputSchema: { type: 'object', properties: { limit: { type: 'integer', minimum: 1, maximum: 20, default: 10 } } } },
  { name: 'solarminer_equipment_inventory', description: 'Read cached inventory for all Gateway-known equipment, including safe MAC/private IP, product identity and confirmation state. Does not scan the LAN.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'solarminer_dps_assessment', description: 'Read the saved Tuya DPS interpretations, unknown assignments, confidence and mapping conflicts. Reference data is not treated as confirmed truth.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'solarminer_energy_forecast_evaluation', description: 'Read the existing Energy Engine forecast, production/consumption history, calibration and error metrics for evaluation; never changes the algorithm.', inputSchema: { type: 'object', properties: { history_hours: { type: 'integer', minimum: 1, maximum: 168, default: 168 } } } },
  { name: 'solarminer_update_outcomes', description: 'Read bounded update attempts, activation failures and rollback diagnostics from persisted Gateway records.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'solarminer_device_response_history', description: 'Read cached device state changes and confirmed/unconfirmed command outcomes to compare requested inputs with observed responses.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'solarminer_validate_intelligence_workspace', description: 'Run a fixed regression suite in the isolated checkout. Use intelligence for the MCP/agent tests and gateway-python for the complete Gateway Python regression suite. Arbitrary commands and paths are not accepted.', inputSchema: { type: 'object', properties: { suite: { type: 'string', enum: ['intelligence', 'gateway-python'] } }, required: ['suite'], additionalProperties: false } },
];

async function readGateway(path) {
  const token = readServiceToken();
  if (!token) throw new Error('intelligence_service_credential_missing');
  const response = await fetch(`${apiBase}${path}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error(`gateway_read_failed_${response.status}`);
  return response.json();
}

async function auditAgentEvent(event, tool) {
  const token = readServiceToken();
  if (!token) return false;
  try {
    const response = await fetch(`${apiBase}/agent-events`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ event, tool }),
      signal: AbortSignal.timeout(5000),
    });
    return response.ok;
  } catch { return false; }
}

async function validateIntelligenceWorkspace(args) {
  if (!['intelligence', 'gateway-python'].includes(args?.suite)) throw new Error('validation_suite_not_allowed');
  const token = readServiceToken();
  if (!token) throw new Error('intelligence_service_credential_missing');
  const response = await fetch(`${apiBase}/workspace-tests`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ suite: args.suite }),
    signal: AbortSignal.timeout(640000),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload || !['passed', 'failed'].includes(payload.status)) {
    const reason = typeof payload?.detail === 'string' ? payload.detail : `workspace_validation_failed_${response.status}`;
    throw new Error(reason.slice(0, 120));
  }
  return payload;
}

function result(value) {
  return { content: [{ type: 'text', text: JSON.stringify(value) }], structuredContent: value };
}

async function dispatch(message) {
  const { id, method, params = {} } = message;
  if (method === 'initialize') return { jsonrpc: '2.0', id, result: {
    protocolVersion: params.protocolVersion || protocolVersion,
    capabilities: { tools: {} }, serverInfo: { name: 'solarminer-intelligence', version: '0.1.0' },
  } };
  if (method === 'notifications/initialized' || method === 'notifications/cancelled') return null;
  if (method === 'ping') return { jsonrpc: '2.0', id, result: {} };
  if (method === 'tools/list') return { jsonrpc: '2.0', id, result: { tools } };
  if (method === 'tools/call') {
    const name = params.name;
    if (!tools.some(tool => tool.name === name)) return { jsonrpc: '2.0', id, error: { code: -32602, message: 'unknown_tool' } };
    try {
      const args = params.arguments || {};
      if (name === 'solarminer_gateway_diagnostics') {
        return { jsonrpc: '2.0', id, result: result(await readGateway(`/diagnostics?limit=${encodeURIComponent(args.limit || 100)}`)) };
      }
      if (name === 'solarminer_github_diagnostics') {
        return { jsonrpc: '2.0', id, result: result(await readGateway(`/github-reports?limit=${encodeURIComponent(args.limit || 10)}`)) };
      }
      if (name === 'solarminer_validate_intelligence_workspace') {
        return { jsonrpc: '2.0', id, result: result(await validateIntelligenceWorkspace(args)) };
      }
      const snapshot = await readGateway(`/snapshot?history_hours=${encodeURIComponent(args.history_hours || 24)}`);
      if (name === 'solarminer_device_readings') return { jsonrpc: '2.0', id, result: result(snapshot.device_engine) };
      if (name === 'solarminer_energy_status') return { jsonrpc: '2.0', id, result: result(snapshot.energy_engine) };
      if (name === 'solarminer_recent_events') return { jsonrpc: '2.0', id, result: result({ audit: snapshot.recent_audit, device_events: snapshot.recent_device_events }) };
      if (name === 'solarminer_equipment_inventory') return { jsonrpc: '2.0', id, result: result(snapshot.device_inventory) };
      if (name === 'solarminer_dps_assessment') return { jsonrpc: '2.0', id, result: result(snapshot.tuya_dps_knowledge) };
      if (name === 'solarminer_energy_forecast_evaluation') return { jsonrpc: '2.0', id, result: result(snapshot.energy_engine) };
      if (name === 'solarminer_update_outcomes') return { jsonrpc: '2.0', id, result: result(snapshot.update_history) };
      if (name === 'solarminer_device_response_history') return { jsonrpc: '2.0', id, result: result(snapshot.recent_device_events) };
      return { jsonrpc: '2.0', id, result: result(snapshot) };
    } catch (error) {
      return { jsonrpc: '2.0', id, result: { isError: true, content: [{ type: 'text', text: String(error?.message || 'gateway_unavailable') }] } };
    }
  }
  if (id === undefined) return null;
  return { jsonrpc: '2.0', id, error: { code: -32601, message: 'method_not_found' } };
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  if (!line.trim()) continue;
  let message;
  try {
    message = JSON.parse(line);
    const response = await dispatch(message);
    if (response) process.stdout.write(`${JSON.stringify(response)}\n`);
  } catch {
    process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id: message?.id ?? null, error: { code: -32700, message: 'parse_error' } })}\n`);
  }
}
