import { readFile, rename, stat, unlink, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { dirname, join } from 'node:path';

const TARGET = process.argv[2] || '/opt/solarminer/intelligence/app/node_modules/@twigpine/openclaude/dist/sdk.mjs';
const VERSION_FILE = join(dirname(TARGET), '..', 'package.json');
const VERSION = '0.36.0';
const MARKER = 'solarminer_persistent_sdk_error_hook_v1';
const ANCHOR = 'function logError(error) {\n  const err = toError(error);';

const packageInfo = JSON.parse(await readFile(VERSION_FILE, 'utf8'));
if (packageInfo.version !== VERSION) throw new Error(`openclaude_version_mismatch:${packageInfo.version}`);
let source = await readFile(TARGET, 'utf8');
if (source.includes(MARKER)) {
  console.log('SDK error hook already installed');
} else {
  const occurrences = source.split(ANCHOR).length - 1;
  if (occurrences !== 1) throw new Error(`openclaude_sdk_error_hook_anchor_mismatch:${occurrences}`);
  const addition = `${ANCHOR}\n  // ${MARKER}\n  try { globalThis[Symbol.for("solarminer.openclaude.sdk-error-hook")]?.(sanitizeError(err)); } catch {}`;
  source = source.replace(ANCHOR, addition);
  const original = await stat(TARGET);
  const temporary = `${TARGET}.${randomUUID()}.tmp`;
  await writeFile(temporary, source, { mode: original.mode & 0o777 });
  try { await rename(temporary, TARGET); }
  catch (error) { await unlink(temporary).catch(() => {}); throw error; }
  console.log('SDK error hook installed');
}

