#!/usr/bin/env python3
"""Compile a full, exact-PID Tuya Local device reference catalog.

This tool reads YAML as data with safe_load; it never imports or executes the
source integration. PyYAML is needed only when refreshing the bundled JSON.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PINNED_COMMIT = "75019afbada5210f8752c6476b50c2c1a3fc74fe"
def _representation(entity: dict[str, Any], dp: dict[str, Any]) -> dict[str, Any]:
    mapping = dp.get("mapping") if isinstance(dp.get("mapping"), list) else []
    scales = [row.get("scale") for row in mapping if isinstance(row, dict) and "scale" in row]
    return {key: value for key, value in {
        "entity_type": entity.get("entity"), "entity_name": entity.get("translation_key") or entity.get("name") or dp.get("name"),
        "entity_class": entity.get("class"), "data_type": dp.get("type"), "unit": dp.get("unit"),
        "scale_divisor": scales[0] if scales and len(set(map(str, scales))) == 1 else None,
        "mapping": mapping or None, "range": dp.get("range"), "step": dp.get("step"),
        "mask": dp.get("mask"), "format": dp.get("format"), "endianness": dp.get("endianness"),
        "mask_signed": dp.get("mask_signed"), "optional": bool(dp.get("optional")),
        "persist": dp.get("persist"), "force": bool(dp.get("force")), "readonly": dp.get("readonly"),
    }.items() if value is not None}


def compile_catalog(source_root: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("Install PyYAML in the refresh environment to compile Tuya Local YAML") from exc
    records: list[dict[str, Any]] = []
    for path in sorted((source_root / "custom_components/tuya_local/devices").rglob("*.yaml")):
        try:
            config = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(config, dict):
            continue
        products = [row for row in config.get("products", []) if isinstance(row, dict)
                    and isinstance(row.get("id"), str) and row.get("id")]
        if not products:
            continue
        grouped: dict[int, list[dict[str, Any]]] = {}
        for entity in config.get("entities", []) if isinstance(config.get("entities"), list) else []:
            if not isinstance(entity, dict):
                continue
            for dp in entity.get("dps", []) if isinstance(entity.get("dps"), list) else []:
                if not isinstance(dp, dict) or isinstance(dp.get("id"), bool):
                    continue
                try:
                    dps_id = int(dp.get("id"))
                except (TypeError, ValueError):
                    continue
                if not 1 <= dps_id <= 65535:
                    continue
                grouped.setdefault(dps_id, []).append(_representation(entity, dp))
        dps_rows = []
        for dps_id, representations in sorted(grouped.items()):
            units = {str(row.get("unit") or "") for row in representations}
            types = {str(row.get("data_type") or "unknown") for row in representations}
            names = sorted({str(row.get("entity_name") or "") for row in representations if row.get("entity_name")})
            one = representations[0] if len(representations) == 1 else {}
            label = names[0] if len(names) == 1 else ", ".join(names) if names else f"DPS {dps_id}"
            row = {"id": dps_id, "name": label, "entity_name": label,
                   "type": next(iter(types)) if len(types) == 1 else "composite",
                   "unit": next(iter(units)) if len(units) == 1 and next(iter(units)) else None,
                   "read_supported": True, "write_supported": False,
                   "source": "fran122157/tuya-local", "representations": representations}
            if one.get("range") is not None:
                row["range"] = one["range"]
            if one.get("scale_divisor") is not None:
                row["scale"] = one["scale_divisor"]
            dps_rows.append(row)
        product = products[0]
        records.append({"config": path.name, "name": config.get("name") or product.get("model") or path.stem,
                        "products": products, "dps": dps_rows,
                        "product_name": product.get("model") or config.get("name") or path.stem,
                        "category": str(config.get("category") or "")})
    configs_total = len(list((source_root / "custom_components/tuya_local/devices").rglob("*.yaml")))
    return {"schema_version": 1, "source": {
        "repository": "fran122157/tuya-local", "upstream_project": "make-all/tuya-local",
        "url": f"https://github.com/fran122157/tuya-local/tree/{PINNED_COMMIT}/custom_components/tuya_local/devices",
        "commit": PINNED_COMMIT, "license": "MIT", "license_file": "third_party/tuya-local/LICENSE.md",
        "configs_total": configs_total, "configs_compiled": len(records),
        "configs_skipped": max(0, configs_total - len(records)),
        "notice": "All usable device YAML references are indexed by exact Product ID; source YAML is parsed as data only. Commands remain disabled."},
        "records": records}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path, help="Checkout of the pinned tuya-local repository")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = compile_catalog(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    product_ids = {str(product.get("id")) for record in catalog["records"] for product in record["products"]}
    print(f"compiled {len(catalog['records'])} profiles and {len(product_ids)} exact Product IDs")


if __name__ == "__main__":
    main()
