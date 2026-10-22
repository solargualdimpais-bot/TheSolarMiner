# Tesla Fleet na área Carregador EV

## Utilização prevista

A PWA já reserva a área **Energia → Carregador EV** para carregar um Tesla com base em excedente solar, preservar o objetivo de carga da casa ao pôr do sol e priorizar pedidos urgentes. Os parâmetros X/Y/Z existentes são guardados localmente no browser. O Gateway desta versão ainda não tem o motor energético que calcula essas decisões, nem um atuador Tesla que execute os comandos. Portanto, esta integração acrescenta a ligação e a leitura do estado de carga do Tesla para informar essa área; não ativa carregamento automático.

## Configuração e leitura

Na PWA, inicia sessão como Owner e abre **Energia → Carregador EV → Ligação Tesla Fleet para carregamento**. Indica a região Tesla, Client ID da aplicação Fleet, refresh token obtido no fluxo OAuth autorizado pela Tesla e o ID do veículo ou VIN. A aplicação Tesla necessita dos âmbitos `openid`, `offline_access` e `vehicle_device_data`. O Gateway guarda e roda o refresh token; a PWA limpa o campo após guardar e nunca recebe o segredo de volta.

O botão **Consultar carregamento** solicita uma leitura sob ação do Owner. A resposta pode incluir nome, últimos quatro caracteres do VIN, nível da bateria, estado de carregamento, ligação ao carregador, limite de carga, potência, taxa de carga e tempo estimado até cheio. Os dados são marcados `LIVE_UNVERIFIED`. Não se consulta localização, estado de condução, odómetro, climatização ou Tesla Energy/Powerwall. A leitura do veículo pode acordá-lo e a API Tesla pode cobrar chamadas; consulta apenas quando necessário.

## Contrato

- `GET /api/v1/energy/ev/tesla` — consulta configuração pública, Owner; não devolve refresh token.
- `PUT /api/v1/energy/ev/tesla` — valida e grava região, Client ID, refresh token e um veículo selecionado, Owner.
- `POST /api/v1/energy/ev/tesla/read` — renova o token e lê dados de carga do veículo selecionado, Owner.
- O endpoint genérico `/api/v1/integrations/hardware/read` não consulta Tesla.
- Não existem comandos de start/stop, alteração de amperagem/limite, scheduler de carga ou aplicação das estratégias X/Y/Z.

## Próxima etapa para automatização

Para executar as estratégias será necessário implementar no Gateway um motor energético que receba leituras verificadas do inversor, bateria e Tesla, calcule excedente e restrições domésticas e registe motivos/decisões. O envio de comandos Tesla é uma capacidade separada: a aplicação Fleet requer o âmbito `vehicle_charging_cmds`, chave virtual do veículo e protocolo de comando suportado. Deve passar por autorização explícita do Owner, limites de segurança, auditoria e confirmação de resultado. Esta versão deliberadamente não pede esse âmbito nem envia comandos.

## Limites

A primeira autorização OAuth e obtenção do refresh token permanecem no processo externo definido pela Tesla; a PWA ainda não fornece callback OAuth. A integração real não pode ser confirmada sem uma aplicação Tesla autorizada e uma conta/veículo de teste. Confirma os requisitos, regiões e custos diretamente na [documentação Fleet API da Tesla](https://developer.tesla.com/docs/fleet-api).
