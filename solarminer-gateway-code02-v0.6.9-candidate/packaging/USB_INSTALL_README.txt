SolarMiner Gateway CODE02 0.6.242 — instalador inicial USB

O envio automático de diagnósticos para o repositório privado exige um token Fine-grained limitado ao repositório de diagnósticos e à permissão Issues: Read and write. Configura-o depois em Owner → Gateway → Relatórios automáticos; sem token, os relatórios permanecem na fila local.
==========================================================

Requisitos: Gateway Lenovo AMD64, Debian 13 (Trixie), Python 3.13 ou posterior e acesso à Internet para os repositórios oficiais Debian e Tailscale.

1. Extrai todo o conteúdo deste ZIP para a raiz da pen USB.
2. No Gateway, inicia sessão como root e monta a pen.
3. Como root, executa `sh /mnt/solarminer-usb/install-from-usb.sh` (monta primeiro a partição da pen em `/mnt/solarminer-usb`).

O script valida manifesto, assinatura Ed25519, hash, tamanho, versão e arquitetura antes de instalar. Por padrão, se a partição SOLARMINER_DATA existente for ext4, reutiliza-a intacta: aí ficam a base de dados, o Owner, chaves, configurações e histórico. Quando encontra um Owner ativo com hash válido, pede a palavra-passe no terminal sem a mostrar nem a guardar em logs. A validação usa a consola local real, mesmo que o instalador tenha reservado o stdin para o próprio script. Tentativas não têm limite. Se não conseguires validá-la, podes tentar outra vez ou escrever exatamente `APAGAR DADOS` para formatar apenas a partição SOLARMINER_DATA e criar tudo de novo. Essa ação apaga a base, Owner, dispositivos, configurações, histórico e relatórios guardados nessa partição; não pode ser desfeita. Uma base marcada como inicializada mas sem Owner verificável é recusada e preservada. Uma partição SolarMiner com formato inesperado é recusada. Faz uma cópia externa antes de confirmar a formatação. O progresso fica em /var/log/solarminer-first-install.log.

Na primeira ligação, `tailscale up` pode apresentar um endereço para aprovar este Gateway na tua conta Tailscale. Essa aprovação é obrigatória se não existir uma chave de inscrição previamente configurada. No painel de administração Tailscale ativa MagicDNS e HTTPS Certificates. Depois da aprovação, o instalador solicita o certificado, configura Nginx e testa o endpoint HTTPS com o nome Tailscale, TLS/SNI e API que a PWA usa. Se a aprovação ou os certificados estiverem pendentes, o instalador identifica esse estado em vez de declarar o endpoint pronto. Instala a app Tailscale no iPhone e liga-o à mesma conta/Tailnet. Não abras nem encaminhes portas no router.

A pen não executa programas automaticamente ao ser inserida; em Debian, inicia o script uma vez como root. Este comando destina-se apenas a um Debian limpo. Podes formatar a partição do Debian mantendo a partição SOLARMINER_DATA intacta. Não escolhas opções de instalação que apaguem o disco inteiro. A formatação da partição de dados só ocorre se escreveres explicitamente `APAGAR DADOS` no instalador. Mantém uma cópia externa. Para um Gateway já instalado, usa `repair-existing-from-usb.sh` e segue `REPAIR_EXISTING_README.txt`. A chave privada de release não é incluída neste ZIP.

Na primeira ligação, usa o endpoint Tailscale detetado (a opção recomendada para evitar instalar certificados no iPhone). Se o disco de dados já contiver Owner, usa as credenciais existentes; uma nova palavra-passe só é definida quando não existe Owner ativo. O IP LAN `https://192.168.8.168:8443` está disponível na rede local, mas usa um certificado local próprio; o iPhone tem de confiar nesse certificado. Não existe forma de um PWA HTTPS confiar em HTTPS de IP privado sem certificado confiável. Guarda a chave de recuperação Owner, apresentada uma única vez, num ficheiro offline. O manual completo fica em /usr/share/doc/solarminer-gateway/OWNER_FIRST_BOOTSTRAP.md.

