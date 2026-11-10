# Gateway 0.6.228

- Reutiliza a especificação cloud uma vez por Product ID durante a sincronização Tuya.
- Preserva definições `values` recebidas como objetos JSON, incluindo unidades, limites, escalas e enumerações.
- Acrescenta automaticamente ao perfil do PID os IDs DPS novos observados em leituras LAN normais ou manuais.
- Mantém associações existentes e não inventa códigos, unidades, escalas ou valores DPS a partir da ordem da lista.
- Mantém os valores atuais na leitura de cada equipamento; o perfil partilhado do PID guarda apenas definições e metadados de descoberta.
