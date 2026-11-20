import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const here = path.dirname(fileURLToPath(import.meta.url));

test('SDK diagnostics persist correlated errors, redact credentials and rotate bounded logs', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-sdk-diagnostics-'));
  t.after(() => rm(temp, { recursive: true, force: true }));
  process.env.SOLARMINER_INTELLIGENCE_DIAGNOSTICS_LOG = path.join(temp, 'diagnostics.log');
  const diagnostics = await import(`./sdk-diagnostics.mjs?test=${Date.now()}`);
  diagnostics.setIntelligenceDiagnosticContext({ diagnosticId: 'efde4a1f-2b0c-4b84-a958-7cf31acb9596', stage: 'sdk_stream_wait', startedAt: Date.now() - 42 });
  diagnostics.installOpenClaudeErrorHook();
  globalThis[Symbol.for('solarminer.openclaude.sdk-error-hook')](
    Object.assign(new Error('provider failed token=secretValue123'), { stack: 'Error: provider failed Authorization: Bearer secretBearer987' }));
  const first = JSON.parse((await readFile(process.env.SOLARMINER_INTELLIGENCE_DIAGNOSTICS_LOG, 'utf8')).trim());
  assert.equal(first.diagnostic_id, 'efde4a1f-2b0c-4b84-a958-7cf31acb9596');
  assert.equal(first.stage, 'sdk_stream_wait');
  assert.equal(first.source, 'openclaude_sdk_exception');
  assert.match(first.error.message, /\[REDACTED\]/);
  assert.doesNotMatch(JSON.stringify(first), /secretValue123|secretBearer987/);
  await writeFile(process.env.SOLARMINER_INTELLIGENCE_DIAGNOSTICS_LOG, 'x'.repeat(10 * 1024 * 1024));
  diagnostics.writeIntelligenceDiagnostic({ stage: 'test_rotation', error: new Error('rotate') });
  assert.ok((await readFile(`${process.env.SOLARMINER_INTELLIGENCE_DIAGNOSTICS_LOG}.1`, 'utf8')).length > 0);
});

test('SDK patcher accepts only 0.36.0, patches a single anchor and is idempotent', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'solarminer-sdk-patcher-'));
  t.after(() => rm(temp, { recursive: true, force: true }));
  const sdkDir = path.join(temp, 'dist');
  await mkdir(sdkDir);
  await writeFile(path.join(temp, 'package.json'), JSON.stringify({ version: '0.36.0' }));
  const bundle = path.join(sdkDir, 'sdk.mjs');
  const anchor = `function logError(error) {\n  const err = toError(error);`;
  await writeFile(bundle, anchor);
  const patcher = path.join(here, 'patch-openclaude-sdk-errors.mjs');
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const result = spawnSync(process.execPath, [patcher, bundle], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
  }
  const patched = await readFile(bundle, 'utf8');
  assert.equal(patched.split('solarminer_persistent_sdk_error_hook_v1').length - 1, 1);
  await writeFile(path.join(temp, 'package.json'), JSON.stringify({ version: '0.37.0' }));
  const mismatch = spawnSync(process.execPath, [patcher, bundle], { encoding: 'utf8' });
  assert.notEqual(mismatch.status, 0);
  assert.match(mismatch.stderr, /openclaude_version_mismatch/);
});
