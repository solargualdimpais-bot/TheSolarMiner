# The Solar Miner PWA v0.5.7

## Base visual preservada

A versão v0.5.7 parte da PWA v0.5.6. Foram mantidos o layout, tipografia, modal de produção com os quatro KPI e gráfico detalhado, hierarquia da casa, favoritos DEMO, automatismos locais e os testes de regressão da v0.5.6. A v0.5.5 não foi usada como base de substituição.

## Alterações

- Formulários de login e resgate de convite.
- Bootstrap inicial de Owner limitado ao browser local do Gateway.
- Identidade de dispositivo Ed25519 e persistência da chave privada como CryptoKey não exportável no IndexedDB.
- Token de sessão apenas em memória; pedidos autenticados usam `cache: no-store` e `credentials: omit`.
- Gestão Owner de convites, QR SVG gerado pelo backend, lista e revogação.
- Verificação de fingerprint/assinatura do Gateway antes do login e resgate.
- Leitura autenticada de status, categorias e equipamentos; distinção LIVE/STALE/UNKNOWN/UNAVAILABLE sem fallback silencioso para DEMO.
- Service worker v0.5.7 com allowlist de recursos estáticos e exclusão de API, query strings, headers de autenticação e conteúdo pessoal.
- Presença de sessão através da API autenticada existente, sem inferir presença física ou LAN/REMOTO.

## Não incluído

- Comandos físicos, drivers novos, sincronização de favoritos/PROFILE no backend, série temporal inexistente, validação visual em Safari/iPhone e publicação.
