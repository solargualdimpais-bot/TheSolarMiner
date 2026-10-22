# Contratos API — PWA v0.5.4

## Gateway signed automatic updates (CODE02 0.6.27)

The Gateway checks its configured, administrator-allowlisted GitHub release daily. It automatically queues an update only after Ed25519 manifest and package verification and a successful independent recovery preflight. The privileged update helper performs SQLite backup, staging, activation, health check and rollback. The Owner PWA can still request an immediate check or manual application and reads progress from `GET /api/v1/system/update/status`.

## Hardware integrations and EV charging (Gateway CODE02 0.6.26)

The Owner PWA calls `GET /api/v1/integrations/hardware`, `PUT /api/v1/integrations/hardware`, and `POST /api/v1/integrations/hardware/read` for Deye, Antminer and Tuya. Tesla Fleet is configured and read only in Energy → EV charger with `GET/PUT /api/v1/energy/ev/tesla` and `POST /api/v1/energy/ev/tesla/read`. Owner is required. Secrets stay on the Gateway and are never returned. Tesla responses contain charge-state fields for one selected vehicle, without location, climate or driving data. No Tesla command is sent; X/Y/Z remain local settings until a Gateway energy engine and supported command flow exist.

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
