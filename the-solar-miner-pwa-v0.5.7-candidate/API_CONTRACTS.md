# Contratos API — PWA v0.5.4

## Hardware integrations (Gateway CODE02 0.6.24)

The Owner PWA calls `GET /api/v1/integrations/hardware`, `PUT /api/v1/integrations/hardware`, and `POST /api/v1/integrations/hardware/read` through the authenticated Gateway client. The Owner role is required. The Tuya Access Secret is sent only over the authenticated Gateway connection, held in the form until save, cleared from the field after save, and never returned by the Gateway. Device endpoints accept private IP literals only. Results remain read-only; no device control API is called.

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
