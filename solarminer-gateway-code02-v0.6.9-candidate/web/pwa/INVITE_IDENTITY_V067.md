# PWA v0.5.5 — helpers de convite e confiança

O módulo `gateway-connection.js` acrescenta:

- `parseInviteQr(raw)`: valida estrutura, HTTPS, expiração e fingerprint SHA-256 completa. O resultado inicial mantém `identityValidated: false`.
- `verifyGatewayIdentityChallenge(invite, challenge)`: compara a fingerprint completa com a chave pública recebida e valida a assinatura Ed25519 sobre método/caminho/timestamp/nonce.
- `signInviteRedemption(...)`: constrói a assinatura canónica esperada pelo endpoint CODE02 v0.6.7, incluindo hashes de token, password e chave pública DER.

Estes helpers são testados localmente em Node.js, mas não estão integrados numa interface visual de convite. A leitura de QR, criação visual de QR, ativação de credenciais e o fluxo de ponta a ponta em Safari/iPhone não estão implementados/validados nesta entrega. Não confundir validação unitária do helper com validação do fluxo real do browser.
