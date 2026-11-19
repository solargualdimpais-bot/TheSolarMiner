import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { diagnoseGatewayIntelligenceFailure } from '../gateway-auth.js';

const read = name => readFileSync(new URL(`../${name}`, import.meta.url), 'utf8');
const html = read('index.html');
const app = read('app.js');
const auth = read('gateway-auth.js');

test('Owner has an Intelligence panel with protected provider setup and read-only scope disclosure', () => {
  assert.match(html, /data-owner-tab="intelligence"/);
  assert.match(html, /data-owner-panel="intelligence"/);
  for (const tab of ["ollama", "openclaude", "openai", "chat", "reviews"]) {
    assert.match(html, new RegExp(`data-intelligence-tab="${tab}"`));
    assert.match(html, new RegExp(`data-intelligence-panel="${tab}"`));
  }
  assert.match(html, /gateway-intelligence-download-progress/);
  assert.match(html, /gateway-intelligence-ollama-installation/);
  assert.match(html, /gateway-intelligence-model-installation/);
  assert.match(html, /gateway-intelligence-openclaude-installation/);
  assert.match(html, /gateway-intelligence-bootstrap-start/);
  assert.match(html, /gateway-intelligence-status-refresh/);
  assert.match(html, /gateway-intelligence-api-key/);
  assert.match(html, /gateway-intelligence-model/);
  assert.match(html, /gateway-intelligence-question/);
  assert.match(html, /gateway-intelligence-ask-provider/);
  assert.match(html, /Por defeito, perguntas e relatórios usam o Ollama local/i);
  assert.match(html, /OpenAI só é usada quando o Owner a escolhe/i);
  assert.match(html, /previsões e histórico do Energy Engine/i);
  assert.match(html, /Aguardando a primeira revisão diária/i);
  assert.match(html, /gateway-intelligence-reviews-refresh/);
  assert.match(html, /não envia comandos físicos/i);
});

test('PWA uses authenticated Gateway endpoints for provider setup, revocation and analysis', () => {
  assert.match(auth, /\/api\/v1\/intelligence\/provider/);
  assert.match(auth, /\/api\/v1\/intelligence\/ask/);
  assert.match(auth, /\/api\/v1\/intelligence\/bootstrap/);
  assert.match(auth, /startGatewayIntelligenceBootstrap/);
  assert.match(auth, /diagnoseGatewayIntelligenceFailure/);
  assert.match(auth, /error\?\.status === 401/);
  assert.match(auth, /error\?\.status === 403/);
  assert.match(auth, /error\?\.status === 404/);
  assert.match(auth, /intelligence_bootstrap_unavailable/);
  assert.match(auth, /intelligence_agent_unavailable/);
  assert.match(auth, /ollama_runtime_unavailable/);
  assert.match(auth, /ollama_model_not_installed/);
  assert.match(auth, /timeoutMs = 45000/);
  assert.match(auth, /X-SolarMiner-Diagnostic-ID/);
  assert.match(auth, /readGatewayIntelligenceRequestDiagnostic/);
  assert.match(auth, /timeoutMs = 320000/);
  assert.match(auth, /const diagnosticId = crypto\.randomUUID\(\);[\s\S]*?\/api\/v1\/intelligence\/ask[\s\S]*?diagnosticId/);
  assert.match(auth, /new URLSearchParams\(\{ diagnostic_id: diagnosticId \}\)/);
  assert.match(auth, /intelligence_analysis_timeout/);
  assert.match(auth, /\/api\/v1\/health/);
  assert.match(auth, /\/api\/v1\/info/);
  assert.match(auth, /credentials: "omit"/);
  assert.match(auth, /O browser não conseguiu estabelecer HTTPS/);
  assert.match(auth, /saveGatewayIntelligenceProvider\(apiKey, model\)/);
  assert.match(auth, /revokeGatewayIntelligenceProvider/);
  assert.match(auth, /askGatewayIntelligence/);
  assert.match(auth, /readGatewayIntelligenceReviews/);
  assert.match(app, /refreshGatewayIntelligenceProvider/);
  assert.match(app, /Diagnóstico: \$\{diagnosis\}/);
  assert.match(app, /diagnoseGatewayIntelligenceFailure\(error\)/);
  assert.match(app, /state\.bootstrap/);
  assert.match(app, /installed\.ollama === true \? \(local\.runtime === "available" \? "instalado e a responder" : "instalado; serviço sem resposta"\)/);
  assert.match(app, /installed\.ollama === false \? "executável não encontrado" : "estado de instalação desconhecido/);
  assert.match(app, /estado de instalação desconhecido porque a consulta ao Gateway falhou/);
  assert.match(app, /installed\.model \? "instalado"/);
  assert.match(app, /installed\.openclaude === true \? "instalado"/);
  assert.match(app, /ollama_binary_check_failed: "não foi possível verificar a presença do executável Ollama"/);
  assert.match(app, /startGatewayIntelligenceBootstrap\(\)/);
  assert.match(app, /Instalar\/atualizar componentes do Intelligence/);
  assert.match(app, /gateway-intelligence-download-progress/);
  assert.match(app, /setInterval\(refreshGatewayIntelligenceProvider, 15000\)/);
  assert.match(app, /gatewayIntelligenceProviderRefreshInFlight/);
  assert.match(app, /OpenClaude ativo, mas ainda não pronto/);
  assert.match(app, /OpenClaude indisponível/);
  assert.match(app, /refreshGatewayIntelligenceReviews/);
  assert.match(app, /key\.value = ""/);
  assert.match(app, /answer\.textContent = result\.answer/);
  assert.match(app, /confirm\("Esta pergunta e o contexto necessário serão enviados à OpenAI/);
  assert.match(app, /local\.loaded/);
  assert.match(app, /local\.working/);
  assert.match(app, /local\.runtime === "available"/);
  assert.match(app, /modelo ainda não instalado/);
  assert.doesNotMatch(app, /innerHTML\s*=\s*result\.answer/);
});

test('Intelligence diagnostics distinguish Gateway transport, API, auth, and bootstrap failures', async () => {
  const response = (status, body = {}) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
  const error = status => Object.assign(new Error('request failed'), { status });
  const gatewayUrl = 'https://gateway.example.ts.net';

  assert.match(await diagnoseGatewayIntelligenceFailure(error(401)), /sessão Owner expirou/);
  assert.match(await diagnoseGatewayIntelligenceFailure(error(403)), /não tem permissão Owner/);
  assert.match(await diagnoseGatewayIntelligenceFailure(error(404)), /versão do Gateway podem estar dessincronizadas/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(error(503), { detail: 'intelligence_bootstrap_unavailable' })), /broker de instalação/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(error(503), { detail: 'intelligence_agent_unavailable' })), /serviço local OpenClaude/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(error(503), { detail: 'ollama_runtime_unavailable' })), /não prova que o Ollama esteja desinstalado/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(error(503), { detail: 'ollama_model_not_installed' })), /modelo local pedido não está instalado/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(error(503), { detail: 'intelligence_credentials_not_configured' })), /falta configurar a credencial/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(error(429), { detail: 'intelligence_agent_busy' })), /agente local está ocupado/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(error(429), { detail: 'intelligence_hourly_limit_reached' })), /limite de 30 perguntas/);
  assert.match(await diagnoseGatewayIntelligenceFailure(error(503)), /erro interno HTTP 503/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(new Error('timeout'), { code: 'timeout' })), /Tempo limite: a consulta do estado do Intelligence/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(new Error('timeout'), { code: 'timeout', operation: 'analysis', timeoutMs: 320000 })), /análise excedeu 320 segundos/);
  assert.match(await diagnoseGatewayIntelligenceFailure(Object.assign(error(504), { detail: 'intelligence_analysis_timeout' })), /excedeu o limite de cinco minutos/);

  const noConnection = await diagnoseGatewayIntelligenceFailure(new TypeError('fetch failed'), {
    gatewayUrl, fetchImpl: async () => { throw new TypeError('fetch failed'); },
  });
  assert.match(noConnection, /estabelecer HTTPS/);

  const timedOut = await diagnoseGatewayIntelligenceFailure(new TypeError('fetch failed'), {
    gatewayUrl, timeoutMs: 1,
    fetchImpl: (_, { signal }) => new Promise((_, reject) => signal.addEventListener('abort', () => {
      const timeout = new Error('timeout'); timeout.name = 'AbortError'; reject(timeout);
    }, { once: true })),
  });
  assert.match(timedOut, /excedeu o tempo limite/);

  const partialApi = await diagnoseGatewayIntelligenceFailure(new TypeError('fetch failed'), {
    gatewayUrl, fetchImpl: async url => url.pathname.endsWith('/health') ? response(200) : response(503),
  });
  assert.match(partialApi, /respondem, mas um endpoint público foi recusado/);

  const protectedProbe = await diagnoseGatewayIntelligenceFailure(new TypeError('fetch failed'), {
    gatewayUrl, fetchImpl: async () => response(401),
  });
  assert.match(protectedProbe, /endpoint público está a exigir autenticação/);

  const reachable = await diagnoseGatewayIntelligenceFailure(new TypeError('fetch failed'), {
    gatewayUrl, fetchImpl: async () => response(200),
  });
  assert.match(reachable, /consulta autenticada do Intelligence falhou/);

  const intelligenceRouteFailure = await diagnoseGatewayIntelligenceFailure(Object.assign(new TypeError('fetch failed'), { code: 'transport_error' }), {
    gatewayUrl, fetchImpl: async () => response(200),
  });
  assert.match(intelligenceRouteFailure, /pedido autenticado ao Intelligence falhou/);

  const requestId = 'a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1';
  const timedOutInRoute = await diagnoseGatewayIntelligenceFailure(Object.assign(new Error('timeout'), {
    code: 'timeout', operation: 'analysis', requestId, timeoutMs: 320000,
  }), { diagnosticFetch: async () => ({ state: 'in_progress', stage: 'openclaude_agent', stage_elapsed_ms: 12000 }) });
  assert.match(timedOutInRoute, /processá-lo na etapa “openclaude agent” há 12 s/);
  assert.match(timedOutInRoute, new RegExp(requestId));

  const routeFailure = await diagnoseGatewayIntelligenceFailure(Object.assign(new TypeError('fetch failed'), {
    code: 'transport_error', requestId,
  }), { gatewayUrl, fetchImpl: async () => response(200),
    diagnosticFetch: async () => ({ state: 'failed', stage: 'openclaude_agent', error_type: 'Error', error_reason: 'intelligence_permission_denied' }) });
  assert.match(routeFailure, /falha na etapa “openclaude agent” \(Error\), motivo: intelligence permission denied/);

  const traceLookupFailed = await diagnoseGatewayIntelligenceFailure(Object.assign(new TypeError('Failed to fetch'), {
    code: 'transport_error', requestId,
  }), { diagnosticFetch: async () => { throw Object.assign(new TypeError('Failed to fetch'), { code: 'transport_error' }); } });
  assert.match(traceLookupFailed, /Não foi possível consultar o registo do pedido/);
  assert.match(traceLookupFailed, new RegExp(requestId));
  assert.match(traceLookupFailed, /Falha original da pergunta: TypeError: Failed to fetch \(transport_error\)/);

  const agentTrace = await diagnoseGatewayIntelligenceFailure(Object.assign(new TypeError('Failed to fetch'), {
    code: 'transport_error', requestId,
  }), { diagnosticFetch: async () => ({ state: 'failed', stage: 'openclaude_agent',
    agent_trace: { state: 'failed', stage: 'sdk_stream_wait', error_type: 'Error',
      mcp_tool_calls: 1, mcp_tool_results: 0 } }) });
  assert.match(agentTrace, /OpenClaude: failed na etapa “sdk stream wait” \(Error\); chamadas MCP 1, resultados 0/);

  const rejectedTrace = await diagnoseGatewayIntelligenceFailure(Object.assign(new TypeError('Failed to fetch'), {
    code: 'transport_error', requestId,
  }), { diagnosticFetch: async () => ({ state: 'rejected', http_status: 403, request_id: requestId }) });
  assert.match(rejectedTrace, /recusou o pedido.*HTTP 403/);
  assert.match(rejectedTrace, new RegExp(requestId));

  const routeNotSeen = await diagnoseGatewayIntelligenceFailure(Object.assign(new TypeError('fetch failed'), {
    code: 'transport_error', requestId,
  }), { gatewayUrl, fetchImpl: async () => response(200),
    diagnosticFetch: async () => ({ state: 'not_seen', request_id: requestId }) });
  assert.match(routeNotSeen, /não registou este pedido/);
  assert.match(routeNotSeen, /solarminer-intelligence-access\.log/);

  const localAgentUnavailable = await diagnoseGatewayIntelligenceFailure(Object.assign(error(503), { detail: 'intelligence_agent_unavailable' }));
  assert.match(localAgentUnavailable, /serviço local OpenClaude/);
});
