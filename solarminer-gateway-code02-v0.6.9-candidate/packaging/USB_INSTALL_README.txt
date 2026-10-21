SolarMiner Gateway CODE02 0.6.9 — instalador inicial USB
=========================================================

Requisitos: Gateway Lenovo AMD64, Debian 13 (Trixie) ou posterior, Python 3.13 ou posterior e acesso à Internet para os repositórios oficiais Debian.

1. Extrai todo o conteúdo deste ZIP para a raiz da pen USB.
2. No Gateway, inicia sessão como root e monta a pen.
3. Executa: sh /media/<utilizador>/<PEN>/install-from-usb.sh

O script não pede URL ou hashes. Verifica primeiro o manifesto assinado, a assinatura Ed25519, o hash, o tamanho, a versão, a origem autorizada e a arquitetura. Depois instala o pacote SolarMiner e dependências Debian, configura a origem oficial de atualizações e executa o health check. O progresso fica em /var/log/solarminer-first-install.log.

A pen não executa programas automaticamente ao ser inserida. Executa o comando acima uma vez. Não uses este instalador para atualizar um Gateway já configurado. A chave pública é pública; a chave privada nunca é incluída neste ZIP.

Se a instalação falhar, não repitas às cegas: consulta o log como root. A conta Owner e a confiança TLS são configuradas no primeiro acesso à PWA, conforme a documentação instalada em /usr/share/doc/solarminer-gateway/.
