# SolarMiner Gateway 0.6.34

## Controlo local da mineradora Braiins OS

- Acrescenta API Gateway exclusiva do Owner para definir alvo de potência e pausar, parar ou iniciar a mineração.
- Usa a REST API pública do Braiins OS, autentica no próprio Gateway e guarda as credenciais apenas no ficheiro privado de integrações.
- Mantém CGMiner 4028 em modo somente leitura. A PWA pede confirmação individual para cada ação e mostra o resultado confirmado pelo firmware.
- Documenta que a integração REST requer Braiins OS 25.07 ou posterior. Firmware anterior recebe uma mensagem de incompatibilidade; não há fallback para comandos CGMiner de escrita.
- Limita o alvo a 2900 W, próximo da especificação de 2760 W ±5% do Antminer S19K Pro; a instalação elétrica e o PSU continuam a determinar o valor adequado.

## Diagnóstico Deye

- A resposta Modbus identifica separadamente a conectividade TCP e o timeout de FC43/FC03.
- Explicita que credenciais da página web do inversor não são credenciais Modbus TCP e indica verificar Link 2 e Unit ID.
- Não adivinha mapa de registos nem escreve no inversor.

## Limites

- O Gateway não foi validado com um Antminer físico nesta alteração. O firmware, as credenciais locais e a disponibilidade da API REST têm de ser confirmados no próprio dispositivo.
- A ligação HTTP da API local atravessa a LAN sem TLS; usa apenas numa rede privada confiável.
