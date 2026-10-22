# Acesso remoto por Tailscale

O pacote SolarMiner 0.6.22 instala o cliente Tailscale oficial para Debian 13 AMD64, ativa `tailscaled`, cria um verificador de estado de leitura para a PWA e agenda a emissão/renovação do certificado HTTPS do MagicDNS. O Gateway não cria uma conta Tailscale, não guarda uma auth key e não instala Tailscale no iPhone.

## Primeira instalação

1. A pen instala o Tailscale a partir do repositório oficial assinado e ativa `tailscaled`.
2. Depois de registares o Owner, abre Gestão do Gateway → Tailscale na PWA e toca em **Ligar Gateway ao Tailscale**. A PWA pede ao Gateway para executar `tailscale up` e mostra um link temporário. Abre o link e autoriza este Gateway na tua conta. Também podes usar o URL apresentado pelo instalador no terminal.
3. No Tailscale Admin Console, ativa MagicDNS e **HTTPS Certificates**. A emissão TLS requer esta opção; o nome do dispositivo e o domínio do Tailnet ficam publicados no Certificate Transparency, conforme o funcionamento de certificados públicos.
4. Instala a app Tailscale no iPhone, inicia sessão no mesmo Tailnet e liga a app.
5. Liga a PWA ao Gateway pelo IP LAN ou pelo nome `*.ts.net`. Depois de uma sessão Owner, a área Tailscale consulta o endpoint detetado, permite configurar/guardar o endereço do Gateway e fornece **Usar para ligar**. A PWA guarda esse endereço localmente e tenta-o automaticamente se o endpoint principal falhar.

O Tailscale estabelece ligações de saída e não exige encaminhamento de portas no router. O Gateway serve o IP LAN na porta HTTPS 8443 e o endpoint MagicDNS na porta HTTPS 443. O Nginx usa um certificado público Tailscale para `*.ts.net`; a API continua a aplicar sessões, roles Owner, TLS e autenticação Ed25519.

## Limites de TLS e da primeira autorização

O endpoint local `https://192.168.8.168:8443` usa o certificado TLS local provisionado no Gateway. Como endereços RFC1918 não podem receber um certificado público de uma CA, cada browser que aceda diretamente a esse IP tem de confiar explicitamente no certificado/CA local. O PWA não contorna erros TLS. Para não instalar certificado no iPhone, usa `https://<nome-do-gateway>.<tailnet>.ts.net` dentro e fora da rede, com Tailscale ligado no iPhone.

A instalação não pode autorizar o Gateway num Tailnet por conta própria sem uma credencial pertencente ao utilizador. O processo pede aprovação por URL na conta Tailscale. Esta autorização não pode ser substituída por registar automaticamente o primeiro visitante como Owner: o Owner continua a provar a palavra-passe definida localmente durante a instalação.

## API Owner

- `GET /api/v1/system/tailscale` — devolve estado reduzido (instalado/ligado), nome MagicDNS, endpoint detetado/configurado e se os ficheiros TLS estão prontos. Só Owner.
- `PUT /api/v1/system/tailscale` — grava `{ "endpoint": "https://host.tailnet.ts.net" }` ou `{ "endpoint": null }` para voltar à deteção automática. Só Owner; exige HTTPS, host `*.ts.net`, porta padrão e sem caminho, query, fragmento ou credenciais.

A API usa um helper root de leitura para o estado e um helper fixo para executar `tailscale up`; ambos são limitados por sudoers. A PWA recebe apenas o URL temporário de autorização, nunca a auth key, chaves privadas ou estado completo dos peers. O URL não é escrito nos logs.

## Diagnóstico local como root

```sh
systemctl status tailscaled solarminer-tailscale-cert.timer nginx solarminer-gateway
tailscale status
solarminer-gateway tailscale-info
journalctl -u solarminer-tailscale-cert.service -n 40 --no-pager
```

Se o Tailscale está ligado mas HTTPS não está pronto, confirma MagicDNS e HTTPS Certificates no Admin Console. O timer tenta novamente periodicamente.
