"""Read-only, exact-Product-ID references compiled from the pinned Tuya Local fork."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    try:
        value = json.loads(Path(__file__).with_name("tuya_local_catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"source": {}, "records": []}
    return value if isinstance(value, dict) and isinstance(value.get("records"), list) else {"source": {}, "records": []}


@lru_cache(maxsize=1)
def profiles_by_product_id() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    source = catalog().get("source", {})
    for record in catalog().get("records", []):
        if not isinstance(record, dict):
            continue
        for product in record.get("products", []):
            if not isinstance(product, dict) or not isinstance(product.get("id"), str):
                continue
            product_id = product["id"]
            rows = [dict(row, confidence="COMMUNITY_REFERENCE", validation_status="suggestion_only",
                         write_supported=False, source=f"{source.get('repository')}@{source.get('commit')}")
                    for row in record.get("dps", []) if isinstance(row, dict)]
            result[product_id] = {"product_id": product_id, "product_name": product.get("model") or record.get("product_name") or record.get("name"),
                                  "manufacturer": product.get("manufacturer") or "Tuya", "category": record.get("category") or "breaker",
                                  "source": source, "config": record.get("config"), "dps": rows}
    return result


def product_schema(profile: dict[str, Any]) -> dict[str, Any]:
    return {"protocol": "tuya", "manufacturer": profile.get("manufacturer", "Tuya"),
            "product_name": profile.get("product_name"), "category": profile.get("category", "breaker"),
            "device_kind": "energy_monitor_switch", "schema_source": "TUYA_LOCAL_EXACT_PRODUCT_REFERENCE",
            "reference_source": profile.get("source", {}).get("repository"),
            "reference_commit": profile.get("source", {}).get("commit"),
            "reference_license": profile.get("source", {}).get("license"),
            "functions": [], "status_spec": [], "dps_profile": {"product_id": profile.get("product_id"),
            "dps": [], "reference_dps": profile.get("dps", [])}}
