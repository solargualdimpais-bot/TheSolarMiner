# Engine energético — CODE02 0.6.39

## Recolha e cálculos

Com o Deye configurado, o Gateway recolhe telemetria FC03 a cada 30 segundos, mantém a leitura mais recente em memória e grava uma amostra por minuto no SQLite, com retenção de 90 dias. A PWA consulta os valores enquanto está visível. O SOC observado, capacidade configurada por banco, energia acima do mínimo e espaço de carga até ao máximo são apresentados no Engine. A tendência de FV é apenas indicativa e não usa meteorologia.

## Cargas flexíveis

O Owner pode configurar até 8 bancos de bateria e 64 cargas através do Engine PWA. Os tipos de carga incluem mineradora, AQS (smart ou controlada por disjuntor Tuya), carregador EV, soalho radiante/toalheiro e carga genérica. Cada carga define potência nominal, mínimo/máximo, prioridade, estado habilitado e elegibilidade para despacho automático. A configuração é validada e guardada no Gateway.

Uma carga Tuya necessita de um dispositivo previamente registado nas integrações e de um código de função de interruptor, por exemplo `switch_1`. O Owner pode enviar comandos manuais de ligar/desligar com confirmação explícita. O Gateway exige sessão Owner, valida que o dispositivo está configurado, comunica apenas com a API HTTPS oficial da Tuya e tenta confirmar o estado depois do comando. Um HTTP aceite sem confirmação de estado é apresentado como não confirmado.

## Planeamento e despacho

O despacho automático executa a cada intervalo configurado (mínimo de 5 minutos) quando o Owner o ativa e confirma o comissionamento. Dá prioridade à bateria; desliga cargas flexíveis se ainda houver espaço para carregar ou se a bateria estiver a carregar/descarregar. Só considera cargas flexíveis com a capacidade configurada, SOC no limite e potência de bateria estabilizada. Depois distribui o excedente pela ordem de prioridade, respeitando potências nominais e limites da mineradora. A Tesla continua bloqueada como atuador, porque a integração Tesla existente só lê estado. A Tuya é lida antes de cada ciclo; estado desconhecido bloqueia o comando correspondente. Os tempos mínimos ligado/desligado limitam mudanças repetidas.

A elegibilidade é bloqueada quando o Owner não ativou e comissionou a automatização, o mapa físico Deye não foi confirmado, a amostra tem mais de 90 segundos ou faltam SOC, PV, carga, potência da bateria ou capacidade configurada. A confirmação de mapa e sentido dos CTs é uma responsabilidade de comissionamento no local; o código não consegue provar remotamente que a instalação física está correta. Nesta candidata, as leituras continuam marcadas `LIVE_UNVERIFIED` até validação real.

O endpoint de resumo disponibiliza o plano, o último resultado e os motivos de bloqueio. A mineradora só pode ser automática quando configurada com um `requires_load_id` que aponta para um relé Tuya incluído na mesma lista e com prioridade anterior; se o relé não ficar ligado e confirmado, o comando Braiins é bloqueado. Comandos automáticos dependem de confirmação física da topologia, do sinal da potência da bateria e dos datapoints de cada interruptor. Os comandos Tuya manuais exigem Owner e confirmação a cada ação. Não marques o mapa como verificado para contornar falhas de leitura.

## Configuração de cargas no Engine

O editor Owner guarda `battery_banks`, `loads` e `automation` em `/api/v1/energy/engine/config`. Cada carga pode incluir `id`, `name`, `kind`, `control_type`, `rated_power_w`, `minimum_power_w`, `maximum_power_w`, `priority`, `enabled`, `automatic`, `tuya_device_id`, `tuya_switch_code`, `requires_load_id`, `minimum_on_seconds` e `minimum_off_seconds`. Identificadores são únicos e limitados a caracteres seguros. O servidor rejeita potências e referências Tuya inválidas.

## Limitações físicas

- O mapa usado para o logger DYDA_WiBLE 1.7.2 continua candidato; cada endereço, escala e sinal deve ser confirmado com registos físicos antes de automatizar.
- O SOC agregado do Deye é aplicado a cada banco configurado como estimativa. Não substitui SOC separado quando os bancos têm BMS independentes.
- A potência nominal de uma carga é uma estimativa para planeamento, não um medidor de consumo real.
- Tuya Cloud depende de credenciais, região, permissões do projeto e códigos de datapoint válidos. Os segredos permanecem no Gateway.
- A Tuya e a Braiins possuem comandos explícitos Owner; Tesla permanece leitura apenas. Nenhuma previsão indicativa pode por si só acionar uma carga.
