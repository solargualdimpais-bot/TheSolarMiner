"""Owner-configured, read-only SolarMiner hardware integrations.

Credentials and endpoints are stored on the Gateway under its private data
directory. This module exposes no device-control operations.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from . import deye_modbus

TUYA_REGIONS = {
    "china": "https://openapi.tuyacn.com",
    "us": "https://openapi.tuyaus.com",
    "us_east": "https://openapi-ueaz.tuyaus.com",
    "eu_central": "https://openapi.tuyaeu.com",
    "eu_west": "https://openapi-weaz.tuyaeu.com",
    "india": "https://openapi.tuyain.com",
    "singapore": "https://openapi-sg.iotbing.com",
}
MAX_CONFIG_BYTES = 32_768
CGMINER_COMMANDS = ("summary", "stats", "devs")


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
        "antminer": {k: config.get("antminer", {}).get(k) for k in ("host", "port", "model") if config.get("antminer", {}).get(k) is not None},
        "tuya": {"region": tuya.get("region"), "client_id": tuya.get("client_id"), "device_ids": [x.get("device_id") for x in tuya.get("devices", []) if isinstance(x, dict)], "devices": [{"device_id": x.get("device_id"), "name": x.get("name")} for x in tuya.get("devices", []) if isinstance(x, dict)], "configured": bool(tuya.get("client_id") and tuya.get("client_secret"))},
        "secrets_returned": False,
    }


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
    old = existing if existing is not None else load_config()
    result: dict[str, Any] = {k: old.get(k, {}) for k in ("deye", "antminer", "tuya")}
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
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535: raise ValueError("invalid_port")
            model = item.get("model", "S19K Pro")
            if model != "S19K Pro": raise ValueError("unsupported_antminer_model")
            result["antminer"] = {"host": host, "port": port, "model": model}
        else: result["antminer"] = {}
    if "tuya" in payload:
        item = payload["tuya"]
        if not isinstance(item, dict): raise ValueError("invalid_tuya_config")
        region = item.get("region", result.get("tuya", {}).get("region", "eu_central"))
        if region not in TUYA_REGIONS: raise ValueError("invalid_tuya_region")
        client_id = item.get("client_id", result.get("tuya", {}).get("client_id"))
        client_secret = item.get("client_secret") or result.get("tuya", {}).get("client_secret")
        if client_id is not None and (not isinstance(client_id, str) or not 1 <= len(client_id) <= 128): raise ValueError("invalid_tuya_client_id")
        if client_secret is not None and (not isinstance(client_secret, str) or not 8 <= len(client_secret) <= 256): raise ValueError("invalid_tuya_client_secret")
        devices = item.get("devices", result.get("tuya", {}).get("devices", []))
        if not isinstance(devices, list) or len(devices) > 50: raise ValueError("invalid_tuya_devices")
        normalized = []
        for device in devices:
            if not isinstance(device, dict): raise ValueError("invalid_tuya_device")
            device_id, name = device.get("device_id"), device.get("name", "Tuya device")
            if not isinstance(device_id, str) or not 1 <= len(device_id) <= 128 or not all(c.isalnum() or c in "_-" for c in device_id): raise ValueError("invalid_tuya_device_id")
            if not isinstance(name, str) or not name.strip() or len(name) > 120: raise ValueError("invalid_tuya_device_name")
            normalized.append({"device_id": device_id, "name": name.strip()})
        if normalized and (not client_id or not client_secret): raise ValueError("tuya_credentials_required")
        result["tuya"] = {"region": region, "client_id": client_id, "client_secret": client_secret, "devices": normalized}
    return result


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
        raise RuntimeError("tuya_api_rejected_request")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect_rejected", headers, fp)


def _tuya_request(config: dict[str, Any], path: str, token: str | None = None) -> dict[str, Any]:
    client_id, secret = config["client_id"], config["client_secret"]
    timestamp, nonce = str(int(time.time() * 1000)), uuid.uuid4().hex
    canonical = f"GET\n{hashlib.sha256(b'').hexdigest()}\n\n{path}"
    to_sign = client_id + (token or "") + timestamp + nonce + canonical
    signature = hmac.new(secret.encode(), to_sign.encode(), hashlib.sha256).hexdigest().upper()
    headers = {"client_id": client_id, "sign": signature, "sign_method": "HMAC-SHA256", "t": timestamp, "nonce": nonce}
    if token: headers["access_token"] = token
    return _json_request(TUYA_REGIONS[config["region"]] + path, headers)


def read_tuya(config: dict[str, Any]) -> list[dict[str, Any]]:
    if not config.get("client_id") or not config.get("client_secret"): raise ValueError("tuya_credentials_required")
    auth = _tuya_request(config, "/v1.0/token?grant_type=1")
    token = (auth.get("result") or {}).get("access_token")
    if not isinstance(token, str) or not token: raise RuntimeError("tuya_token_missing")
    output = []
    for item in config.get("devices", []):
        device_id = item["device_id"]
        result = _tuya_request(config, f"/v1.0/devices/{urllib.parse.quote(device_id, safe='')}/status", token).get("result")
        if not isinstance(result, list): raise RuntimeError("tuya_status_invalid")
        output.append({"device_id": device_id, "name": item["name"], "status": result, "source": "TUYA_CLOUD_READ_ONLY", "trust": "LIVE_UNVERIFIED", "observed_at": time.time()})
    return output


def read_antminer(host: str, port: int = 4028, timeout: float = 2.0) -> dict[str, Any]:
    address = _private_ip(host)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535: raise ValueError("invalid_port")
    responses = {}
    for command in CGMINER_COMMANDS:
        message = json.dumps({"command": command}, separators=(",", ":")).encode() + b"\0"
        try:
            with socket.create_connection((address, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                sock.sendall(message)
                chunks, total = [], 0
                while total < 262_144:
                    part = sock.recv(min(16_384, 262_144 - total))
                    if not part: break
                    chunks.append(part); total += len(part)
                    if b"\0" in part: break
        except (OSError, TimeoutError) as exc:
            raise RuntimeError(f"antminer_{command}_connection_failed") from exc
        raw = b"".join(chunks).split(b"\0", 1)[0].strip()
        if not raw: raise RuntimeError(f"antminer_{command}_empty_response")
        try: response = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc: raise RuntimeError(f"antminer_{command}_invalid_json") from exc
        if not isinstance(response, dict): raise RuntimeError(f"antminer_{command}_invalid_response")
        responses[command] = response
    return {"host": address, "port": port, "model": "S19K Pro", "protocol": "CGMiner-compatible read-only", "commands": list(CGMINER_COMMANDS), "data": responses, "trust": "LIVE_UNVERIFIED", "control_commands_sent": False, "observed_at": time.time()}


def read_deye(config: dict[str, Any]) -> dict[str, Any]:
    host, port, unit = config["host"], config["port"], config.get("unit_id", 1)
    result = deye_modbus.read_holding_registers(host, 0, 1, port=port, unit_id=unit, timeout=2.0)
    return {"model": config.get("model"), "protocol": "Modbus TCP FC03 read-only", "result": result.as_dict(), "metrics_decoded": False, "reason": "model_register_map_not_verified", "trust": "LIVE_UNVERIFIED", "control_commands_sent": False}


def collect(config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"deye": None, "antminer": None, "tuya": [], "errors": [], "collected_at": time.time()}
    if config.get("deye", {}).get("host"):
        try: result["deye"] = read_deye(config["deye"])
        except Exception as exc: result["errors"].append({"provider": "deye", "reason": str(exc)[:160]})
    if config.get("antminer", {}).get("host"):
        try: result["antminer"] = read_antminer(config["antminer"]["host"], config["antminer"]["port"])
        except Exception as exc: result["errors"].append({"provider": "antminer", "reason": str(exc)[:160]})
    if config.get("tuya", {}).get("devices"):
        try: result["tuya"] = read_tuya(config["tuya"])
        except Exception as exc: result["errors"].append({"provider": "tuya", "reason": str(exc)[:160]})
    return result
