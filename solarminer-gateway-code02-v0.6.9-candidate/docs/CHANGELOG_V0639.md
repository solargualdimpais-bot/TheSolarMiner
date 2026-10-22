# CODE02 v0.6.39

## Alterações

- Owner pode configurar até oito bancos de bateria e 64 cargas flexíveis pela PWA: múltiplos AQS, aquecimento radiante/toalheiro, mineradora, EV e cargas genéricas.
- O schema aceita AQS inteligente Tuya e AQS comandado por disjuntor Tuya, com referência a dispositivo e datapoint configurados.
- Comando manual Owner de interruptor Tuya com confirmação explícita, leitura de retorno e auditoria sem segredos.
- Despacho automático opcional no Gateway, em intervalo mínimo de cinco minutos, com pré-requisitos de Owner, bateria configurada, telemetria recente, comissionamento e confirmação do mapa Deye.
- Se a bateria voltar a ter margem de carga ou estiver a carregar/descarregar, o plano manda desligar as cargas flexíveis antes de voltar a atribuir excedente.
- Relé Tuya obrigatório como dependência explícita para mineradora automática; a ativação exige confirmação do relé antes do comando Braiins, e a paragem da mineradora precede a abertura do relé.
- Leituras com mais de 90 segundos, estado Tuya desconhecido ou dependências não confirmadas bloqueiam a ação.
- Resultados do último ciclo ficam visíveis na API/PWA e a auditoria regista apenas ações e estados, sem credenciais.

## Limitações e validação necessária

- O mapa Deye do logger DYDA_WiBLE 1.7.2 permanece `LIVE_UNVERIFIED`; não ativar automatização antes de confirmar no local o mapa, o sentido da potência da bateria, os CTs e os campos FV/carga.
- O SOC atribuído a vários bancos continua a usar o SOC agregado do Deye; bancos com BMS independente necessitam de mapeamento individual.
- A integração Tesla ainda só lê estado; cargas Tesla ficam bloqueadas como atuadores.
- O proprietário deve confirmar potência nominal, mínimo/máximo, prioridade, datapoints Tuya, dependência do relé e tempos de permanência para cada instalação.
