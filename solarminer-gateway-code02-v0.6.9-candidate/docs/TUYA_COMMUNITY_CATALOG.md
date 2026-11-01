# Tuya community DPS catalogue

The Gateway bundles a generated, read-only reference snapshot from
[`make-all/tuya-local`](https://github.com/make-all/tuya-local), licensed MIT.
The snapshot is pinned to commit `70cab728f3fed1f3c6ca8aa0b892aae471839769`
and stored in `src/solarminer_gateway/tuya_community_catalog.json`.

It contains 1,778 device configurations, 1,571 configurations with one or more
Product IDs, and 29,206 DPS mapping entries. One upstream YAML file could not be
parsed by the importer and is excluded. Each retained entry preserves the
upstream configuration name, Product IDs, manufacturer/model metadata, DP ID,
type, label, entity, unit, range, scale, and value mapping where supplied.

The Gateway uses these entries only as community hints when the device's exact
Product ID matches. It does not treat them as Tuya's official schema, does not
infer command write permissions from them, and will not apply a conflicting
mapping. The live Tuya product schema or an explicit owner mapping remains the
authority for writable commands. Product family names and matching DP numbers
alone are not sufficient.

The owner-provided QCCDZ EV notes are maintained separately in the registry.
An exact Product ID/schema mapping takes precedence when it conflicts; for
example, the bundled Absina Wallbox profile identifies DP 18 as factory reset,
so it must not be presented as the charger switch for that exact product unless
its current Tuya schema explicitly maps it to `switch`.

The same catalogue also includes eight generic protocol/family templates (85
DPS rows) from [`DzurisHome/Tuya-Data-Points`](https://github.com/DzurisHome/Tuya-Data-Points),
pinned to commit `efe4058b40f4b0ff82c9251a47a1221e825d6c16`. These templates have
no Product IDs and are reference material only; the Gateway does not apply them
to devices automatically. Its MIT license is included in
`third_party/tuya-data-points/LICENSE` and in the Debian package documentation.

The smaller `dulfer/localtuya-device-datapoints` repository was reviewed as an
additional reference, but it has no declared repository license, so its data is
not redistributed in this package.

The source repository's MIT license is included at
`third_party/tuya-local/LICENSE.md` and in the Debian package documentation.
