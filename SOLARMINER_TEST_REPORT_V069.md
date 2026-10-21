# Relatório de testes — CODE02 v0.6.9 / PWA v0.5.7

Execução em ambiente de desenvolvimento em 2026-10-19. Os grupos backend foram executados separadamente, com timeout por comando. Os grupos listados não se sobrepõem.

## Backend

| Grupo | Comando | Resultado | Duração pytest aproximada |
|---|---|---:|---:|
| Contratos v0.6.1–v0.6.4, conectores, Gateway e presença | `PYTHONPATH=src timeout 100s python3 -m pytest -q --maxfail=1 -k 'not slow' tests/test_code02_v061.py tests/test_code02_v062.py tests/test_code02_v063.py tests/test_code02_v064.py tests/test_connectors.py tests/test_gateway.py tests/test_presence.py` | 142 passed | 23.53 s |
| Pairing/browser WebCrypto | `PYTHONPATH=src timeout 60s python3 -m pytest -q --maxfail=1 tests/test_browser_pairing.py` | 10 passed | 4.14 s |
| Recuperação preexistente | `PYTHONPATH=src timeout 60s python3 -m pytest -q --maxfail=1 tests/test_recovery.py` | 28 passed | 6.25 s |
| Backup SQLite + troca/recovery de deployment | `PYTHONPATH=src timeout 60s python3 -m pytest -q --maxfail=1 tests/test_database_backup.py tests/test_deployment_recovery.py` | 11 passed | 1.69 s |
| Convites/update API + novo pipeline | `PYTHONPATH=src timeout 90s python3 -m pytest -q --maxfail=1 tests/test_v067_invites_updates.py tests/test_system_update_pipeline.py` | 15 passed | 4.08 s |

Total aritmético backend sem sobreposição: **206 passed**, zero falhas/ignorados nestes grupos.

## PWA

- `node --check app.js`: PASS.
- `node --check gateway-auth.js`: PASS.
- `node --test tests/*.test.js`: **72 passed, 0 failed, 0 skipped**, cerca de 0.56 s.

## Pipeline de atualização — testes novos

- Pacote `.deb` descartável com manifesto Ed25519, tamanho/hash e payload backend+PWA: a máquina de estados termina em `COMMITTED` quando o health-check injetado confirma a versão esperada. Este teste não contacta um Gateway HTTPS real.
- Health-check sem resposta: deadline de 60 segundos verificado com relógio simulado, sem esperar um minuto real.
- Preflight com recuperação independente indisponível: enqueue recusado.
- Health-check da nova release falhado: rollback do symlink para a versão anterior, restauro SQLite real a partir do backup temporário e estado terminal `ROLLED_BACK`; o resultado do health-check é injetado neste teste.
- API: owner e operação `VERIFIED` enfileiram via helper e devolvem HTTP 202; testes sem operação verificada mantêm bloqueio HTTP 503.
- Recuperação de estado `SWITCHED` simulado: restaura o symlink anterior, repõe backup SQLite real de teste e grava `ROLLED_BACK`.

## Verificações adicionais

- `python3 -m py_compile src/solarminer_gateway/*.py`: PASS.
- `sh -n` para scripts de instalação/helper: PASS.
- `visudo -cf packaging/solarminer-update-apply.sudoers`: PASS.
- `systemd-analyze verify` sobre cópias temporárias das units, substituindo apenas `ExecStart` por `/bin/true` para permitir validação de sintaxe sem instalar os helpers: PASS. Os binários reais foram confirmados no conteúdo do `.deb`; as units não foram ativadas no host.
- `.deb` construído com `dpkg-deb --build`, metadados e conteúdo inspecionados; não instalado.

## Verificações não executadas

- Não foi instalado o `.deb` em Debian/systemd real; `sudoers`, timer, units e helper privilegiado ainda precisam de validação no host de ensaio.
- Não houve reboot real, corte de energia, SIGKILL em todas as fronteiras do novo pipeline, upgrade com a base real ou health-check durante 60 segundos contra Gateway instalado.
- Não houve Safari/iPhone/QR nativo/IndexedDB real nem instalação física.
