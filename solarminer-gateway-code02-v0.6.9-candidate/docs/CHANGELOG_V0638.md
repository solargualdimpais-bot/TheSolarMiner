# CODE02 v0.6.38

## Telemetria Deye a cada 30 segundos

- O Gateway consulta o Deye por FC03 a cada 30 segundos, independentemente de pedidos da PWA.
- A amostra atualizada fica em memória para leitura autenticada pela API e PWA; a PWA atualiza a informação a cada 30 segundos enquanto está aberta/visível.
- Uma amostra por minuto é persistida no registo energético SQLite, mantendo a retenção de 90 dias.
- A API declara cadência de amostragem, cadência de persistência, hora/idade e estado (`LIVE`, `STALE`, `WAITING_FOR_SAMPLE`, `UNKNOWN`) da última leitura.
- O intervalo mínimo de configuração `SOLARMINER_ENERGY_SAMPLE_SECONDS` passa a 30 segundos.
- O motor continua estritamente analítico (`READ_ONLY_ANALYTICS`, `controls_enabled: false`). Não foi ativado despacho automático: o mapa Deye está por validar, Tuya/Tesla são apenas leitura e os controlos de mineração ainda exigem comando explícito Owner.
