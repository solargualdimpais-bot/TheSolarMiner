# Acesso por LAN e Tailscale

## Endereço local

O serviço Gateway escuta em `https://<ip-lan>:8443`, por exemplo `https://192.168.8.168:8443`, sem qualquer encaminhamento no router. O Gateway provisiona um certificado local autoassinado com os IPs encontrados durante a instalação. O browser tem de confiar nesse certificado; o PWA não contorna alertas nem permite ignorar erros TLS. Após formatar o Gateway, o certificado local muda.

## Acesso remoto recomendado: Tailscale

O instalador USB instala o cliente Tailscale oficial para Debian 13 AMD64 e ativa o serviço. Na consola do Gateway, `tailscale up` apresenta o URL para autorizar esse dispositivo na tua conta Tailscale. A autorização é necessária: o Gateway não recebe credenciais Tailscale da PWA e não pode aderir ao Tailnet sem aprovação da conta.

No painel de administração Tailscale, ativa MagicDNS e HTTPS Certificates. A aplicação Tailscale também tem de estar ligada no iPhone à mesma Tailnet. O Gateway solicita/renova um certificado público para o nome `*.ts.net` e o Nginx serve a API por TCP 443. Não é necessário comprar domínio nem abrir portas no router. O nome do dispositivo/Tailnet fica publicado no Certificate Transparency quando o certificado é emitido.

Na PWA Owner, a secção **Tailscale** apresenta o nome detetado, permite guardar o endpoint e selecioná-lo. O PWA guarda-o no browser para tentar automaticamente esse endpoint quando a ligação LAN principal falhar. O endpoint Tailscale exige HTTPS válido, app Tailscale ligada e sessão normal do SolarMiner; não desativa autenticação da aplicação.

Se não quiseres instalar certificado no iPhone, usa o endereço `https://<gateway>.<tailnet>.ts.net` dentro e fora de casa, mantendo Tailscale ligado. Um IP privado como `192.168.8.168` não pode ter certificado público correspondente; o acesso direto a esse IP exige que o browser confie no certificado local.

## Verificar o estado como root

```sh
systemctl status tailscaled solarminer-tailscale-cert.timer nginx solarminer-gateway
tailscale status
nginx -t
journalctl -u solarminer-tailscale-cert.service -n 40 --no-pager
```

Se o cliente está ligado mas o certificado não está pronto, confirma MagicDNS e HTTPS Certificates no Admin Console. O timer tenta novamente. A porta 8443 é para acesso LAN; não a encaminhes na Internet. Tailscale não requer encaminhamento manual de portas e funciona através de CGNAT.

## Acesso público direto opcional

O pacote mantém uma rotina opcional para certificado público por IPv4. Esta não é necessária para Tailscale e não supera CGNAT. Não configures port forwarding para o Gateway como parte da instalação Tailscale.
