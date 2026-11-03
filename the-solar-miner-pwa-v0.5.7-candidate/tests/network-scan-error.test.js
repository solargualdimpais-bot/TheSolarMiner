import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("local network scan distinguishes a missing Gateway response from zero devices", async () => {
  const source = await readFile(new URL("../gateway-auth.js", import.meta.url), "utf8");
  const start = source.indexOf("export async function scanGatewayLocalNetwork()");
  const end = source.indexOf("export async function applyGatewayLocalNetworkMatches()", start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  const implementation = source.slice(start, end);
  assert.match(implementation, /catch \(error\)/);
  assert.match(implementation, /error instanceof TypeError/);
  assert.match(implementation, /network_scan_gateway_unreachable/);
  assert.match(implementation, /não recebeu resposta do Gateway/);
});
