# SolarMiner Gateway 0.6.24

- Acrescenta endpoints de configuração e leitura Owner para Deye Modbus TCP, Antminer S19K Pro e Tuya Cloud.
- Restringe os destinos LAN a endereços IP privados literais.
- Mantém Deye em registos FC03 brutos até validação do mapa de registos para o modelo/firmware exatos.
- Limita Antminer a consultas `summary`, `stats` e `devs`.
- Guarda credenciais Tuya no Gateway com permissões restritas; respostas e logs não incluem o segredo.
- A PWA Owner apresenta os formulários e inicia leituras autenticadas sem armazenar credenciais Tuya no browser.
