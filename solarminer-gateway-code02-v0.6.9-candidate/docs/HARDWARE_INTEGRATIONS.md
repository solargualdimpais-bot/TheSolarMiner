# Integrações de equipamentos: suporte e diagnóstico

Este documento descreve o código presente nesta candidata. Configurar um IP, nome ou marca não significa que o dispositivo esteja suportado. Só Deye, Antminer via API BOSminer, Tuya Cloud e Tesla Fleet têm código de integração. MOES pode usar a integração Tuya Cloud quando o equipamento estiver associado ao projeto Tuya e autorizado; Shelly ainda não tem driver no Gateway.

## Deye SUN-15K-SG05LP3-EU-SM2

A PWA Owner guarda IP, porta TCP (502 por omissão) e Unit ID. O Gateway verifica TCP, tenta a identificação Modbus padrão FC43/MEI14 e, se o equipamento responder com exceção ou exceder o timeout dessa função, tenta uma única leitura FC03 no endereço base 0. O valor lido é descartado e nunca é apresentado como métrica. O fallback distingue firmware que não implementa FC43 de falha de rede/Modbus. Um timeout, Unit ID incorreto, serviço Modbus desativado, porta inacessível ou outra rede/VLAN continuam a impedir leitura.

Não está incorporado um mapa de registos confirmado para a variante e revisão de firmware exatas. Por isso não se mostram potência, energia, tensão ou comandos de controlo. O probe FC03 serve apenas para confirmar resposta Modbus e não substitui um mapa validado.

## Antminer S19K Pro com Braiins OS

A PWA configura IP privado, porta 4028 para as consultas CGMiner compatíveis, porta 80 para a API REST pública Braiins OS e credenciais locais. O Gateway confirma TCP e consulta `summary`, `stats` e `devs` na porta 4028. Para controlo usa apenas os endpoints fixos da REST API Braiins OS: alvo de potência, pause, stop e start. A REST API está documentada para Braiins OS 25.07 ou posterior; a versão anterior pode expor apenas a API gRPC e será indicada como não suportada por esta integração. O utilizador e palavra-passe são guardados apenas no Gateway com permissões de ficheiro restritas; a palavra-passe não é devolvida à PWA nem registada. Cada comando exige sessão Owner e confirmação explícita na PWA. O alvo aceite pelo equipamento tem limite de entrada de 1–2900 W e o valor devolvido pelo firmware é apresentado como aplicado. A ligação Gateway–minerador usa HTTP na LAN privada e deve permanecer numa rede local confiável.

O controlo não é executado pela API CGMiner da porta 4028. Essa interface continua apenas de leitura. A API pública Braiins OS autentica por `POST /api/v1/auth/login`, envia o token de sessão no cabeçalho `Authorization` e implementa `PUT /api/v1/performance/power-target`, `/api/v1/actions/pause`, `/api/v1/actions/stop` e `/api/v1/actions/start`. A PWA nunca liga diretamente ao minerador.

### Diagnóstico Deye e credenciais da página web

Uma ligação TCP aberta à porta 502 não prova que exista resposta Modbus. Se FC43 e a sonda FC03 terminarem em timeout, a resposta agora identifica os dois resultados e explica que o login da página web não autentica Modbus. As credenciais HTTP da interface local são um mecanismo separado; não são enviadas nem usadas pelo protocolo Modbus TCP. Para o modelo configurado, confirmar no equipamento que `Link 2 Modbus TCP` está ativo e consultar o endereço/Unit ID Modbus configurado. A versão atual não tenta adivinhar endereços de registo nem envia escritas ao inversor.

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
