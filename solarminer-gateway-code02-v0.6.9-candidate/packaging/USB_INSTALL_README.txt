SolarMiner Gateway CODE02 0.6.214 — instalador inicial USB

O envio automático de diagnósticos para o repositório privado exige um token Fine-grained limitado ao repositório de diagnósticos e à permissão Issues: Read and write. Configura-o depois em Owner → Gateway → Relatórios automáticos; sem token, os relatórios permanecem na fila local.
==========================================================

Requisitos: Gateway Lenovo AMD64, Debian 13 (Trixie), Python 3.13 ou posterior e acesso à Internet para os repositórios oficiais Debian e Tailscale.

1. Extrai todo o conteúdo deste ZIP para a raiz da pen USB.
2. No Gateway, inicia sessão como root e monta a pen.
3. Como root, executa `sh /mnt/solarminer-usb/install-from-usb.sh` (monta primeiro a partição da pen em `/mnt/solarminer-usb`).

O script valida manifesto, assinatura Ed25519, hash, tamanho, versão e arquitetura antes de instalar. Se a partição SOLARMINER_DATA existente for ext4, reutiliza-a sem a formatar: aí ficam a base de dados, as credenciais do Owner, chaves e configurações. Se essa base contiver um Owner ativo, mantém a conta e a palavra-passe. Uma partição SolarMiner existente com outro formato é recusada para proteger os dados. Se a partição SOLARMINER_DATA for apagada ou formatada, o Owner e os dados também desaparecem; faz uma cópia externa antes. O progresso fica em /var/log/solarminer-first-install.log.

No fim, `tailscale up` apresenta um endereço de autorização. Abre-o num dispositivo, inicia sessão na tua conta Tailscale e autoriza o Gateway. No painel de administração Tailscale ativa MagicDNS e HTTPS Certificates. Instala a app Tailscale no iPhone e liga-o à mesma conta/Tailnet. O Gateway deteta o nome `*.ts.net`, solicita o certificado HTTPS e publica o endpoint na área Owner da PWA. Não abras nem encaminhes portas no router.

A pen não executa programas automaticamente ao ser inserida; em Debian, inicia o script uma vez como root. Este comando destina-se apenas a um Debian limpo. Podes reinstalar/formatar apenas a partição do Debian desde que mantenhas intacta a partição SOLARMINER_DATA. Não escolhas opções de instalação que apaguem o disco inteiro nem formates a partição de dados. Mantém uma cópia externa. Para um Gateway já instalado, usa `repair-existing-from-usb.sh` e segue `REPAIR_EXISTING_README.txt`. A chave privada de release não é incluída neste ZIP.

Na primeira ligação, usa o endpoint Tailscale detetado (a opção recomendada para evitar instalar certificados no iPhone). Se o disco de dados já contiver Owner, usa as credenciais existentes; uma nova palavra-passe só é definida quando não existe Owner ativo. O IP LAN `https://192.168.8.168:8443` está disponível na rede local, mas usa um certificado local próprio; o iPhone tem de confiar nesse certificado. Não existe forma de um PWA HTTPS confiar em HTTPS de IP privado sem certificado confiável. Guarda a chave de recuperação Owner, apresentada uma única vez, num ficheiro offline. O manual completo fica em /usr/share/doc/solarminer-gateway/OWNER_FIRST_BOOTSTRAP.md.

