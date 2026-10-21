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
sh /media/<utilizador>/<PEN>/install-from-usb.sh
```

O pacote de entrega oficial `solarminer-gateway-usb-installer_0.6.9_amd64.zip` inclui o script, o pacote Debian AMD64, o manifesto Ed25519 e a chave pública de release derivada no workflow da chave privada mantida como segredo de GitHub Actions. Não copies a chave privada para a pen ou Gateway.

O instalador não pede URLs, hashes nem impressão digital: usa o repositório oficial `https://github.com/solargualdimpais-bot/TheSolarMiner`. Antes de instalar o SolarMiner, valida no Gateway Debian 13 ou posterior, AMD64 e Python 3.13 ou posterior, o esquema/versão/origem do manifesto, a assinatura Ed25519, o tamanho e SHA-256 do pacote e a arquitetura Debian. Se a assinatura ou qualquer validação falhar, termina sem instalar o SolarMiner. Depois instala o pacote e dependências apenas dos repositórios Debian, provisiona a chave pública e a allowlist oficial, ativa o serviço e o timer diário e verifica o health endpoint local. Em falha, tenta remover o pacote e restaurar a configuração inicial; consulta `/var/log/solarminer-first-install.log`.

É necessária ligação à Internet durante a instalação para atualizar o APT e instalar dependências Debian. O primeiro arranque do serviço não cria automaticamente a conta Owner: conclui o bootstrap inicial e o emparelhamento seguindo `A2_OWNER_RECOVERY.md` e `TLS_TRUST.md`. A instalação não atualiza firmware no ato da inserção da pen; atualizações futuras são verificadas diariamente, mas continuam a exigir ação explícita do Owner para aplicação.

O instalador destina-se à instalação inicial num Debian limpo. Não o uses para atualizar um Gateway existente; nesse caso usa o fluxo de atualização assinado da PWA e o rollback documentado.

## Instalação sem pen USB

É tecnicamente possível depois de Debian estar instalado e ter acesso à Internet: o Gateway pode obter o pacote de um release público HTTPS. Para o fazer com segurança, é necessário publicar um pacote `.deb` AMD64 e manifesto assinado, provisionar a chave pública por uma origem independente e conhecer a sua impressão SHA-256. O repositório atualmente não tem releases GitHub publicados; por isso não existe ainda um artefacto remoto que este método possa instalar.

Não usar `curl | sh` para executar código não verificado. A instalação remota tem de verificar a assinatura Ed25519 e o hash do pacote antes de chamar `dpkg`; não deve fazer `git pull`, executar scripts do release ou instalar dependências fornecidas pelo repositório.

## Limite da validação

A construção do `.deb` em amd64 e a instalação/arranque em Debian limpo são verificações separadas. Este documento não constitui evidência de que o pacote atual foi instalado num Gateway físico. Registar a versão Debian, `dpkg --print-architecture`, o SHA-256 do `.deb`, o resultado do serviço e do health check durante um ensaio antes de declarar a instalação validada.
