# Envio automático de erros para GitHub

Desde a versão 0.6.33, o processo Python do Gateway guarda localmente erros de aplicação e respostas HTTP 5xx, incluindo falhas registadas nas consultas de hardware e na verificação de atualização, e tenta criar uma issue no repositório público `solargualdimpais-bot/TheSolarMiner` de hora a hora. Se a rede ou o GitHub estiver indisponível, a fila permanece no Gateway e será novamente tentada. Os relatórios são enviados em lotes de até 100 registos. A fila local tem limite de 2 MiB; se permanecer cheia durante uma indisponibilidade prolongada, elimina os registos mais antigos para proteger o disco.

## Privacidade

As issues são públicas. O Gateway envia apenas hora UTC, nível, nome do componente, tipo da exceção e mensagem sanitizada. Remove URLs, credenciais reconhecidas, endereços IPv4/IPv6, endereços MAC, nomes de utilizador e caminhos locais. Não envia ficheiros de log completos, tracebacks, pedidos HTTP, conteúdo da base de dados ou identidade do Gateway. A fila local está em `/var/lib/solarminer/error-reports.ndjson`, acessível apenas à conta do serviço.

Esta sanitização reduz a exposição de dados, mas mensagens novas podem conter dados que não sejam reconhecidos pelos filtros. Como o repositório é público, revê a informação sanitizada antes de ativar o envio, conforme a política de privacidade do proprietário.

## Ativar o envio

O GitHub não permite criar issues anonimamente. É necessária uma Fine-grained Personal Access Token limitada ao repositório `TheSolarMiner` com a permissão `Issues: Read and write`; não concedas `Contents` nem permissões de administração. Consulta a [documentação oficial do endpoint Create an issue](https://docs.github.com/en/rest/issues/issues#create-an-issue).

No Gateway, como `root`, executa o comando interativo. O token é pedido duas vezes sem aparecer no ecrã e fica guardado com permissões `root:solarminer 0640`:

```sh
solarminer-gateway github-error-token
```

O token não é exposto à PWA nem escrito nos logs. O timer já está ativo; o próximo envio é tentado dentro de uma hora. Para enviar a fila imediatamente, executa `systemctl start solarminer-error-report.service` como `root`.

Sem o ficheiro de token, o serviço não envia nada e mantém a fila local. Para desativar o envio, apaga `/etc/solarminer/github-issues-token` como `root`; os relatórios locais ficam retidos.

## Ver estado local

Como `root`, usa `systemctl status solarminer-error-report.timer`, `systemctl status solarminer-error-report.service` e `journalctl -u solarminer-error-report.service`. Uma falha de rede ou API deixa os registos na fila e não interrompe o Gateway.

O relatório automático cobre erros emitidos pelo processo Python do Gateway. Falhas anteriores ao arranque do processo, logs do kernel, Nginx, APT e comandos de instalação/reparação não são enviados por este mecanismo.
