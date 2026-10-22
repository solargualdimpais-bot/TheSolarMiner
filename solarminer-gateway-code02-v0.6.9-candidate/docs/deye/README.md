# Deye SUN-15K-SG05LP3-EU-SM2 — leitura Modbus FC03

O Gateway implementa a leitura de telemetria em modo exclusivamente de leitura para o modelo configurado `SUN-15K-SG05LP3-EU-SM2`, através do logger `DYDA_WiBLE_1.7.2`, no endereço TCP/Unit ID indicados pelo Owner. A leitura usa FC03 nas janelas PDU `0`, `108–109`, `500`, `514–535`, `586–592`, `598–625`, `627–655` e `672–679`. Não usa FC43 neste logger e não envia FC05/06/15/16/22/23 nem outro comando de escrita.

## Campos recolhidos

As referências abaixo usam a notação 4xxxx; o pedido Modbus converte `40001` para o offset PDU `0`.

| Área | Campos | Referências Modbus | Escala/tipo |
|---|---|---|---|
| Estado | Código de estado | 40501 | U16 |
| Limites configurados da bateria | Corrente máxima de carga e descarga | 40109–40110 | A ×1; parâmetros de configuração lidos via FC03, sem escrita |
| MPPT 1 | Potência, tensão, corrente | 40673, 40677, 40678 | W ×1, V ×0,1, A ×0,1 |
| MPPT 2 | Potência, tensão, corrente | 40674, 40679, 40680 | W ×1, V ×0,1, A ×0,1 |
| Bateria | Energia de carga/descarga diária e acumulada | 40515–40520 | kWh ×0,1; acumulados U32 com low word antes de high word |
| Bateria | Temperatura, tensão, SOC, potência e corrente assinadas, capacidade corrigida | 40587–40593 (campos mapeados; 40590 reservado) | °C `(raw−1000)×0,1`, V ×0,01, %, S16 W ×1, S16 A ×0,01, Ah ×1 |
| Rede interna | Tensão L1–L3, potência/frequência/corrente por fase e totais aplicáveis | 40599–40613 | V ×0,1, W ×1, Hz ×0,01, S16 A ×0,01 |
| Medidor/CT externo | Corrente e potência por fase e total | 40614–40620 | S16 A ×0,01, S16 W ×1 |
| Lado da rede | Fator de potência e potência por fase/total | 40622–40626 | S16 ÷1000, S16 W ×1 |
| Saída do inversor | Tensão, corrente e potência por fase; total; frequência | 40628–40639 (campos mapeados) | V ×0,1, S16 A ×0,01, S16 W ×1, Hz ×0,01 |
| UPS/cargas | Potência UPS por fase/total, tensão das cargas e potência de carga por fase/total | 40641–40654 (campos mapeados) | W ×1, V ×0,1, S16 W ×1 |
| Energia | Importação/exportação diária e acumulada da rede, consumo diário/acumulado das cargas, energia FV diária/acumulada | 40521–40530 e 40535–40536 (40531–40534 reservados para energia diária individual dos PVs) | kWh ×0,1; acumulados U32 low word primeiro |

A potência FV total é calculada como a soma de MPPT 1 e MPPT 2. O protocolo marca energia diária individual de PV1/PV2 como reservada, por isso a integração só expõe a energia FV diária e acumulada total. Corrente e potência assinadas da bateria são preservadas e também separadas em campos de carga/descarga; a direção do sinal foi inferida da leitura observada e ainda precisa de confirmação no ecrã do inversor. Os limites 40109/40110 são os valores configurados no inversor, não o limite dinâmico que o BMS pode anunciar. O datasheet oficial indica máximo de 280 A de carga/descarga para o modelo de 15 kW, enquanto a leitura desta instalação devolveu 100 A e 200 A configurados. O Gateway não deduz importação/exportação a partir de CTs cuja configuração não esteja confirmada. Os registos 40648–40650 são omitidos porque a tabela de protocolo os identifica como não usados.

## Como estes campos foram escolhidos

A PWA mostra no resumo produção solar e SOC da bateria. As páginas Inversores/Baterias têm espaço para produção e fluxo de bateria, e a configuração solar expõe MPPTs. O endpoint de hardware Owner faz a leitura e grava a amostra no registo canónico `energy_equipment` / `energy_readings`; a atualização das páginas usa esses registos. A PWA apresenta a leitura principal do inversor como potência FV total, e da bateria como SOC. A página de detalhe lista todas as métricas, unidades e referências Modbus.

## Origem e limites do mapa

- A família oficial [SUN-14/15/16/18/20K-SG05LP3-EU-SM2](https://www.deyeinverter.com/product/three-phase-hybrid-inverter-1/sun14-15-16-18-20ksg05lp3eusm2-1420kw-three-phase-2-mppt-hybrid-inverter-lv-battery-supported.html) é trifásica, baixa tensão e tem dois MPPTs. O [datasheet oficial](https://www.deyeinverter.com/deyeinverter/2024/06/01/datasheet_sun-14-15-16-18-20k-sg05lp3-eu-sm2_240601_en.pdf) indica máximo de 280 A de carga/descarga no modelo de 15 kW.
- A Deye publica o [manual e os documentos do produto](https://www.deyeinverter.com/download/product-manual/), mas o manual de utilizador não traz o mapa Modbus completo.
- Os endereços/escalas foram cruzados com uma cópia pública do [protocolo Modbus de armazenamento trifásico Deye](https://badenergy.dk/wp-content/uploads/2025/01/Deye_3p_modbus_address_list.pdf) e com a implementação pública [Deye Modbus for Home Assistant](https://github.com/Developer089/deye-modbus-ha/blob/main/custom_components/deye_modbus/maps/sun_3ph_hybrid.yaml), que declara derivar do protocolo Deye. A tabela comunitária previamente recolhida permanece em [`SG05LP3-register-map-community.tsv`](SG05LP3-register-map-community.tsv), com SHA-256 e proveniência em [`SG05LP3_REGISTER_MAP_SOURCE.md`](SG05LP3_REGISTER_MAP_SOURCE.md).
- Estas fontes não certificam a revisão exata do firmware do inversor nem o mapeamento do logger `DYDA_WiBLE_1.7.2`.
- Todos os dados ficam com confiança `LIVE_UNVERIFIED`. Não devem comandar automações ou decisões de proteção.

## Ensaio físico registado

Foram feitas leituras FC03 read-only ao endereço `192.168.8.10:502`, Unit ID 1, a partir do computador de desenvolvimento na mesma LAN. As oito janelas responderam, incluindo os novos blocos PDU 108–109 e 514–535. Na leitura mais recente, PV1 foi 403,6 V / 3,7 A / 1479 W e PV2 221,1 V / 0,8 A / 162 W; a soma dos canais deu 1641 W. A bateria devolveu 53,42 V, SOC 100%, temperatura 25,0 °C, corrente +1,78 A e potência +73 W, interpretadas pelo código como descarga. Os contadores devolvidos foram: PV diário/acumulado 37,8/1889,0 kWh; bateria, carga diária/acumulada 7,4/716,7 kWh e descarga diária/acumulada 4,9/647,5 kWh; consumo diário/acumulado 33,7/1613,1 kWh; limites configurados de carga/descarga 100/200 A. Nesta leitura, a potência de cada MPPT ficou próxima de tensão × corrente. Estes são valores observados no logger e convertidos pela tabela; não foram comparados simultaneamente com o visor.

Na mesma leitura, tensão/frequência da rede vieram a zero. O registo de tipo de dispositivo devolveu raw `5`, enquanto o protocolo publica `0x0500` para trifásico; essa diferença permanece uma incompatibilidade a resolver. Por isso os campos de rede e a identidade Modbus não são confirmados só pelo facto de os outros registos responderem.

O ensaio foi feito do computador de desenvolvimento, não a partir do Gateway instalado. Os valores não foram comparados em simultâneo com o ecrã do inversor nem com instrumentos elétricos independentes. É uma confirmação de resposta e coerência pontual, não certificação de exatidão.
