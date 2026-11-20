import { appendFileSync, closeSync, fchmodSync, fstatSync, openSync, renameSync, statSync, unlinkSync } from 'node:fs';

const LOG_PATH = process.env.SOLARMINER_INTELLIGENCE_DIAGNOSTICS_LOG || '/var/log/solarminer-intelligence/diagnostics.log';
const MAX_BYTES = 10 * 1024 * 1024;
const ROTATIONS = 5;
const CONTEXT_KEY = Symbol.for('solarminer.intelligence.diagnostic-context');
const SDK_HOOK_KEY = Symbol.for('solarminer.openclaude.sdk-error-hook');

function redact(value) {
  return String(value ?? '')
    .replace(/(authorization\s*[:=]\s*bearer\s+)[^\s,;"']+/ig, '$1[REDACTED]')
    .replace(/((?:access[\s_-]*token|refresh[\s_-]*token|token|password|passwd|secret|api[\s_-]*key|cookie)\s*[:=]\s*)[^\s,;"']+/ig, '$1[REDACTED]')
    .replace(/\b(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{20,})\b/g, '[REDACTED]')
    .slice(0, 16000);
}

function rotateIfNeeded() {
  let size = 0;
  try { size = statSync(LOG_PATH).size; } catch (error) { if (error?.code !== 'ENOENT') throw error; }
  if (size < MAX_BYTES) return;
  try { unlinkSync(`${LOG_PATH}.${ROTATIONS}`); } catch (error) { if (error?.code !== 'ENOENT') throw error; }
  for (let index = ROTATIONS - 1; index >= 1; index -= 1) {
    try { renameSync(`${LOG_PATH}.${index}`, `${LOG_PATH}.${index + 1}`); }
    catch (error) { if (error?.code !== 'ENOENT') throw error; }
  }
  try { renameSync(LOG_PATH, `${LOG_PATH}.1`); }
  catch (error) { if (error?.code !== 'ENOENT') throw error; }
}

export function sanitizeSdkError(error) {
  if (typeof error === 'string') return { message: redact(error) };
  if (!error || typeof error !== 'object') return { message: redact(String(error)) };
  const message = typeof error.message === 'string' ? error.message
    : typeof error.error === 'string' ? error.error
      : typeof error.reason === 'string' ? error.reason
        : typeof error.code === 'string' ? `SDK error (${error.code})` : 'OpenClaude reported an error without a message';
  const stack = typeof error.stack === 'string' ? error.stack
    : typeof error.error === 'string' ? error.error : '';
  return {
    name: redact(typeof error.name === 'string' ? error.name : error.type || 'Error').slice(0, 128),
    message: redact(message || stack).slice(0, 4000),
    ...(stack ? { stack: redact(stack).slice(0, 12000) } : {}),
    ...(typeof error.code === 'string' && /^[A-Z0-9_.-]{1,64}$/i.test(error.code) ? { code: error.code } : {}),
  };
}

export function writeIntelligenceDiagnostic({ diagnosticId = null, stage = 'unknown', durationMs = 0,
  source = 'openclaude_sdk', error } = {}) {
  try {
    rotateIfNeeded();
    const context = globalThis[CONTEXT_KEY] || {};
    const safeId = typeof diagnosticId === 'string' && /^[0-9a-f-]{36}$/i.test(diagnosticId)
      ? diagnosticId : (typeof context.diagnosticId === 'string' ? context.diagnosticId : null);
    const payload = {
      timestamp: new Date().toISOString(), diagnostic_id: safeId,
      stage: redact(stage).slice(0, 96), duration_ms: Number.isFinite(durationMs) ? Math.max(0, Math.floor(durationMs)) : 0,
      source: redact(source).slice(0, 64), error: sanitizeSdkError(error),
    };
    const line = `${JSON.stringify(payload)}\n`;
    const descriptor = openSync(LOG_PATH, 'a', 0o600);
    try {
      if (!fstatSync(descriptor).isFile()) return;
      fchmodSync(descriptor, 0o600);
      appendFileSync(descriptor, line, { encoding: 'utf8' });
    } finally { closeSync(descriptor); }
  } catch {
    // Diagnostics are best-effort and must never change inference behavior.
  }
}

export function installOpenClaudeErrorHook() {
  try {
    globalThis[SDK_HOOK_KEY] = error => {
      const context = globalThis[CONTEXT_KEY] || {};
      writeIntelligenceDiagnostic({ diagnosticId: context.diagnosticId, stage: context.stage || 'sdk_internal_error',
        durationMs: context.startedAt ? Date.now() - context.startedAt : 0, source: 'openclaude_sdk_exception', error });
    };
  } catch { /* Error reporting must not interfere with the SDK. */ }
}

export function setIntelligenceDiagnosticContext({ diagnosticId = null, stage = 'unknown', startedAt = Date.now() } = {}) {
  try { globalThis[CONTEXT_KEY] = { diagnosticId, stage, startedAt }; } catch { /* best effort */ }
}

