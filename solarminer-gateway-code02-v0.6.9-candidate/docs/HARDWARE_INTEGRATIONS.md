# Integrações de equipamentos: suporte e diagnóstico

Este documento descreve o código presente nesta candidata. Configurar um IP, nome ou marca não significa que o dispositivo esteja suportado. Há drivers para Deye e Antminer na LAN, Tuya Wi-Fi local em modelos compatíveis, e Tesla Fleet pela Cloud. O inventário Tuya continua a usar a Cloud para descobrir dispositivos, chaves locais e esquemas; leituras e comandos Tuya operacionais usam apenas a LAN, sem fallback para a Cloud. Shelly ainda não tem driver no Gateway.

## Deye SUN-15K-SG05LP3-EU-SM2

A PWA Owner guarda IP, porta TCP (502 por omissão) e Unit ID. Para esta referência configurada, o Gateway usa apenas FC03 e lê oito janelas: estado, limites configurados de corrente, contadores de energia, bateria, rede/CT, saída AC/cargas e os dois MPPTs. A leitura de hardware é exclusiva do Owner; uma resposta bem-sucedida grava as métricas no registo de energia existente, de onde a Home e as áreas Inversores/Baterias as consultam. A PWA mostra as leituras com o nome, unidade, registo e classe `LIVE_UNVERIFIED`.

O mapa descreve tensão, corrente e potência FV por MPPT; tensão, corrente e potência assinadas, SOC, temperatura, capacidade e energias diárias/acumuladas da bateria; limite de corrente de carga/descarga configurado; energia FV diária/acumulada; importação/exportação da rede; consumo diário/acumulado; tensão/frequência/corrente/potência das fases da rede; saída do inversor; saída UPS; tensão e potência de carga. Os limites de corrente 40109/40110 são campos R/W no protocolo mas são consultados apenas por FC03, sem escrita; são valores configurados, não limites dinâmicos anunciados pelo BMS. Os valores da rede interna, CT externo e lado da rede ficam separados porque dependem da configuração do medidor. Os registos de corrente da carga que o protocolo marca como sem uso são omitidos. As energias de PV1/PV2 separadas estão marcadas como reservadas e não são interpretadas. A potência FV total é a soma das duas potências de MPPT.

O protocolo trifásico Deye e a implementação pública SG04/SG05 LP3 consultada fornecem endereços e escalas; o datasheet oficial confirma que a família SG05LP3-EU-SM2 de 14–20 kW tem dois MPPTs. A tabela continua sem validação oficial de compatibilidade com a revisão de firmware e com o logger `DYDA_WiBLE_1.7.2`. As oito janelas FC03 responderam na leitura física feita a partir do computador na mesma LAN. Os contadores devolvidos foram PV diário/acumulado 37,5/1888,7 kWh, bateria carga diária/acumulada 7,4/716,7 kWh, descarga diária/acumulada 4,9/647,5 kWh, consumo diário/acumulado 33,4/1612,8 kWh e limites configurados 100/200 A. As energias vieram do logger e ainda não foram comparadas com o visor. Na amostra instantânea anterior, os registos de tensão/frequência da rede vieram a zero, o tipo de dispositivo devolveu `5` face ao `0x0500` publicado, e PV2 apresentou diferença entre potência e tensão×corrente. Estes campos permanecem não confirmados; a página Owner mostra o mapa candidato e não usa esses valores para automações.

## Antminer S19K Pro com Braiins OS

A PWA configura o IP privado, a porta 4028 para telemetria CGMiner compatível, a porta da API REST Braiins OS e as credenciais locais. São dois canais distintos: a porta 4028 é apenas leitura; o controlo efetivo usa endpoints fixos da API REST Braiins OS para alvo de potência, pausar, parar e iniciar. O Gateway consulta `summary`, `stats` e `devs` na porta 4028 e tenta também o comando opcional `tunerstatus`. `summary` pode fornecer hashrate atual/médio (`GHS 5s`/`GHS av`, convertido para TH/s na Home); `tunerstatus` pode fornecer potência aproximada (`ApproximateMinerPowerConsumption`) e limite/alvo (`PowerLimit`) em watts. A disponibilidade destes campos depende da versão e resposta da API; a PWA distingue “ligação de leitura ativa”, hashrate zero e hashrate não reportado, sem inferir mineração ativa a partir da conectividade. As leituras são guardadas como `LIVE_UNVERIFIED`. A API REST é documentada para Braiins OS 25.07 ou posterior; a documentação indica que versões anteriores podem expor apenas gRPC e não são suportadas por esta integração REST. O utilizador e palavra-passe ficam no Gateway com permissões de ficheiro restritas, e a palavra-passe não é devolvida à PWA nem registada. Cada comando exige sessão Owner e confirmação explícita na PWA. O alvo de potência é limitado a 1–2900 W e o valor devolvido pelo firmware é apresentado como aplicado. A ligação Gateway–minerador usa HTTP na LAN privada e deve permanecer numa rede local confiável.

O controlo não é executado pela API CGMiner da porta 4028. Essa interface continua apenas de leitura. A API pública Braiins OS autentica por `POST /api/v1/auth/login`, envia o token de sessão no cabeçalho `Authorization` e implementa `PUT /api/v1/performance/power-target`, `/api/v1/actions/pause`, `/api/v1/actions/stop` e `/api/v1/actions/start`. A PWA nunca liga diretamente ao minerador.

### Diagnóstico Deye e credenciais da página web

Uma ligação TCP aberta à porta 502 não prova que os registos estejam mapeados como esperado. O Gateway ignora FC43 no logger DYDA porque a sequência FC43→FC03 expirava; as leituras FC03 diretas responderam. As credenciais HTTP da interface local são separadas e não são enviadas ao Modbus. As métricas incluem leituras brutas e conversões baseadas no mapa, com `LIVE_UNVERIFIED` até confirmação da variante/firmware e dos canais de medição do logger. Não são enviados comandos ao inversor.

## Tuya e MOES

O Owner configura no Gateway a região, Client ID/Secret e UID da conta associada ao projeto Tuya. `POST /api/v1/integrations/tuya/sync` importa por páginas até 200 dispositivos do projeto, incluindo offline, e tenta consultar para cada um os detalhes, a chave LAN, o estado atual e o esquema de funções/estados. O Gateway conserva a `local_key` apenas no ficheiro privado, com permissões restritas; a API/PWA só recebe `local_key_available`, nunca o valor. A sincronização preserva favoritos, divisões, códigos de controlo e registos anteriores mesmo que um aparelho deixe de aparecer na lista Cloud. Falhas de detalhe/esquema são contabilizadas sem apagar a lista importada.

O esquema importado descreve o que a Cloud declara para aquele modelo, por exemplo códigos, tipos e escalas; não significa que cada função já esteja ligada a um controlo na PWA. O Owner configura o IP privado, versão de protocolo e, se a numeração automática não corresponder ao aparelho, o mapa código→DPS. A `local_key` só é importada durante a sincronização e permanece no ficheiro privado do Gateway. A configuração e os nomes de canais são locais ao Gateway.

A operação local depende de o equipamento ser um dispositivo Tuya Wi-Fi compatível, estar acessível na sub-rede do Gateway, aceitar a versão de protocolo configurada e ter `local_key`, IP e mapa DPS corretos. O driver usa TinyTuya 1.20.0, com chamadas LAN diretas para estado e comandos. Não há fallback Cloud se a ligação local falhar: a PWA apresenta o dispositivo indisponível e o controlo automático bloqueia quando o estado LAN não foi confirmado. O esquema Tuya e a obtenção inicial/renovação de chaves continuam a depender da sincronização explícita com a Cloud. O suporte não cobre automaticamente todos os produtos Tuya, outros fabricantes, dispositivos Zigbee/BLE ligados atrás de hubs ou ações proprietárias como cenas e configuração avançada de relé.

MOES não é um protocolo de rede uniforme. Um equipamento MOES só funciona localmente se for um modelo Tuya Wi-Fi compatível e a sincronização tiver fornecido a chave local e o esquema. Marca ou app Smart Life, por si só, não garantem que o protocolo LAN seja compatível. Os comandos de interruptor e nível configurados vão diretamente pela LAN; a confirmação é obtida por nova leitura local. O estado continua `LIVE_UNVERIFIED` até ser verificado no equipamento físico.

O Gateway consulta a cada 60 segundos, mesmo sem a PWA aberta, os dispositivos com chave local e IP configurados e regista no SQLite as transições observadas de cada canal booleano, as passagens disponível/indisponível na LAN, os comandos manuais confirmados ou sem confirmação e as ações automáticas de Tuya. O Owner consulta até 500 eventos por `GET /api/v1/integrations/tuya/{device_id}/events`. A primeira leitura estabelece o estado inicial; a hora de uma transição offline/ON/OFF fica limitada pelo intervalo de leitura e pelo tempo de resposta do dispositivo. Os eventos começam quando esta versão está instalada e faz leituras locais; não se importam eventos históricos da Tuya. Não há atualmente uma regra de alarme configurável por limite de watts associada ao log.

Os resultados e erros são isolados por ID: um dispositivo sem acesso não elimina a leitura dos outros. Falhas na autenticação Cloud afetam a consulta inteira. Erros reportam identificadores de falha e não devolvem credenciais ou tokens.

## Shelly

Não há driver Shelly, campos de configuração, endpoint, descoberta ou leitura Shelly no Gateway atual. A documentação oficial separa a API HTTP de Gen1 da API JSON-RPC de Gen2/Gen3/Gen4, e os componentes variam por modelo. Assim, o Gateway não pode declarar que qualquer Shelly foi configurado ou ligado. A integração terá de ser implementada e validada por família/modelo antes de ser ativada.

## Tesla Fleet

Tesla é configurado em Energia → Carregador EV e só lê dados de carregamento do veículo selecionado. Requer uma app Fleet autorizada, token e permissões Tesla. Não envia comandos de carregamento, nem executa as estratégias X/Y/Z. Ver [`EV_TESLA_CHARGING.md`](EV_TESLA_CHARGING.md).

## API e acesso

- `GET /api/v1/integrations/hardware` — Owner; devolve configuração não secreta.
- `PUT /api/v1/integrations/hardware` — Owner; valida e guarda Deye, Antminer e Tuya.
- `POST /api/v1/integrations/tuya/sync` — Owner; sincroniza até 200 dispositivos e respetivos esquemas/estados. As chaves locais ficam apenas no Gateway.
- `POST /api/v1/integrations/hardware/read` — Owner; consulta os dispositivos configurados e devolve estado/erro por dispositivo sempre que possível.
- `POST /api/v1/integrations/hardware/{deye|antminer|tuya}/read` — Owner; consulta só o fornecedor selecionado. Tuya aceita `{"device_id":"..."}` para consultar apenas um dispositivo.
- `POST /api/v1/integrations/tuya/switch` — Owner; envia um comando explícito de interruptor para dispositivo configurado com código de função e devolve a confirmação de estado.
- `GET /api/v1/integrations/tuya/{device_id}/events?limit=100` — Owner; consulta o histórico local de estado, disponibilidade, comandos e ações automáticas do dispositivo.
- `GET/PUT /api/v1/energy/ev/tesla` e `POST /api/v1/energy/ev/tesla/read` — Owner; configuração/leitura Tesla.

## Referências oficiais consultadas

- Tuya: [autenticação Cloud](https://developer.tuya.com/en/docs/iot/authentication-method), [assinatura de pedidos](https://developer.tuya.com/en/docs/iot/new-app-singnature) e [regiões e endpoints](https://developer.tuya.com/en/docs/iot/api-request).
- Shelly: [API HTTP Gen1](https://shelly-api-docs.shelly.cloud/gen1/), [RPC Gen2+](https://shelly-api-docs.shelly.cloud/gen2/General/RPCProtocol/) e [canais RPC](https://shelly-api-docs.shelly.cloud/gen2/General/RPCChannels/).
- Braiins: [API BOSminer](https://academy.braiins.com/braiins-os/papi-bosminer) e [API pública BOS](https://academy.braiins.com/braiins-os/papi-about).
- Tesla: [Fleet API e scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview).
- Deye: [manuais oficiais](https://www.deyeinverter.com/download/product-manual/). O manual não foi usado para inventar um mapa Modbus.
