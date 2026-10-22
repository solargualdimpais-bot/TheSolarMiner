# CODE 01 / A1 — RBAC e sessões

## Estado

`PARTIALLY_VALIDATED`. A implementação e os testes abaixo foram feitos numa cópia de trabalho do arquivo CODE 01 v0.4.0 disponível nesta sessão. Não houve acesso confirmado ao repositório privado GitHub e não foi feito upload.

## Matriz RBAC existente preservada

| Papel | read | operate | manage_users | manage_devices | manage_roles | manage_gateway | recover |
|---|---:|---:|---:|---:|---:|---:|---:|
| owner | Sim | Sim | Sim | Sim | Sim | Sim | Sim |
| admin | Sim | Sim | Sim | Sim | Não | Não | Não |
| operator | Sim | Sim | Não | Não | Não | Não | Não |
| viewer | Sim | Não | Não | Não | Não | Não | Não |

A matriz corresponde à constante `PERMISSIONS` já existente. Não foi criada uma segunda implementação de autorização nem alteradas as capacidades dos papéis.

## Endpoints verificados

| Endpoint | Regra observada |
|---|---|
| `GET /api/v1/health` | Público; verifica integridade da base de dados |
| `GET /api/v1/info` | Público |
| `GET /api/v1/bootstrap/status` | Público; não revela o token |
| `POST /api/v1/bootstrap/owner` | Origem HTTPS autorizada, palavra-passe definida localmente na instalação, timestamp/nonce e assinatura Ed25519; token legado continua compatível |
| `POST /api/v1/auth/device-login` | Utilizador e dispositivo associados, prova Ed25519 fresca; sessão temporária sem palavra-passe |
| `POST /api/v1/auth/login` | Compatibilidade com clientes existentes: credenciais, dispositivo associado, assinatura e nonce fresco |
| `GET /api/v1/status` | Sessão válida + `read` |
| `POST /api/v1/auth/logout` | Sessão válida; revoga o token atual |
| `GET/POST /api/v1/users` | Sessão válida + `manage_users` |
| `POST /api/v1/devices` | Sessão válida + `manage_devices` |
| `POST /api/v1/devices/{device_id}/revoke` | Sessão válida + `manage_devices`; revoga sessões do dispositivo |
| `POST /api/v1/users/{user_id}/revoke` | Sessão válida + `manage_users`; protege o último proprietário ativo |
| `GET /api/v1/audit` | Sessão válida + `manage_gateway` (owner) |

Não existe no projeto base um endpoint para alterar o papel de um utilizador, desativar utilizadores por separado ou reativá-los. A tentativa `PUT /api/v1/users/{id}` responde 404. Não foi criado um endpoint novo para mascarar essa lacuna.

## Proteção do último proprietário

Migração aditiva v2, sem remoção de tabelas/colunas:

- `protect_last_active_owner_update`: bloqueia desativação ou despromoção do último proprietário ativo;
- `protect_last_active_owner_delete`: bloqueia a remoção do último proprietário ativo;
- `protect_last_active_owner_replace`: bloqueia o caminho `INSERT OR REPLACE` que substituiria o último proprietário por outro papel/estado;
- `invalidate_sessions_on_role_change`: incrementa `credential_version` quando o papel muda, invalidando sessões existentes;
- `BEGIN IMMEDIATE` no endpoint de revogação serializa os escritores antes da leitura do número de proprietários;
- `RAISE(ABORT, 'last_active_owner_protected')` nos triggers bloqueia operações SQL que contornem a verificação da API;
- a tentativa de revogar o último proprietário é auditada como `denied` e a transação de auditoria é confirmada sem alterar a conta.

A semântica de `BEGIN IMMEDIATE` e `RAISE(ABORT)` segue a documentação oficial do SQLite: https://www.sqlite.org/isolation.html e https://www.sqlite.org/lang_createtrigger.html.

## Testes A1

O log completo está em `evidence/a1-make-test.log`.

| Cenário | Resultado |
|---|---|
| Suite de regressão do projeto | PASS — 20 testes aprovados |
| Viewer não consegue gerir utilizadores | PASS |
| Operator não consegue gerir utilizadores/dispositivos/auditoria | PASS |
| Admin mantém as permissões existentes e não lê auditoria | PASS |
| Criação de proprietário pela API é negada e auditada | PASS |
| Revogação do último proprietário é negada e auditada | PASS |
| Desativação, despromoção, DELETE e REPLACE diretos no SQLite bloqueados para último proprietário | PASS |
| Duas revogações concorrentes de proprietários | PASS — uma operação permitida, a outra rejeitada; fica um proprietário ativo |
| Alteração direta do papel incrementa `credential_version`; sessão anterior rejeitada | PASS |
| Sessão após logout e revogação do dispositivo | PASS (regressão existente) |
| Falha por username duplicado faz rollback sem associação órfã | PASS |
| Todas as rotas protegidas existentes rejeitam acesso direto sem sessão | PASS |
| Migração v2 numa base v1 com dados preserva o utilizador e instala triggers | PASS |
| Integridade SQLite após testes | PASS |
| `make deb` executado duas vezes; hashes iguais | PASS |
| Estrutura do pacote (`dpkg-deb --info` e `--contents`) | PASS |
| Tentativa de alterar o próprio papel por endpoint HTTP | BLOCKED — o endpoint não existe no projeto base; resposta 404, sem evento de auditoria associado |
| Tentativa de alterar o papel de outro utilizador por operação HTTP autorizada | BLOCKED — o fluxo de alteração de papel não existe; não se inventou um endpoint apenas para testes |
| Instalação/remoção do pacote num Debian com systemd ativo | BLOCKED — não executado neste ambiente |
| Ciclo de vida do serviço systemd após instalação/reboot | BLOCKED — não executado neste ambiente |
| Validação em hardware físico | BLOCKED — sem hardware físico |

## Integridade dos artefactos protegidos

Hashes calculados a partir dos ficheiros disponíveis no ambiente:

- Prova 0 Debian: `8716677481e91dd3b95f3de3ca84c9d0076cc708996a21d0211da858edad7fa6` — coincide.
- Prova 0 source ZIP: `e40c462bc3ae638ad73ce48218a81079a9da62b1194dfdc87fa70218092ba4bc` — coincide.
- CODE 01 pacote de base dentro do ZIP de origem: `975eda1d05e756a3685697f716b8998fc7bd351122e97c4a04cb36cbcbdb152a` — coincide.
- Pacote Debian A1 criado em diretório separado: `2d60a9e79cdae4671cadf78c6eba5a08b3581ee242670cc46375736c3ae49f9e`.

O pacote original do CODE 01 e os artefactos Prova 0 não foram substituídos. O pacote A1 foi criado em `dist-a1/`.

## Limitações e decisão

A1 não pode ser declarado concluído porque o projeto base não tem um fluxo de alteração de papéis nem um mecanismo de auditoria para tentativas HTTP de alteração de papel. Criá-los exige uma decisão de API/arquitetura e está fora de uma alteração segura por inferência. A validação de instalação/systemd e hardware também não foi realizada.
