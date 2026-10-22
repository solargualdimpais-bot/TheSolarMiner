SolarMiner Gateway 0.6.24 — reparar Gateway instalado através de USB

Usa este procedimento num Gateway Debian 13 amd64 que já tenha SolarMiner instalado e cuja chave pública de release esteja em /etc/solarminer/release-pubkey.pem.

1. Extrai todos os ficheiros deste ZIP para a raiz da pen.
2. No Gateway, inicia sessão como root e monta a pen em /mnt/solarminer-usb.
3. Executa: sh /mnt/solarminer-usb/repair-existing-from-usb.sh
4. O script só prossegue se a assinatura Ed25519, a chave já confiada, o hash, o tamanho, a versão e a arquitetura forem válidos. Instala/verifica o cliente Tailscale oficial, cria um backup SQLite, instala o pacote e ativa a nova release. O bundle também contém os pacotes assinados 0.6.10–0.6.14 e 0.6.20 para rollback do pacote instalado.
5. Se a instalação ou o health check falhar, o script tenta reinstalar a versão anterior assinada, reativar a release anterior e restaurar a base de dados. Consulta o log antes de repetir.
6. Depois de o script confirmar sucesso, executa como root, um comando de cada vez: `systemctl stop solarminer-gateway.service`; `solarminer-gateway bootstrap-token`; `systemctl start solarminer-gateway.service`.
7. Confirma a emissão escrevendo ISSUE-OWNER-BOOTSTRAP-TOKEN. Usa o token e a fingerprint na PWA em até 15 minutos.
8. Se o Gateway ainda não estiver autorizado no Tailnet, executa `tailscale up` como root e aprova o URL na conta Tailscale. Ativa MagicDNS e HTTPS Certificates no Admin Console.

O script não usa o updater online nem executa `git pull`. Mantém o log em /var/log/solarminer-usb-repair.log, o backup em /var/lib/solarminer/backups/ e a release anterior em /opt/solarminer/releases/. Não apagues esses ficheiros. Este procedimento exige Debian 13 amd64, a chave de release já provisionada e uma versão instalada entre 0.6.10 e 0.6.14, ou a 0.6.20.
