# Relatório de testes — CODE02 v0.6.8 / PWA v0.5.7

Data da execução: 2026-10-19 (UTC do ambiente de execução). Os grupos abaixo foram executados separadamente, cada um com timeout; não foi usado um único comando agregado para todas as suites.

## Backend — grupos sem sobreposição

| Grupo | Comando | Resultado | Duração medida pelo pytest |
|---|---|---:|---:|
| Contratos CODE02 v0.6.1–v0.6.4, conectores, Gateway e presença | `PYTHONPATH=src timeout 90s python3 -m pytest -q --maxfail=1 -k 'not slow' tests/test_code02_v061.py tests/test_code02_v062.py tests/test_code02_v063.py tests/test_code02_v064.py tests/test_connectors.py tests/test_gateway.py tests/test_presence.py` | **142 passed** | 24.34 s |
| Interoperabilidade browser/WebCrypto e pairing | `PYTHONPATH=src timeout 60s python3 -m pytest -q --maxfail=1 tests/test_browser_pairing.py` | **10 passed** | 4.11 s |
| Recuperação existente | `PYTHONPATH=src timeout 60s python3 -m pytest -q --maxfail=1 tests/test_recovery.py` | **28 passed** | 6.68 s |
| Convites v0.6.7, backup/restauro, recuperação de releases e nova integração | `PYTHONPATH=src timeout 60s python3 -m pytest -q --maxfail=1 tests/test_v067_invites_updates.py tests/test_database_backup.py tests/test_deployment_recovery.py` | **20 passed** | 4.08 s |

Total aritmético dos grupos backend sem sobreposição: **200 testes aprovados**. Não houve falhas nem testes ignorados nesses grupos. O total não substitui os resultados separados acima.

## PWA — grupo separado

- `node --check app.js`: PASS.
- `node --check gateway-auth.js`: PASS.
- `node --test tests/*.test.js`: **72 passed, 0 failed, 0 skipped**, 0.56 s.

## Verificações de sintaxe e falha

- `python3 -m py_compile src/solarminer_gateway/*.py`: PASS.
- Parser HTML: sem IDs duplicados; todos os ficheiros de script referenciados pelo HTML existem.
- `systemd-analyze verify` para a unidade e timer de recuperação: PASS com um `ExecStart` temporário apontado ao wrapper no diretório de build; isto valida a sintaxe/estrutura, não a execução no host instalado.
- `dpkg-deb --build` e inspeção com `dpkg-deb --info/--contents`: PASS; o pacote não foi instalado.
- Backup/restauro SQLite: tests em DB temporária em WAL, verificação de hash/tamanho/versão, sidecar e integridade.
- `SIGKILL` durante `ALTER TABLE` sem commit numa DB temporária: a alteração não fica aplicada e `PRAGMA integrity_check` devolve `ok`.
- `SIGKILL` antes/depois de troca atómica de symlink num diretório temporário: recuperação limpa o staging ou restaura o apontador anterior.
- A API continua a devolver HTTP 503 para `/api/v1/system/update/apply`; o teste confirma o bloqueio intencional.

## Não executado / não alegado

- Não houve instalação do `.deb`, arranque do serviço em host systemd real, reboot real ou teste offline num Gateway físico.
- Não houve testes visuais de browser, Safari/iPhone, permissões reais IndexedDB/CryptoKey, leitor QR nativo ou instalação PWA em ecrã inicial.
- Os testes de `SIGKILL` são de isolamento e não validam um pipeline completo de atualização do CODE02 em produção.
- A unidade systemd não foi iniciada no host de desenvolvimento; não se afirma que o timer ou serviço funcionaram num Gateway real.
