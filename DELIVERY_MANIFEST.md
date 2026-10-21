# SolarMiner CODE02 v0.6.9 — entrega de ensaio

- `solarminer-gateway_0.6.9_amd64.deb`: pacote Debian construído e inspecionado; não instalado.
- `solarminer-gateway-code02-v0.6.9-source.zip`: código backend, pipeline de atualização, scripts, unidades, testes e documentação.
- `the-solar-miner-pwa-v0.5.7-source.zip`: código PWA preservado.
- `SOLARMINER_TEST_REPORT_V069.md`: resultados por grupo e limitações de validação.
- `INSTALL_CANDIDATE_V069_TEST_ENV.md`: procedimento para VM Debian descartável.
- `UPDATE_AND_ROLLBACK_V069.md`: estados persistentes, backup, health-check 60 s, rollback e recuperação.
- `CODE02_V069_IMPLEMENTATION.md`: resumo da implementação.
- `ACCEPTANCE_MATRIX_V069.md`: matriz de aceitação por área.
- `SOLARMINER_PROMPT_82641_REVISED.md`: prompt revisto anteriormente.
- `SOURCE_TREE_MANIFEST_V069.sha256` e `SOLARMINER_UPDATE_V069_SHA256SUMS.txt`: integridade dos ficheiros.

## Estado

Pipeline implementado e coberto por testes automatizados temporários; 206 testes backend em grupos sem sobreposição e 72 testes PWA aprovados. Ainda não houve instalação Debian real, ativação das units num host, reboot/corte de energia nem validação física. Candidata para VM de ensaio, não para Gateway físico/produção.
