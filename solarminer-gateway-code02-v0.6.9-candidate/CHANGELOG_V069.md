# Changelog CODE02 v0.6.9 / PWA v0.5.7

- Adicionada máquina de estados persistente do updater: `APPLY_QUEUED`, `PRECHECK`, `BACKUP_CREATED`, `STAGED`, `SWITCHED`, `SERVICE_RESTARTING`, `HEALTH_CHECKING`, `COMMITTED`, `ROLLING_BACK`, `ROLLED_BACK`, `FAILED` e `RECOVERY_BLOCKED`.
- O endpoint de apply passa a enfileirar a operação numa unidade systemd independente e responder `202`, apenas depois de pré-condições de segurança.
- Revalidação root de manifesto Ed25519, SHA-256, tamanho, versão, arquitetura e dependências.
- Backup SQLite antes de ativação, symlink atómico, health-check HTTPS autenticado pelo certificado local até 60 segundos e rollback de release/base de dados.
- Recuperação offline em boot e timer, independente do processo da API.
- Health endpoint inclui `package_version` sem alterar o contrato público `version`.
- PWA estática passa a ser resolvida da release ativa, para backend e interface mudarem como uma unidade.
- PWA permanece v0.5.7; PROFILE/favoritos, comandos físicos e fase E continuam fora deste incremento.
