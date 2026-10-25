SolarMiner Gateway CODE02 0.6.86 — instalador inicial USB

O envio automático de erros para issues GitHub requer um token Fine-grained com Issues: Read and write, limitado a este repositório. Depois da instalação, como root, executa `solarminer-gateway github-error-token` no Gateway. Sem token, os relatórios ficam apenas na fila local.
==========================================================

Requisitos: Gateway Lenovo AMD64, Debian 13 (Trixie), Python 3.13 ou posterior e acesso à Internet para os repositórios oficiais Debian e Tailscale.

1. Extrai todo o conteúdo deste ZIP para a raiz da pen USB.
2. No Gateway, inicia sessão como root e monta a pen.
3. Como root, executa `sh /mnt/solarminer-usb/install-from-usb.sh` (monta primeiro a partição da pen em `/mnt/solarminer-usb`).

O script valida manifesto, assinatura Ed25519, hash, tamanho, versão e arquitetura antes de instalar. Instala o cliente Tailscale pelo repositório oficial assinado, instala o Gateway, provisiona a identidade TLS e pede para escolher e confirmar a palavra-passe inicial do Owner; os caracteres ficam visíveis no terminal e o log não recebe a palavra-passe. O progresso fica em /var/log/solarminer-first-install.log.

No fim, `tailscale up` apresenta um endereço de autorização. Abre-o num dispositivo, inicia sessão na tua conta Tailscale e autoriza o Gateway. No painel de administração Tailscale ativa MagicDNS e HTTPS Certificates. Instala a app Tailscale no iPhone e liga-o à mesma conta/Tailnet. O Gateway deteta o nome `*.ts.net`, solicita o certificado HTTPS e publica o endpoint na área Owner da PWA. Não abras nem encaminhes portas no router.

A pen não executa programas automaticamente ao ser inserida; em Debian, inicia o script uma vez como root. Este comando destina-se apenas a um Debian limpo. Para um Gateway já instalado com versão 0.6.10–0.6.14 e 0.6.20, usa `repair-existing-from-usb.sh` e segue `REPAIR_EXISTING_README.txt`. A chave privada de release não é incluída neste ZIP.

Na primeira ligação, usa o endpoint Tailscale detetado (a opção recomendada para evitar instalar certificados no iPhone). Só o primeiro registo com a palavra-passe definida na consola pode criar o Owner. O IP LAN `https://192.168.8.168:8443` está disponível na rede local, mas usa um certificado local próprio; o iPhone tem de confiar nesse certificado. Não existe forma de um PWA HTTPS confiar em HTTPS de IP privado sem certificado confiável. Guarda a chave de recuperação Owner, apresentada uma única vez, num ficheiro offline. O manual completo fica em /usr/share/doc/solarminer-gateway/OWNER_FIRST_BOOTSTRAP.md.
