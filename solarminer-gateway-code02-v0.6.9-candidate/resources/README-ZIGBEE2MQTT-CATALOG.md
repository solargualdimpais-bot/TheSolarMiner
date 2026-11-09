# Catálogo Zigbee2MQTT para o SolarMiner

`zigbee2mqtt-device-catalog.json` é uma fotografia estruturada dos documentos oficiais por modelo em `Koenkk/zigbee2mqtt.io`, no commit indicado no próprio ficheiro. O gerador `build_zigbee2mqtt_catalog.py` permite refazer a fotografia a partir de uma cópia local de `docs/devices/`.

## Conteúdo

- 5.445 perfis documentados, com fabricante, modelo, resumo de capacidades e URL de origem.
- 35.773 registos de capacidades com tipo, propriedades, suporte documentado de `/get` e `/set`, unidades, limites, valores enumerados e exemplos MQTT encontrados nas páginas.
- 17.470 opções de configuração específicas por modelo.
- A página upstream reportava 5.868 dispositivos suportados nessa revisão. Esse número não corresponde a páginas Markdown distintas; o catálogo conserva ambos os números em campos separados em vez de inventar os perfis que não têm página individual.

## Compatibilidade com o catálogo de equipamentos SolarMiner

Os perfis são importados para a mesma SQLite e tabela-mestre `smart_product_catalog` que já contém Tuya e Shelly. A chave composta `manufacturer + protocol + product_code` mantém modelos iguais de protocolos diferentes separados; os detalhes ricos ficam em `smart_product_profile_details`, ligados pela mesma chave. Cada perfil usa `protocol: "zigbee2mqtt"`, `manufacturer` e `product_code` igual ao modelo Zigbee documentado. As capacidades Zigbee são propriedades do conversor (`property`, `type`, `get_supported`, `reports_state`, `set_supported`); não são DPS Tuya. Assim, o mesmo sistema genérico de fabricante/modelo/cartão pode ser reutilizado sem misturar um mapa DPS Tuya com as propriedades de um equipamento Zigbee.

Os registos Tuya existentes não são migrados nem reescritos pela importação Zigbee. O mapa DPS mantém-se no esquema Tuya atual; os outros protocolos usam perfis próprios sob a mesma base central. A importação é repetível e só volta a atualizar o catálogo quando muda a revisão da fonte. Este ficheiro é uma base de metadados para futuras inserções. Por si só não emparelha, lê nem controla equipamentos; isso requer um coordenador Zigbee e integração MQTT/Zigbee2MQTT no Gateway.

## Fonte e licença

Fonte: [Koenkk/zigbee2mqtt.io](https://github.com/Koenkk/zigbee2mqtt.io), páginas geradas a partir de `zigbee-herdsman-converters`. A documentação desse repositório está sob GPL-3.0; a licença original foi incluída em `ZIGBEE2MQTT-LICENSE.txt`. Cada perfil mantém o link da página de origem. O catálogo deve continuar acompanhado desta atribuição e licença.
