"""Mock-only tests for local Shelly Gen1 and Gen2+ protocol adapters."""
from __future__ import annotations

from solarminer_gateway import shelly_integration as shelly


def test_gen2_identification_normalizes_identity_components_and_capabilities(monkeypatch):
    def rpc(host, method, params=None, **auth):
        if method == "Shelly.GetDeviceInfo":
            return {"id": "shellyplus1pm-aabbcc", "mac": "AA:BB:CC:DD:EE:FF", "model": "SNSW-001P16EU", "gen": 2, "ver": "1.4.4"}
        if method == "Shelly.GetStatus":
            return {"switch:0": {"output": True, "apower": 48.2, "voltage": 230.1, "current": 0.21,
                                  "aenergy": {"total": 120.0}}, "sys": {"uptime": 10}}
        raise AssertionError(method)

    monkeypatch.setattr(shelly, "_rpc", rpc)
    result = shelly.identify_and_read("192.168.1.21")
    assert result["generation"] == 2
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result["protocol"] == "shelly_rpc"
    assert {"relay", "power"}.issubset(result["capabilities"])
    assert result["components"][0]["status"]["output"] is True
    assert result["command_sent"] is False


def test_gen1_falls_back_to_http_and_extracts_meter_channels(monkeypatch):
    def rpc(*args, **kwargs):
        raise RuntimeError("shelly_http_404")

    def request(host, path, **kwargs):
        if path == "/shelly":
            return {"type": "SHPLG-S", "mac": "AA:BB:CC:DD:EE:11", "fw": "1.13"}
        if path == "/status":
            return {"relays": [{"ison": True}], "meters": [{"power": 62.5, "total": 3400}]}
        raise AssertionError(path)

    monkeypatch.setattr(shelly, "_rpc", rpc)
    monkeypatch.setattr(shelly, "_request", request)
    result = shelly.identify_and_read("192.168.1.22")
    assert result["generation"] == 1
    assert result["protocol"] == "shelly_http_gen1"
    assert result["components"][0]["status"]["ison"] is True
    assert "power" in result["capabilities"]


def test_switch_control_does_not_repeat_command_and_requires_readback(monkeypatch):
    calls = []
    def rpc(host, method, params=None, **auth):
        calls.append((method, params))
        return {}
    def read(host, **auth):
        return {"host": host, "components": [{"component": "switch", "id": 0,
                "status": {"output": True}}], "observed_at": 1.0}
    monkeypatch.setattr(shelly, "_rpc", rpc)
    monkeypatch.setattr(shelly, "identify_and_read", read)
    result = shelly.control_switch("192.168.1.23", 2, 0, True)
    assert calls == [("Switch.Set", {"id": 0, "on": True})]
    assert result["command_confirmed"] is True
    assert result["command_state"] == "CONFIRMED"


def test_switch_control_marks_accepted_but_unverified_state_unknown(monkeypatch):
    monkeypatch.setattr(shelly, "_rpc", lambda *args, **kwargs: {})
    monkeypatch.setattr(shelly, "identify_and_read", lambda *args, **kwargs: {"components": [], "observed_at": 1.0})
    result = shelly.control_switch("192.168.1.24", 2, 1, False)
    assert result["command_accepted"] is True
    assert result["command_confirmed"] is False
    assert result["command_state"] == "UNKNOWN"


def test_registered_identity_mac_mismatch_is_not_reported_as_connected(monkeypatch):
    monkeypatch.setattr(shelly, "identify_and_read", lambda *args, **kwargs: {
        "host": "192.168.1.25", "mac": "AA:BB:CC:DD:EE:02", "model": "Shelly Plus 1",
        "protocol": "shelly_rpc", "generation": 2, "components": [], "command_sent": False})
    result = shelly.read_devices({"devices": [{"device_id": "shelly:AA:BB:CC:DD:EE:01",
        "host": "192.168.1.25", "mac": "AA:BB:CC:DD:EE:01", "name": "test"}]})
    assert result[0]["connection_state"] == "identity_conflict"
    assert result[0]["reason"] == "shelly_mac_mismatch"


def test_invalid_or_non_private_hosts_are_rejected_before_network_io():
    for host in ("example.com", "8.8.8.8", "127.0.0.1", "169.254.2.1", "192.168.1.1/path"):
        try:
            shelly.identify_and_read(host)
        except ValueError as exc:
            assert str(exc) == "shelly_private_ip_required"
        else:
            raise AssertionError(f"host unexpectedly accepted: {host}")


def test_bluetooth_bridge_probe_is_read_only_and_reports_exact_api_support(monkeypatch):
    monkeypatch.setattr(shelly, "identify_and_read", lambda *args, **kwargs: {
        "host": "192.168.1.40", "model": "Shelly BLU Gateway", "firmware": "1.7.0",
        "generation": 2, "mac": "AA:BB:CC:DD:EE:40", "capabilities": ["bluetooth"],
        "components": [{"component": "ble", "id": 0, "status": {}}]})
    calls = []
    def rpc(host, method, **kwargs):
        calls.append(method)
        if method == "BTHome.GetStatus":
            return {"errors": []}
        raise AssertionError(method)
    monkeypatch.setattr(shelly, "_rpc", rpc)
    result = shelly.inspect_bluetooth_bridge("192.168.1.40")
    assert result["bridge_candidate"] is True
    assert result["bthome_discovery_api"] == "available"
    assert calls == ["BTHome.GetStatus"]


def test_bluetooth_bridge_probe_does_not_assume_bthome_api(monkeypatch):
    monkeypatch.setattr(shelly, "identify_and_read", lambda *args, **kwargs: {
        "host": "192.168.1.41", "model": "Shelly BLU Gateway", "firmware": "1.7.0",
        "generation": 2, "mac": "AA:BB:CC:DD:EE:41", "capabilities": ["bluetooth"],
        "components": [{"component": "ble", "id": 0, "status": {}}]})
    monkeypatch.setattr(shelly, "_rpc", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("shelly_rpc_method_not_found")))
    result = shelly.inspect_bluetooth_bridge("192.168.1.41")
    assert result["bridge_candidate"] is True
    assert result["bthome_discovery_api"] == "not_supported"


def test_bluetooth_discovery_uses_and_removes_only_its_temporary_script(monkeypatch):
    calls = []
    monkeypatch.setattr(shelly, "identify_and_read", lambda *args, **kwargs: {
        "host": "192.168.1.40", "model": "Shelly BLU Gateway", "firmware": "1.7.0",
        "generation": 2, "mac": "AA:BB:CC:DD:EE:40", "capabilities": ["bluetooth"],
        "components": [{"component": "ble", "id": 0, "status": {}}]})
    def rpc(host, method, params=None, **auth):
        calls.append((method, params))
        if method == "BTHome.GetStatus":
            return {"errors": []}
        if method == "Script.List":
            return {"scripts": [{"id": 1, "name": "user-script", "running": True}]}
        if method == "Script.Create":
            return {"id": 2}
        if method == "Script.Eval":
            return {"result": '{"AA:BB:CC:DD:EE:01":{"name":"SBHT-003C","rssi":-58,"manufacturer":"Shelly","values":[{"name":"temperature","val":21.5}]}}'}
        return {}
    monkeypatch.setattr(shelly, "_rpc", rpc)
    monkeypatch.setattr(shelly.time, "sleep", lambda _: None)
    result = shelly.discover_bluetooth_devices("192.168.1.40", duration_seconds=2)
    assert result["supported"] is True
    assert result["devices"][0]["mac"] == "AA:BB:CC:DD:EE:01"
    assert result["devices"][0]["model"] == "SBHT-003C"
    assert result["devices"][0]["values"][0]["name"] == "temperature"
    assert [method for method, _ in calls] == ["BTHome.GetStatus", "Script.List", "Script.Create",
        "Script.PutCode", "Script.Start", "Script.Eval", "Script.Stop", "Script.Delete"]
    assert all(params is None or params.get("id") != 1 for _, params in calls)


def test_bluetooth_discovery_does_not_stop_scripts_when_all_slots_are_busy(monkeypatch):
    calls = []
    monkeypatch.setattr(shelly, "inspect_bluetooth_bridge", lambda *args, **kwargs: {
        "bridge_candidate": True, "generation": 2, "mac": "AA:BB:CC:DD:EE:40", "model": "Shelly BLU Gateway"})
    def rpc(host, method, params=None, **auth):
        calls.append(method)
        if method == "Script.List":
            return {"scripts": [{"id": i, "running": True} for i in (1, 2, 3)]}
        return {}
    monkeypatch.setattr(shelly, "_rpc", rpc)
    result = shelly.discover_bluetooth_devices("192.168.1.40")
    assert result["supported"] is False
    assert result["reason"] == "bluetooth_script_slots_busy"
    assert calls == ["Script.List"]
