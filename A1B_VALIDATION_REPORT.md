# Relatório de validação — SolarMiner Gateway CODE 01 / A1b

**Estado final: PARTIALLY_VALIDATED**

A1b foi implementada numa cópia separada da entrega A1 real. O pacote tem versão `0.4.1`; os artefactos anteriores não foram sobrescritos. Ver `docs/A1B_SECURITY.md` para detalhes, matriz RBAC, endpoints, códigos HTTP, sessões, auditoria e classificação dos requisitos.

## Resultados da execução

- `make test`: 32 passed.
- Teste concorrente de despromoção entre dois owners: executado em cinco instâncias de teste independentes, usando duas threads e uma barreira; em cada execução, 1 operação teve sucesso, 1 foi recusada, e permaneceu pelo menos 1 owner ativo.
- Falha da auditoria de sucesso: alteração revertida, HTTP 503, nenhum evento de sucesso falso; evento de falha registado quando a tabela de auditoria continuou disponível.
- Migração: versões 1 e 2 preservadas; triggers A1 presentes; `INSERT OR REPLACE` bloqueado.
- Reautenticação, autorização, auditoria, invalidação de sessões, reativação sem restauração de sessões antigas, compatibilidade da rota de revogação e regressões anteriores cobertos pelos testes.
- `make deb`: duas construções independentes; hashes comparados no log.
- `dpkg-deb --info` e `dpkg-deb --contents`: executados sobre o pacote A1b.
- SHA-256 do pacote Debian A1b: `760a19a3f9d3a257eb1139c05761118c41bc5bcc1e10cc6844833aebecb9292f`; o payload Python empacotado foi comparado byte a byte com o código-fonte testado.
- SHA-256 do ZIP de código-fonte A1b: consta no manifesto de entrega externo, calculado após a criação do arquivo final.

## Integridade dos artefactos protegidos

Os valores abaixo são recalculados a partir dos ficheiros reais e registados em `evidence/a1b/protected-artifacts-sha256.txt`:

- CODE 01 original (pacote Debian dentro do ZIP original): esperado `975eda1d05e756a3685697f716b8998fc7bd351122e97c4a04cb36cbcbdb152a`.
- Prova 0 source ZIP: esperado `e40c462bc3ae638ad73ce48218a81079a9da62b1194dfdc87fa70218092ba4bc`.
- Prova 0 Debian: esperado `8716677481e91dd3b95f3de3ca84c9d0076cc708996a21d0211da858edad7fa6`.
- A1 source ZIP: esperado `50d3e9ce3b9dfd8a5343a2abd3bb168b44558a18a274a18b62b8ebda493c55ad`.
- A1 Debian: esperado `2d60a9e79cdae4671cadf78c6eba5a08b3581ee242670cc46375736c3ae49f9e`.

## Classificação

| Requisito | Estado | Evidência/nota |
|---|---|---|
| Endpoints PATCH role/status | PASS | Testes HTTP de owner autorizado, payload inválido e alvo inexistente |
| Owner-only e anti-escalada | PASS | Admin/operator/viewer recusados; papel consultado no servidor |
| Reautenticação atual | PASS | Palavra-passe incorreta recusa; segredo não aparece em resposta, auditoria ou logs |
| Auditoria de sucessos/recusas | PASS | Eventos transacionais e testes de conteúdo |
| Auditoria obrigatória falha sem alteração parcial | PASS | Teste de falha de inserção de auditoria |
| Autoalteração de papel e autodesativação | PASS | Recusadas e auditadas |
| Último owner ativo | PASS | Triggers UPDATE/DELETE/REPLACE e corrida concorrente; não fica zero owner |
| Invalidação de sessões por alteração de papel | PASS | `credential_version` A1 e sessão antiga rejeitada |
| Invalidação por desativação/reativação | PASS | Sessão antiga permanece inválida; novo login após reativação |
| Migração A1 v2 e preservação de dados/triggers | PASS | Testes existentes de migração e teste A1b |
| Regressões HTTP do CODE 01 | PASS | Suite integral `make test` |
| Reprodutibilidade do pacote | PASS | Duas construções e hashes iguais |
| Inspeção de pacote Debian | PASS | `dpkg-deb --info` e `--contents` |
| Instalação em Debian de destino e ciclo systemd | BLOCKED | Não executado neste ambiente |
| Hardware físico | BLOCKED | Não disponível neste ambiente |
| Publicação GitHub | NOT_APPLICABLE | Explicitamente fora do âmbito |
| A2 / CODE 02 | NOT_APPLICABLE | Não iniciados |

## Artefactos

O pacote Debian A1b, o ZIP do código-fonte A1b, logs de testes/construção, hashes e relatório são entregues separadamente. A1b não deve ser declarada release final de produção enquanto os bloqueios de instalação/systemd e hardware não forem verificados.
