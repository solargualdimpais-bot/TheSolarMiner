SolarMiner Gateway CODE02 0.6.16 — instalador inicial USB
==========================================================

Requisitos: Gateway Lenovo AMD64, Debian 13 (Trixie) ou posterior, Python 3.13 ou posterior e acesso à Internet para os repositórios oficiais Debian.

1. Extrai todo o conteúdo deste ZIP para a raiz da pen USB.
2. No Gateway, inicia sessão como root e monta a pen.
3. Como root, executa `sh /mnt/solarminer-usb/install-from-usb.sh` (monta primeiro a partição da pen em `/mnt/solarminer-usb`).

O script valida manifesto, assinatura Ed25519, hash, tamanho, versão e arquitetura antes de instalar. O pacote provisiona uma identidade Ed25519 própria do Gateway e ativa a API com TLS. No fim, pede para escolher e confirmar a palavra-passe inicial do Owner; os caracteres ficam visíveis no terminal e o log não recebe a palavra-passe. O progresso fica em /var/log/solarminer-first-install.log.

A pen não executa programas automaticamente ao ser inserida; em Debian, inicia o script uma vez como root. Este comando destina-se apenas a um Debian limpo. Para um Gateway já instalado com versão 0.6.10–0.6.14, usa `repair-existing-from-usb.sh` e segue `REPAIR_EXISTING_README.txt`. A chave privada de release não é incluída neste ZIP.

Depois da instalação, abre a PWA no iPhone, introduz o endpoint HTTPS e testa-o. Se ainda não existir Owner, a PWA abre a janela inicial: introduz o nome e a palavra-passe que escolheste na consola do Gateway. O manual completo fica em /usr/share/doc/solarminer-gateway/OWNER_FIRST_BOOTSTRAP.md.
