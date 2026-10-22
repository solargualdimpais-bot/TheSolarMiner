# Contratos PWA / Gateway CODE02 0.6.39

## Engine energético

- `GET /api/v1/energy/engine?history_hours=24` requer sessão autenticada com permissão `read`; aceita 1–168 horas. Retorna leituras Deye, séries históricas, projeções, plano de cargas e último ciclo automático. Inclui `sampling_interval_seconds` (30 s), `persistence_interval_seconds` (60 s), `live_sample_at`, `live_sample_age_seconds` e `live_sample_state` (`LIVE`, `STALE`, `WAITING_FOR_SAMPLE` ou `UNKNOWN`). Leituras acima de 90 s bloqueiam o controlo.
- `PUT /api/v1/energy/engine/config` é Owner-only. Recebe a capacidade agregada e SOC mínimo/máximo, até 8 `battery_banks`, até 64 `loads` e `automation`. Cada banco exige id, nome, capacidade e limites SOC. Cada carga define tipo, controlo, potência, prioridade, habilitação, elegibilidade automática e tempos mínimos ligado/desligado. A mineradora automática precisa de `requires_load_id` que aponte para um relé Tuya configurado, ativo, elegível e de prioridade anterior.
- O Gateway lê Deye por FC03 a cada 30 segundos, independentemente dos pedidos da PWA. O último sample atualiza os cartões imediatamente; uma amostra por minuto é guardada em `energy_readings`; amostras Deye com mais de 90 dias são eliminadas.
- O engine calcula energia acima do SOC mínimo, espaço de carga até ao máximo configurado e potências aproximadas a partir de tensão e limites de corrente configurados. Estes limites não são os limites dinâmicos do BMS.
- As previsões usam regressão linear do histórico recente, com pelo menos três amostras em dez minutos. Não usam meteorologia nem calculam o máximo diário solar.
- O despacho é desligado por padrão e requer Owner a ativar e confirmar comissionamento e mapa Deye. A cada ciclo lê primeiro o estado Tuya; falhas e estado desconhecido bloqueiam as ações dependentes. Uma dependência de relé não confirmada impede o arranque do minerador; na redução de excedente, a ordem de paragem precede abrir o relé.
- As leituras do mapa Deye permanecem `LIVE_UNVERIFIED` até validação física do modelo/logger/firmware, do sentido da potência e dos CTs. A caixa Owner de confirmação não prova esses dados.

## Integrações existentes

A configuração de Deye, Antminer e Tuya, as leituras manuais e os comandos suportados da Antminer continuam nos endpoints documentados em `API.md` e `HARDWARE_INTEGRATIONS.md`. `POST /api/v1/integrations/tuya/switch` é Owner-only e comanda um interruptor previamente configurado com datapoint explícito. Tesla Fleet permanece uma integração de leitura do estado de carregamento; não comanda o veículo.
