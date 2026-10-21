# Publicação e primeira configuração Owner

## Publicar a PWA no GitHub Pages

O workflow .github/workflows/pwa-pages.yml publica a cópia integrada com a API e os controlos Owner de solarminer-gateway-code02-v0.6.9-candidate/web/pwa. Não publica a candidata visual isolada, que contém apenas dados sintéticos.

Na primeira publicação, abre **Settings → Pages** no repositório e seleciona **GitHub Actions** em **Build and deployment → Source**. Depois de guardar, o workflow valida a sintaxe JavaScript, executa os testes da PWA e publica o artefacto em:

https://solargualdimpais-bot.github.io/TheSolarMiner/

Cada alteração posterior à PWA em main volta a executar as verificações e a publicar o site. O origin permitido no Gateway é exatamente https://solargualdimpais-bot.github.io; não são permitidos origins com wildcard.

## Requisitos de rede e TLS

- O browser que abre a PWA tem de alcançar o Gateway pela porta TCP 8443.
- A ligação é HTTPS estrita. Instala no dispositivo cliente o certificado público /var/lib/solarminer/server.crt depois de confirmares a sua fingerprint SHA-256 no Gateway. Não uses -k, não desatives a validação TLS e não confies num certificado entregue apenas pela mesma ligação que estás a tentar validar.
- O hostname usado pelo browser tem de constar no SAN do certificado. O certificado instalado inicialmente inclui localhost, o hostname conhecido no momento da instalação e 127.0.0.1; um endereço IP LAN pode exigir renovação do certificado com esse IP no SAN.
- O browser precisa de suportar Web Crypto Ed25519 e IndexedDB. A chave privada do cliente é não exportável e fica no armazenamento de identidade do origin da PWA.

## Criar o primeiro Owner

1. Inicia sessão no terminal do Gateway como root. O serviço de primeira instalação cria uma identidade Ed25519 por Gateway e nunca a substitui durante upgrades.
2. Se o token de bootstrap expirou, executa os três comandos seguintes, um a um: para o serviço, gera token/fingerprint e volta a iniciar o serviço.

   systemctl stop solarminer-gateway.service

   solarminer-gateway bootstrap-token

   systemctl start solarminer-gateway.service

   O comando exige root, terminal interativo e serviço parado. Gera um token aleatório de utilização única, válido por 15 minutos, e imprime também a fingerprint da identidade Ed25519. Não guardes o token em ficheiro de texto, shell history, logs ou mensagens.

3. Abre o URL do GitHub Pages, escolhe **Gateway · detalhes**, introduz o endereço HTTPS do Gateway (por exemplo https://solarminer-gateway:8443) e seleciona **Testar endpoint**.
4. Compara, caractere por caractere, a fingerprint mostrada pelo comando local com a do campo de bootstrap da PWA. Usa o mesmo URL/hostname validado no certificado TLS.
5. Introduz o token, nome do Owner, palavra-passe e MAC como metadado declarado. A criação assina o pedido com uma nova chave Ed25519 do browser; o Gateway consome o token uma vez e devolve a chave de recuperação apenas na resposta de sucesso. Guarda a chave de recuperação offline.

O servidor aceita bootstrap remoto apenas por same-origin ou por um origin HTTPS exato em SOLARMiner_CORS_ORIGINS, com token de bootstrap válido, assinatura Ed25519 e nonce/timestamp novos. O endpoint não devolve o token. Após expirar, emite outro apenas através do comando local root.

## Modo Owner e limites de dados

Uma sessão Owner pode consultar os dados disponíveis no Gateway, gerir convites e verificar/aplicar atualizações assinadas. A PWA autenticada já não preenche cartões com amostras simuladas; áreas sem contrato de API ou sem equipamento registado mostram estado vazio/indisponível. A gestão Owner fica em **Gateway · detalhes**.

O Gateway disponibiliza APIs de leitura/identidade, administração e atualização, mas não há ainda uma API de comandos físicos para todos os equipamentos, regras de automatização, meteorologia ou histórico energético. A interface não afirma que esses elementos funcionam como controlos reais. A integração física exige perfil e validação específica de cada inversor, bateria, carregador ou dispositivo.

## Recuperar um Gateway 0.6.10–0.6.14 antes da primeira conta Owner

O Gateway que ainda não tem Owner e apresenta `recovery required` não deve ser atualizado pelo fluxo online enquanto o estado de recuperação da instalação anterior estiver bloqueado. A atualização remota 0.6.12 falhou porque o nome do asset `.deb` publicado não coincidia com o nome assinado no manifesto; por isso o pacote não foi aplicado e o Gateway permaneceu na 0.6.10. A versão 0.6.14 do script USB também tinha um defeito: `/etc/os-release` substituía a variável `VERSION` destinada ao pacote Debian, fazendo a validação recusar um pacote que era realmente 0.6.14. A 0.6.15 separa esses valores e inclui uma verificação no workflow para impedir regressão.

No Debian 13 amd64, inicia sessão como `root`, monta a pen em `/mnt/solarminer-usb` e executa `sh /mnt/solarminer-usb/repair-existing-from-usb.sh`. Depois de confirmar que o script terminou com health check válido, emite o token local de bootstrap, um comando de cada vez:

```sh
systemctl stop solarminer-gateway.service
solarminer-gateway bootstrap-token
systemctl start solarminer-gateway.service
```

Escreve a confirmação `ISSUE-OWNER-BOOTSTRAP-TOKEN` quando solicitada; compara a fingerprint local com a PWA e conclui a criação do Owner em 15 minutos. A versão 0.6.15 inclui o comando `bootstrap-token` no wrapper instalado e mantém o origin oficial do GitHub Pages permitido. O iPhone continua a exigir confiança explícita num certificado válido para o IP/hostname usado; a PWA não pode ignorar nem instalar essa confiança silenciosamente. Se a assinatura, a origem, a instalação ou o health check falhar, conserva `/var/log/solarminer-usb-repair.log` e `/var/lib/solarminer/backups/`.
