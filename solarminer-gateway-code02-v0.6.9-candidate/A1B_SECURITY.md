# SolarMiner Gateway — CODE 01 / A1b

## Estado e âmbito

**Estado: PARTIALLY_VALIDATED.** A1b parte do ZIP real da entrega A1 (SHA-256 `50d3e9ce3b9dfd8a5343a2abd3bb168b44558a18a274a18b62b8ebda493c55ad`) e mantém o modelo SQLite e os mecanismos de autenticação existentes. A versão de pacote foi incrementada de `0.4.0` para `0.4.1`. Não foi criada uma migração de esquema v3 porque os novos fluxos usam as colunas/tabelas já existentes; a inicialização continua a aplicar/verificar os triggers da migração A1 v2.

A implementação limita-se à gestão segura de papéis e estados, reautenticação, auditoria e compatibilidade necessária. A A1b é uma cópia de trabalho separada; não houve publicação GitHub nem instalação física.

## Matriz RBAC preservada

| Papel | read | operate | manage_users | manage_devices | manage_roles | manage_gateway | recover |
|---|---:|---:|---:|---:|---:|---:|---:|
| owner | Sim | Sim | Sim | Sim | Sim | Sim | Sim |
| admin | Sim | Sim | Sim | Sim | Não | Não | Não |
| operator | Sim | Sim | Não | Não | Não | Não | Não |
| viewer | Sim | Não | Não | Não | Não | Não | Não |

A matriz existente `PERMISSIONS` não foi alterada. Os dois novos endpoints exigem adicionalmente que o ator seja `owner` ativo, com reautenticação bem-sucedida. A rota antiga `POST /api/v1/users/{id}/revoke` foi restringida à mesma política porque altera o mesmo estado de conta e, sem esta correção, permitiria contornar os novos controlos através do papel `admin`.

## Endpoints

| Método e caminho | Permissão | Corpo | Resultado |
|---|---|---|---|
| `PATCH /api/v1/users/{id}/role` | owner ativo + palavra-passe atual | `{"role":"owner|admin|operator|viewer","current_password":"..."}` | Altera papel; trigger A1 incrementa `credential_version` |
| `PATCH /api/v1/users/{id}/status` | owner ativo + palavra-passe atual | `{"status":"active|revoked","current_password":"..."}` | Ativa/desativa conta; revoga sessões ao desativar |
| `POST /api/v1/users/{id}/revoke` (compatibilidade endurecida) | owner ativo + palavra-passe atual | `{"current_password":"..."}` | Revoga conta; não permite revogar a própria conta |

`revoked` é o estado inativo já definido pelo esquema A1; não foi criada uma coluna de estado paralela. Campos adicionais, tipos não-string e valores desconhecidos são recusados. Os papéis válidos são `owner`, `admin`, `operator` e `viewer`. O estado válido é `active` ou `revoked`.

## Reautenticação e consistência

- A palavra-passe atual é verificada com o `PasswordHasher` Argon2id já existente, contra o hash da conta do ator autenticado; não foi criado um segundo sistema de credenciais.
- Dentro de `BEGIN IMMEDIATE`, o servidor volta a confirmar que o ator é owner ativo e que a sessão continua existente, não revogada, não expirada, associada a dispositivo ativo e com `credential_version` atual.
- Identidade e papel não são aceites a partir do corpo HTTP. Os endpoints não aceitam alterar o próprio papel nem desativar a própria conta.
- Alterações de papel usam `invalidate_sessions_on_role_change`; sessões antigas do alvo deixam de passar a validação de versão. A sessão do owner executor não é alterada por operação sobre outro utilizador.
- Desativar revoga as sessões do alvo e as associações a dispositivos na mesma transação. Reativar repõe apenas associações a dispositivos que continuam ativos; sessões antigas permanecem revogadas e é necessário login novo.
- O registo de sucesso de auditoria e a alteração de privilégios pertencem à mesma transação. Se a inserção da auditoria falhar, a alteração é revertida. É tentado um evento de falha após rollback; se a própria base de auditoria estiver indisponível, não é possível garantir esse evento, mas a alteração permanece revertida e a API falha fechada.

## Códigos HTTP

| Código | Uso efetivo |
|---|---|
| `200` | Alteração concluída |
| `400` | Papel/estado semanticamente inválido |
| `401` | Palavra-passe de reautenticação incorreta ou sessão já inválida |
| `403` | Papel não autorizado ou tentativa de autoalteração proibida |
| `404` | Utilizador visado inexistente, após autorização/reautenticação |
| `409` | Conflito com invariantes, incluindo último owner ativo |
| `422` | JSON/corpo ausente ou malformado, tipo incorreto, campo obrigatório ausente ou campo extra |
| `503` | Erro de base de dados; a resposta não expõe SQL nem stack trace |

Pedidos sem sessão válida continuam a ser rejeitados com `401`. Tentativas autenticadas recusadas são auditadas. Pedidos sem contexto de sessão válido não são atribuídos a uma identidade de auditoria.

## Proteção do último owner e migração

A1b preserva os triggers A1:

- `protect_last_active_owner_update` — impede despromoção/desativação direta do último owner ativo;
- `protect_last_active_owner_delete` — impede remoção direta do último owner ativo;
- `protect_last_active_owner_replace` — impede contorno via `INSERT OR REPLACE`;
- `invalidate_sessions_on_role_change` — incrementa `credential_version` ao alterar papel.

A proteção não depende apenas da API. A escrita usa `BEGIN IMMEDIATE`, o trigger aplica `RAISE(ABORT, 'last_active_owner_protected')` e a recusa deixa a operação sem alterações parciais. Os testes verificam atualização de estado, alteração de papel, DELETE e `INSERT OR REPLACE`. A migração v2 existente continua presente e os triggers são reinstalados/verificados durante a inicialização; não há migração v3 porque não houve alteração de esquema.

## Evidência de testes

O log integral encontra-se em `evidence/a1b/make-test.log`. Na execução final, `make test` aprovou 32 testes. A corrida de dois owners que tentam despromover um ao outro é parametrizada e executada em cinco bases de teste independentes; cada execução usa duas threads, uma barreira de sincronização antes dos pedidos e HTTP real via TestClient. Em todas as execuções, uma operação foi concluída e a outra recusada; ficou pelo menos um owner ativo, e a auditoria registou um sucesso e uma recusa.

O teste de falha de auditoria injeta um trigger que aborta o evento de sucesso, verifica HTTP `503`, confirma que o papel original foi preservado e que não existe evento de sucesso falso. Os testes de sessão confirmam invalidação após mudança de papel e desativação, impossibilidade de login durante desativação, novo login após reativação e continuidade da sessão do owner executor.

## Limitações e bloqueios

- Não foi executado o pacote num sistema Debian de destino com systemd ativo; o ciclo de instalação/arranque/reboot permanece `BLOCKED`.
- Não foi possível validar hardware físico; permanece `BLOCKED`.
- O hash final do ZIP A1b é calculado após a criação do arquivo final e não é um valor predefinido no código.
- Os códigos `422` são os códigos reais de validação de corpo emitidos pelo FastAPI/Pydantic; não são apresentados como `400`.
