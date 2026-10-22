# Primeiro Owner por palavra-passe local

## Instalação nova

O instalador USB valida e instala o pacote assinado. No fim, abre o comando local `solarminer-gateway owner-password` e pede duas vezes uma palavra-passe entre 8 e 128 caracteres. O terminal mostra os caracteres enquanto são escritos. A palavra-passe não é enviada para logs nem guardada em texto simples; o Gateway guarda temporariamente apenas um verificador Argon2id.

No iPhone, abre a PWA, introduz o endpoint HTTPS do Gateway e escolhe **Testar endpoint**. Se o Gateway ainda não tiver Owner, a PWA abre a janela **Registar este telemóvel como Owner**. Introduz o nome e a mesma palavra-passe definida na consola local. O verificador temporário de configuração é consumido uma única vez; o Owner e o dispositivo são registados numa transação, e a palavra-passe passa a ser o verificador de acesso da conta Owner. A chave de recuperação é apresentada apenas nessa resposta. Guarda-a offline.

O fluxo continua a exigir HTTPS validado pelo browser, origem PWA permitida e prova Ed25519 da chave criada no dispositivo. A fingerprint do Gateway é verificada automaticamente através da ligação TLS validada, sem ser necessário copiar uma sequência de 64 caracteres. O Gateway não usa o MAC do telemóvel como prova de identidade.

## Ligações seguintes

A PWA guarda a chave privada Ed25519 como `CryptoKey` não exportável no IndexedDB do browser. Ao reabrir a PWA, o endpoint guardado é testado e o Gateway emite uma sessão temporária apenas após uma assinatura nova dessa chave (`POST /api/v1/auth/device-login`). A palavra-passe não volta a ser pedida. A chave privada não sai do browser.

Apagar os dados do Safari/PWA, mudar de browser ou trocar de telemóvel também apaga/perde a identidade local. O primeiro Owner já não pode ser registado de novo; usa a recuperação autorizada do Owner ou associa outro dispositivo através do procedimento administrativo suportado.

## Limites e tratamento de erro

- A senha inicial tem de ser definida no próprio Gateway como root; o bootstrap remoto sem essa configuração é recusado.
- Cinco tentativas de bootstrap por endereço de origem em quinze minutos são permitidas. Depois disso, o Gateway responde `429 bootstrap_attempts_limited`.
- O verificador temporário é apagado na mesma transação que cria o Owner. Não existe senha universal ou valor predefinido.
- O endpoint só permite um Owner inicial. A configuração de Owner não cria permissões para outros utilizadores.
- Se o certificado HTTPS não for confiável ou não corresponder ao endpoint, o browser bloqueia a ligação; a PWA não contorna TLS.
