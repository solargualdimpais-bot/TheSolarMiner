SolarMiner Gateway CODE02 0.6.12 — instalador inicial USB
==========================================================

Requisitos: Gateway Lenovo AMD64, Debian 13 (Trixie) ou posterior, Python 3.13 ou posterior e acesso à Internet para os repositórios oficiais Debian.

1. Extrai todo o conteúdo deste ZIP para a raiz da pen USB.
2. No Gateway, inicia sessão como root e monta a pen.
3. Executa: sh /media/<utilizador>/<PEN>/install-from-usb.sh

O script valida manifesto, assinatura Ed25519, hash, tamanho, versão e arquitetura antes de instalar. O pacote provisiona uma identidade Ed25519 própria do Gateway e ativa a API com TLS. O progresso fica em /var/log/solarminer-first-install.log.

A pen não executa programas automaticamente ao ser inserida. Executa o comando acima uma vez. Este ZIP destina-se à instalação inicial; para um Gateway já instalado usa o fluxo autenticado de atualização assinada. A chave privada de release não é incluída neste ZIP.

Depois de ativar o Gateway, segue a secção “Configuração inicial Owner e GitHub Pages” no guia Debian instalado em /usr/share/doc/solarminer-gateway/INSTALL_DEBIAN_AMD64.md.
