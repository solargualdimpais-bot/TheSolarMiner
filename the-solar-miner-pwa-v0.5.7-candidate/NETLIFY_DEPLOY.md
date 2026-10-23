# Publicar The Solar Miner PWA v0.5.14

O repositório publica automaticamente a PWA em GitHub Pages pelo workflow `pwa-pages.yml`. Para alojamento Netlify, publica o conteúdo desta pasta com `index.html` na raiz e HTTPS ativo.

A PWA precisa alcançar o Gateway através de HTTPS cujo certificado seja confiável pelo browser e cujo nome/IP conste no certificado. A PWA não ignora erros TLS nem aceita endpoints arbitrários sem validar a identidade do Gateway.

Após publicar, atualiza a PWA instalada e confirma que o rodapé indica 0.5.14. O perfil da casa (nome, fotografia, transparência e pisos/divisões) fica no Gateway e é partilhado com as PWA autenticadas; só o Owner o altera. A lista de favoritos é específica de cada PWA. Consulta `API_CONTRACTS.md` e `CHANGELOG_V0510.md`.
