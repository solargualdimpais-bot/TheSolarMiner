# Contratos API — PWA v0.5.7 / Gateway CODE02 v0.6.39

## Cargas configuráveis (Gateway 0.6.39)

O Owner guarda até 8 `battery_banks` e 64 `loads` por `PUT /api/v1/energy/engine/config`. `kind` aceita `miner`, `water_heater`, `underfloor_heating`, `ev_charger` ou `generic`; `control_type` aceita `tuya_smart`, `tuya_breaker`, `antminer_braiins`, `tesla_fleet` ou `manual`. Os registos suportam vários AQS e cargas de aquecimento sem alteração do código. A amostra com mais de 90 segundos bloqueia o despacho automático. O ciclo corre na cadência guardada no Gateway quando o Owner ativa a opção, com validação física do mapa obrigatória.

O Owner pode testar um interruptor registado através de `POST /api/v1/integrations/tuya/switch` com `{ "device_id": "...", "on": true }`. A PWA pede confirmação, o Gateway verifica Owner e dispositivo previamente configurado, e o resultado declara se o estado foi confirmado. Segredos Tuya não são devolvidos.

## Engine energético (Gateway 0.6.38)

Após autenticação, a PWA consulta `GET /api/v1/energy/engine?history_hours=24`. Apresenta histórico de FV, cargas, bateria e SOC, contadores Deye e projeção indicativa de FV. O Owner pode guardar no Gateway capacidade instalada e SOC mínimo/máximo através de `PUT /api/v1/energy/engine/config`. A energia em kWh fica indisponível até a capacidade ser configurada. A projeção não usa meteorologia nem controla equipamentos; os dados permanecem `LIVE_UNVERIFIED`.

## Braiins OS Owner control (Gateway 0.6.36)

The PWA configures local Braiins OS REST credentials through the authenticated Owner Gateway API. Secrets are held by the Gateway and never returned. The PWA calls `POST /api/v1/integrations/antminer/control` only after an explicit Owner confirmation. Supported actions are `set_power_target` (1–2900 W), `pause`, `stop`, and `start`; Gateway audit records contain action/result only, never credentials or session tokens. Braiins OS REST support requires firmware 25.07 or later. CGMiner-compatible port 4028 remains read-only.

## Gateway hardware connectivity and telemetry (CODE02 0.6.36)

`POST /api/v1/integrations/hardware/read` returns a `configuration` object and per-device `connection_state`. For the configured Deye `SUN-15K-SG05LP3-EU-SM2`, the Gateway reads the candidate telemetry map with FC03 only and skips FC43. The response includes PV1/PV2 voltage, current and power; battery SOC, voltage, signed current/power and charge/discharge splits, temperature and corrected capacity; daily/cumulative PV, battery, grid and load energy; configured battery charge/discharge current limits; grid/CT, inverter AC and load channels; and map-quality checks. A successful snapshot is saved in the canonical energy registry and becomes visible on the Home, Inversores and Baterias pages. Every Deye reading is `LIVE_UNVERIFIED`. The map is based on the three-phase Deye protocol and a public SG04/SG05 implementation, but exact logger/firmware applicability remains unconfirmed. The response reports raw type-code mismatch, zero grid channels, or MPPT power/current inconsistencies rather than hiding them. Battery current limits are read-only values from R/W registers and are not the live BMS limits. Antminer reports its configured model as unverified. Tuya Cloud status is isolated by device ID; one failing ID does not discard successful reads for others. MOES is supported only when exposed through the configured Tuya Cloud project. Shelly has no Gateway driver. This endpoint sends no Modbus control command.

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
