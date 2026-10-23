"""Owner-configured SolarMiner hardware integrations and explicit controls.

Credentials and endpoints are stored on the Gateway under its private data
directory. Tuya device keys are excluded from public projections.
"""
from __future__ import annotations

import hashlib
import hmac
import errno
import ipaddress
import json
import os
import re
import sys
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from . import deye_modbus

# TinyTuya is bundled with the signed Gateway package so local control works
# without an installer-time network dependency. It is used only for LAN I/O.
_TUYA_VENDOR = Path(__file__).with_name("_vendor")
if _TUYA_VENDOR.is_dir() and str(_TUYA_VENDOR) not in sys.path:
    sys.path.insert(0, str(_TUYA_VENDOR))
try:
    import tinytuya
except ImportError:  # Keep the rest of the Gateway usable if packaging is incomplete.
    tinytuya = None


class TuyaSyncCancelled(Exception):
    """Raised when an Owner cancels an in-progress inventory sync."""

TUYA_REGIONS = {
    "china": "https://openapi.tuyacn.com",
    "us": "https://openapi.tuyaus.com",
    "us_east": "https://openapi-ueaz.tuyaus.com",
    "eu_central": "https://openapi.tuyaeu.com",
    "eu_west": "https://openapi-weaz.tuyaeu.com",
    "india": "https://openapi.tuyain.com",
    "singapore": "https://openapi-sg.iotbing.com",
}
TESLA_API_BASES = {
    "north_america": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "europe": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "china": "https://fleet-api.prd.cn.vn.cloud.tesla.cn",
}
TESLA_AUTH_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
MAX_CONFIG_BYTES = 1_048_576
MAX_TUYA_DEVICES = 200
CGMINER_COMMANDS = ("summary", "stats", "devs")
CGMINER_OPTIONAL_READ_COMMANDS = ("tunerstatus",)
_TESLA_EV_READ_LOCK = threading.Lock()


def _data_dir() -> Path:
    return Path(os.environ.get("SOLARMINER_DATA_DIR", "/var/lib/solarminer"))


def _config_path() -> Path:
    return _data_dir() / "hardware-integrations.json"


def load_config() -> dict[str, Any]:
    path = _config_path()
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("integration_config_too_large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("integration_config_invalid")
    return value


def save_config(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("integration_config_invalid")
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_CONFIG_BYTES:
        raise ValueError("integration_config_too_large")
    directory = _data_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    path = _config_path()
    temporary = path.with_suffix(".json.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return public_config(value)


def public_config(value: dict[str, Any] | None = None) -> dict[str, Any]:
    config = value if value is not None else load_config()
    tuya = config.get("tuya", {}) if isinstance(config.get("tuya", {}), dict) else {}
    return {
        "deye": {k: config.get("deye", {}).get(k) for k in ("host", "port", "unit_id", "model") if config.get("deye", {}).get(k) is not None},
        "antminer": {k: config.get("antminer", {}).get(k) for k in ("host", "port", "rest_port", "model") if config.get("antminer", {}).get(k) is not None},
        "antminer_control_configured": bool(config.get("antminer", {}).get("username") and config.get("antminer", {}).get("password")),
        "tuya": {"region": tuya.get("region"), "client_id": tuya.get("client_id"), "uid": tuya.get("uid"), "device_ids": [x.get("device_id") for x in tuya.get("devices", []) if isinstance(x, dict)], "devices": [{"device_id": x.get("device_id"), "name": x.get("name"), "room": x.get("room", ""), "floor": x.get("floor", ""), "name_source": x.get("name_source", "cloud"), "switch_code": x.get("switch_code"), "switch_channels": [item.get("code") for item in x.get("functions", []) if isinstance(item, dict) and str(item.get("type", "")).lower() in {"bool", "boolean"}], "channel_labels": x.get("channel_labels", {}), "capability_labels": x.get("capability_labels", {}), "level_code": x.get("level_code"), "level_min": x.get("level_min", 0), "level_max": x.get("level_max", 100), "category": x.get("category"), "product_id": x.get("product_id"), "product_name": x.get("product_name"), "online": x.get("online"), "ip": x.get("local_ip") or x.get("ip"), "local_ip": x.get("local_ip", ""), "local_protocol": x.get("local_protocol", "3.3"), "local_dps_map": x.get("local_dps_map", {}), "local_control_state": x.get("local_control_state", "not_tested"), "cloud_source": x.get("cloud_source"), "cloud_missing": x.get("cloud_missing", False), "local_key_available": bool(x.get("local_key")), "functions": x.get("functions", []), "status_spec": x.get("status_spec", []), "current_status": x.get("current_status", []), "last_status_at": x.get("last_status_at")} for x in tuya.get("devices", []) if isinstance(x, dict)], "configured": bool(tuya.get("client_id") and tuya.get("client_secret"))},
        "secrets_returned": False,
    }


def public_tesla_config(value: dict[str, Any] | None = None) -> dict[str, Any]:
    config = value if value is not None else load_config()
    tesla = config.get("tesla", {}) if isinstance(config.get("tesla", {}), dict) else {}
    return {"region": tesla.get("region", "europe"), "vehicle_ids": tesla.get("vehicle_ids", []),
            "client_id": tesla.get("client_id"), "configured": bool(tesla.get("client_id") and tesla.get("refresh_token")),
            "purpose": "ev_charging_status_read_only", "control_available": False, "secrets_returned": False}


def _private_ip(host: Any) -> str:
    if not isinstance(host, str) or len(host) > 64:
        raise ValueError("private_ip_literal_required")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("private_ip_literal_required") from exc
    if not address.is_private or address.is_loopback or address.is_multicast or address.is_unspecified or address.is_link_local:
        raise ValueError("private_lan_target_required")
    return str(address)


def _port(value: Any, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError("invalid_port")
    return value if value else default


def validate_config(payload: Any, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("integration_config_invalid")
    if "tesla" in payload:
        raise ValueError("tesla_config_must_use_ev_api")
    old = existing if existing is not None else load_config()
    result: dict[str, Any] = {k: old.get(k, {}) for k in ("deye", "antminer", "tuya")}
    result["tesla"] = old.get("tesla", {})
    if "deye" in payload:
        item = payload["deye"]
        if not isinstance(item, dict): raise ValueError("invalid_deye_config")
        if item.get("enabled", True):
            host = _private_ip(item.get("host"))
            port = item.get("port", 502)
            unit = item.get("unit_id", 1)
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535: raise ValueError("invalid_port")
            if isinstance(unit, bool) or not isinstance(unit, int) or not 0 <= unit <= 247: raise ValueError("invalid_unit_id")
            model = item.get("model", "SUN-15K-SG05LP3-EU-SM2")
            if model not in {"SUN-15K-SG05LP3-EU-SM2", "other"}: raise ValueError("unsupported_deye_model")
            result["deye"] = {"host": host, "port": port, "unit_id": unit, "model": model}
        else: result["deye"] = {}
    if "antminer" in payload:
        item = payload["antminer"]
        if not isinstance(item, dict): raise ValueError("invalid_antminer_config")
        if item.get("enabled", True):
            host = _private_ip(item.get("host"))
            port = item.get("port", 4028)
            rest_port = item.get("rest_port", 80)
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535: raise ValueError("invalid_port")
            if isinstance(rest_port, bool) or not isinstance(rest_port, int) or not 1 <= rest_port <= 65535: raise ValueError("invalid_rest_port")
            model = item.get("model", "S19K Pro")
            if model != "S19K Pro": raise ValueError("unsupported_antminer_model")
            old_antminer = result.get("antminer", {})
            username = item.get("username") or old_antminer.get("username")
            password = item.get("password") or old_antminer.get("password")
            if username is not None and (not isinstance(username, str) or not 1 <= len(username) <= 128): raise ValueError("invalid_antminer_username")
            if password is not None and (not isinstance(password, str) or not 1 <= len(password) <= 512): raise ValueError("invalid_antminer_password")
            result["antminer"] = {"host": host, "port": port, "rest_port": rest_port, "model": model,
                                  "username": username, "password": password}
        else: result["antminer"] = {}
    if "tuya" in payload:
        item = payload["tuya"]
        if not isinstance(item, dict): raise ValueError("invalid_tuya_config")
        region = item.get("region", result.get("tuya", {}).get("region", "eu_central"))
        if region not in TUYA_REGIONS: raise ValueError("invalid_tuya_region")
        client_id = item.get("client_id", result.get("tuya", {}).get("client_id"))
        client_secret = item.get("client_secret") or result.get("tuya", {}).get("client_secret")
        uid = item.get("uid", result.get("tuya", {}).get("uid"))
        if uid is not None and (not isinstance(uid, str) or not 1 <= len(uid) <= 128 or not all(c.isalnum() or c in "_-" for c in uid)):
            raise ValueError("invalid_tuya_uid")
        if client_id is not None and (not isinstance(client_id, str) or not 1 <= len(client_id) <= 128): raise ValueError("invalid_tuya_client_id")
        if client_secret is not None and (not isinstance(client_secret, str) or not 8 <= len(client_secret) <= 256): raise ValueError("invalid_tuya_client_secret")
        devices = item.get("devices", result.get("tuya", {}).get("devices", []))
        if not isinstance(devices, list) or len(devices) > MAX_TUYA_DEVICES: raise ValueError("invalid_tuya_devices")
        normalized = []
        existing_devices = {x.get("device_id"): x for x in result.get("tuya", {}).get("devices", []) if isinstance(x, dict)}
        for device in devices:
            if not isinstance(device, dict): raise ValueError("invalid_tuya_device")
            device_id, name = device.get("device_id"), device.get("name", "Tuya device")
            if not isinstance(device_id, str) or not 1 <= len(device_id) <= 128 or not all(c.isalnum() or c in "_-" for c in device_id): raise ValueError("invalid_tuya_device_id")
            if not isinstance(name, str) or not name.strip() or len(name) > 120: raise ValueError("invalid_tuya_device_name")
            switch_code = device.get("switch_code")
            normalized_device = {"device_id": device_id, "name": name.strip()}
            # Cloud-imported secrets and capability metadata can only come from
            # the Gateway's previous trusted inventory, never from PWA input.
            previous = existing_devices.get(device_id, {})
            for key in ("local_key", "local_ip", "local_protocol", "local_dps_map", "local_control_state", "product_id", "product_name", "category", "online", "ip", "functions", "status_spec", "current_status", "last_status_at", "cloud_source", "cloud_missing", "last_synced_at"):
                if key in previous:
                    normalized_device[key] = previous[key]
            name_source = device.get("name_source", previous.get("name_source", "cloud"))
            if name_source not in {"cloud", "local"}: raise ValueError("invalid_tuya_name_source")
            normalized_device["name_source"] = name_source
            if name_source == "local": normalized_device["local_name"] = name.strip()
            for key in ("room", "floor"):
                value = device.get(key, previous.get(key, ""))
                if not isinstance(value, str) or len(value) > 120: raise ValueError(f"invalid_tuya_{key}")
                normalized_device[key] = value.strip()
            local_ip_value = device.get("local_ip", previous.get("local_ip") or previous.get("ip"))
            if local_ip_value:
                normalized_device["local_ip"] = _private_ip(local_ip_value)
            protocol = str(device.get("local_protocol", previous.get("local_protocol", "3.3")))
            if protocol not in {"3.1", "3.2", "3.3", "3.4", "3.5"}:
                raise ValueError("invalid_tuya_local_protocol")
            normalized_device["local_protocol"] = protocol
            dps_map = device.get("local_dps_map", previous.get("local_dps_map", {}))
            if not isinstance(dps_map, dict) or len(dps_map) > 128:
                raise ValueError("invalid_tuya_local_dps_map")
            allowed_dps_codes = {entry.get("code") for entry in [*previous.get("functions", []), *previous.get("status_spec", [])]
                                 if isinstance(entry, dict) and isinstance(entry.get("code"), str)}
            clean_dps_map: dict[str, str] = {}
            for code, dps in dps_map.items():
                if code not in allowed_dps_codes or not isinstance(dps, (str, int)) or not str(dps).isdigit() or not 1 <= int(dps) <= 65535:
                    raise ValueError("invalid_tuya_local_dps_map")
                clean_dps_map[code] = str(int(dps))
            normalized_device["local_dps_map"] = clean_dps_map
            channel_labels = device.get("channel_labels", previous.get("channel_labels", {}))
            if not isinstance(channel_labels, dict) or len(channel_labels) > 32: raise ValueError("invalid_tuya_channel_labels")
            available_codes = {entry.get("code") for entry in previous.get("functions", []) if isinstance(entry, dict) and str(entry.get("type", "")).lower() in {"bool", "boolean"}}
            clean_labels = {}
            for code, label in channel_labels.items():
                if code not in available_codes or not isinstance(label, str) or len(label) > 80: raise ValueError("invalid_tuya_channel_label")
                clean_labels[code] = label.strip()
            normalized_device["channel_labels"] = clean_labels
            capability_labels = device.get("capability_labels", previous.get("capability_labels", {}))
            if not isinstance(capability_labels, dict) or len(capability_labels) > 64: raise ValueError("invalid_tuya_capability_labels")
            all_codes = {entry.get("code") for entry in [*previous.get("functions", []), *previous.get("status_spec", [])] if isinstance(entry, dict) and isinstance(entry.get("code"), str)}
            clean_capability_labels = {}
            for code, label in capability_labels.items():
                if code not in all_codes or not isinstance(label, str) or len(label) > 80: raise ValueError("invalid_tuya_capability_label")
                clean_capability_labels[code] = label.strip()
            normalized_device["capability_labels"] = clean_capability_labels
            if switch_code is not None:
                if not isinstance(switch_code, str) or not 1 <= len(switch_code) <= 64 or not all(c.isalnum() or c in "_-" for c in switch_code): raise ValueError("invalid_tuya_switch_code")
                normalized_device["switch_code"] = switch_code
            level_code = device.get("level_code")
            if level_code is not None:
                if not isinstance(level_code, str) or not 1 <= len(level_code) <= 64 or not all(c.isalnum() or c in "_-" for c in level_code): raise ValueError("invalid_tuya_level_code")
                level_min, level_max = device.get("level_min", 0), device.get("level_max", 100)
                if isinstance(level_min, bool) or not isinstance(level_min, int) or isinstance(level_max, bool) or not isinstance(level_max, int) or not 0 <= level_min < level_max <= 100000: raise ValueError("invalid_tuya_level_range")
                normalized_device.update({"level_code": level_code, "level_min": level_min, "level_max": level_max})
            normalized.append(normalized_device)
        if normalized and (not client_id or not client_secret): raise ValueError("tuya_credentials_required")
        result["tuya"] = {"region": region, "client_id": client_id, "client_secret": client_secret,
                           "uid": uid, "devices": normalized}
    return result


def validate_tesla_config(item: Any, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(item, dict): raise ValueError("invalid_tesla_config")
    old = (existing if existing is not None else load_config()).get("tesla", {})
    if item.get("enabled") is False: return {}
    client_id = item.get("client_id", old.get("client_id"))
    refresh_token = item.get("refresh_token") or old.get("refresh_token")
    region = item.get("region", old.get("region", "europe"))
    vehicle_ids = item.get("vehicle_ids", old.get("vehicle_ids", []))
    if region not in TESLA_API_BASES: raise ValueError("invalid_tesla_region")
    if not isinstance(client_id, str) or not 1 <= len(client_id) <= 256: raise ValueError("invalid_tesla_client_id")
    if not isinstance(refresh_token, str) or not 8 <= len(refresh_token) <= 4096: raise ValueError("invalid_tesla_refresh_token")
    if not isinstance(vehicle_ids, list) or len(vehicle_ids) != 1: raise ValueError("invalid_tesla_vehicle_ids")
    normalized_ids = []
    for value in vehicle_ids:
        if not isinstance(value, str) or not 1 <= len(value) <= 64 or not all(c.isalnum() or c in "-_" for c in value): raise ValueError("invalid_tesla_vehicle_id")
        if value not in normalized_ids: normalized_ids.append(value)
    return {"region": region, "client_id": client_id, "refresh_token": refresh_token, "vehicle_ids": normalized_ids}


def _json_request(url: str, headers: dict[str, str], timeout: float = 8.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={**headers, "Accept": "application/json"}, method="GET")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200: raise RuntimeError("tuya_http_error")
            raw = response.read(1_048_577)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"tuya_http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("tuya_connection_failed") from exc
    if len(raw) > 1_048_576: raise RuntimeError("tuya_response_too_large")
    try: value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise RuntimeError("tuya_invalid_json") from exc
    if not isinstance(value, dict) or value.get("success") is not True:
        code = value.get("code") if isinstance(value, dict) else None
        safe_code = str(code)[:32] if isinstance(code, (str, int)) and str(code).replace("_", "").replace("-", "").isalnum() else None
        raise RuntimeError(f"tuya_api_rejected_request:{safe_code}" if safe_code else "tuya_api_rejected_request")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect_rejected", headers, fp)


def _tuya_request(config: dict[str, Any], path: str, token: str | None = None, *,
                  method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if method not in {"GET", "POST"}:
        raise ValueError("tuya_method_not_allowed")
    # Cloud keys copied from the Tuya console can carry surrounding whitespace
    # (for example, a trailing newline from a mobile clipboard). It is not part
    # of either credential and would otherwise invalidate every HMAC signature.
    client_id = str(config["client_id"]).strip()
    secret = str(config["client_secret"]).strip()
    if not client_id or not secret:
        raise ValueError("tuya_credentials_required")
    timestamp, nonce = str(int(time.time() * 1000)), uuid.uuid4().hex
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") if payload is not None else b""
    canonical = f"{method}\n{hashlib.sha256(body).hexdigest()}\n\n{path}"
    to_sign = client_id + (token or "") + timestamp + nonce + canonical
    signature = hmac.new(secret.encode(), to_sign.encode(), hashlib.sha256).hexdigest().upper()
    headers = {"client_id": client_id, "sign": signature, "sign_method": "HMAC-SHA256", "t": timestamp, "nonce": nonce}
    if token: headers["access_token"] = token
    if method == "GET":
        return _json_request(TUYA_REGIONS[config["region"]] + path, headers)
    headers["Accept"] = "application/json"
    if body:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(TUYA_REGIONS[config["region"]] + path,
                                     data=body if method == "POST" else None,
                                     headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=8.0) as response:
            raw = response.read(1_048_577)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"tuya_http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("tuya_connection_failed") from exc
    if len(raw) > 1_048_576:
        raise RuntimeError("tuya_response_too_large")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("tuya_invalid_json") from exc
    if not isinstance(value, dict) or value.get("success") is not True:
        code = value.get("code") if isinstance(value, dict) else None
        safe_code = str(code)[:32] if isinstance(code, (str, int)) and str(code).replace("_", "").replace("-", "").isalnum() else None
        raise RuntimeError(f"tuya_api_rejected_request:{safe_code}" if safe_code else "tuya_api_rejected_request")
    return value


def _tuya_lan_client(device: dict[str, Any]):
    if tinytuya is None:
        raise RuntimeError("tuya_lan_driver_unavailable")
    key = device.get("local_key")
    host = device.get("local_ip") or device.get("ip")
    if not isinstance(key, str) or len(key) < 8:
        raise RuntimeError("tuya_local_key_missing")
    host = _private_ip(host)
    protocol = str(device.get("local_protocol", "3.3"))
    if protocol not in {"3.1", "3.2", "3.3", "3.4", "3.5"}:
        raise RuntimeError("tuya_local_protocol_unsupported")
    client = tinytuya.Device(device["device_id"], host, key, version=float(protocol), connection_timeout=2)
    client.set_socketTimeout(2)
    client.set_retry(False)
    return client


def _tuya_local_dps(device: dict[str, Any], code: str) -> str:
    mapping = device.get("local_dps_map") if isinstance(device.get("local_dps_map"), dict) else {}
    value = mapping.get(code)
    if value is not None:
        return str(value)
    if code == "switch":
        return "1"
    match = re.fullmatch(r"switch_(\d+)", code)
    if match and 1 <= int(match.group(1)) <= 64:
        return str(int(match.group(1)))
    if code.isdigit() and 1 <= int(code) <= 65535:
        return str(int(code))
    raise ValueError("tuya_local_datapoint_mapping_required")


def _tuya_local_status(device: dict[str, Any]) -> dict[str, Any]:
    result = _tuya_lan_client(device).status()
    if not isinstance(result, dict) or not isinstance(result.get("dps"), dict):
        raise RuntimeError("tuya_lan_status_unavailable")
    code_by_dps: dict[str, str] = {}
    for entry in [*device.get("functions", []), *device.get("status_spec", [])]:
        if not isinstance(entry, dict) or not isinstance(entry.get("code"), str):
            continue
        try:
            code_by_dps[_tuya_local_dps(device, entry["code"])] = entry["code"]
        except ValueError:
            continue
    status = [{"code": code_by_dps.get(str(dps), f"dps_{dps}"), "value": value}
              for dps, value in result["dps"].items()]
    return {"device_id": device["device_id"], "name": device.get("name", "Tuya device"),
            "status": status, "connection_state": "local_responded", "source": "TUYA_LAN",
            "trust": "LIVE_UNVERIFIED", "observed_at": time.time()}


def read_tuya(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Read Tuya device status over LAN only; never fall back to Tuya Cloud."""
    devices = [item for item in config.get("devices", [])
               if isinstance(item, dict) and isinstance(item.get("device_id"), str)]
    if not devices:
        return []

    def read_one(item: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = _tuya_local_status(item)
            result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
            return result
        except (RuntimeError, ValueError, OSError, TypeError) as exc:
            return {"device_id": item["device_id"], "name": item.get("name", "Tuya device"),
                    "connection_state": "failed", "reason": str(exc)[:120],
                    "source": "TUYA_LAN", "trust": "UNAVAILABLE",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1)}

    # Keep polling a large home bounded and return rows in their configured order.
    with ThreadPoolExecutor(max_workers=min(8, len(devices)), thread_name_prefix="tuya-lan") as pool:
        return list(pool.map(read_one, devices))


def synchronize_tuya_devices(config: dict[str, Any], *, cancelled: threading.Event | None = None) -> dict[str, Any]:
    """Import the Tuya project's inventory and safe device capabilities.

    Device local keys are persisted in the private Gateway config only. This
    function returns private records to its in-process caller for persistence;
    the API uses public_config and exposes only a boolean.
    """
    if not config.get("client_id") or not config.get("client_secret"):
        raise ValueError("tuya_credentials_required")
    if not config.get("uid"):
        raise ValueError("tuya_uid_required")
    def check_cancelled() -> None:
        if cancelled is not None and cancelled.is_set():
            raise TuyaSyncCancelled("tuya_sync_cancelled")

    check_cancelled()
    try:
        auth = _tuya_request(config, "/v1.0/token?grant_type=1")
    except (RuntimeError, ValueError) as exc:
        # Identify the failing stage without returning request headers or secrets.
        raise RuntimeError(f"tuya_authentication_failed:{str(exc)[:80]}") from exc
    token = (auth.get("result") or {}).get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("tuya_token_missing")

    by_id = {x.get("device_id"): x for x in config.get("devices", []) if isinstance(x, dict)}
    discovered: list[dict[str, Any]] = []
    cursor = ""
    seen_cursors: set[str] = set()
    pages = 0
    while True:
        check_cancelled()
        query = {"page_size": "20"}
        if cursor:
            query["last_id"] = cursor
        # Tuya calculates the signature over query parameters in alphabetical
        # order. The first page only has page_size, but subsequent pages also
        # include last_id, which must precede page_size in the signed URL.
        path = "/v2.0/cloud/thing/device?" + urllib.parse.urlencode(sorted(query.items()))
        try:
            rows = _tuya_request(config, path, token).get("result")
        except (RuntimeError, ValueError) as exc:
            raise RuntimeError(f"tuya_inventory_request_failed:{str(exc)[:80]}") from exc
        check_cancelled()
        if not isinstance(rows, list):
            raise RuntimeError("tuya_device_list_invalid")
        pages += 1
        for row in rows:
            if not isinstance(row, dict):
                continue
            device_id = row.get("id") or row.get("device_id")
            if not isinstance(device_id, str) or not 1 <= len(device_id) <= 128 or not all(c.isalnum() or c in "_-" for c in device_id):
                continue
            previous = by_id.get(device_id, {})
            item = {
                "device_id": device_id,
                "name": str(previous.get("local_name") if previous.get("name_source") == "local" else (row.get("customName") or row.get("name") or previous.get("name") or "Tuya device"))[:120],
                "category": str(row.get("category") or previous.get("category") or "")[:64],
                "product_id": str(row.get("productId") or row.get("product_id") or previous.get("product_id") or "")[:128],
                "product_name": str(row.get("productName") or row.get("product_name") or previous.get("product_name") or "")[:120],
                "online": bool(row.get("isOnline", row.get("online", False))),
                "ip": str(row.get("ip") or previous.get("ip") or "")[:64],
                "cloud_source": "TUYA_PROJECT",
                "cloud_missing": False,
                "last_synced_at": int(time.time()),
            }
            key = row.get("localKey") or row.get("local_key")
            if isinstance(key, str) and 8 <= len(key) <= 256:
                item["local_key"] = key
            elif isinstance(previous.get("local_key"), str):
                item["local_key"] = previous["local_key"]
            for retained in ("switch_code", "level_code", "level_min", "level_max", "favorite", "room", "floor", "name_source", "local_name", "channel_labels", "capability_labels", "local_ip", "local_protocol", "local_dps_map", "local_control_state"):
                if retained in previous:
                    item[retained] = previous[retained]
            discovered.append(item)
        if len(discovered) > MAX_TUYA_DEVICES:
            raise RuntimeError("tuya_device_limit_exceeded")
        if len(rows) < 20:
            break
        next_cursor = rows[-1].get("id") or rows[-1].get("device_id") if rows else None
        if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
            raise RuntimeError("tuya_device_pagination_invalid")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
        if pages >= 10:
            raise RuntimeError("tuya_device_limit_exceeded")

    # Read each device's latest metadata and DP schema. Per-device failures are
    # reported without discarding the successfully imported inventory.
    details_failures = 0
    for item in discovered:
        check_cancelled()
        quoted = urllib.parse.quote(item["device_id"], safe="")
        try:
            details = _tuya_request(config, f"/v2.0/cloud/thing/{quoted}", token).get("result")
            if isinstance(details, dict):
                key = details.get("local_key") or details.get("localKey")
                if isinstance(key, str) and 8 <= len(key) <= 256:
                    item["local_key"] = key
                if details.get("ip"):
                    item["ip"] = str(details["ip"])[:64]
                item["online"] = bool(details.get("is_online", details.get("online", item["online"])))
                if item.get("name_source") != "local":
                    item["name"] = str(details.get("custom_name") or details.get("name") or item["name"])[:120]
                item["product_id"] = str(details.get("product_id") or item["product_id"])[:128]
                item["product_name"] = str(details.get("product_name") or item["product_name"])[:120]
                item["category"] = str(details.get("category") or item["category"])[:64]
        except (RuntimeError, ValueError):
            details_failures += 1
        try:
            # Inventory sync uses Cloud only for discovery/configuration.
            # Operational state is deliberately read from the device over LAN.
            previous_status = by_id.get(item["device_id"], {})
            if isinstance(previous_status.get("current_status"), list):
                item["current_status"] = previous_status["current_status"]
                item["last_status_at"] = previous_status.get("last_status_at")
        except (RuntimeError, ValueError):
            details_failures += 1
        try:
            spec = _tuya_request(config, f"/v1.0/iot-03/devices/{quoted}/specification", token).get("result")
            if isinstance(spec, dict):
                functions = spec.get("functions", [])
                statuses = spec.get("status", [])
                if isinstance(functions, list):
                    item["functions"] = [{k: entry.get(k) for k in ("code", "name", "type", "values", "desc") if k in entry}
                                          for entry in functions if isinstance(entry, dict)][:128]
                if isinstance(statuses, list):
                    item["status_spec"] = [{k: entry.get(k) for k in ("code", "name", "type", "values", "desc") if k in entry}
                                            for entry in statuses if isinstance(entry, dict)][:128]
                item["category"] = str(spec.get("category") or item["category"])[:64]
        except (RuntimeError, ValueError):
            details_failures += 1
        check_cancelled()

    check_cancelled()
    return {"devices": discovered, "device_count": len(discovered),
            "local_keys_available": sum(bool(item.get("local_key")) for item in discovered),
            "schema_failures": details_failures, "pages": pages}


def control_tuya_switch(config: dict[str, Any], device_id: str, on: bool, code: str | None = None) -> dict[str, Any]:
    """Toggle only a switch datapoint explicitly assigned in Owner config."""
    if not isinstance(on, bool):
        raise ValueError("tuya_switch_state_must_be_boolean")
    if not isinstance(config, dict):
        raise RuntimeError("tuya_config_unavailable")
    device = next((item for item in config.get("devices", [])
                   if isinstance(item, dict) and item.get("device_id") == device_id), None)
    if device is None:
        raise ValueError("tuya_device_not_configured")
    code = code or device.get("switch_code")
    allowed_codes = {entry.get("code") for entry in device.get("functions", []) if isinstance(entry, dict) and str(entry.get("type", "")).lower() in {"bool", "boolean"}}
    if device.get("switch_code"):
        allowed_codes.add(device["switch_code"])
    if code not in allowed_codes:
        raise ValueError("tuya_switch_function_code_not_configured")
    if not isinstance(code, str) or not code or not code.replace("_", "").replace("-", "").isalnum() or len(code) > 64:
        raise ValueError("tuya_switch_function_code_not_configured")
    dps = _tuya_local_dps(device, code)
    client = _tuya_lan_client(device)
    response = client.set_status(on, switch=int(dps))
    if not isinstance(response, dict) or (response.get("Error") and not response.get("dps")):
        raise RuntimeError("tuya_lan_command_rejected")
    observed = None
    try:
        rows = _tuya_local_status(device).get("status", [])
        observed = next((item.get("value") for item in rows if item.get("code") == code), None)
    except (RuntimeError, ValueError, OSError):
        pass
    state = observed if isinstance(observed, bool) else None
    return {"device_id": device_id, "switch_code": code, "requested_on": on,
            "command_accepted": True, "observed_on": state,
            "state_confirmed": state is on, "connection_state": "control_confirmed" if state is on else "command_accepted_state_unconfirmed",
            "control_command_sent": True, "source": "TUYA_LAN"}


def control_tuya_level(config: dict[str, Any], device_id: str, percent: int) -> dict[str, Any]:
    """Set a configured Tuya dimmer/cover datapoint from 0–100 percent."""
    if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
        raise ValueError("tuya_level_percent_out_of_range")
    if not isinstance(config, dict):
        raise RuntimeError("tuya_config_unavailable")
    device = next((item for item in config.get("devices", []) if isinstance(item, dict) and item.get("device_id") == device_id), None)
    if device is None:
        raise ValueError("tuya_device_not_configured")
    code = device.get("level_code")
    low, high = device.get("level_min", 0), device.get("level_max", 100)
    if not isinstance(code, str) or not code or isinstance(low, bool) or isinstance(high, bool) or not isinstance(low, int) or not isinstance(high, int) or not 0 <= low < high <= 100000:
        raise ValueError("tuya_level_function_not_configured")
    target = round(low + (high - low) * percent / 100)
    dps = _tuya_local_dps(device, code)
    response = _tuya_lan_client(device).set_value(int(dps), target)
    if not isinstance(response, dict) or (response.get("Error") and not response.get("dps")):
        raise RuntimeError("tuya_lan_command_rejected")
    try:
        rows = _tuya_local_status(device).get("status", [])
        observed = next((item.get("value") for item in rows if item.get("code") == code), None)
    except (RuntimeError, ValueError, OSError):
        observed = None
    return {"device_id": device_id, "level_code": code, "requested_percent": percent, "requested_value": target,
            "command_accepted": True, "control_command_sent": True, "state_confirmed": observed == target,
            "observed_value": observed, "connection_state": "control_confirmed" if observed == target else "command_accepted_state_unconfirmed",
            "source": "TUYA_LAN"}


def read_antminer(host: str, port: int = 4028, timeout: float = 2.0) -> dict[str, Any]:
    address = _private_ip(host)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535: raise ValueError("invalid_port")
    responses = {}
    optional_commands = []
    for command in (*CGMINER_COMMANDS, *CGMINER_OPTIONAL_READ_COMMANDS):
        # Braiins OS documents a newline-terminated JSON request (the newline
        # comes from `echo`). NUL-terminating this frame can leave BOSminer
        # waiting for a complete request and makes an open API look offline.
        message = json.dumps({"command": command}, separators=(",", ":")).encode() + b"\n"
        try:
            with socket.create_connection((address, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                sock.sendall(message)
                shutdown = getattr(sock, "shutdown", None)
                if callable(shutdown):
                    shutdown(socket.SHUT_WR)
                chunks, total = [], 0
                while total < 262_144:
                    part = sock.recv(min(16_384, 262_144 - total))
                    if not part: break
                    chunks.append(part); total += len(part)
                    if b"\0" in part: break
        except (OSError, TimeoutError) as exc:
            if command in CGMINER_OPTIONAL_READ_COMMANDS:
                continue
            raise RuntimeError(f"antminer_{command}_connection_failed") from exc
        raw = b"".join(chunks).split(b"\0", 1)[0].strip()
        if not raw:
            if command in CGMINER_OPTIONAL_READ_COMMANDS: continue
            raise RuntimeError(f"antminer_{command}_empty_response")
        try: response = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            if command in CGMINER_OPTIONAL_READ_COMMANDS: continue
            raise RuntimeError(f"antminer_{command}_invalid_json") from exc
        if not isinstance(response, dict):
            if command in CGMINER_OPTIONAL_READ_COMMANDS: continue
            raise RuntimeError(f"antminer_{command}_invalid_response")
        responses[command] = response
        if command in CGMINER_OPTIONAL_READ_COMMANDS: optional_commands.append(command)
    return {"host": address, "port": port, "configured_model": "S19K Pro", "model_identity_verified": False, "protocol": "BOSminer CGMiner-compatible read-only", "connection_state": "api_responded", "commands": list(CGMINER_COMMANDS), "optional_commands": optional_commands, "data": responses, "trust": "LIVE_UNVERIFIED", "control_commands_sent": False, "observed_at": time.time()}


_BOS_CONTROL_ACTIONS = {
    "pause": ("PUT", "/api/v1/actions/pause", None),
    "stop": ("PUT", "/api/v1/actions/stop", None),
    "start": ("PUT", "/api/v1/actions/start", None),
}


def _bos_rest_request(host: str, port: int, path: str, *, method: str = "GET",
                      token: str | None = None, payload: dict[str, Any] | None = None,
                      timeout: float = 8.0) -> dict[str, Any]:
    """Call a fixed Braiins OS REST API path on a private miner address."""
    address = _private_ip(host)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid_rest_port")
    if not isinstance(path, str) or not path.startswith("/api/v1/") or ".." in path or "?" in path or "#" in path:
        raise ValueError("invalid_antminer_api_path")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "SolarMiner-Gateway"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = token
    request = urllib.request.Request(f"http://{address}:{port}{path}", data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(262_145)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("antminer_api_authentication_failed") from exc
        if exc.code == 404 or exc.code == 405:
            raise RuntimeError("antminer_public_api_unsupported_or_wrong_port") from exc
        raise RuntimeError(f"antminer_api_http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("antminer_public_api_connection_failed") from exc
    if len(raw) > 262_144:
        raise RuntimeError("antminer_api_response_too_large")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("antminer_api_invalid_json") from exc
    if not isinstance(data, dict):
        raise RuntimeError("antminer_api_invalid_response")
    return data


def _bos_rest_login(config: dict[str, Any]) -> str:
    username, password = config.get("username"), config.get("password")
    if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
        raise RuntimeError("antminer_control_credentials_required")
    response = _bos_rest_request(config["host"], config.get("rest_port", 80), "/api/v1/auth/login",
                                method="POST", payload={"username": username, "password": password})
    token = response.get("token")
    if not isinstance(token, str) or not token or len(token) > 4096:
        raise RuntimeError("antminer_api_login_response_invalid")
    return token


def control_antminer(config: dict[str, Any], action: str, watt: int | None = None) -> dict[str, Any]:
    """Perform one explicit Owner-requested Braiins OS action."""
    if not isinstance(config, dict) or not config.get("host"):
        raise RuntimeError("antminer_not_configured")
    if action not in {*_BOS_CONTROL_ACTIONS, "set_power_target"}:
        raise ValueError("unsupported_antminer_control_action")
    if action == "set_power_target" and (isinstance(watt, bool) or not isinstance(watt, int) or not 1 <= watt <= 2900):
        raise ValueError("power_target_out_of_range_1_2900_watts")
    host = _private_ip(config["host"])
    rest_port = config.get("rest_port", 80)
    token = _bos_rest_login(config)
    if action == "set_power_target":
        response = _bos_rest_request(host, rest_port, "/api/v1/performance/power-target", method="PUT",
                                    token=token, payload={"watt": watt})
        result = response.get("watt")
        if isinstance(result, bool) or not isinstance(result, int):
            raise RuntimeError("antminer_power_target_response_invalid")
        return {"action": action, "requested_watt": watt, "applied_watt": result,
                "connection_state": "control_applied", "control_command_sent": True}
    method, path, payload = _BOS_CONTROL_ACTIONS[action]
    response = _bos_rest_request(host, rest_port, path, method=method, token=token, payload=payload)
    return {"action": action, "result": response, "connection_state": "control_applied",
            "control_command_sent": True}


def probe_tcp(host: str, port: int, timeout: float = 2.0) -> dict[str, Any]:
    """Confirm private-LAN TCP reachability without sending a device command."""
    address = _private_ip(host)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid_port")
    try:
        with socket.create_connection((address, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
        return {"state": "tcp_reachable", "host": address, "port": port}
    except TimeoutError as exc:
        raise RuntimeError("tcp_connection_timeout") from exc
    except OSError as exc:
        if getattr(exc, "errno", None) == errno.ECONNREFUSED:
            reason = "tcp_connection_refused"
        elif getattr(exc, "errno", None) == errno.ENETUNREACH:
            reason = "network_unreachable"
        elif getattr(exc, "errno", None) == errno.EHOSTUNREACH:
            reason = "host_unreachable"
        else:
            reason = f"tcp_connection_error:{type(exc).__name__}"
        raise RuntimeError(reason) from exc


_DEYE_SG05LP3_MODEL = "SUN-15K-SG05LP3-EU-SM2"
_DEYE_SG05LP3_MAP_SOURCE = "https://github.com/mxbode/Deye-SUN-SG05LP3-EU-SM2-Modbus-TSV"
_DEYE_SG05LP3_MAP_SHA256 = "ba9e0b87ed37cc28ed9fc1493a07d9b26d6dc4d15fc95b1786424e85d99b9c48"


def _read_deye_sg05lp3_candidate_map(host: str, port: int, unit: int) -> dict[str, Any]:
    """Read the SG05LP3 live-telemetry allowlist using FC03 only.

    Register offsets and scales follow the three-phase energy-storage protocol
    table and a public implementation for SG04/SG05 LP3 inverters. The exact
    15 kW model is confirmed to have two MPPTs by its manufacturer datasheet.
    The current DYDA_WiBLE endpoint has returned coherent FC03 values for PV,
    battery and load blocks. The map remains candidate because exact firmware
    and logger semantics have not been certified by Deye.

    Eight bounded windows avoid one request per metric and preserve the
    logger's working FC03-only behavior. 4xxxx references are converted using
    40001 == PDU offset 0. No write function is present in this path.
    """
    def read(offset: int, count: int) -> tuple[int, ...]:
        result = deye_modbus.read_holding_registers(host, start_address=offset, count=count,
                                                     port=port, unit_id=unit, timeout=2.0)
        return result.raw_registers

    def u16(raw: int) -> int:
        return raw

    def s16(raw: int) -> int:
        return raw - 0x10000 if raw & 0x8000 else raw

    # Exact allowlist windows: battery current limits, inverter status, energy
    # counters, battery, grid/CT, AC/load and two populated MPPT channels.
    # All accesses use FC03; R/W configuration registers are read-only here.
    device_type = read(0, 1)[0]
    battery_limits = read(108, 2)        # refs 40109..40110; read-only FC03
    status = read(500, 1)[0]
    energy = read(514, 22)              # refs 40515..40536
    battery = read(586, 7)            # refs 40587..40593
    grid = read(598, 28)              # refs 40599..40626
    output = read(627, 29)            # refs 40628..40656
    pv = read(672, 8)                 # refs 40673..40680 (two MPPTs)

    metrics: list[dict[str, Any]] = []

    def add(field: str, reference: int, raw: int, value: int | float, unit: str,
            category: str, label: str, *, derived: bool = False,
            registers: list[int] | None = None) -> None:
        metric = {"field": field, "register": reference, "raw_value": raw,
                  "value": value, "unit": unit, "category": category,
                  "label": label, "derived": derived}
        if registers:
            metric["registers"] = registers
        metrics.append(metric)

    # PV1/PV2 powers are at offsets 672/673. Voltage/current are interleaved
    # at offsets 676..679: each is scaled by 0.1 according to the protocol.
    pv_specs = (
        ("pv1", 40673, pv[0], 40677, pv[4], 40678, pv[5], "MPPT 1"),
        ("pv2", 40674, pv[1], 40679, pv[6], 40680, pv[7], "MPPT 2"),
    )
    for name, p_ref, p_raw, v_ref, v_raw, i_ref, i_raw, label in pv_specs:
        add(f"{name}_input_power", p_ref, u16(p_raw), u16(p_raw), "W", "inversores", f"Potência {label}")
        add(f"{name}_voltage", v_ref, u16(v_raw), round(u16(v_raw) * 0.1, 1), "V", "inversores", f"Tensão {label}")
        add(f"{name}_current", i_ref, u16(i_raw), round(u16(i_raw) * 0.1, 1), "A", "inversores", f"Corrente {label}")
    pv_total = pv[0] + pv[1]
    add("pv_total_power", 40673, pv_total, pv_total, "W", "inversores", "Potência FV total", derived=True)

    # Energy counters in 40515..40536 use 0.1 kWh per word. Cumulative
    # counters are low-word first, then high-word, per the three-phase protocol.
    def add_energy(field: str, offset: int, raw: int, label: str, category: str,
                   *, high_offset: int | None = None) -> None:
        if high_offset is None:
            add(field, 40001 + offset, raw, round(raw * 0.1, 1), "kWh", category, label)
            return
        low = raw
        high = energy[high_offset - 514]
        combined = (high << 16) | low
        add(field, 40001 + offset, combined, round(combined * 0.1, 1), "kWh", category, label,
            registers=[40001 + offset, 40001 + high_offset])

    add_energy("battery_daily_charge_energy", 514, energy[0], "Energia diária de carga", "baterias")
    add_energy("battery_daily_discharge_energy", 515, energy[1], "Energia diária de descarga", "baterias")
    add_energy("battery_total_charge_energy", 516, energy[2], "Energia acumulada de carga", "baterias", high_offset=517)
    add_energy("battery_total_discharge_energy", 518, energy[4], "Energia acumulada de descarga", "baterias", high_offset=519)
    add_energy("grid_daily_import_energy", 520, energy[6], "Energia diária importada da rede", "inversores")
    add_energy("grid_daily_export_energy", 521, energy[7], "Energia diária exportada para a rede", "inversores")
    add_energy("grid_total_import_energy", 522, energy[8], "Energia acumulada importada da rede", "inversores", high_offset=523)
    add_energy("grid_total_export_energy", 524, energy[10], "Energia acumulada exportada para a rede", "inversores", high_offset=525)
    add_energy("load_daily_energy", 526, energy[12], "Consumo diário das cargas", "inversores")
    add_energy("load_total_energy", 527, energy[13], "Consumo acumulado das cargas", "inversores", high_offset=528)
    add_energy("pv_daily_energy", 529, energy[15], "Energia FV produzida hoje", "inversores")
    add_energy("pv_total_energy", 534, energy[20], "Energia FV acumulada", "inversores", high_offset=535)

    add("battery_max_charge_current", 40109, battery_limits[0], battery_limits[0], "A",
        "baterias", "Limite configurado de corrente de carga")
    add("battery_max_discharge_current", 40110, battery_limits[1], battery_limits[1], "A",
        "baterias", "Limite configurado de corrente de descarga")

    battery_specs = (
        ("battery_temperature", 40587, battery[0], round((battery[0] - 1000) * 0.1, 1), "°C", "Temperatura da bateria"),
        ("battery_voltage", 40588, battery[1], round(battery[1] * 0.01, 2), "V", "Tensão da bateria"),
        ("battery_soc", 40589, battery[2], battery[2], "%", "Carga da bateria"),
        ("battery_output_power", 40591, battery[4], s16(battery[4]), "W", "Potência de carga/descarga"),
        ("battery_output_current", 40592, battery[5], round(s16(battery[5]) * 0.01, 2), "A", "Corrente de carga/descarga"),
        ("battery_corrected_capacity", 40593, battery[6], battery[6], "Ah", "Capacidade corrigida da bateria"),
    )
    for field, ref, raw, value, unit, label in battery_specs:
        add(field, ref, raw, value, unit, "baterias", label)
    # The protocol labels these signed values as battery output current/power.
    # On this live endpoint negative values coincided with PV surplus and are
    # reported as charging; positive values are reported as discharging.
    current_a = round(s16(battery[5]) * 0.01, 2)
    power_w = s16(battery[4])
    add("battery_charge_current", 40592, battery[5], max(0.0, -current_a), "A", "baterias", "Corrente de carga", derived=True)
    add("battery_discharge_current", 40592, battery[5], max(0.0, current_a), "A", "baterias", "Corrente de descarga", derived=True)
    add("battery_charge_power", 40591, battery[4], max(0, -power_w), "W", "baterias", "Potência de carga", derived=True)
    add("battery_discharge_power", 40591, battery[4], max(0, power_w), "W", "baterias", "Potência de descarga", derived=True)

    def at(block: tuple[int, ...], base: int, offset: int) -> int:
        return block[offset - base]

    # Grid side / meter channels. Internal and external CT values are kept
    # separate: the protocol says some total fields vary with meter settings.
    for phase, offset, ref in zip("abc", (598, 599, 600), (40599, 40600, 40601)):
        raw = at(grid, 598, offset)
        add(f"grid_voltage_{phase}", ref, raw, round(u16(raw) * 0.1, 1), "V", "inversores", f"Tensão da rede {phase.upper()}")
    add("grid_frequency", 40610, at(grid, 598, 609), round(u16(at(grid, 598, 609)) * 0.01, 2), "Hz", "inversores", "Frequência da rede")
    for phase, offset in zip("abc", (604, 605, 606)):
        raw = at(grid, 598, offset)
        add(f"grid_internal_power_{phase}", 40001 + offset, raw, s16(raw), "W", "inversores", f"Potência interna da rede {phase.upper()}")
    raw = at(grid, 598, 607)
    add("grid_internal_power_total", 40608, raw, s16(raw), "W", "inversores", "Potência interna total da rede")
    for phase, offset in zip("abc", (610, 611, 612)):
        raw = at(grid, 598, offset)
        add(f"grid_internal_current_{phase}", 40001 + offset, raw, round(s16(raw) * 0.01, 2), "A", "inversores", f"Corrente interna da rede {phase.upper()}")
    for phase, offset in zip("abc", (613, 614, 615)):
        raw = at(grid, 598, offset)
        add(f"grid_ct_current_{phase}", 40001 + offset, raw, round(s16(raw) * 0.01, 2), "A", "inversores", f"Corrente do CT {phase.upper()}")
    for phase, offset in zip("abc", (616, 617, 618)):
        raw = at(grid, 598, offset)
        add(f"grid_ct_power_{phase}", 40001 + offset, raw, s16(raw), "W", "inversores", f"Potência do CT {phase.upper()}")
    raw = at(grid, 598, 619)
    add("grid_ct_power_total", 40620, raw, s16(raw), "W", "inversores", "Potência total do CT")
    raw = at(grid, 598, 621)
    add("grid_power_factor", 40622, raw, round(s16(raw) / 1000, 3), "", "inversores", "Fator de potência da rede")
    for phase, offset in zip("abc", (622, 623, 624)):
        raw = at(grid, 598, offset)
        add(f"grid_side_power_{phase}", 40001 + offset, raw, s16(raw), "W", "inversores", f"Potência do lado da rede {phase.upper()}")
    raw = at(grid, 598, 625)
    add("grid_side_power_total", 40626, raw, s16(raw), "W", "inversores", "Potência total do lado da rede")

    # Inverter AC output and load output; load-current registers 647..649 are
    # explicitly marked unusable in the protocol and are intentionally omitted.
    for phase, offset in zip("abc", (627, 628, 629)):
        raw = at(output, 627, offset)
        add(f"inverter_voltage_{phase}", 40001 + offset, raw, round(u16(raw) * 0.1, 1), "V", "inversores", f"Tensão do inversor {phase.upper()}")
    for phase, offset in zip("abc", (630, 631, 632)):
        raw = at(output, 627, offset)
        add(f"inverter_current_{phase}", 40001 + offset, raw, round(s16(raw) * 0.01, 2), "A", "inversores", f"Corrente do inversor {phase.upper()}")
    for phase, offset in zip("abc", (633, 634, 635)):
        raw = at(output, 627, offset)
        add(f"inverter_power_{phase}", 40001 + offset, raw, s16(raw), "W", "inversores", f"Potência do inversor {phase.upper()}")
    raw = at(output, 627, 636)
    add("inverter_power_total", 40637, raw, s16(raw), "W", "inversores", "Potência total do inversor")
    raw = at(output, 627, 638)
    add("inverter_frequency", 40639, raw, round(u16(raw) * 0.01, 2), "Hz", "inversores", "Frequência do inversor")
    for phase, offset in zip("abc", (640, 641, 642)):
        raw = at(output, 627, offset)
        add(f"ups_load_power_{phase}", 40001 + offset, raw, u16(raw), "W", "inversores", f"Potência da saída UPS {phase.upper()}")
    raw = at(output, 627, 643)
    add("ups_load_power_total", 40644, raw, u16(raw), "W", "inversores", "Potência total da saída UPS")
    for phase, offset in zip("abc", (644, 645, 646)):
        raw = at(output, 627, offset)
        add(f"load_voltage_{phase}", 40001 + offset, raw, round(u16(raw) * 0.1, 1), "V", "inversores", f"Tensão da carga {phase.upper()}")
    for phase, offset in zip("abc", (650, 651, 652)):
        raw = at(output, 627, offset)
        add(f"load_power_{phase}", 40001 + offset, raw, s16(raw), "W", "inversores", f"Potência da carga {phase.upper()}")
    raw = at(output, 627, 653)
    add("load_total_power", 40654, raw, s16(raw), "W", "inversores", "Consumo total das cargas")

    metric_values = {item["field"]: item["value"] for item in metrics}
    quality_checks: list[dict[str, Any]] = []
    if device_type != 0x0500:
        quality_checks.append({"field": "device_type", "state": "protocol_value_mismatch",
                              "expected": "0x0500", "observed_raw": device_type})
    for mppt in ("pv1", "pv2"):
        voltage = metric_values[f"{mppt}_voltage"]
        current = metric_values[f"{mppt}_current"]
        power = metric_values[f"{mppt}_input_power"]
        calculated = voltage * current
        difference = abs(power - calculated)
        tolerance = max(50.0, max(power, calculated) * 0.2)
        quality_checks.append({"field": f"{mppt}_power_vs_voltage_current", "state": "consistent" if difference <= tolerance else "inconsistent",
                              "register_power_w": power, "voltage_times_current_w": round(calculated, 1),
                              "difference_w": round(difference, 1), "tolerance_w": round(tolerance, 1)})
    if all(metric_values.get(f"grid_voltage_{phase}") == 0 for phase in "abc") and metric_values.get("grid_frequency") == 0:
        quality_checks.append({"field": "grid_voltage_and_frequency", "state": "all_zero_check_meter_or_logger_mapping"})

    return {
        "device_type_code": device_type,
        "status_code": status,
        "metrics": metrics,
        "quality_checks": quality_checks,
        "read_windows": [
            {"start_address": 0, "count": 1}, {"start_address": 108, "count": 2},
            {"start_address": 500, "count": 1}, {"start_address": 514, "count": 22},
            {"start_address": 586, "count": 7}, {"start_address": 598, "count": 28},
            {"start_address": 627, "count": 29}, {"start_address": 672, "count": 8},
        ],
        "register_map": {
            "source": _DEYE_SG05LP3_MAP_SOURCE,
            "sha256": _DEYE_SG05LP3_MAP_SHA256,
            "supplement": "docs/deye/SG05LP3-register-map-supplement.tsv",
            "protocol_reference": "Deye three-phase energy-storage Modbus protocol registers 108-109 and 514-535; cross-checked against public SG04/SG05 LP3 implementation",
            "status": "COMMUNITY_MAP_LIVE_BLOCKS_CONFIRMED_NOT_MANUFACTURER_FIRMWARE_VALIDATED",
            "address_convention": "zero-based_PDU_offset_0_is_40001_reference",
            "notes": ["Only two MPPT channels are enabled for the configured 2-MPPT product family.",
                      "Daily per-MPPT PV energy counters 40531-40534 are marked reserved and are not decoded.",
                      "Battery current limits are configuration values read using FC03; no write is issued.",
                      "Grid totals are exposed as separate internal, external CT and grid-side readings because their source depends on inverter meter configuration.",
                      "Load-current offsets 647-649 are omitted; protocol labels them unusable.",
                      "No Modbus writes are implemented or sent."],
        },
    }


def read_deye(config: dict[str, Any]) -> dict[str, Any]:
    host, port, unit = config["host"], config["port"], config.get("unit_id", 1)
    # FC43/MEI 14 is optional in Modbus devices. Some inverter firmware only
    # implements FC03, so retry with a harmless, single-register read at the
    # base address if device identification is unsupported. The value is
    # deliberately discarded: this is transport/protocol detection, not a
    # verified Deye metric or register map.
    tcp = probe_tcp(host, port, timeout=2.0)
    if str(config.get("model", "")).strip().upper() == _DEYE_SG05LP3_MODEL:
        try:
            mapped = _read_deye_sg05lp3_candidate_map(host, port, unit)
            return {"host": host, "port": port, "unit_id": unit, "model": config.get("model"),
                    "tcp": tcp, "protocol": "Modbus TCP FC03 read-only",
                    "probe_method": "SG05LP3 community map; FC43 skipped",
                    "connection_state": "mapped_registers_response", "modbus_identity": None,
                    "device_type_code": mapped["device_type_code"], "status_code": mapped["status_code"],
                    "metrics": mapped["metrics"], "quality_checks": mapped["quality_checks"],
                    "register_map": mapped["register_map"],
                    "read_windows": mapped["read_windows"],
                    "metrics_decoded": True, "trust": "LIVE_UNVERIFIED",
                    "reason": "candidate_map_registers_responded; exact_firmware_semantics_unverified",
                    "diagnostic_detail": "Registos de FV/MPPT, bateria, rede e cargas responderam. O mapa é baseado no protocolo trifásico Deye e numa implementação pública SG04/SG05; confirmar a variante de firmware e a configuração do contador/CT antes de usar os valores em automações.",
                    "web_ui_credentials_apply_to_modbus": False, "control_commands_sent": False}
        except deye_modbus.ModbusError as exc:
            return {"host": host, "port": port, "unit_id": unit, "model": config.get("model"),
                    "tcp": tcp, "protocol": "Modbus TCP FC03 read-only",
                    "probe_method": "SG05LP3 community map; FC43 skipped",
                    "connection_state": "mapped_register_read_failed", "metrics_decoded": False,
                    "register_map": {"source": _DEYE_SG05LP3_MAP_SOURCE, "sha256": _DEYE_SG05LP3_MAP_SHA256,
                                     "status": "COMMUNITY_MAP_NOT_FULLY_VALIDATED"},
                    "web_ui_credentials_apply_to_modbus": False,
                    "diagnostic_detail": f"A leitura Modbus do mapa candidato falhou ({type(exc).__name__}); FC43 não foi enviado.",
                    "reason": "mapped_register_read_failed", "trust": "UNAVAILABLE", "control_commands_sent": False}
    probe_method = "FC43/MEI14"

    def fc03_fallback(fc43_error: str) -> tuple[str, dict[str, Any] | None, str]:
        try:
            read = deye_modbus.read_holding_registers(host, start_address=0, count=1,
                                                       port=port, unit_id=unit, timeout=2.0)
            return ("modbus_register_probe_response",
                    {"function_code": read.function_code, "register_count": read.register_count,
                     "value_discarded": True, "fc43_result": fc43_error},
                    "modbus_reachable_model_register_map_not_verified")
        except deye_modbus.ModbusExceptionResponse as exc:
            return ("modbus_exception_response",
                    {"function_code": exc.function_code, "exception_code": exc.exception_code,
                     "fc43_result": fc43_error},
                    "device_replied_to_modbus_but_rejected_identification_and_base_register_probe")
        except deye_modbus.ModbusTimeout:
            return ("modbus_timeout", {"fc43_result": fc43_error},
                    "modbus_identification_failed_then_register_probe_timed_out")
        except deye_modbus.ModbusProtocolError as exc:
            return ("invalid_modbus_response", {"error": str(exc), "fc43_result": fc43_error},
                    "invalid_modbus_response_during_register_probe")
        except deye_modbus.ModbusError as exc:
            return ("modbus_transport_error", {"error": str(exc), "fc43_result": fc43_error},
                    "modbus_transport_error_during_register_probe")

    try:
        identity = deye_modbus.read_device_identification(host, port=port, unit_id=unit, timeout=2.0)
        modbus_state = identity["state"]
        identity_data = identity
        reason = "model_register_map_not_verified"
    except deye_modbus.ModbusExceptionResponse as exc:
        probe_method = "FC03 fallback after FC43 exception"
        modbus_state, identity_data, reason = fc03_fallback(f"exception:{exc.exception_code}")
    except deye_modbus.ModbusTimeout:
        probe_method = "FC03 fallback after FC43 timeout"
        modbus_state, identity_data, reason = fc03_fallback("timeout")
    except deye_modbus.ModbusProtocolError as exc:
        modbus_state = "invalid_modbus_response"
        identity_data = {"error": str(exc)}
        reason = "invalid_modbus_response_check_target_and_protocol"
    except deye_modbus.ModbusError as exc:
        modbus_state = "modbus_transport_error"
        identity_data = {"error": str(exc)}
        reason = "modbus_transport_error"
    return {"host": host, "port": port, "unit_id": unit, "model": config.get("model"),
            "tcp": tcp,
            "protocol": "Modbus TCP read-only protocol probe",
            "probe_method": probe_method,
            "connection_state": modbus_state, "modbus_identity": identity_data,
            "web_ui_credentials_apply_to_modbus": False,
            "diagnostic_detail": ("TCP respondeu, mas FC43 e a leitura FC03 não receberam resposta Modbus. O login da página web é independente; confirmar que Link 2 Modbus TCP está ativo e que o Unit ID corresponde ao endereço Modbus do inversor." if modbus_state == "modbus_timeout" else None),
            "metrics_decoded": False, "reason": reason, "trust": "LIVE_UNVERIFIED",
            "control_commands_sent": False}


def _tesla_http(url: str, *, token: str | None = None, form: dict[str, str] | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": "SolarMiner-Gateway"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode("ascii")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=12.0) as response:
            raw = response.read(2_097_153)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"tesla_http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("tesla_connection_failed") from exc
    if len(raw) > 2_097_152: raise RuntimeError("tesla_response_too_large")
    try: payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise RuntimeError("tesla_invalid_json") from exc
    if not isinstance(payload, dict): raise RuntimeError("tesla_invalid_response")
    if "error" in payload: raise RuntimeError("tesla_api_rejected_request")
    return payload


def read_tesla(config: dict[str, Any], persist_rotated_token=None) -> tuple[dict[str, Any], str]:
    """Refresh OAuth credentials and read explicitly selected Tesla vehicles only."""
    region = config.get("region")
    if region not in TESLA_API_BASES: raise ValueError("invalid_tesla_region")
    auth = _tesla_http(TESLA_AUTH_URL, form={
        "grant_type": "refresh_token", "client_id": config["client_id"],
        "refresh_token": config["refresh_token"],
    })
    access_token, rotated_refresh = auth.get("access_token"), auth.get("refresh_token")
    if not isinstance(access_token, str) or not access_token or not isinstance(rotated_refresh, str) or not rotated_refresh:
        raise RuntimeError("tesla_token_refresh_invalid")
    if persist_rotated_token is not None:
        # Refresh tokens are single-use/rotating; save the replacement before
        # making any billable vehicle-data request that could subsequently fail.
        persist_rotated_token(rotated_refresh)
    base = TESLA_API_BASES[region]
    vehicles_payload = _tesla_http(base + "/api/1/vehicles", token=access_token)
    vehicles = vehicles_payload.get("response")
    if not isinstance(vehicles, list): raise RuntimeError("tesla_vehicle_list_invalid")
    selected = set(config.get("vehicle_ids", []))
    output = []
    for vehicle in vehicles:
        if not isinstance(vehicle, dict): continue
        vehicle_id = str(vehicle.get("id_s") or vehicle.get("id") or "")
        vin = vehicle.get("vin")
        if vehicle_id not in selected and vin not in selected: continue
        if not vehicle_id.isdigit(): continue
        detail = _tesla_http(base + f"/api/1/vehicles/{vehicle_id}/vehicle_data", token=access_token).get("response")
        if not isinstance(detail, dict): raise RuntimeError("tesla_vehicle_data_invalid")
        # Copy only approved fields; nested Tesla payloads can contain location data.
        charge = detail.get("charge_state") if isinstance(detail.get("charge_state"), dict) else {}
        safe_charge = {key: charge[key] for key in ("battery_level", "charging_state", "charge_limit_soc", "charger_power", "charge_rate", "time_to_full_charge", "plugged_in") if key in charge}
        output.append({"vehicle_id": vehicle_id, "name": vehicle.get("display_name"), "vin_suffix": vin[-4:] if isinstance(vin, str) and len(vin) >= 4 else None,
                       "charge_state": safe_charge, "trust": "LIVE_UNVERIFIED"})
    return ({"vehicles": output, "selected_count": len(selected), "source": "TESLA_FLEET_API_EV_CHARGING_READ_ONLY", "trust": "LIVE_UNVERIFIED", "control_commands_sent": False, "observed_at": time.time()}, rotated_refresh)


def collect(config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"deye": None, "antminer": None, "tuya": [], "errors": [],
                              "configuration": {"deye": "configured" if config.get("deye", {}).get("host") else "not_configured",
                                                "antminer": "configured" if config.get("antminer", {}).get("host") else "not_configured"},
                              "collected_at": time.time()}
    if config.get("deye", {}).get("host"):
        try: result["deye"] = read_deye(config["deye"])
        except Exception as exc:
            reason = str(exc)[:160]
            result["errors"].append({"provider": "deye", "reason": reason})
            result["deye"] = {"host": config["deye"].get("host"), "port": config["deye"].get("port", 502),
                               "connection_state": "tcp_unreachable" if reason.startswith(("tcp_", "network_unreachable", "host_unreachable")) else "failed",
                               "reason": reason, "metrics_decoded": False}
    if config.get("antminer", {}).get("host"):
        host, port = config["antminer"]["host"], config["antminer"]["port"]
        try:
            tcp = probe_tcp(host, port, timeout=2.0)
            result["antminer"] = read_antminer(host, port)
            result["antminer"]["tcp"] = tcp
        except Exception as exc:
            reason = str(exc)[:160]
            result["errors"].append({"provider": "antminer", "reason": reason})
            result["antminer"] = {"host": host, "port": port,
                                   "connection_state": "tcp_reachable_api_failed" if reason.startswith("antminer_") else "tcp_unreachable",
                                   "reason": reason}
    if config.get("tuya", {}).get("devices"):
        try:
            result["tuya"] = read_tuya(config["tuya"])
            result["configuration"]["tuya"] = "configured"
            for device in result["tuya"]:
                if device.get("connection_state") == "failed":
                    result["errors"].append({"provider": "tuya", "device_id": device["device_id"],
                                             "reason": device["reason"]})
        except Exception as exc: result["errors"].append({"provider": "tuya", "reason": str(exc)[:160]})
    else:
        result["configuration"]["tuya"] = "not_configured"
    return result


def read_tesla_ev(config: dict[str, Any]) -> dict[str, Any]:
    with _TESLA_EV_READ_LOCK:
        config = validate_tesla_config(config, {"tesla": config})
        def persist_rotated_token(rotated: str) -> None:
            full_config = load_config()
            full_config["tesla"] = {**config, "refresh_token": rotated}
            save_config(full_config)
            config["refresh_token"] = rotated
        result, _rotated = read_tesla(config, persist_rotated_token)
        return result
