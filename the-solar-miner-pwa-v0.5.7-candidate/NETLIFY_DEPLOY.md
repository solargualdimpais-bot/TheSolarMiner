# Publicar The Solar Miner PWA v0.5.7 no Netlify

## Publicação

1. Obter a árvore `the-solar-miner-pwa-v0.5.7-candidate` da branch aprovada do repositório.
2. Publicar o conteúdo dessa pasta como site estático, selecionando como diretório de publicação a pasta que contém `index.html`. Não usar o ZIP v0.5.4 citado em instruções antigas.
3. Confirmar que o site está em HTTPS. A PWA usa Web Crypto, IndexedDB e service worker, que requerem contexto seguro.
4. Abrir o URL no iPhone, recarregar e instalar no ecrã inicial. Fechar e reabrir para permitir que o service worker `the-solar-miner-static-v0.5.7` atualize os recursos.
5. Confirmar os refinamentos descritos no README v0.5.7: diálogo de produção, seletor de lettering, título “A Minha Casa” e controlos locais de favoritos.
6. Validar separadamente a ligação ao Gateway. O Gateway tem de ser alcançável por HTTPS, com certificado e nome/IP confiáveis pelo browser e SAN correspondente. O browser não permite ignorar erros de certificado.

## Limites

A PWA pode mostrar valores sintéticos e funcionalidades DEMO. Os controlos de equipamentos não enviam comandos físicos; automatismos, administração, favoritos e preferências locais não representam estado sincronizado do Gateway. Fotos e preferências ficam no armazenamento local do browser. Safari/iPhone real e instalação PWA física ainda não foram validados para esta candidata.

Consulte `API_CONTRACTS.md`, `BACKEND_DEPENDENCIES.md` e `INVITE_IDENTITY_V067.md` para dependências e fluxo de identidade/convites.