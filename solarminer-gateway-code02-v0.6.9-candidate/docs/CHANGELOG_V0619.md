# SolarMiner Gateway 0.6.19

- Instalação USB para Debian 13 AMD64 inclui instalação do cliente Tailscale a partir do repositório oficial assinado, ativa `tailscaled` e apresenta o fluxo oficial de autorização do Gateway.
- O serviço Gateway escuta no IP da rede local para suportar `https://<ip-lan>:8443`; a validação TLS continua obrigatória.
- Emissão periódica de certificado HTTPS Tailscale para o nome MagicDNS `*.ts.net` e reverse proxy Nginx em 443, sem port forwarding nem domínio comprado.
- API Owner `GET/PUT /api/v1/system/tailscale` reporta o estado reduzido do Tailscale e grava um endpoint MagicDNS validado.
- A PWA Owner pode consultar, guardar e usar o endpoint Tailscale. A PWA tenta o endpoint Tailscale previamente guardado se a ligação principal falhar.
- O primeiro Owner continua a ser criado através da palavra-passe escolhida na consola local durante a instalação. O primeiro visitante não recebe privilégios Owner automaticamente.

## Limitação conhecida

O acesso HTTPS direto a um IP LAN privado requer confiança explícita no certificado local nesse browser. Para evitar instalar uma CA/certificado no iPhone, usa o endpoint HTTPS `*.ts.net` com a app Tailscale ligada no telefone. A aprovação do Gateway no Tailnet e a ativação de MagicDNS/HTTPS Certificates exigem ação na conta Tailscale do Owner.
