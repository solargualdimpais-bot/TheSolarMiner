"""Local Shelly Gen1 HTTP and Gen2+ RPC adapters."""
from __future__ import annotations

import ipaddress
import json
import re
import concurrent.futures
import threading
import time
import uuid
import urllib.error
import urllib.request
from typing import Any

_DEVICE_IO_LIMIT = threading.BoundedSemaphore(8)
_BLU_DISCOVERY_LOCK = threading.Lock()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect_rejected", headers, fp)


def _host(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("shelly_private_ip_required")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("shelly_private_ip_required") from exc
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
        raise ValueError("shelly_private_ip_required")
    return str(address)


def _request(host: str, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
             username: str = "", password: str = "", timeout: float = 3.0) -> dict[str, Any]:
    host = _host(host)
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "SolarMiner-Gateway"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"http://{host}{path}", data=body, headers=headers, method=method)
    try:
        handlers: list[Any] = [_NoRedirect()]
        if username or password:
            password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            password_manager.add_password(None, f"http://{host}/", username, password)
            handlers.extend([urllib.request.HTTPDigestAuthHandler(password_manager),
                             urllib.request.HTTPBasicAuthHandler(password_manager)])
        with urllib.request.build_opener(*handlers).open(request, timeout=timeout) as response:
            raw = response.read(262145)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"shelly_http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("shelly_connection_failed") from exc
    if len(raw) > 262144:
        raise RuntimeError("shelly_response_too_large")
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("shelly_invalid_json") from exc
    if not isinstance(result, dict):
        raise RuntimeError("shelly_invalid_response")
    return result


def _rpc(host: str, method: str, params: dict[str, Any] | None = None, **auth: str) -> dict[str, Any]:
    result = _request(host, "/rpc", method="POST", payload={"id": 1, "method": method,
                     **({"params": params} if params is not None else {})}, **auth)
    if result.get("error"):
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        if error.get("code") == -32601:
            raise RuntimeError("shelly_rpc_method_not_found")
        raise RuntimeError("shelly_rpc_rejected")
    value = result.get("result")
    if not isinstance(value, dict):
        raise RuntimeError("shelly_rpc_invalid_result")
    return value


def identify_and_read(host: str, *, username: str = "", password: str = "") -> dict[str, Any]:
    """Try Shelly RPC first, then Gen1 HTTP. Return normalized evidence, no commands."""
    host = _host(host)
    auth = {"username": username, "password": password}
    try:
        info = _rpc(host, "Shelly.GetDeviceInfo", **auth)
        status = _rpc(host, "Shelly.GetStatus", **auth)
        components = []
        for key, value in status.items():
            match = re.fullmatch(r"(switch|cover|input|temperature|voltmeter|em|pm|devicepower|light|rgb|rgbw|cct):(\d+)", str(key))
            if match and isinstance(value, dict):
                components.append({"component": match.group(1), "id": int(match.group(2)), "status": value})
            elif key == "ble" and isinstance(value, dict):
                components.append({"component": "ble", "id": 0, "status": value})
        capabilities = []
        for component in components:
            name = component["component"]
            capability = {"switch": "relay", "cover": "cover", "input": "input", "temperature": "temperature",
                          "voltmeter": "voltage", "em": "energy", "pm": "power", "devicepower": "device_power",
                          "light": "dimming", "rgb": "color", "rgbw": "color", "cct": "color_temperature",
                          "ble": "bluetooth"}.get(name)
            if capability and capability not in capabilities:
                capabilities.append(capability)
            component_status = component.get("status") if isinstance(component.get("status"), dict) else {}
            measured = {
                "power": any(key in component_status for key in ("apower", "active_power", "power")),
                "voltage": "voltage" in component_status,
                "current": "current" in component_status,
                "energy": any(key in component_status for key in ("aenergy", "energy", "total")),
            }
            for metric, present in measured.items():
                if present and metric not in capabilities:
                    capabilities.append(metric)
        return {"host": host, "manufacturer": "Shelly", "model": str(info.get("model") or info.get("app") or "")[:120],
                "device_id": str(info.get("id") or "")[:120], "mac": str(info.get("mac") or "").upper(),
                "firmware": str(info.get("ver") or "")[:80], "generation": int(info.get("gen", 2)),
                "protocol": "shelly_rpc", "connection_state": "connected", "components": components,
                "capabilities": capabilities, "status": status, "observed_at": __import__("time").time(),
                "command_sent": False}
    except RuntimeError as exc:
        if str(exc) not in {"shelly_rpc_method_not_found", "shelly_http_404", "shelly_http_405"}:
            raise
    info = _request(host, "/shelly", **auth)
    status = _request(host, "/status", **auth)
    if not any(key in info for key in ("type", "mac", "fw")):
        raise RuntimeError("shelly_device_not_identified")
    components = []
    for key, rows in (("relays", "relay"), ("meters", "meter"), ("emeters", "emeter")):
        values = status.get(key)
        if isinstance(values, list):
            components.extend({"component": rows, "id": index, "status": item}
                              for index, item in enumerate(values) if isinstance(item, dict))
    lights = status.get("lights")
    if isinstance(lights, list):
        color_model = "color" in str(info.get("type") or "").lower() or "bulb" in str(info.get("type") or "").lower()
        for index, item in enumerate(lights):
            if isinstance(item, dict):
                components.append({"component": "color" if color_model else "light", "id": index, "status": item})
    capabilities = []
    if components:
        capabilities.append("relay")
    if any(row.get("component") in {"meter", "emeter"} for row in components):
        capabilities.extend(["power", "energy"])
    for row in components:
        kind, light_status = row.get("component"), row.get("status", {})
        if kind in {"light", "color"}:
            capabilities.append("dimming")
        if kind == "color" and any(key in light_status for key in ("red", "green", "blue")):
            capabilities.append("color")
        if kind == "color" and "temp" in light_status:
            capabilities.append("color_temperature")
        for key, capability in (("power", "power"), ("voltage", "voltage"), ("current", "current"), ("energy", "energy")):
            if key in light_status and capability not in capabilities:
                capabilities.append(capability)
    return {"host": host, "manufacturer": "Shelly", "model": str(info.get("type") or "Shelly Gen1")[:120],
            "device_id": str(info.get("device") or "")[:120], "mac": str(info.get("mac") or "").upper(),
            "firmware": str(info.get("fw") or "")[:80], "generation": 1, "protocol": "shelly_http_gen1",
            "connection_state": "connected", "components": components, "capabilities": capabilities,
            "status": status, "observed_at": __import__("time").time(), "command_sent": False}


def control_light(host: str, generation: int, component: str, channel: int, *, on: bool | None = None,
                  brightness: int | None = None, rgb: list[int] | None = None, white: int | None = None,
                  color_temperature: int | None = None, username: str = "", password: str = "") -> dict[str, Any]:
    """Apply a bounded light setting once and verify it through a fresh local read."""
    host = _host(host)
    allowed = {"light", "rgb", "rgbw", "cct", "color"}
    if component not in allowed or isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 31:
        raise ValueError("shelly_light_component_invalid")
    if on is None and brightness is None and rgb is None and white is None and color_temperature is None:
        raise ValueError("shelly_light_command_empty")
    if on is not None and not isinstance(on, bool):
        raise ValueError("shelly_light_state_invalid")
    if brightness is not None and (isinstance(brightness, bool) or not isinstance(brightness, int) or not 0 <= brightness <= 100):
        raise ValueError("shelly_brightness_invalid")
    if rgb is not None and (not isinstance(rgb, list) or len(rgb) != 3 or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255 for v in rgb)):
        raise ValueError("shelly_rgb_invalid")
    if white is not None and (isinstance(white, bool) or not isinstance(white, int) or not 0 <= white <= 255):
        raise ValueError("shelly_white_invalid")
    if color_temperature is not None and (isinstance(color_temperature, bool) or not isinstance(color_temperature, int) or not 2000 <= color_temperature <= 10000):
        raise ValueError("shelly_color_temperature_invalid")
    auth = {"username": username, "password": password}
    command_started = time.perf_counter()
    if generation >= 2:
        rpc_component = {"color": "rgb", "light": "light"}.get(component, component)
        method = {"light": "Light.Set", "rgb": "RGB.Set", "rgbw": "RGBW.Set", "cct": "CCT.Set"}.get(rpc_component)
        if not method:
            raise ValueError("shelly_light_component_invalid")
        params: dict[str, Any] = {"id": channel}
        if on is not None: params["on"] = on
        if brightness is not None: params["brightness"] = brightness
        if rgb is not None: params["rgb"] = rgb
        if white is not None: params["white"] = white
        if color_temperature is not None: params["ct"] = color_temperature
        _rpc(host, method, params, **auth)
    elif generation == 1:
        from urllib.parse import urlencode
        query: dict[str, Any] = {}
        if on is not None: query["turn"] = "on" if on else "off"
        if brightness is not None: query["brightness"] = brightness
        if component in {"color", "rgb", "rgbw"} or rgb is not None or white is not None:
            if rgb is not None:
                query.update({"red": rgb[0], "green": rgb[1], "blue": rgb[2], "mode": "color"})
            if white is not None: query["white"] = white
            if color_temperature is not None: query.update({"temp": color_temperature, "mode": "white"})
            endpoint = f"/color/{channel}"
        else:
            if color_temperature is not None: query["temp"] = color_temperature
            endpoint = f"/light/{channel}"
        _request(host, f"{endpoint}?{urlencode(query)}", **auth)
    else:
        raise ValueError("shelly_generation_unsupported")
    device_command_latency_ms = round((time.perf_counter() - command_started) * 1000)
    readback_started = time.perf_counter()
    reading = identify_and_read(host, **auth)
    readback_latency_ms = round((time.perf_counter() - readback_started) * 1000)
    state = "CONFIRMED"
    for item in reading.get("components", []):
        if item.get("component") not in {component, "color" if component in {"rgb", "rgbw"} else component} or item.get("id") != channel:
            continue
        observed = item.get("status", {})
        if on is not None and observed.get("output", observed.get("ison")) != on: state = "UNKNOWN"
        if brightness is not None and observed.get("brightness") != brightness: state = "UNKNOWN"
        if rgb is not None and observed.get("rgb", [observed.get("red"), observed.get("green"), observed.get("blue")]) != rgb: state = "UNKNOWN"
        if color_temperature is not None and observed.get("ct", observed.get("temp")) != color_temperature: state = "UNKNOWN"
        break
    else:
        state = "UNKNOWN"
    return {"command_accepted": True, "command_confirmed": state == "CONFIRMED", "command_state": state,
            "device_command_latency_ms": device_command_latency_ms, "readback_latency_ms": readback_latency_ms,
            "reading": reading}


def control_switch(host: str, generation: int, channel: int, on: bool, *, username: str = "", password: str = "") -> dict[str, Any]:
    """Set an idempotent relay state once, then verify with a fresh read."""
    host = _host(host)
    if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 31:
        raise ValueError("shelly_switch_channel_invalid")
    if not isinstance(on, bool):
        raise ValueError("shelly_switch_state_invalid")
    auth = {"username": username, "password": password}
    command_started = time.perf_counter()
    if generation >= 2:
        _rpc(host, "Switch.Set", {"id": channel, "on": on}, **auth)
    elif generation == 1:
        from urllib.parse import urlencode
        _request(host, f"/relay/{channel}?{urlencode({'turn': 'on' if on else 'off'})}", **auth)
    else:
        raise ValueError("shelly_generation_unsupported")
    device_command_latency_ms = round((time.perf_counter() - command_started) * 1000)
    readback_started = time.perf_counter()
    verified = identify_and_read(host, **auth)
    readback_latency_ms = round((time.perf_counter() - readback_started) * 1000)
    observed = None
    for component in verified.get("components", []):
        status = component.get("status", {})
        if component.get("id") == channel and component.get("component") in {"switch", "relay"}:
            observed = status.get("output", status.get("ison"))
            break
    if isinstance(observed, bool) and observed == on:
        state = "CONFIRMED"
    else:
        state = "UNKNOWN"
    return {"connection_state": "connected", "command_accepted": True,
            "command_confirmed": state == "CONFIRMED", "command_state": state,
            "requested_on": on, "observed_on": observed, "device_command_latency_ms": device_command_latency_ms,
            "readback_latency_ms": readback_latency_ms, "reading": verified}


def read_devices(config: dict[str, Any]) -> list[dict[str, Any]]:
    devices = config.get("devices", []) if isinstance(config, dict) else []
    eligible = [device for device in devices if isinstance(device, dict) and device.get("host")][:100] if isinstance(devices, list) else []
    def read_one(device: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(device, dict) or not device.get("host"):
            return {}
        try:
            with _DEVICE_IO_LIMIT:
                reading = identify_and_read(device["host"], username=str(device.get("username") or ""),
                                            password=str(device.get("password") or ""))
            expected_mac = _normalize_mac(device.get("mac"))
            observed_mac = _normalize_mac(reading.get("mac"))
            if expected_mac and expected_mac != observed_mac:
                return {"device_id": str(device.get("device_id") or "")[:128],
                        "name": str(device.get("name") or "Shelly device")[:120],
                        "host": device.get("host"), "mac": observed_mac, "manufacturer": "Shelly",
                        "protocol": reading.get("protocol"), "connection_state": "identity_conflict",
                        "reason": "shelly_mac_mismatch", "observed_at": __import__("time").time(),
                        "command_sent": False}
            reading.update({"device_id": str(device.get("device_id") or "")[:128],
                            "name": str(device.get("name") or reading.get("model") or "Shelly device")[:120]})
            return reading
        except (RuntimeError, ValueError) as exc:
            return {"device_id": str(device.get("device_id") or "")[:128],
                            "name": str(device.get("name") or "Shelly device")[:120], "host": device.get("host"),
                            "manufacturer": "Shelly", "protocol": device.get("protocol") or "auto",
                            "connection_state": "failed", "reason": str(exc)[:120], "observed_at": __import__("time").time(),
                            "command_sent": False}
    if len(eligible) < 2:
        return [read_one(device) for device in eligible]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(eligible)), thread_name_prefix="shelly-read") as pool:
        return list(pool.map(read_one, eligible))


def inspect_bluetooth_bridge(host: str, *, username: str = "", password: str = "") -> dict[str, Any]:
    """Read-only capability probe; never changes pairing or bridge configuration."""
    reading = identify_and_read(host, username=username, password=password)
    components = reading.get("components", [])
    model_evidence = " ".join(str(reading.get(key) or "") for key in ("model", "device_id")).casefold()
    compact_evidence = re.sub(r"[^a-z0-9]", "", model_evidence)
    known_gateway_model = (any(token in model_evidence for token in ("blu gateway", "blu gw", "blugw", "gwf-kz01"))
                           or "sngwbt01" in compact_evidence)
    has_ble = "bluetooth" in reading.get("capabilities", []) or any(
        isinstance(item, dict) and item.get("component") == "ble" for item in components) or known_gateway_model
    try:
        _rpc(host, "BTHome.GetStatus", username=username, password=password)
        bthome_api = True
    except RuntimeError as exc:
        if str(exc) in {"shelly_http_401", "shelly_http_403"}:
            return {"bridge_candidate": has_ble, "ble_component": has_ble,
                    "bthome_discovery_api": "authentication_required", "model": reading.get("model"),
                    "firmware": reading.get("firmware"), "generation": reading.get("generation"),
                    "mac": reading.get("mac"), "host": reading.get("host")}
        bthome_api = False
    return {"bridge_candidate": has_ble, "ble_component": has_ble,
            "bthome_discovery_api": "available" if bthome_api else "not_supported",
            "model": reading.get("model"), "firmware": reading.get("firmware"),
            "generation": reading.get("generation"), "mac": reading.get("mac"), "host": reading.get("host")}


def discover_bluetooth_devices(host: str, *, username: str = "", password: str = "",
                               duration_seconds: float = 30.0) -> dict[str, Any]:
    """Discover Shelly BLU advertisements through a compatible Shelly BLE bridge.

    The bridge runs a uniquely named, short-lived scanner script. Existing user
    scripts are never read, overwritten, stopped, or deleted. The temporary slot
    is removed in a finally block, including on scan or parsing failures.
    """
    host = _host(host)
    try:
        # Battery sensors can advertise infrequently unless the user wakes
        # them. Five seconds caused false negatives in the add flow.
        duration_seconds = max(5.0, min(60.0, float(duration_seconds)))
    except (TypeError, ValueError):
        duration_seconds = 5.0
    bridge = inspect_bluetooth_bridge(host, username=username, password=password)
    model = str(bridge.get("model") or "")
    if not bridge.get("bridge_candidate") or int(bridge.get("generation") or 0) < 2:
        return {"bridge": bridge, "supported": False, "devices": [], "reason": "bluetooth_scanner_not_supported"}

    script_id: int | None = None
    with _BLU_DISCOVERY_LOCK:
        try:
            script_list = _rpc(host, "Script.List", username=username, password=password)
            scripts = script_list.get("scripts", [])
            if not isinstance(scripts, list):
                raise RuntimeError("shelly_script_list_invalid")
            managed = [item for item in scripts if isinstance(item, dict)
                       and str(item.get("name") or "").startswith("SolarMiner BLE scan ")]
            if any(item.get("running") is True for item in managed):
                return {"bridge": bridge, "supported": False, "devices": [], "reason": "bluetooth_scan_already_running"}
            for item in managed:
                stale_id = item.get("id")
                if item.get("running") is not True and isinstance(stale_id, int) and not isinstance(stale_id, bool):
                    try:
                        _rpc(host, "Script.Delete", {"id": stale_id}, username=username, password=password)
                    except (RuntimeError, OSError, ValueError):
                        pass
            if sum(1 for item in scripts if isinstance(item, dict) and item.get("running") is True) >= 3:
                return {"bridge": bridge, "supported": False, "devices": [], "reason": "bluetooth_script_slots_busy"}
            created = _rpc(host, "Script.Create", {"name": f"SolarMiner BLE scan {uuid.uuid4().hex[:8]}"},
                           username=username, password=password)
            script_id = created.get("id")
            if isinstance(script_id, bool) or not isinstance(script_id, int) or script_id < 0:
                raise RuntimeError("shelly_script_create_invalid")
            scan_ms = int(duration_seconds * 1000)
            script_code = f'''var SolarMinerBleResults = {{}};
var SolarMinerIsRunning = typeof BLE.Scanner.isRunning === "function" ? BLE.Scanner.isRunning() :
  (typeof BLE.Scanner.IsRunning === "function" ? BLE.Scanner.IsRunning() : false);
var SolarMinerSubscribe = BLE.Scanner.subscribe || BLE.Scanner.Subscribe;
var SolarMinerStart = BLE.Scanner.start || BLE.Scanner.Start;
if (typeof SolarMinerSubscribe !== "function") throw Error("ble_scanner_subscribe_not_supported");
SolarMinerSubscribe.call(BLE.Scanner, function(event, result) {{
  if (event !== BLE.Scanner.SCAN_RESULT || !result || !result.addr) return;
  var name = String(result.local_name || "");
  var serviceData = result.service_data || result.serviceData || {{}};
  var bthome = "";
  if (serviceData && typeof serviceData === "object") {{
    for (var key in serviceData) if (String(key).toLowerCase() === "fcd2") {{ bthome = serviceData[key]; break; }}
  }}
  var shellyName = /^SB[A-Z0-9_-]{{2,}}/i.test(name) || /^Shelly BLU/i.test(name);
  if (!shellyName && !bthome) return;
  var address = String(result.addr).toUpperCase();
  var values = null;
  if (bthome && typeof BTHome !== "undefined") {{ try {{ values = BTHome.parseData(String(bthome), address); }} catch (_) {{ values = null; }} }}
  SolarMinerBleResults[address] = {{mac:address,name:name,rssi:Number(result.rssi)||null,
    service_data:String(bthome||""),values:values,manufacturer:shellyName?"Shelly":"BTHome",observed_at:Date.now()}};
}});
if (!SolarMinerIsRunning) {{
  if (typeof SolarMinerStart !== "function") throw Error("ble_scanner_start_not_supported");
  var SolarMinerBleScanStarted = SolarMinerStart.call(BLE.Scanner, {{duration_ms:{scan_ms},active:true,interval_ms:100,window_ms:100}});
  if (SolarMinerBleScanStarted === null || SolarMinerBleScanStarted === false) throw Error("ble_scan_start_failed");
}}
'''
            _rpc(host, "Script.PutCode", {"id": script_id, "code": script_code}, username=username, password=password)
            _rpc(host, "Script.Start", {"id": script_id}, username=username, password=password)
            time.sleep(duration_seconds + 0.4)
            evaluated = _rpc(host, "Script.Eval", {"id": script_id, "code": "JSON.stringify(SolarMinerBleResults)"},
                             username=username, password=password)
            encoded = evaluated.get("result", "{}")
            if not isinstance(encoded, str) or len(encoded) > 65536:
                raise RuntimeError("shelly_ble_scan_response_invalid")
            try:
                found = json.loads(encoded)
            except json.JSONDecodeError as exc:
                raise RuntimeError("shelly_ble_scan_response_invalid") from exc
            if not isinstance(found, dict):
                raise RuntimeError("shelly_ble_scan_response_invalid")
            devices = []
            for mac, item in found.items():
                normalized = _normalize_mac(mac)
                if not normalized or not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "Shelly BLU")[:80]
                devices.append({"mac": normalized, "name": name, "model": name,
                                "manufacturer": "Shelly" if item.get("manufacturer") == "Shelly" else "BTHome",
                                "protocol": "shelly_blu_bthome" if item.get("manufacturer") == "Shelly" else "bthome",
                                "device_type": "smart_sensor", "rssi": item.get("rssi"),
                                "values": item.get("values") if isinstance(item.get("values"), list) else [],
                                "bridge_mac": bridge.get("mac"), "bridge_host": host,
                                "bridge_model": model, "discovery_method": "shelly_blu_gateway_ble"})
            return {"bridge": bridge, "supported": True, "devices": devices,
                    "reason": "no_advertisements_received" if not devices else ""}
        except RuntimeError as exc:
            reason = str(exc)
            if reason in {"shelly_rpc_method_not_found", "shelly_rpc_rejected"}:
                reason = "bluetooth_scanner_not_supported"
            return {"bridge": bridge, "supported": False, "devices": [], "reason": reason}
        finally:
            if script_id is not None:
                try:
                    _rpc(host, "Script.Stop", {"id": script_id}, username=username, password=password)
                except (RuntimeError, OSError, ValueError):
                    pass
                try:
                    _rpc(host, "Script.Delete", {"id": script_id}, username=username, password=password)
                except (RuntimeError, OSError, ValueError):
                    pass


def _normalize_mac(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    compact = re.sub(r"[^0-9A-Fa-f]", "", value)
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
        return ""
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2)).upper()
