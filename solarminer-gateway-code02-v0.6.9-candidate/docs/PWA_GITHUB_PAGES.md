# Publicação e primeira configuração Owner

## Publicar no GitHub Pages

O workflow `.github/workflows/pwa-pages.yml` publica a PWA integrada em `web/pwa`. Na primeira publicação, seleciona **Settings → Pages → GitHub Actions** em *Build and deployment → Source*. O endereço é `https://solargualdimpais-bot.github.io/TheSolarMiner/`. Alterações em `main` voltam a publicar a PWA depois das verificações do workflow.

O Gateway permite apenas a origem exata `https://solargualdimpais-bot.github.io`; não usa wildcard.

## Rede e TLS

O Gateway serve a LAN em `https://<IP-LAN>:8443`. Para acesso remoto, o Gateway entra no Tailnet, pede um certificado HTTPS para o seu nome MagicDNS `*.ts.net` e o Nginx recebe essa ligação em TCP 443. O iPhone também tem de estar ligado ao mesmo Tailnet. Não é necessário encaminhar portas no router.

A renovação de certificado por IPv4 público é opcional e fica desativada por padrão. Não uses um IP público por CGNAT. O acesso direto por IP LAN usa a identidade TLS local do Gateway e exige confiança TLS explícita no browser; o nome MagicDNS `*.ts.net` usa o certificado público emitido pela Tailscale.

O browser precisa de Web Crypto Ed25519 e IndexedDB. A PWA não ignora nem contorna erros TLS.

## Criar o primeiro Owner

1. No fim da instalação USB, introduz duas vezes na consola local do Gateway a palavra-passe inicial do Owner. Os caracteres são visíveis enquanto escreves; fica guardado apenas um verificador Argon2id.
2. Abre o GitHub Pages no iPhone, toca em **Ligar Gateway**, informa o endpoint LAN ou Tailscale e testa a ligação. Para Tailscale, ativa MagicDNS e HTTPS Certificates e mantém a app Tailscale ligada no iPhone.
3. Quando surgir `BOOTSTRAP_PENDING`, escolhe **Registar este telemóvel como Owner**, informa o nome e a palavra-passe definida localmente. A PWA gera uma chave Ed25519 para esse browser. Guarda offline a chave de recuperação mostrada uma única vez.

O bootstrap exige uma origem permitida, palavra-passe configurada localmente, assinatura de dispositivo e uso único. Não pede token nem MAC.

## Aceder noutro browser/dispositivo

Na primeira ligação desse browser, introduz o nome e a palavra-passe de uma conta ativa do Gateway. A PWA cria a chave Ed25519 local e o Gateway associa o dispositivo à conta. A palavra-passe só é transmitida pelo endpoint HTTPS e não é escrita nos logs. Os limites por IP e as rotas continuam a respeitar o papel da conta. Depois, a identidade do dispositivo fica guardada no armazenamento do browser e é usada para as sessões seguintes.

Se apagares os dados do Safari ou trocares de equipamento, autentica novamente com as credenciais da conta. O fluxo de recuperação de Owner continua separado e exige a chave de recuperação.

## Âmbito funcional

Uma sessão Owner consulta dados disponibilizados pelo Gateway, gere utilizadores/convites e verifica/aplica atualizações assinadas. Áreas sem contrato de API ou sem equipamento registado mostram estado vazio/indisponível. A integração física de inversores, baterias e outros equipamentos continua dependente do perfil e da validação de cada modelo.
