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

O pacote de entrega oficial `solarminer-gateway-usb-installer_0.6.15_amd64.zip` inclui o instalador inicial, a ferramenta de reparação para Gateway existente, pacotes de rollback assinados 0.6.10–0.6.14, o pacote Debian AMD64, o manifesto Ed25519 e a chave pública de release derivada no workflow da chave privada mantida como segredo de GitHub Actions. Não copies a chave privada para a pen ou Gateway.

O instalador não pede URLs, hashes nem impressão digital: usa o repositório oficial `https://github.com/solargualdimpais-bot/TheSolarMiner`. Antes de instalar o SolarMiner, valida no Gateway Debian 13 ou posterior, AMD64 e Python 3.13 ou posterior, o esquema/versão/origem do manifesto, a assinatura Ed25519, o tamanho e SHA-256 do pacote e a arquitetura Debian. Se a assinatura ou qualquer validação falhar, termina sem instalar o SolarMiner. Depois instala o pacote e dependências apenas dos repositórios Debian, provisiona a chave pública e a allowlist oficial, ativa o serviço e o timer diário e verifica o health endpoint local. Em falha, tenta remover o pacote e restaurar a configuração inicial; consulta `/var/log/solarminer-first-install.log`.

É necessária ligação à Internet durante a instalação para atualizar o APT e instalar dependências Debian. O instalador provisiona uma identidade Ed25519 estável por Gateway. A conta Owner tem de ser criada separadamente depois de publicares a PWA integrada em GitHub Pages e preparares confiança TLS no browser; segue PWA_GITHUB_PAGES.md. O primeiro Owner exige token local curto e confirmação manual da fingerprint. A instalação não atualiza firmware automaticamente; atualizações são verificadas diariamente, mas continuam a exigir ação explícita do Owner para aplicação.

O instalador inicial destina-se a um Debian limpo. Para reparar um Gateway 0.6.10–0.6.14 preso em `RECOVERY_BLOCKED`, usa o script específico do bundle; não forces o updater online. Extrai os ficheiros do ZIP, monta a pen em `/mnt/solarminer-usb` e executa como `root` `sh /mnt/solarminer-usb/repair-existing-from-usb.sh`. O script valida manifesto, assinatura com a chave já confiada, hash, tamanho, versão e arquitetura, cria backup SQLite, ativa a release assinada e tenta reinstalar a versão anterior assinada, repor a release e restaurar a base de dados se o health check falhar. Log: `/var/log/solarminer-usb-repair.log`; backups: `/var/lib/solarminer/backups/`.

## Configuração inicial Owner e publicação PWA

O workflow pwa-pages.yml publica a cópia integrada com a API em https://solargualdimpais-bot.github.io/TheSolarMiner/ depois de o administrador selecionar GitHub Actions em Settings → Pages → Build and deployment → Source. Usa a aplicação ligada ao Gateway; o diretório isolado da candidata PWA permanece um artefacto visual sem funções Gateway.

Depois de o serviço estar instalado, se o token inicial tiver expirado, inicia sessão como root e executa, um por vez: `systemctl stop solarminer-gateway.service`; `solarminer-gateway bootstrap-token`; `systemctl start solarminer-gateway.service`. O executável inclui o caminho correto dos módulos Python. O comando imprime um token de utilização única e a fingerprint da identidade Ed25519 do Gateway. Abre a PWA, introduz o endpoint HTTPS com SAN válido, confirma a fingerprint, usa o token e cria o Owner. O procedimento completo, incluindo confiança TLS e limites da API física, está em PWA_GITHUB_PAGES.md.

Após a reparação USB do Gateway existente, executa como `root` `systemctl stop solarminer-gateway.service`, `solarminer-gateway bootstrap-token` e `systemctl start solarminer-gateway.service`, um por vez. Não uses `curl | sh`, `git pull` nem código fonte como atualizador.

## Limite da validação

A construção do `.deb` em amd64 e a instalação/arranque em Debian limpo são verificações separadas. Este documento não constitui evidência de que o pacote atual foi instalado num Gateway físico. Registar a versão Debian, `dpkg --print-architecture`, o SHA-256 do `.deb`, o resultado do serviço e do health check durante um ensaio antes de declarar a instalação validada.
