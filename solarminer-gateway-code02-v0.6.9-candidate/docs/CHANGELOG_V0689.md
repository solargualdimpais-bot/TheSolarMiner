# Gateway 0.6.89 / Owner PWA 0.5.54

- Corrige a unidade W/kW que bloqueava o diagnóstico atual de curtailment.
- Permite que a Deye Cloud dê apoio histórico de menor confiança quando faltam canais MPPT; exige leituras repetidas de produção, carga, SOC e baixa potência de carga.
- Mostra SOC 100% apenas quando a leitura Deye recente coincide com o máximo de tensão observado e carga quase nula; mantém esse valor fora do SOC integrado e do despacho automático.
- Mostra no Engine um estado atual simples de limitação FV e as evidências usadas.
- Huawei HiLink tenta o corpo password-only primeiro e, se o firmware o rejeitar, repete com Username admin, mantendo o hash de desafio e o token/cookie de sessão.
- Antminer: Owner mantém os dados de ligação; Energia ganha leituras de pool, hashes aceites, erros, tuner e configuração, comandos com confirmação e explorador das operações OpenAPI documentadas.
- O teste unificado volta a aplicar somente o alvo atual quando consegue lê-lo; se não conseguir, não envia ordem. O painel distingue resposta da API, pool ativa e shares aceites.
- O gateway valida operação e destino privado, limita a exploração aos endpoints declarados pela Braiins OS, oculta segredos na resposta e permite consultar as definições avançadas com os valores predefinidos.
- O controlo de potência deixa de assumir que todos os modelos param em 2,9 kW; a Braiins OS valida os limites reais do equipamento.
- A suite PWA continua sincronizada entre a versão publicada e a cópia incorporada no Gateway.
