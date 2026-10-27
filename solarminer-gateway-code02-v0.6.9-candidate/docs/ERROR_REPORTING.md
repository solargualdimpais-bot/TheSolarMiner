# Envio automático de diagnósticos privados

O Gateway mantém em fila local os erros da aplicação e respostas HTTP 5xx e, de hora a hora, tenta criar um relatório no repositório privado `solargualdimpais-bot/TheSolarMiner-Diagnostics`. Mesmo sem erros na fila da aplicação, o serviço horário verifica os logs allowlisted para enviar falhas novas do Gateway, atualizador, recuperação, Nginx e Tailscale; guarda uma impressão digital para não repetir a mesma falha em cada ciclo. Cada relatório inclui até 50 eventos sanitizados e um instantâneo limitado de até 80 linhas, obtido pelo broker privilegiado. Se a rede, o Gateway auxiliar ou o GitHub estiver indisponível, a fila mantém-se para nova tentativa. A fila tem limite de 2 MiB e elimina os registos mais antigos se ficar cheia.

## Privacidade

As issues e diagnósticos só são visíveis a quem tem acesso ao repositório privado. Antes do envio, o Gateway remove credenciais reconhecidas, tokens GitHub, URLs, endereços IPv4/IPv6, endereços MAC, nomes de utilizador e caminhos locais. O snapshot é limitado a 80 linhas recentes dos serviços allowlisted; não inclui pedidos HTTP, conteúdo da base de dados, comandos do utilizador ou identidade do Gateway. A fila e o token ficam em `/var/lib/solarminer`, acessíveis apenas à conta do serviço. O token nunca é devolvido à PWA nem incluído no relatório.

Esta sanitização reduz a exposição de dados, mas mensagens novas podem conter dados que não sejam reconhecidos pelos filtros. Como o repositório é público, revê a informação sanitizada antes de ativar o envio, conforme a política de privacidade do proprietário.

## Ativar o envio

Cria uma Fine-grained Personal Access Token apenas para `TheSolarMiner-Diagnostics`, com `Issues: Read and write`; não concedas `Contents` nem permissões de administração. Consulta a [documentação oficial do endpoint Create an issue](https://docs.github.com/en/rest/issues/issues#create-an-issue). Na PWA, usa Owner → Gateway → Relatórios automáticos e guarda o token no Gateway. O campo é limpo depois do envio e o endpoint devolve apenas o estado configurado. O próximo envio ocorre no ciclo horário; a fila não é apagada quando a configuração é removida.

Para desativar, usa “Desativar envio” no mesmo painel. Sem token, os relatórios permanecem localmente. A configuração também pode ser feita localmente como root com `solarminer-gateway github-error-token`.

## Ver estado local

Como `root`, usa `systemctl status solarminer-error-report.timer`, `systemctl status solarminer-error-report.service` e `journalctl -u solarminer-error-report.service`. Uma falha de rede ou API deixa os registos na fila e não interrompe o Gateway.

O snapshot inclui serviços e logs allowlisted obtidos pelo broker, inclusive atualização e recuperação. Não inclui logs do kernel, APT, conteúdo da base de dados nem informação anterior à retenção do journal. Se o Gateway estiver desligado, sem rede ou não conseguir executar o timer, não consegue enviar os seus próprios diagnósticos; o envio depende de a máquina voltar a comunicar e do token estar configurado.
