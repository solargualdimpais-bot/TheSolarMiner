# Gateway 0.6.186

- Tesla Fleet: fluxo OAuth Authorization Code com estado aleatório de uso único.
- Client Secret mantido apenas em memória durante a troca do código; refresh token guardado no Gateway.
- Callback derivado da origem HTTPS e envio à PWA apenas de dados seguros do veículo.
