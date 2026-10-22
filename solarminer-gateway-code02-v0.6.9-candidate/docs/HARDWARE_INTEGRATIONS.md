# Ligações de leitura de equipamentos

Esta versão disponibiliza configuração Owner e leituras iniciadas no Gateway para Deye, Antminer S19K Pro e Tuya Cloud. Tesla Fleet foi movida para **Energia → Carregador EV** e serve exclusivamente para ler o estado de carregamento do veículo. A API genérica de hardware não executa comandos de controlo.

## Configuração na PWA

Abre **Owner → Ligações de leitura** numa sessão Owner autenticada para Deye, Antminer e Tuya. Configura Tesla em **Energia → Carregador EV**.

- **Deye trifásico de 15 kW · Modbus TCP:** indica o IP LAN do inversor, porta Modbus e Unit ID. A ligação confirma primeiro TCP e envia a função padrão Read Device Identification (FC43/MEI 14), sem adivinhar um endereço de registo. Uma resposta de exceção também prova que o equipamento recebeu a consulta Modbus. Ainda não existe mapa de registos confirmado para a variante exata e o firmware, pelo que não são apresentados valores de potência, energia ou tensão.
- **Antminer S19K Pro com Braiins OS:** indica o IP LAN e a porta da API BOSminer (predefinição 4028). O Gateway confirma TCP e envia JSON terminado em nova linha, conforme o exemplo oficial, para `summary`, `stats` e `devs`, uma chamada por ligação. A configuração CGMiner read-only é compatível com estas consultas. Esta versão não aplica alvos de potência nem envia comandos de controlo.
- **Tuya Cloud:** escolhe a região da conta/projeto, indica o Client ID/Access ID, Client Secret/Access Secret e os IDs dos dispositivos (um por linha na PWA). A configuração suporta até 50 dispositivos. O projeto Tuya tem de estar associado à conta e ter permissões para consultar o estado. A PWA não guarda o segredo no browser nem o recebe de volta.
- Os requisitos Tesla, os campos usados e os limites de carregamento constam em [`EV_TESLA_CHARGING.md`](EV_TESLA_CHARGING.md).

Carrega **Guardar ligações** e, depois, **Ler equipamentos agora**. O resultado informa separadamente se o IP foi guardado, se a porta TCP está acessível e se a API ou o Modbus respondeu. Assim, uma resposta vazia deixa de confundir equipamento não configurado com ligação falhada. Valores Tuya e Antminer são `LIVE_UNVERIFIED` até comparação física. O painel não os apresenta como dados fisicamente corroborados. A leitura Tesla acontece no painel EV, separada das integrações genéricas.

## Endpoints

- `GET /api/v1/integrations/hardware` — Owner; devolve endereços, IDs e estado de configuração, sem segredos.
- `PUT /api/v1/integrations/hardware` — Owner; valida e guarda configuração em `hardware-integrations.json` dentro de `SOLARMINER_DATA_DIR`, com modo POSIX `0600`.
- `POST /api/v1/integrations/hardware/read` — Owner; executa leituras limitadas, devolve resultados e erros sem expor credenciais.

As credenciais Tuya e Tesla são guardadas no Gateway com permissões do utilizador de serviço, não cifradas separadamente. Restringe o acesso ao Gateway e às cópias do seu diretório de dados. Nunca coloques segredos ou tokens em tickets, logs ou capturas de ecrã. O Gateway regista apenas fornecedor, resultado, erros sem segredos e a indicação de que comandos de controlo não foram enviados.

## Limitações e validação

- O acesso Tuya depende de credenciais próprias e permissões da conta/projeto. Esta versão consulta a API Cloud e não implementa chaves locais Tuya.
- O probe de identidade Modbus Deye pode não ser suportado pelo firmware; nesse caso o painel diferencia TCP acessível de identificação Modbus rejeitada ou sem resposta. A descodificação de métricas fica desativada até obter o mapa específico, revisão de firmware e validação com leituras do equipamento.
- A ligação real da API BOSminer ao S19K Pro depende de a porta 4028 aceitar ligações do Gateway. O teste simulado não comprova acesso ao hardware; o resultado real distingue porta inacessível de API sem resposta.
- A configuração Tuya exige credenciais próprias e permissões da conta/projeto.
- Não há integração de comandos de escrita, nem aplicação de receitas ou controlos elétricos.

## Referências

- Tuya, [Autenticação Cloud](https://developer.tuya.com/en/docs/iot/authentication-method) e [assinatura de pedidos](https://developer.tuya.com/en/docs/iot/new-app-singnature).
- Tuya, [regiões e estrutura dos pedidos](https://developer.tuya.com/en/docs/iot/api-request).
- BITMAIN, [especificações oficiais do Antminer S19K Pro](https://support.bitmain.com/hc/en-us/articles/23833956049049-S19K-Pro-Specifications).
- Deye, [manuais oficiais](https://www.deyeinverter.com/download/product-manual/). O manual consultado não foi usado para inferir um mapa Modbus TCP para o Gateway.
