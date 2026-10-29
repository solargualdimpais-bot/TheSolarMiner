# Changelog CODE02 v0.6.8 / PWA v0.5.7

## CODE02

- `PACKAGE_VERSION` passa a `0.6.8`; o contrato público da API permanece `0.6.0`.
- O Gateway emite um código de convite de utilização única; a PWA gera o QR e apresenta uma página de ativação.
- `/api/v1/energy/categories` identifica corretamente a PWA incorporada v0.5.7.
- Novo `database_backup.py`: backup SQLite consistente, sidecar de metadados, validação SHA-256/tamanho/schema e restauro offline fail-closed.
- Novo `deployment_recovery.py`: journal durável, lock, troca atómica de symlink e recuperação após `SIGKILL`.
- Novo wrapper `solarminer-recovery` e units systemd service/timer independentes da API.
- Testes novos para backup/restauro WAL, metadados, interrupção de ALTER TABLE, troca de symlink e journal corrompido.
- `/api/v1/system/update/apply` mantém HTTP 503 até a integração completa do pipeline de ativação.

## PWA

- Versão `0.5.7`, mantendo a base visual v0.5.6.
- Fluxo de bootstrap Owner local, login, convite e revogação.
- Chave de dispositivo persistida como CryptoKey não exportável; token de sessão apenas em memória.
- Consulta autenticada dos endpoints existentes de status, categorias e equipamentos.
- Estados de dados LIVE/STALE/UNKNOWN/UNAVAILABLE sem inventar leituras nem usar fallback silencioso para DEMO.
- Service worker versionado, cache estático allowlisted e exclusão de APIs/autenticação.
- Presença de sessão autenticada, sem alegar presença física ou método LAN/REMOTO.
