# Tesla Fleet: relay público na Oracle

## O que fica onde

- A Tesla chama apenas o endpoint HTTPS do relay na VM Oracle.
- O relay guarda o código OAuth temporariamente em memória, até dez minutos.
- O Gateway de casa inicia a sessão e consulta o relay por HTTPS de saída. Não é preciso abrir portas no modem nem expor o Gateway.
- O Gateway troca o código diretamente com a Tesla e guarda o refresh token no seu ficheiro de configuração privado. O relay nunca recebe credenciais Tesla, tokens ou dados do veículo.
- A PWA não guarda o segredo de partilha do relay. O Owner introdu-lo uma vez; o Gateway valida-o e limpa o campo.

## Antes de criar a VM

1. Regista um domínio que controles. Cria um registo DNS `A` para o IPv4 público da VM, sem proxy/CDN à frente. O endereço tem de resolver publicamente antes da emissão do certificado.
2. Na Tesla Developer, o campo Redirect URI tem de ser um endpoint HTTPS no domínio do relay. O portal pode aplicar validações próprias ao domínio; a documentação não garante que aceite um domínio específico. Confirma a validação no portal antes de contar com a integração.
3. A VCN precisa de sub-rede pública, rota `0.0.0.0/0` para Internet Gateway e IPv4 público na VM. A lista de segurança deve permitir TCP 80 e 443 de entrada. Mantém TCP 22 limitado ao IPv4 público do computador administrador. A firewall Ubuntu do instalador permite apenas SSH, HTTP e HTTPS.

O TCP 80 é usado pelo desafio HTTP do Let's Encrypt para emitir e renovar o certificado. O serviço de callback serve HTTPS diretamente com Uvicorn; não coloques Nginx, Cloudflare Proxy nem outro proxy inverso à frente.

## Instalação automatizada na Ubuntu 24.04

Leva o diretório `tools/tesla_oauth_relay` para a VM e executa, como root, uma vez:

```bash
sudo bash install-ubuntu.sh <dominio-publico> <email-para-renovacao>
```

O instalador instala dependências, confirma DNS, emite o certificado, cria uma conta Linux sem login, instala o serviço restrito, ativa a firewall local, configura renovação automática e verifica HTTPS localmente. Se DNS ou emissão TLS falharem, corrige a causa e volta a executar o mesmo comando. O instalador reutiliza a chave já criada numa repetição segura.

No Oracle Cloud, confirma também que as regras de entrada da Security List/NSG permitem TCP 80 e 443. Uma regra de firewall Ubuntu não abre a Security List da Oracle.

O instalador cria uma chave aleatória de 256 bits em `/root/solarminer-tesla-relay-api-key`, com permissão apenas de root. Depois de confirmar a instalação, copia essa chave localmente para Owner → Equipamentos → Tesla Fleet → “Ligação segura à VM pública”. Introduz o endereço `https://<dominio>` e toca em “Guardar e testar relay”. O Gateway confirma a chave com um endpoint autenticado e não a devolve à PWA. Não a coloques no portal Tesla, num repositório ou numa mensagem.

## Tesla Developer e autorização

1. Na aplicação Tesla, ativa o fluxo **Authorization Code**.
2. Em **Allowed Origin**, copia a origem HTTPS exata da PWA apresentada pelo guia, sem caminho.
3. Em **Redirect URI**, copia o callback HTTPS apresentado pela PWA depois de o relay passar o teste. Não abras o callback manualmente; só a Tesla lhe envia o código.
4. Pede apenas `openid`, `offline_access` e `vehicle_device_data` para o fluxo de leitura atual. A aplicação usa o mesmo Redirect URI na autorização e na troca do código.
5. No SolarMiner, preenche Client ID e Client Secret e toca em “Autorizar com Tesla”. O segredo só transita pela ligação autenticada até ao Gateway e não é persistido. Escolhe o veículo devolvido pela Tesla e guarda a seleção.

## Recuperação de falhas

- **A origem não resolve / certificado não emite:** confirma o registo A, o IPv4 público da VM e a regra Oracle TCP 80. Não tentes OAuth ainda.
- **Relay não responde:** confirma a regra Oracle TCP 443 e `systemctl status solarminer-tesla-relay` na VM.
- **Chave rejeitada:** volta a copiar a chave de `/root/solarminer-tesla-relay-api-key`; não é o Client Secret Tesla.
- **Pedido expirado:** fecha a janela e começa uma autorização nova na PWA. O estado OAuth é temporário, tem validade de dez minutos e não pode ser reutilizado.
- **Redirect URI inválido no portal:** não inventes outro callback. Confirma que está registado exatamente o endereço mostrado pela PWA e verifica a mensagem da Tesla; a aceitação do domínio é validada pelo próprio portal.
- **Tesla não devolve veículo:** verifica aprovação da aplicação, região, autorização do proprietário e se o veículo pertence à conta selecionada.

O relay é apenas para OAuth e leitura. A API atual não envia comandos ao carro. Comandos de carregamento exigem `vehicle_charging_cmds` e uma chave virtual/protocolo de comandos Tesla; essas etapas não são simuladas pelo relay.
