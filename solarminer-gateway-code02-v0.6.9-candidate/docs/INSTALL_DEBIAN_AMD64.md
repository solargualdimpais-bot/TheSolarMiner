# Instalação inicial — Debian amd64

## Destino e pré-requisitos

O pacote CODE02 é `amd64`, adequado ao Intel Core i5-8400. O alvo suportado é Debian 13 (Trixie) ou posterior, com Python 3.13 ou posterior; o runtime requer Pydantic 2 e FastAPI 0.115.11 ou posterior. Debian 12 (Bookworm) não satisfaz estes requisitos do pacote. Confirma no Gateway com:

```sh
cat /etc/os-release
dpkg --print-architecture
python3 --version
```

O resultado de arquitetura tem de ser `amd64`. Não usar pacotes ARM64.

## Instalação inicial através de pen USB

A execução de software automaticamente ao inserir uma pen USB está desativada pelo Debian. A imagem oficial do release contém um instalador não interativo; após copiar a pasta extraída para a pen, inicia sessão no Gateway como `root`, monta a pen e executa **um comando**:

```sh
sh /mnt/solarminer-usb/install-from-usb.sh
```

O workflow de release deve gerar um ZIP versionado com o instalador inicial, instalação/configuração base do Tailscale, a ferramenta de reparação, pacotes de rollback assinados, o pacote Debian AMD64, o manifesto Ed25519 e a chave pública de release derivada no workflow da chave privada mantida como segredo de GitHub Actions. Não copies a chave privada para a pen ou Gateway. Depois da instalação, o Gateway verifica releases assinados diariamente e aplica-os automaticamente apenas quando a verificação e o preflight passam.

O instalador não pede URLs, hashes nem impressão digital: usa o repositório oficial `https://github.com/solargualdimpais-bot/TheSolarMiner`. Antes de instalar o SolarMiner, valida no Gateway Debian 13 ou posterior, AMD64 e Python 3.13 ou posterior, o esquema/versão/origem do manifesto, a assinatura Ed25519, o tamanho e SHA-256 do pacote e a arquitetura Debian. Se a assinatura ou qualquer validação falhar, termina sem instalar o SolarMiner. Depois instala o pacote e dependências apenas dos repositórios Debian, provisiona a chave pública e a allowlist oficial, ativa os serviços e timers e verifica o health endpoint local. Em falha, tenta remover o pacote e restaurar a configuração inicial; consulta `/var/log/solarminer-first-install.log`.

A versão 0.6.46 acrescenta autonomia da bateria na área Energia e diferencia visualmente carga e descarga. Mantém fotografia partilhada, edição do enquadramento e vinheta, gráfico histórico interativo, navegação Casa, consola do Gateway e sincronização de inventário Tuya Cloud. Mantém a configuração de até 8 bancos e 64 cargas flexíveis, incluindo múltiplos AQS e aquecimento radiante, e comandos manuais confirmados de interruptores Tuya. O resumo calcula elegibilidade de despacho e bloqueia dados Deye com mais de 90 segundos. Comandos automáticos continuam bloqueados até comissionamento físico; esta versão não substitui validação de campo. Consulta `HARDWARE_INTEGRATIONS.md`, `ENERGY_ENGINE.md` e `docs/deye/README.md`.

O Gateway regista erros sanitizados e pode enviar diagnósticos técnicos para o repositório privado `TheSolarMiner-Diagnostics`. O Owner configura o Fine-grained Personal Access Token em Owner → Gateway → Relatórios automáticos; limita-o a esse repositório e à permissão `Issues: Read and write`. O token fica guardado apenas no Gateway e nunca é devolvido à PWA. Consulta `ERROR_REPORTING.md` para o conteúdo, privacidade e limites do envio.

É necessária ligação à Internet durante a instalação para atualizar o APT e instalar dependências Debian e Tailscale. A pen ativa o cliente Tailscale, mas não pode autenticar-se por ti: abre no telefone o URL apresentado no terminal e autoriza o Gateway com a tua conta. No painel Tailscale ativa MagicDNS e HTTPS Certificates. Instala e liga Tailscale no iPhone. O nome `*.ts.net` é detetado e aparece na secção Owner da PWA; não compres domínio nem abras portas no router. Se preferires `https://192.168.8.168:8443` diretamente, o browser tem de confiar no certificado local do Gateway. O primeiro Owner ainda exige a palavra-passe definida na consola. A instalação não atualiza firmware automaticamente; atualizações são verificadas diariamente, mas continuam a exigir ação explícita do Owner para aplicação.

Se o endpoint Tailscale responder `502 Bad Gateway`, abre Owner → Tailscale → “Detetar estado” e consulta os quatro checks: certificado válido para o nome `.ts.net`, configuração Nginx válida, Nginx ativo e serviço Gateway ativo. Depois abre Owner → Consola para ler os registos recentes dos serviços. Esta consola não executa comandos livres; permite atualizar os logs e iniciar a verificação normal de uma release assinada. A opção de atualização não aplica a release.

O instalador inicial destina-se a um Debian limpo. Para reparar uma instalação existente, usa o script específico do bundle; não forces o updater online se o Gateway indicar `RECOVERY_BLOCKED`. Extrai os ficheiros do ZIP, monta a pen em `/mnt/solarminer-usb` e executa como `root` `sh /mnt/solarminer-usb/repair-existing-from-usb.sh`. O script valida manifesto, assinatura com a chave já confiada, hash, tamanho, versão e arquitetura, cria backup SQLite, ativa a release assinada e tenta reinstalar a versão anterior assinada, repor a release e restaurar a base de dados se o health check falhar. Log: `/var/log/solarminer-usb-repair.log`; backups: `/var/lib/solarminer/backups/`.

## Configuração inicial Owner e publicação PWA

O workflow pwa-pages.yml publica a cópia integrada com a API em https://solargualdimpais-bot.github.io/TheSolarMiner/ depois de o administrador selecionar GitHub Actions em Settings → Pages → Build and deployment → Source. Usa a aplicação ligada ao Gateway; o diretório isolado da candidata PWA permanece um artefacto visual sem funções Gateway.

Se a instalação USB terminar antes de definires a palavra-passe inicial, inicia sessão como `root` e executa `solarminer-gateway owner-password` num terminal interativo. O comando mostra os caracteres digitados, pede confirmação, grava apenas um verificador Argon2id e só funciona antes de existir um Owner.

Após reparar um Gateway existente, se ele ainda não tiver Owner e a configuração local inicial estiver disponível, executa como `root` `solarminer-gateway owner-password` num terminal interativo. Instalações antigas cujo estado já mudou para `RECOVERY_REQUIRED` continuam a exigir o procedimento de recuperação documentado; o novo fluxo não contorna nem recria credenciais numa base de dados existente. Não uses `curl | sh`, `git pull` nem código fonte como atualizador.

Para permitir acesso remoto direto por IP, configura o encaminhamento TCP 80→80 e TCP 443→443 no router. Usa o IPv4 público no campo Gateway da PWA. O serviço continua interno em 127.0.0.1:8443. O router/ISP precisa de IPv4 público e, para usar esse mesmo endpoint enquanto estás na rede local, NAT loopback. Consulta `docs/REMOTE_ACCESS_AND_TLS.md`.

## Limite da validação

A construção do `.deb` em amd64 e a instalação/arranque em Debian limpo são verificações separadas. Este documento não constitui evidência de que o pacote atual foi instalado num Gateway físico. Registar a versão Debian, `dpkg --print-architecture`, o SHA-256 do `.deb`, o resultado do serviço e do health check durante um ensaio antes de declarar a instalação validada.
