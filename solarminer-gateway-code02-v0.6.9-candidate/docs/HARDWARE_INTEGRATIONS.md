# Ligações de leitura de equipamentos

Esta versão disponibiliza configuração Owner e leituras iniciadas no Gateway para o Deye, Antminer S19K Pro, Tuya Cloud e Tesla Fleet API. Todos os alvos LAN são IPs privados literais. A API não executa comandos de controlo.

## Configuração na PWA

Abre **Gateway · detalhes → Ligações de leitura** numa sessão Owner autenticada.

- **Deye trifásico de 15 kW · Modbus TCP:** indica o IP LAN do inversor, porta Modbus e Unit ID. A leitura usa apenas FC03. A árvore do repositório não contém um mapa de registos confirmado para a variante exata e o firmware do aparelho. A resposta permanece como registos brutos; não deve ser interpretada como potência, energia ou tensão.
- **Antminer S19K Pro:** indica o IP LAN e a porta da API de monitorização (predefinição 4028). O Gateway emite somente `summary`, `stats` e `devs`, uma chamada por ligação. O firmware do minerador/rede tem de aceitar o IP do Gateway. Não se configuram pools, ventoinhas, reinícios ou outras funções.
- **Tuya Cloud:** escolhe a região da conta/projeto, indica o Client ID/Access ID, Client Secret/Access Secret e os IDs dos dispositivos (um por linha na PWA). A configuração suporta até 50 dispositivos. O projeto Tuya tem de estar associado à conta e ter permissões para consultar o estado. A PWA não guarda o segredo no browser nem o recebe de volta.
- **Tesla Fleet API (veículos):** indica a região, Client ID de uma aplicação registada na Tesla, o refresh token obtido após autorização do titular e os IDs numéricos ou VINs selecionados (um por linha). A aplicação tem de conceder `openid`, `offline_access` e `vehicle_device_data`. O Gateway renova e guarda o refresh token rotativo. Só consulta os veículos selecionados e remove dados de localização/estado de condução da resposta. Não acorda veículos nem envia comandos. Esta integração não abrange Tesla Energy/Powerwall nem Fleet Telemetry. A primeira autorização OAuth e a obtenção inicial do refresh token têm de ser feitas através do fluxo de autorização registado na Tesla; esta versão não implementa o callback OAuth dentro da PWA.

Carrega **Guardar ligações** e, depois, **Ler equipamentos agora**. A resposta aparece no painel de estado de hardware. Valores Tuya e Antminer são `LIVE_UNVERIFIED` até comparação física. O painel não os apresenta como dados fisicamente corroborados.

## Endpoints

- `GET /api/v1/integrations/hardware` — Owner; devolve endereços, IDs e estado de configuração, sem segredos.
- `PUT /api/v1/integrations/hardware` — Owner; valida e guarda configuração em `hardware-integrations.json` dentro de `SOLARMINER_DATA_DIR`, com modo POSIX `0600`.
- `POST /api/v1/integrations/hardware/read` — Owner; executa leituras limitadas, devolve resultados e erros sem expor credenciais.

As credenciais Tuya e Tesla são guardadas no Gateway com permissões do utilizador de serviço, não cifradas separadamente. Restringe o acesso ao Gateway e às cópias do seu diretório de dados. Nunca coloques segredos ou tokens em tickets, logs ou capturas de ecrã. O Gateway regista apenas fornecedor, resultado, erros sem segredos e a indicação de que comandos de controlo não foram enviados.

## Limitações e validação

- O acesso Tuya depende de credenciais próprias e permissões da conta/projeto. Esta versão consulta a API Cloud e não implementa chaves locais Tuya.
- O transporte Deye é implementado, mas a descodificação de métricas fica desativada até obter o mapa de registos específico, a revisão de firmware e validação com leituras do equipamento.
- A compatibilidade da API CGMiner com o firmware concreto do S19K Pro tem de ser confirmada na rede local. A leitura simulada não comprova acesso ao hardware.
- A integração Tesla exige uma app Fleet válida, consentimento do titular e refresh token ativo. Os refresh tokens são de utilização rotativa; o Gateway persiste cada token novo antes de terminar a leitura. A ligação real não foi testada sem credenciais de uma conta Tesla. A primeira troca OAuth continua a ser um passo externo.
- Não há integração de comandos de escrita, nem aplicação de receitas ou controlos elétricos.

## Referências

- Tuya, [Autenticação Cloud](https://developer.tuya.com/en/docs/iot/authentication-method) e [assinatura de pedidos](https://developer.tuya.com/en/docs/iot/new-app-singnature).
- Tuya, [regiões e estrutura dos pedidos](https://developer.tuya.com/en/docs/iot/api-request).
- Tesla, [OAuth e refresh tokens](https://developer.tesla.com/docs/fleet-api/authentication/third-party-tokens), [perfis e dados do veículo](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints) e [regiões da Fleet API](https://developer.tesla.com/docs/fleet-api/getting-started/regions-countries).
- BITMAIN, [especificações oficiais do Antminer S19K Pro](https://support.bitmain.com/hc/en-us/articles/23833956049049-S19K-Pro-Specifications).
- Deye, [manuais oficiais](https://www.deyeinverter.com/download/product-manual/). O manual consultado não foi usado para inferir um mapa Modbus TCP para o Gateway.
