# Acesso à PWA por IP público e HTTPS

## O que esta versão configura

O serviço SolarMiner escuta apenas em `127.0.0.1:8443`. O Nginx incluído no pacote publica a API nas portas TCP 80 e 443, limita tentativas de autenticação e encaminha pedidos para o serviço local com validação TLS. A porta 80 serve somente o desafio ACME. O Gateway tenta emitir um certificado público Let's Encrypt para o seu IPv4 público e renova-o automaticamente; os certificados de IP usam o perfil de curta duração e precisam de renovação frequente.

Na primeira instalação, o Gateway precisa de acesso à Internet. O router tem de encaminhar **TCP 80 para a porta 80 do Gateway** e **TCP 443 para a porta 443 do Gateway**. A reserva DHCP deve manter o IP LAN do mini PC. Não encaminhes a porta 8443 para a Internet. Após configurar as regras, o serviço tenta emitir o certificado no arranque e repete a tentativa periodicamente.

## Endereço para a PWA

Usa no campo do Gateway o **IPv4 público** apresentado pelo teu router ou pelo fornecedor de Internet, sem `:8443`, por exemplo `https://203.0.113.40`. O Gateway instala certificado para o IP público que deteta. Se estiveres dentro de casa e quiseres usar o mesmo endereço, o router tem de suportar NAT loopback/hairpin; nesse caso o tráfego regressa ao Gateway e o certificado continua a corresponder ao IP.

Um endereço privado como `192.168.x.x` não corresponde ao certificado público do IP WAN. Para usar diretamente o IP LAN sem aviso TLS é necessário um nome de domínio apontado à rede e um certificado para esse nome, ou instalar uma CA privada em cada dispositivo. Esta implementação escolhe o acesso pelo IP público, sem instalar uma CA no iPhone.

## Condições que dependem do router e do ISP

- O router precisa de receber um IPv4 público e permitir encaminhamento TCP 80/443. CGNAT, bloqueio do ISP ou ausência de IPv4 público impedem acesso direto, independentemente do software.
- O IPv4 público deve permanecer estável para o endereço guardado na PWA continuar válido. Se mudar, a rotina renova o certificado para o novo IP, mas é necessário atualizar o endpoint guardado na PWA.
- O iPhone precisa de ligação à Internet para alcançar o endpoint. A PWA usa HTTPS e valida a cadeia e o SAN do certificado; não desativa erros TLS nem aceita certificados autoassinados.
- Esta configuração publica a API do Gateway na Internet. Usa contas individuais e palavras-passe fortes já registadas no Gateway. Um novo browser que introduz credenciais válidas regista a sua chave Ed25519 como dispositivo dessa conta; o Gateway aplica limites de tentativas e mantém auditoria sem guardar a palavra-passe nos logs.

## Verificar o estado

No Gateway, como `root`, consulta:

```sh
systemctl status nginx solarminer-gateway solarminer-public-tls-renew.timer
journalctl -u solarminer-public-tls-renew.service -n 40 --no-pager
nginx -t
```

O endpoint público só fica pronto quando o certificado estiver emitido e o Nginx o tiver carregado. O certificado local de bootstrap serve para a ligação interna entre Nginx e o serviço e não é apresentado ao browser.

## Limites da confirmação

O código pode automatizar o serviço, o certificado, o proxy e a autenticação. Não consegue configurar o router, remover CGNAT, escolher um IPv4 estático nem confirmar a acessibilidade externa sem dados do ISP/router. Confirma o primeiro arranque numa rede externa antes de considerar o acesso remoto validado.
