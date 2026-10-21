# Relatório de regressão CODE02/PWA — v0.6.7 parcial

## Preservação
- A base de referência foi verificada por SHA-256 antes de começar e não foi modificada.
- O incremento é aditivo; não foram removidos testes existentes.
- Os contratos `/api/v1/health` e `/api/v1/info` mantêm o valor de versão API `0.6.0`; versão do pacote/release é `0.6.7`.
- Tabela `schema_migrations` recebe versão 6 e a criação das novas tabelas é aditiva via `CREATE TABLE IF NOT EXISTS`.
- Nova dependência Python: nenhuma. Utiliza `cryptography` já existente.
- Novas tabelas: `invites`, `invite_nonces`, `invite_attempts`, `update_operations`.

## Estado funcional
- Convites backend: implementado e testado localmente nos casos listados no relatório de testes.
- Gateway identity challenge: implementado; teste local com par Ed25519 gerado por teste. Requer provisionamento real independente antes de ativar.
- Verificação de manifesto e staging: implementados no módulo; não foi feita transferência para release remota real.
- Ativação/rollback remoto: não implementados; endpoint `apply` recusa a operação.
- PWA: helpers de confiança e assinatura implementados; UI/fluxo completo de convites não integrado.

## Riscos residuais
- Provisionamento e gestão/recuperação da chave de identidade Gateway ainda são procedimentos externos.
- `SOLARMINER_PUBLIC_URL`, fingerprint/identidade e release public key exigem configuração segura.
- O update manager ainda não implementa ativação, migração, backup coordenado, health-check 60s ou recuperação independente.
- Sem `.deb`, não existe artefacto de deployment CODE02 v0.6.7 pronto para instalação.
- Nenhum teste real de Safari/iPhone, Tailscale ou hardware físico.
