# SolarMiner CODE02 v0.6.5 + The Solar Miner PWA v0.2.0 — guia local

## Testes

Backend (a partir da raiz do código fonte):

```sh
PYTHONPATH=src pytest -q
```

PWA:

```sh
npm test
python3 -m http.server 4173 --bind 127.0.0.1
```

Abra `http://127.0.0.1:4173` para testar a interface `SIMULATED`. Este modo não chama endpoints de autenticação nem comunica com equipamentos.

## Fluxo integrado automatizado

O teste `tests/test_browser_pairing.py::test_complete_browser_pair_login_read_logout_over_local_http` provisiona um owner em banco temporário, emite um código com sessão autenticada, inicia Uvicorn em `127.0.0.1` e executa o módulo JavaScript/Web Crypto para emparelhar, iniciar sessão, consultar `GET /api/v1/energy/equipment` e terminar sessão. Não instala o pacote, não cria VM e não contacta equipamentos físicos.

```sh
PYTHONPATH=src pytest -q tests/test_browser_pairing.py
```

Este teste é uma integração do cliente JavaScript/Web Crypto contra HTTP local em loopback; não é um teste de browser gráfico nem de Safari/iOS.

## Emparelhar um browser novo

1. Tem de existir um utilizador ativo no Gateway e uma sessão real de `owner`/`admin` já autenticada noutro dispositivo.
2. Na PWA autenticada, abra **Ligação e definições**, escreva o username ativo que deve ficar associado e escolha **Gerar código de 5 minutos**.
3. Transfira o código por canal privado. Só é apresentado uma vez; expira e não pode ser reutilizado.
4. No browser novo, indique a origem do Gateway, username, password, código e MAC declarado. Escolha **Emparelhar / iniciar sessão**.
5. A PWA gera a chave privada Ed25519 não exportável localmente, envia apenas a chave pública e prova assinada, inicia sessão pelo contrato `LOGIN` existente e lê os endpoints autorizados.
6. Para terminar sessão, use **Terminar sessão**. Para associar outra chave no mesmo browser, use **Remover identidade deste browser** e peça novo código. Isto apaga a chave local; não revoga o dispositivo no servidor.

Não há refresh token; após oito horas, a PWA volta a pedir password e assinatura da chave já associada. Um dispositivo revogado precisa de uma nova associação autorizada.

## Desenvolvimento com origens separadas

Se a PWA de desenvolvimento estiver em `http://127.0.0.1:4173` e o Gateway de teste em `http://127.0.0.1:8000`, iniciar o processo de desenvolvimento do Gateway com a allowlist exata:

```sh
SOLARMINER_CORS_ORIGINS=http://127.0.0.1:4173
```

Defina-a antes de importar `solarminer_gateway.app`. Não use wildcard. O Gateway deve usar diretório e base de dados temporários para testes. A primeira criação do owner continua a exigir o processo bootstrap local existente; a PWA não contorna o bootstrap loopback-only.

## Produção / iPhone

Não use HTTP remoto nem certificados autoassinados não confiáveis. A PWA deve ser servida na mesma origem HTTPS do Gateway; o certificado tem de ser confiável no iPhone e o endereço tem de ser estável. Para acesso remoto, validar Tailscale sem abrir portas públicas. Ainda falta validar Web Crypto Ed25519 e persistência de CryptoKey no Safari/iOS, certificados, DNS, rede local e Tailscale no equipamento-alvo.
