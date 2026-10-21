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

## Compatibilidade do Gateway instalado

O fluxo remoto de bootstrap e a identidade por dispositivo são introduzidos no pacote 0.6.12. Um Gateway 0.6.10 já instalado tem de receber uma atualização assinada para 0.6.12 antes de a PWA publicada poder criar o Owner remotamente. O pacote 0.6.11 não deve ser usado para este upgrade: o respetivo `postinst` não corre no pipeline que ativa a release por symlink. Na versão 0.6.12, o comando local de emissão do token também cria ou valida a identidade, preservando chaves já existentes. A publicação Pages, por si só, não atualiza o pacote do Gateway.

### Atualizar o Gateway 0.6.10 já instalado

Depois de o release assinado `gateway-v0.6.12` estar publicado, inicia sessão no Gateway como `root` e executa estes comandos, um de cada vez. O primeiro corre a verificação configurada no próprio Gateway; não instala nada. O segundo procura uma operação `VERIFIED` para a versão 0.6.12. Só continua se encontrar essa operação:

```sh
systemctl start solarminer-update-check-daily.service
OP_ID=$(/usr/bin/python3 -c 'import sqlite3; c=sqlite3.connect("/var/lib/solarminer/gateway.db"); r=c.execute("SELECT id FROM update_operations WHERE state=? AND target_version=? ORDER BY updated_at DESC LIMIT 1", ("VERIFIED", "0.6.12")).fetchone(); print(r[0] if r else "")')
test -n "$OP_ID" || { echo "Não existe pacote 0.6.12 validado; não foi aplicada nenhuma atualização."; exit 1; }
/usr/sbin/solarminer-update-apply --enqueue "$OP_ID"
```

O helper root volta a executar o preflight e enfileira a instalação pelo serviço systemd isolado; a rotina existente valida novamente manifesto, assinatura e pacote e executa backup, staging, ativação, health check e rollback. A verificação diária não aplica atualizações sozinha. Confirma o resultado com `systemctl status "solarminer-update-apply@$OP_ID.service"` e consulta `/var/lib/solarminer/gateway.db` para o estado final. Se a operação não aparecer como `VERIFIED`, não forces a instalação: verifica a chave de release, a allowlist e o log de `solarminer-update-check-daily.service`.

Este procedimento depende de o Gateway 0.6.10 ter sido instalado com a chave pública de release e a allowlist oficial, como no instalador USB assinado. Não usa `sudo`; os comandos são executados numa sessão root. O procedimento e o health check precisam ainda de ser confirmados no Gateway físico antes de declarar a instalação validada.
