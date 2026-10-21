# Limitações conhecidas v0.6.8

- Não foi feita instalação no Gateway físico, nem publicação em produção.
- Não foi feita validação visual em Safari/iPhone, leitores QR nativos, permissões IndexedDB/CryptoKey ou instalação PWA em ecrã inicial.
- O endpoint `/api/v1/system/update/apply` continua HTTP 503. O módulo de troca de release e o recovery timer são primitivas preparatórias, não um pipeline completo de atualização.
- O serviço de recuperação systemd foi incluído no pacote, mas a unidade não foi ativada/testada num host real nesta sessão.
- A identidade Ed25519 do Gateway tem de ser provisionada com chaves correspondentes e permissões corretas. A PWA falha de forma fechada se o desafio não estiver disponível/for inválido.
- Bootstrap inicial só funciona localmente no próprio Gateway; o backend rejeita bootstrap remoto.
- O MAC introduzido no fluxo é declaração, não deteção física.
- A API atual não fornece série temporal de energia; a PWA não inventa histórico real.
- Favoritos, preferências PROFILE e alterações da casa permanecem locais ao browser. Não existe sincronização dessas preferências entre browsers/utilizadores.
- Automatismos e controlos de dispositivos continuam em DEMO/local. Nenhum comando físico foi implementado ou enviado.
- Fase E (integrações específicas e produção) está adiada; não foram adicionados drivers ou registos Modbus/Tuya/Shelly/ONVIF/mineradoras.
- Os testes de falha foram executados apenas em bases e diretórios temporários.
