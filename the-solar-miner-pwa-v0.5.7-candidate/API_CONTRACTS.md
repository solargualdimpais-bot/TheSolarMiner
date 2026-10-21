# Contratos API — PWA v0.5.7

## Endpoints efetivamente utilizados pela PWA existente

| Método | Endpoint | Utilização |
|---|---|---|
| GET | `/api/v1/health` | Diagnóstico explícito de saúde/versão |
| GET | `/api/v1/info` | Diagnóstico explícito de identificação do serviço |

As chamadas de diagnóstico existentes continuam a ser separadas das novas áreas locais. O incremento v0.5.4 não acrescenta chamadas API.

## Atualizações assinadas do Gateway — v0.5.7 / CODE 02 v0.6.9

| Método | Endpoint | Utilização |
|---|---|---|
| POST | `/api/v1/system/update/check` | Owner autenticado envia `{"repository_url":"https://github.com/owner/repository"}`; Gateway resolve o repositório através da allowlist administrativa, valida manifesto/pacote assinado e devolve a versão candidata e preflight |
| GET | `/api/v1/system/update/status` | Consulta estado persistente da operação |
| POST | `/api/v1/system/update/apply` | Owner confirma explicitamente a versão verificada; enfileira a ativação existente com backup, health check e rollback |

O campo de URL apenas escolhe uma origem pública já autorizada no dispositivo. A PWA não recebe credenciais. Verificar não aplica; a aplicação exige uma ação Owner separada e é bloqueada se assinatura, pacote, compatibilidade ou preflight falharem. O Gateway só consulta manifesto/pacote de lançamento HTTPS e não clona o repositório nem executa scripts ou dependências obtidos dele. Os estados e códigos de rejeição são apresentados pela PWA sem inserir conteúdo remoto como HTML.

## Contratos necessários que não foram encontrados no CODE 02 v0.6.5 inspecionado

- Preferências pessoais autenticadas: leitura/gravação por utilizador, com versionamento/migração aditiva.
- Gestão de utilizadores: listagem, convite/associação, alteração de estado e papéis, com RBAC e auditoria no servidor.
- Automatismos: capacidades declaradas por dispositivo; CRUD de regras; condições e operadores; scheduler/avaliação no Gateway; execução segura de ações; prevenção de ciclos; histórico de avaliação/execução e motivos; tratamento de fontes desatualizadas/offline.
- Meteorologia/presença/astronomia: fonte meteorológica configurada, timestamp/validade, localização e fuso horário, nascer/pôr do Sol, e fontes de presença autorizadas.
- Produção solar: leituras históricas por timestamp em kW/kWh, previsão central, fonte/atualização/confiança e API para potencial diário/restante calculado pelo Gateway.

## Sem endpoints inventados

A PWA v0.5.4 mantém os dados de demonstração em `localStorage`. Nenhum dos contratos acima é tratado como existente, e nenhum resultado local é apresentado como gravação ou execução no Gateway.
