# Integrações de equipamentos: suporte e diagnóstico

Este documento descreve o código presente nesta candidata. Configurar um IP, nome ou marca não significa que o dispositivo esteja suportado. Só Deye, Antminer via API BOSminer, Tuya Cloud e Tesla Fleet têm código de integração. MOES pode usar a integração Tuya Cloud quando o equipamento estiver associado ao projeto Tuya e autorizado; Shelly ainda não tem driver no Gateway.

## Deye SUN-15K-SG05LP3-EU-SM2

A PWA Owner guarda IP, porta TCP (502 por omissão) e Unit ID. O Gateway verifica TCP, tenta a identificação Modbus padrão FC43/MEI14 e, se o equipamento responder com exceção ou exceder o timeout dessa função, tenta uma única leitura FC03 no endereço base 0. O valor lido é descartado e nunca é apresentado como métrica. O fallback distingue firmware que não implementa FC43 de falha de rede/Modbus. Um timeout, Unit ID incorreto, serviço Modbus desativado, porta inacessível ou outra rede/VLAN continuam a impedir leitura.

Não está incorporado um mapa de registos confirmado para a variante e revisão de firmware exatas. Por isso não se mostram potência, energia, tensão ou comandos de controlo. O probe FC03 serve apenas para confirmar resposta Modbus e não substitui um mapa validado.

## Antminer S19K Pro com Braiins OS

A PWA configura IP privado e porta 4028. O Gateway confirma TCP e consulta `summary`, `stats` e `devs` através da API CGMiner compatível do BOSminer, usando um pedido JSON terminado em nova linha. Cada comando usa uma ligação separada. A resposta comprova que uma API respondeu, mas o Gateway não verifica a identidade física do modelo; `configured_model` é o modelo indicado pelo Owner.

As leituras são apenas de monitorização. Esta integração não muda potência, perfil do tuner, pools, estado de mineração ou comandos CGMiner. A API CGMiner em modo read-only pode responder às consultas; se a API estiver desativada, protegida ou inacessível, a leitura falha. A API pública BOSminer mais recente também oferece interfaces REST/gRPC, que ainda não estão implementadas neste Gateway.

## Tuya e MOES via Tuya Cloud

O Gateway assina chamadas Cloud com Client ID/Secret, escolhe o endpoint regional configurado, obtém token e consulta `/v1.0/devices/{id}/status`. O segredo permanece no Gateway. Até 50 IDs podem ser configurados.

MOES não é um protocolo de rede uniforme. Um equipamento MOES só funciona nesta integração se a conta/projeto Tuya Cloud aplicável o expuser, as permissões de API estiverem ativas e o ID pertencer ao projeto. A marca MOES ou a utilização da app Smart Life, isoladamente, não garantem acesso. Não existe integração Tuya LAN/local nem controlo de equipamentos nesta candidata.

Os resultados e erros são isolados por ID: um dispositivo sem acesso não elimina a leitura dos outros. Falhas na autenticação Cloud afetam a consulta inteira. Erros reportam identificadores de falha e não devolvem credenciais ou tokens.

## Shelly

Não há driver Shelly, campos de configuração, endpoint, descoberta ou leitura Shelly no Gateway atual. A documentação oficial separa a API HTTP de Gen1 da API JSON-RPC de Gen2/Gen3/Gen4, e os componentes variam por modelo. Assim, o Gateway não pode declarar que qualquer Shelly foi configurado ou ligado. A integração terá de ser implementada e validada por família/modelo antes de ser ativada.

## Tesla Fleet

Tesla é configurado em Energia → Carregador EV e só lê dados de carregamento do veículo selecionado. Requer uma app Fleet autorizada, token e permissões Tesla. Não envia comandos de carregamento, nem executa as estratégias X/Y/Z. Ver [`EV_TESLA_CHARGING.md`](EV_TESLA_CHARGING.md).

## API e acesso

- `GET /api/v1/integrations/hardware` — Owner; devolve configuração não secreta.
- `PUT /api/v1/integrations/hardware` — Owner; valida e guarda Deye, Antminer e Tuya.
- `POST /api/v1/integrations/hardware/read` — Owner; consulta os dispositivos configurados e devolve estado/erro por dispositivo sempre que possível.
- `GET/PUT /api/v1/energy/ev/tesla` e `POST /api/v1/energy/ev/tesla/read` — Owner; configuração/leitura Tesla.

## Referências oficiais consultadas

- Tuya: [autenticação Cloud](https://developer.tuya.com/en/docs/iot/authentication-method), [assinatura de pedidos](https://developer.tuya.com/en/docs/iot/new-app-singnature) e [regiões e endpoints](https://developer.tuya.com/en/docs/iot/api-request).
- Shelly: [API HTTP Gen1](https://shelly-api-docs.shelly.cloud/gen1/), [RPC Gen2+](https://shelly-api-docs.shelly.cloud/gen2/General/RPCProtocol/) e [canais RPC](https://shelly-api-docs.shelly.cloud/gen2/General/RPCChannels/).
- Braiins: [API BOSminer](https://academy.braiins.com/braiins-os/papi-bosminer) e [API pública BOS](https://academy.braiins.com/braiins-os/papi-about).
- Tesla: [Fleet API e scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview).
- Deye: [manuais oficiais](https://www.deyeinverter.com/download/product-manual/). O manual não foi usado para inventar um mapa Modbus.
