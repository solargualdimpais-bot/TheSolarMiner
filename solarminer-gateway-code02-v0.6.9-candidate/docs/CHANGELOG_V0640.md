# CODE02 v0.6.40

## Alterações

- A PWA Live apresenta o estado real do Gateway por área e não usa os renderizadores de demonstração nas páginas autenticadas; áreas sem integração mostram um estado vazio explicado.
- A Home inclui configuração da casa (nome, cidade e fotografia), tempo vindo do Gateway, produção FV e histórico observado/potencial de três horas anteriores e seis horas de previsão, quando há configuração e dados disponíveis.
- O motor do Gateway persiste amostras energéticas, inclui tensão/corrente/potência por MPPT e aprende uma estimativa de produção potencial e eventos candidatos a curtailment a partir do tempo, histórico, SOC e carga. Os candidatos são estimativas, não uma medição de corte confirmada.
- Favoritos Tuya na Home permitem controlar interruptores ou um nível configurado (dimmer/estores) através de ações Owner autenticadas; a percentagem só é suportada quando o dispositivo tem datapoint e escala configurados no Gateway.
- O Gateway continua a ser a fonte dos dados e credenciais. A fotografia/favoritos e metadados de divisão/piso permanecem locais ao browser nesta versão.

## Limites operacionais

A compatibilidade exata do mapa Deye com o logger e firmware local requer validação física. A previsão depende da cidade, potência FV configurada e disponibilidade do fornecedor meteorológico; sem esses dados a PWA apresenta indisponibilidade em vez de valores inventados. O despacho automático permanece condicionado a comissionamento físico e à telemetria fresca.
