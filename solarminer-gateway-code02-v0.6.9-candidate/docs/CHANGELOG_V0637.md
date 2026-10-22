# CODE02 v0.6.37

## Engine energético ligado às leituras persistidas

- O Gateway recolhia a telemetria Deye FC03 configurada automaticamente a cada cinco minutos, sem depender de pedidos da PWA. Falhas isoladas eram registadas sem parar o serviço.
- As leituras mapeadas continuam no registo canónico e têm retenção de 90 dias para a fonte Deye.
- `GET /api/v1/energy/engine?history_hours=24` fornece leituras recentes, séries temporais PV/cargas/bateria/SOC, contadores energéticos e projeção solar histórica de baixa confiança.
- Owner configura no Gateway a capacidade total de bateria e os SOC mínimo/máximo. O engine calcula kWh disponíveis acima do mínimo, espaço de carga até ao máximo e indica quando o máximo configurado foi atingido.
- A PWA Owner mostra SOC real, produção/consumo, gráfico histórico e contadores de energia Deye.
- A projeção é uma regressão linear simples sobre até três horas de PV medido, sem meteorologia. Nenhum comando de controlo é enviado. Todas as leituras continuam `LIVE_UNVERIFIED`.
