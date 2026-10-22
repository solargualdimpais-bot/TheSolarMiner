# Publicação e primeira configuração Owner

## Publicar no GitHub Pages

O workflow `.github/workflows/pwa-pages.yml` publica a PWA integrada em `web/pwa`. Na primeira publicação, seleciona **Settings → Pages → GitHub Actions** em *Build and deployment → Source*. O endereço é `https://solargualdimpais-bot.github.io/TheSolarMiner/`. Alterações em `main` voltam a publicar a PWA depois das verificações do workflow.

O Gateway permite apenas a origem exata `https://solargualdimpais-bot.github.io`; não usa wildcard.

## Rede e TLS

O backend escuta apenas em `127.0.0.1:8443`. O Nginx do pacote recebe o tráfego externo em TCP 80/443, encaminha a API com TLS verificado para o backend e limita tentativas de login. TCP 80 serve o desafio ACME. O router deve encaminhar WAN TCP 80 → Gateway TCP 80 e WAN TCP 443 → Gateway TCP 443. Não encaminhes 8443.

O Gateway tenta emitir um certificado público Let's Encrypt para o seu IPv4 público e renova-o automaticamente. Na PWA, usa `https://IP-PUBLICO`, sem `:8443`. Um IP LAN `192.168.x.x` não corresponde ao certificado do IP WAN. Para usar o mesmo URL enquanto estás no Wi-Fi, o router precisa de suportar NAT loopback/hairpin. Requisitos, limitações de CGNAT e verificação estão em `docs/REMOTE_ACCESS_AND_TLS.md`.

O browser precisa de Web Crypto Ed25519 e IndexedDB. A PWA não ignora nem contorna erros TLS.

## Criar o primeiro Owner

1. No fim da instalação USB, introduz duas vezes na consola local do Gateway a palavra-passe inicial do Owner. Os caracteres são visíveis enquanto escreves; fica guardado apenas um verificador Argon2id.
2. Abre o GitHub Pages no iPhone, abre **Gateway · detalhes**, informa `https://IP-PUBLICO` e testa a ligação.
3. Quando surgir `BOOTSTRAP_PENDING`, escolhe **Registar este telemóvel como Owner**, informa o nome e a palavra-passe definida localmente. A PWA gera uma chave Ed25519 para esse browser. Guarda offline a chave de recuperação mostrada uma única vez.

O bootstrap exige uma origem permitida, palavra-passe configurada localmente, assinatura de dispositivo e uso único. Não pede token nem MAC.

## Aceder noutro browser/dispositivo

Na primeira ligação desse browser, introduz o nome e a palavra-passe de uma conta ativa do Gateway. A PWA cria a chave Ed25519 local e o Gateway associa o dispositivo à conta. A palavra-passe só é transmitida pelo endpoint HTTPS e não é escrita nos logs. Os limites por IP e as rotas continuam a respeitar o papel da conta. Depois, a identidade do dispositivo fica guardada no armazenamento do browser e é usada para as sessões seguintes.

Se apagares os dados do Safari ou trocares de equipamento, autentica novamente com as credenciais da conta. O fluxo de recuperação de Owner continua separado e exige a chave de recuperação.

## Âmbito funcional

Uma sessão Owner consulta dados disponibilizados pelo Gateway, gere utilizadores/convites e verifica/aplica atualizações assinadas. Áreas sem contrato de API ou sem equipamento registado mostram estado vazio/indisponível. A integração física de inversores, baterias e outros equipamentos continua dependente do perfil e da validação de cada modelo.
