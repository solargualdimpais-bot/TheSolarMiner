# Contratos API — PWA v0.5.4

## Gateway hardware connectivity diagnostics (CODE02 0.6.33)

`POST /api/v1/integrations/hardware/read` returns a `configuration` object and per-device `connection_state`. Deye uses FC43/MEI14 with a read-only FC03 fallback after FC43 rejection or timeout and discards diagnostic values. Antminer reports its configured model as unverified. Tuya Cloud status is isolated by device ID; one failing ID does not discard successful reads for others. MOES is supported only when exposed through the configured Tuya Cloud project. Shelly has no Gateway driver. This endpoint sends no control commands.

## Gateway signed automatic updates (CODE02 0.6.29)

The Gateway checks its configured, administrator-allowlisted GitHub release daily. It automatically queues an update only after Ed25519 manifest and package verification and a successful independent recovery preflight. The privileged update helper performs SQLite backup, staging, activation, health check and rollback. The Owner PWA can still request an immediate check or manual application and reads progress from `GET /api/v1/system/update/status`.

Gateway connection and Tailscale administration live on the authenticated Owner page. The Home dashboard shows Gateway readings using the units and field names returned by the API; it does not substitute simulated values into the live dashboard.

## Hardware integrations and EV charging (Gateway CODE02 0.6.26)

The Owner PWA calls `GET /api/v1/integrations/hardware`, `PUT /api/v1/integrations/hardware`, and `POST /api/v1/integrations/hardware/read` through the authenticated Gateway client for Deye, Antminer and Tuya only. Tesla Fleet configuration and charging-state reads are part of **Energy → EV charger**: `GET/PUT /api/v1/energy/ev/tesla` and `POST /api/v1/energy/ev/tesla/read`. The Owner role is required. Tuya secrets and the Tesla refresh token are sent only over the authenticated Gateway connection, cleared from the form after save, and never returned. Tesla responses contain charging data for the selected vehicle only. They exclude location, climate, driving and unrelated vehicle metadata. The integration is read-only; it does not start, stop or schedule charging. EV strategies X/Y/Z remain local configuration until a Gateway energy engine and a supported Tesla command flow are implemented.

## Endpoints efetivamente utilizados pela PWA existente

| Método | Endpoint | Utilização |
|---|---|---|
| GET | `/api/v1/health` | Diagnóstico explícito de saúde/versão |
| GET | `/api/v1/info` | Diagnóstico explícito de identificação do serviço |

As chamadas de diagnóstico existentes continuam a ser separadas das novas áreas locais. O incremento v0.5.4 não acrescenta chamadas API.

## Contratos necessários que não foram encontrados no CODE 02 v0.6.5 inspecionado

- Preferências pessoais autenticadas: leitura/gravação por utilizador, com versionamento/migração aditiva.
- Gestão de utilizadores: listagem, convite/associação, alteração de estado e papéis, com RBAC e auditoria no servidor.
- Automatismos: capacidades declaradas por dispositivo; CRUD de regras; condições e operadores; scheduler/avaliação no Gateway; execução segura de ações; prevenção de ciclos; histórico de avaliação/execução e motivos; tratamento de fontes desatualizadas/offline.
- Meteorologia/presença/astronomia: fonte meteorológica configurada, timestamp/validade, localização e fuso horário, nascer/pôr do Sol, e fontes de presença autorizadas.
- Produção solar: leituras históricas por timestamp em kW/kWh, previsão central, fonte/atualização/confiança e API para potencial diário/restante calculado pelo Gateway.

## Sem endpoints inventados

A PWA v0.5.4 mantém os dados de demonstração em `localStorage`. Nenhum dos contratos acima é tratado como existente, e nenhum resultado local é apresentado como gravação ou execução no Gateway.
