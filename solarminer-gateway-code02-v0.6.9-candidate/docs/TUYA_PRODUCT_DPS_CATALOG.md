# Tuya product and DPS catalog

## How the catalog is built

The Gateway is the canonical catalog owner. During a Tuya inventory sync it retrieves each device's own specification and stores it under the exact Tuya Product ID. A reusable product entry contains the Product ID, category code, product name, classified device family, channel count, function/status schema, interpreted DPS list, registry version, source and confidence. The current live DPS values remain on the device record and are not copied into the reusable catalog.

Category function and status schemas are stored separately as category references. They are never treated as proof that every product in a category has identical functions. If the device specification is missing, a cached schema is reused only for the same Product ID; otherwise the unrecognized DPS remain unknown and read-only until a reliable mapping exists.

The PWA receives the device's DPS interpretation and product identity from the Gateway. It resolves a channel state by the configured local map, then the device specification, then the exact product profile. The Gateway uses the same local map and device schema for reads and commands. Product/category guesses do not authorize a command.

## Semantic references and category variation

The reusable catalog now separates a semantic concept (for example, switch, daily energy, phase-A voltage) from a product's numeric DP ID. Tuya's official device-specification API supplies the product category plus its own function and status lists; each entry carries the DP ID, code, data type, and value properties. The engine therefore joins a documented category concept to a live DP only through that exact product schema. It does not assign a category-wide numeric DP number.

For the official `dlq` circuit-breaker category, reference concepts include `switch`, `daily_energy`, `month_energy`, `total_ele`, `total_forward_energy`, phase voltage/current/active-power readings, `fault`, and alarm configuration. For `kg` switches, `cz` sockets, and `pc` power strips, references include single/multichannel switches, countdowns, and the standard metering codes. Curtain and lighting categories also have category-specific control vocabularies. Some readings are raw payloads rather than scalars; raw daily-energy data is not converted into a made-up number. The actual product may expose only a subset. “Today” is shown only when the product schema declares an appropriate daily reading; a cumulative total remains cumulative.

Equivalent concepts with different names can share a normalized semantic label only when the category and schema metadata support the match. The numeric DP ID remains product-scoped. A semantic match does not imply that the DP is writable: commands still require that the exact device function schema or an explicit owner mapping authorizes that code and value.

The documented Tuya category instruction set for `dlq` provides function codes and descriptions, while product specifications provide the product's DP IDs and actual functions. Tuya also notes that category-standard functions can be a subset of a product's capabilities. Consequently, the static reference is a vocabulary and interpretation aid, not an exhaustive worldwide device database.

## Product/channel identity

- **Product ID** is the exact reusable product key. Category is retained separately as Tuya's product type code.
- Channel count comes from declared Boolean switch functions and is stored with the product profile. A KG product may therefore be one, two, or six channels depending on its own schema.
- Multi-channel KG mapping is restricted to the six-channel signature. The documented/owner-provided profile covers channels 1–6, the global switch, power-on behavior, global I/O setting and pair modes. Pair modes are applied only when that device's schema declares them.
- The QCCDZ EV switch profile stays scoped to category QCCDZ. It does not apply to QLD or unrelated products.
- Unknown DPS are preserved with their raw reading and an unknown semantic label. Unknown DPS are not made writable by a category match.

## Scope

Tuya's product space has no universal DPS table. The catalog grows from the products in the connected Tuya project and the specification API for each device. It is bounded to 200 exact Product IDs and 512 KiB to keep the Gateway configuration and API response bounded; older cached products can be re-fetched during a later sync. This is an extensible account-specific catalog, not a claim to enumerate every Tuya product worldwide.

## Official references

- [Get device specification attributes](https://developer.tuya.com/en/docs/cloud/60314b4cb7?id=Kawtt7v5aqfq0) — returns category, device functions and status.
- [Tuya Device DPs](https://developer.tuya.com/en/docs/iot/device-function-point?id=Ka6y8bi672n1s) — defines DP identifiers, names and data types.
- [Tuya Product Function Definition](https://developer.tuya.com/en/docs/iot/product-function-definition?id=K9tp14pijmeyh) — describes product-specific function definitions and DP IDs.
- [Tuya standard instruction set for circuit breakers (`dlq`)](https://developer.tuya.com/en/docs/iot/f?id=Kb0kihuxmtj62) — publishes category function codes such as `switch` and `daily_energy`.
- [Tuya standard status set for circuit breakers (`dlq`)](https://developer.tuya.com/en/docs/iot/s?id=Kb0kikd1lya17) — lists report-only phase measurements, cumulative energy, daily/monthly energy and fault status.
- [Tuya product categories](https://developer.tuya.com/en/docs/connect-subdevices-to-gateways/supported-device?id=Kd1fa3alubr6j) — explains category-based standards and that supported functions vary by product.
- [Tuya standard functions for switches, sockets, and power strips](https://developer.tuya.com/en/docs/iot/fkg?id=K9gf7o3qbbklt) — lists category codes for switches and countdowns.
- [Tuya standard functions for curtain controllers](https://developer.tuya.com/en/docs/iot/f?id=K9gf46o5mtfyc) — lists curtain commands, position, modes, and legacy variants.
- [Tuya standard instruction-set overview](https://developer.tuya.com/en/docs/iot/standarddescription?id=K9i5ql6waswzq) — states that category functions are a superset and a product supports a subset.
