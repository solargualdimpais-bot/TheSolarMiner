"""Bundled, offline Tuya handler references compiled from upstream AST data."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    try:
        value = json.loads(Path(__file__).with_name("tuya_device_handlers_catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"source": {}, "profiles": []}
    if not isinstance(value, dict) or not isinstance(value.get("profiles"), list):
        return {"source": {}, "profiles": []}
    return value


@lru_cache(maxsize=1)
def profiles_by_product_id() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in catalog().get("profiles", []):
        if isinstance(item, dict) and isinstance(item.get("product_id"), str):
            result[item["product_id"]] = item
    return result


def semantic_for_code(code: str) -> str:
    key = "".join(ch for ch in str(code).casefold() if ch.isalnum())
    exact = {
        "switch": "switch", "switchled": "switch", "relaystatus": "switch",
        "tempcurrent": "temperature", "temperature": "temperature",
        "humidityvalue": "humidity", "humiditycurrent": "humidity",
        "batterystate": "battery", "batteryvalue": "battery",
        "brightvalue": "brightness", "brightness": "brightness",
        "colourtemperature": "colour_temperature", "colortemperature": "colour_temperature",
        "colourdata": "colour_data", "colordata": "colour_data",
        "curvoltage": "voltage", "curvoltagea": "voltage_phase_a",
        "curcurrent": "current", "curcurrenta": "current_phase_a",
        "curpower": "power", "curactivepowera": "active_power_phase_a",
        "totalenergy": "total_energy", "forwardenergytotal": "total_energy",
        "dailyenergy": "daily_energy", "todayenergy": "daily_energy",
        "doorcontactstate": "contact", "contactstate": "contact", "motionstate": "motion",
        "occupancystatus": "occupancy", "presence": "occupancy", "illuminance": "illuminance",
        "tempcurrentf": "temperature", "tempcurrentc": "temperature", "powerstate": "switch",
    }
    return exact.get(key, "custom_label")


def _scale_divisor(value: Any) -> int | None:
    """Convert upstream Tuya decimal-place scale to the editor's divisor."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9:
        return None
    return 10 ** value


def _condition_applies(condition: Any, device: dict[str, Any], operations: list[dict[str, Any]]) -> bool:
    if not isinstance(condition, dict):
        return True
    if not condition.get("supported"):
        return False
    if condition.get("negates"):
        opposite = next((item.get("condition") for item in operations
                         if isinstance(item, dict) and isinstance(item.get("condition"), dict)
                         and item["condition"].get("id") == condition["negates"]), None)
        return not _condition_applies(opposite, device, operations) if opposite else False
    code = condition.get("status_code")
    rows = device.get("current_status") if isinstance(device.get("current_status"), list) else []
    value = next((row.get("value") for row in rows if isinstance(row, dict)
                  and row.get("code") == code), None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    target = condition.get("value")
    comparisons = {"GtE": lambda: value >= target, "Gt": lambda: value > target,
                   "LtE": lambda: value <= target, "Lt": lambda: value < target,
                   "Eq": lambda: value == target, "NotEq": lambda: value != target}
    try:
        compare = comparisons.get(condition.get("operator"))
        return bool(compare()) if compare and isinstance(target, (int, float)) else False
    except (TypeError, ValueError):
        return False


def apply_profile(device: dict[str, Any], existing_schema: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply supported exact-product definitions to an in-memory device view.

    Unknown/conditional operations remain visible in metadata and are never
    executed. Existing owner mappings and cloud metadata take precedence except
    where an upstream quirk explicitly replaces/removes the exact DP ID/code.
    """
    product_id = str(device.get("product_id") or "")
    handler = profiles_by_product_id().get(product_id)
    if not handler:
        return device, existing_schema if isinstance(existing_schema, dict) else {}
    manufacturer = str(device.get("manufacturer") or "").casefold()
    expected_manufacturer = str(handler.get("manufacturer") or "").casefold()
    if manufacturer and expected_manufacturer and manufacturer != expected_manufacturer:
        return device, existing_schema if isinstance(existing_schema, dict) else {}
    result = dict(device)
    schema = dict(existing_schema or {})
    source = catalog().get("source", {})
    operations = handler.get("operations", [])
    functions = [dict(row) for row in (result.get("functions") or schema.get("functions") or []) if isinstance(row, dict)]
    statuses = [dict(row) for row in (result.get("status_spec") or schema.get("status_spec") or []) if isinstance(row, dict)]
    current_rows = [dict(row) for row in result.get("current_status", []) if isinstance(row, dict)]

    for op in operations if isinstance(operations, list) else []:
        if not isinstance(op, dict):
            continue
        operation = op.get("op")
        if operation == "override_category" and isinstance(op.get("category"), str):
            result["category"] = op["category"]
            continue
        dp_id = op.get("id", op.get("dpid"))
        code = op.get("code", op.get("dpcode"))
        if operation and operation.startswith("add_dpid_") and isinstance(dp_id, int) and isinstance(code, str):
            if not _condition_applies(op.get("condition"), result, operations):
                continue
            row = {"code": code, "name": code.replace("_", " ").title(), "type": op.get("type"), "dp_id": dp_id,
                   "values": json.dumps(op.get("range") or {}, separators=(",", ":"), ensure_ascii=False),
                   "source": "home-assistant-libs/tuya-device-handlers"}
            for target in (statuses if op.get("read_supported") else [], functions if op.get("write_supported") else []):
                target[:] = [old for old in target if old.get("dp_id", old.get("dpId")) != dp_id]
                target.append(dict(row))
            # A declared read/write data point is also available in the
            # product-scoped DPS editor and telemetry interpretation.
            dps_profile = schema.get("dps_profile") if isinstance(schema.get("dps_profile"), dict) else {}
            dps_rows = [dict(x) for x in dps_profile.get("dps", []) if isinstance(x, dict)]
            previous = next((x for x in dps_rows if x.get("dps_id") == dp_id and
                             (x.get("confidence") == "OWNER_CUSTOM" or x.get("source") == "Gateway Product ID mapping")), None)
            dps_rows = [x for x in dps_rows if x.get("dps_id") != dp_id]
            range_data = op.get("range") if isinstance(op.get("range"), dict) else {}
            handler_row = {"dps_id": dp_id, "dpcode": code,
                             "semantic_code": semantic_for_code(code), "display_name": code.replace("_", " ").title(),
                             "data_type": str(op.get("type") or "unknown").casefold(),
                             "unit": range_data.get("unit"), "scale": _scale_divisor(range_data.get("scale")),
                             "tuya_scale": range_data.get("scale"),
                             "minimum": range_data.get("min"), "maximum": range_data.get("max"),
                             "enum_values": range_data.get("range", []),
                             "read_supported": bool(op.get("read_supported")),
                             "write_supported": bool(op.get("write_supported")),
                             "confidence": "EXACT_PRODUCT_HANDLER",
                             "source": source.get("repository", "Tuya device handler")}
            # Owner edits to a Product ID's DPS meaning are durable overrides
            # of the bundled reference, not disposable annotations.
            dps_rows.append(previous or handler_row)
            schema["dps_profile"] = {**dps_profile, "dps": sorted(dps_rows, key=lambda x: x.get("dps_id", 0))}
        elif operation == "remove_dpid" and isinstance(dp_id, int) and isinstance(code, str):
            functions[:] = [x for x in functions if not (x.get("dp_id", x.get("dpId")) == dp_id and x.get("code") == code)]
            statuses[:] = [x for x in statuses if not (x.get("dp_id", x.get("dpId")) == dp_id and x.get("code") == code)]
            current_rows[:] = [x for x in current_rows if not (x.get("dps_id", x.get("dp_id")) == dp_id and x.get("code") == code)]
        elif operation == "set_dpid_strategy_to_enum" and isinstance(dp_id, int):
            # The local reader applies these value conversions only to the
            # exact Product ID and datapoint.
            schema.setdefault("handler_value_mappings", {})[str(dp_id)] = op.get("enum_mapping_map", {})
        elif operation == "map_dpid_initial_status_values" and isinstance(dp_id, int):
            schema.setdefault("handler_initial_status_mappings", {})[str(dp_id)] = op.get("status_mapping", {})
        elif operation == "override_dpid_type_information_cls" and isinstance(dp_id, int):
            schema.setdefault("handler_type_overrides", {})[str(dp_id)] = op.get("type_information")

    result["functions"] = functions
    result["status_spec"] = statuses
    if schema.get("handler_value_mappings"):
        result["handler_value_mappings"] = schema["handler_value_mappings"]
    if schema.get("handler_initial_status_mappings"):
        result["handler_initial_status_mappings"] = schema["handler_initial_status_mappings"]
    if schema.get("handler_type_overrides"):
        result["handler_type_overrides"] = schema["handler_type_overrides"]
    if current_rows:
        result["current_status"] = current_rows
    implemented_ops = {"add_dpid_integer", "add_dpid_enum", "add_dpid_boolean", "add_dpid_bitmap",
                       "remove_dpid", "override_category", "set_dpid_strategy_to_enum",
                       "map_dpid_initial_status_values", "override_dpid_type_information_cls"}
    result["community_handler"] = {"repository": source.get("repository"), "commit": source.get("commit"),
                                    "license": source.get("license"), "description": handler.get("description"),
                                    "model": handler.get("model"), "category": result.get("category"),
                                    "operations": len(operations),
                                    "unsupported_operations": sorted({str(item.get("op")) for item in operations
                                                                      if isinstance(item, dict) and item.get("op") not in implemented_ops})}
    schema.update({"product_name": schema.get("product_name") or handler.get("model") or handler.get("description"),
                   "category": result.get("category") or schema.get("category") or handler.get("category"),
                   "schema_source": "TUYA_EXACT_PRODUCT_HANDLER",
                   "handler_source": source.get("repository"), "handler_commit": source.get("commit"),
                   "handler_license": source.get("license"), "handler_operations": operations,
                   "functions": functions, "status_spec": statuses, "cached_at": int(schema.get("cached_at") or 0)})
    return result, schema


def product_schema(handler: dict[str, Any]) -> dict[str, Any]:
    """Build a displayable/read-only catalog profile for an unconfigured PID."""
    from . import tuya_dps_registry
    dps = []
    for op in handler.get("dps", []) if isinstance(handler.get("dps"), list) else []:
        if not isinstance(op, dict): continue
        args = op.get("range", {}) if isinstance(op.get("range"), dict) else {}
        dp_id, code = op.get("id"), op.get("code")
        if not isinstance(dp_id, int) or not isinstance(code, str): continue
        dps.append({"dps_id": dp_id, "dpcode": code, "semantic_code": semantic_for_code(code),
                    "display_name": code.replace("_", " ").title(), "data_type": str(op.get("type") or "unknown").casefold(),
                    "unit": args.get("unit"), "scale": _scale_divisor(args.get("scale")), "tuya_scale": args.get("scale"), "minimum": args.get("min"),
                    "maximum": args.get("max"), "enum_values": args.get("range", []),
                    "read_supported": bool(op.get("read_supported")), "write_supported": False,
                    "confidence": "EXACT_PRODUCT_HANDLER", "source": catalog().get("source", {}).get("repository")})
    return {"protocol": "tuya", "manufacturer": "Tuya", "product_name": handler.get("model") or handler.get("description") or handler.get("product_id"),
            "category": handler.get("category_override") or handler.get("category"), "device_kind": "unknown",
            "schema_source": "TUYA_EXACT_PRODUCT_HANDLER", "handler_source": catalog().get("source", {}).get("repository"),
            "handler_commit": catalog().get("source", {}).get("commit"), "handler_license": catalog().get("source", {}).get("license"),
            "handler_operations": handler.get("operations", []),
            "handler_unsupported_operations": sorted({str(item.get("op")) for item in handler.get("operations", [])
                                                        if isinstance(item, dict) and item.get("op") not in {
                                                            "add_dpid_integer", "add_dpid_enum", "add_dpid_boolean", "add_dpid_bitmap",
                                                            "remove_dpid", "override_category", "set_dpid_strategy_to_enum",
                                                            "map_dpid_initial_status_values", "override_dpid_type_information_cls"}}),
            "functions": [], "status_spec": [],
            "dps_profile": {"product_id": handler.get("product_id"), "dps": dps,
                             "normalized_characteristics": tuya_dps_registry.normalized_characteristics()},
            "cached_at": 0}
