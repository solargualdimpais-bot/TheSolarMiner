import json

import pytest

from solarminer_gateway import integrations


def test_private_target_validation_rejects_public_and_dns():
    for host in ("8.8.8.8", "example.com", "127.0.0.1", "169.254.1.2"):
        with pytest.raises(ValueError):
            integrations._private_ip(host)
    assert integrations._private_ip("192.168.8.10") == "192.168.8.10"


def test_config_accepts_deye_antminer_and_tuya_and_redacts_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(integrations, "_data_dir", lambda: tmp_path)
    config = integrations.validate_config({
        "deye": {"host": "192.168.8.10", "port": 502, "unit_id": 1, "model": "SUN-15K-SG05LP3-EU-SM2"},
        "antminer": {"host": "192.168.8.20", "port": 4028, "rest_port": 80, "username": "root", "password": "antminer-secret", "model": "S19K Pro"},
        "tuya": {"region": "eu_central", "client_id": "client-id", "client_secret": "secret-value-123", "devices": [{"device_id": "device_123", "name": "Tomada"}]},
    }, existing={})
    public = integrations.save_config(config)
    loaded = integrations.load_config()
    assert loaded["tuya"]["client_secret"] == "secret-value-123"
    assert public["tuya"]["configured"] is True
    assert public["antminer_control_configured"] is True
    assert public["antminer"]["rest_port"] == 80
    assert "antminer-secret" not in json.dumps(public)
    assert "client_secret" not in json.dumps(public)
    assert "secret-value-123" not in json.dumps(public)


@pytest.mark.parametrize("payload", [
    {"deye": {"host": "8.8.8.8", "port": 502, "unit_id": 1}},
    {"antminer": {"host": "gateway.example.com", "port": 4028}},
    {"tuya": {"region": "evil", "client_id": "id", "client_secret": "secret-value-123", "devices": []}},
    {"tuya": {"region": "eu_central", "client_id": "id", "client_secret": "secret-value-123", "devices": [{"device_id": "../bad", "name": "X"}]}},
])
def test_invalid_hardware_config_rejected(payload):
    with pytest.raises(ValueError):
        integrations.validate_config(payload, existing={})


def test_antminer_uses_only_allowlisted_read_commands(monkeypatch):
    calls = []
    frames = []

    class FakeSocket:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def settimeout(self, _timeout): pass
        def sendall(self, payload):
            frames.append(payload)
            calls.append(json.loads(payload)["command"])
        def recv(self, _size): return b'{"STATUS":[{"STATUS":"S"}],"id":1}\0'

    monkeypatch.setattr(integrations.socket, "create_connection", lambda *_args, **_kwargs: FakeSocket())
    response = integrations.read_antminer("192.168.8.20")
    assert calls == ["summary", "stats", "devs"]
    assert response["control_commands_sent"] is False
    assert response["commands"] == ["summary", "stats", "devs"]
    assert response["configured_model"] == "S19K Pro"
    assert response["model_identity_verified"] is False
    assert all(frame.endswith(b"\n") for frame in frames)


def test_antminer_control_uses_authenticated_braiins_public_api(monkeypatch):
    calls = []

    def request(host, port, path, **kwargs):
        calls.append((host, port, path, kwargs))
        if path == "/api/v1/auth/login":
            assert kwargs["payload"] == {"username": "root", "password": "miner-secret"}
            return {"token": "session-token"}
        assert kwargs["token"] == "session-token"
        if path == "/api/v1/performance/power-target":
            assert kwargs["method"] == "PUT" and kwargs["payload"] == {"watt": 2400}
            return {"watt": 2400}
        return {"ok": True}

    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    config = {"host": "192.168.8.69", "rest_port": 80, "username": "root", "password": "miner-secret"}
    result = integrations.control_antminer(config, "set_power_target", 2400)
    assert result == {"action": "set_power_target", "requested_watt": 2400, "applied_watt": 2400,
                      "connection_state": "control_applied", "control_command_sent": True}
    assert len(calls) == 2
    assert all(call[0:2] == ("192.168.8.69", 80) for call in calls)


@pytest.mark.parametrize("action,path", [("pause", "/api/v1/actions/pause"),
                                           ("stop", "/api/v1/actions/stop"),
                                           ("start", "/api/v1/actions/start")])
def test_antminer_start_stop_pause_use_only_fixed_actions(monkeypatch, action, path):
    calls = []

    def request(host, port, route, **kwargs):
        calls.append((route, kwargs))
        return {"token": "session-token"} if route.endswith("/auth/login") else {"accepted": True}

    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.control_antminer({"host": "192.168.8.69", "username": "root", "password": "secret"}, action)
    assert result["connection_state"] == "control_applied"
    assert result["control_command_sent"] is True
    assert calls[-1][0] == path
    assert calls[-1][1]["method"] == "PUT"


def test_antminer_control_rejects_missing_credentials_and_out_of_range_power(monkeypatch):
    with pytest.raises(RuntimeError, match="antminer_control_credentials_required"):
        integrations.control_antminer({"host": "192.168.8.69"}, "start")
    config = {"host": "192.168.8.69", "username": "root", "password": "secret"}
    monkeypatch.setattr(integrations, "_bos_rest_request", lambda *_args, **_kwargs: {"token": "x"})
    with pytest.raises(ValueError, match="power_target_out_of_range"):
        integrations.control_antminer(config, "set_power_target", 0)
    with pytest.raises(ValueError, match="unsupported_antminer_control_action"):
        integrations.control_antminer(config, "reboot")


def test_deye_uses_standard_identification_without_guessing_registers(monkeypatch):
    monkeypatch.setattr(integrations, "probe_tcp", lambda host, port, timeout: {"state": "tcp_reachable", "host": host, "port": port})
    def identify(host, **kwargs):
        assert (host, kwargs["port"], kwargs["unit_id"]) == ("192.168.8.10", 502, 1)
        return {"state": "modbus_identity_response", "objects": []}
    monkeypatch.setattr(integrations.deye_modbus, "read_device_identification", identify)
    result = integrations.read_deye({"host": "192.168.8.10", "port": 502, "unit_id": 1, "model": "SUN-15K-SG05LP3-EU-SM2"})
    assert result["metrics_decoded"] is False
    assert result["connection_state"] == "modbus_identity_response"
    assert result["trust"] == "LIVE_UNVERIFIED"
    assert result["control_commands_sent"] is False


def test_deye_falls_back_to_read_only_fc03_when_identification_is_unsupported(monkeypatch):
    monkeypatch.setattr(integrations, "probe_tcp", lambda host, port, timeout: {"state": "tcp_reachable", "host": host, "port": port})
    def identify(*_args, **_kwargs):
        raise integrations.deye_modbus.ModbusExceptionResponse(0x2B, 1)
    class RegisterProbe:
        function_code = 3
        register_count = 1
        raw_registers = (12345,)
    monkeypatch.setattr(integrations.deye_modbus, "read_device_identification", identify)
    def read_registers(host, **kwargs):
        assert host == "192.168.8.10"
        assert kwargs["start_address"] == 0 and kwargs["count"] == 1
        return RegisterProbe()
    monkeypatch.setattr(integrations.deye_modbus, "read_holding_registers", read_registers)
    result = integrations.read_deye({"host": "192.168.8.10", "port": 502, "unit_id": 1, "model": "other"})
    assert result["connection_state"] == "modbus_register_probe_response"
    assert result["probe_method"] == "FC03 fallback after FC43 exception"
    assert result["metrics_decoded"] is False
    assert result["modbus_identity"]["value_discarded"] is True
    assert result["control_commands_sent"] is False


def test_deye_falls_back_to_fc03_when_fc43_silently_times_out(monkeypatch):
    monkeypatch.setattr(integrations, "probe_tcp", lambda host, port, timeout: {"state": "tcp_reachable", "host": host, "port": port})
    monkeypatch.setattr(integrations.deye_modbus, "read_device_identification",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(integrations.deye_modbus.ModbusTimeout("timeout")))
    monkeypatch.setattr(integrations.deye_modbus, "read_holding_registers", lambda *_args, **_kwargs: type(
        "Probe", (), {"function_code": 3, "register_count": 1, "raw_registers": (999,)}
    )())
    result = integrations.read_deye({"host": "192.168.8.10", "port": 502, "unit_id": 1, "model": "other"})
    assert result["connection_state"] == "modbus_register_probe_response"
    assert result["probe_method"] == "FC03 fallback after FC43 timeout"
    assert result["modbus_identity"]["fc43_result"] == "timeout"
    assert "raw_registers" not in json.dumps(result)


def test_deye_timeout_explains_web_credentials_do_not_authenticate_modbus(monkeypatch):
    monkeypatch.setattr(integrations, "probe_tcp", lambda host, port, timeout: {"state": "tcp_reachable", "host": host, "port": port})
    monkeypatch.setattr(integrations.deye_modbus, "read_device_identification",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(integrations.deye_modbus.ModbusTimeout("timeout")))
    monkeypatch.setattr(integrations.deye_modbus, "read_holding_registers",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(integrations.deye_modbus.ModbusTimeout("timeout")))
    result = integrations.read_deye({"host": "192.168.8.10", "port": 502, "unit_id": 1})
    assert result["connection_state"] == "modbus_timeout"
    assert result["web_ui_credentials_apply_to_modbus"] is False
    assert "Unit ID" in result["diagnostic_detail"]


def test_empty_hardware_configuration_is_reported_as_unconfigured():
    result = integrations.collect({})
    assert result["configuration"] == {"deye": "not_configured", "antminer": "not_configured", "tuya": "not_configured"}
    assert result["deye"] is None and result["antminer"] is None
    assert result["errors"] == []


def test_tuya_request_uses_fixed_https_region_and_does_not_log_or_return_secret(monkeypatch):
    captured = {}

    def fake_request(url, headers, timeout=8.0):
        captured.update(url=url, headers=headers, timeout=timeout)
        return {"success": True, "result": {"access_token": "temporary-token"}}

    monkeypatch.setattr(integrations, "_json_request", fake_request)
    config = {"region": "eu_central", "client_id": "client-id", "client_secret": "secret-value-123"}
    result = integrations._tuya_request(config, "/v1.0/token?grant_type=1")
    assert result["success"] is True
    assert captured["url"] == "https://openapi.tuyaeu.com/v1.0/token?grant_type=1"
    assert captured["headers"]["sign_method"] == "HMAC-SHA256"
    assert captured["headers"]["client_id"] == "client-id"
    assert "secret-value-123" not in json.dumps(captured)


def test_tuya_api_error_code_is_preserved_but_message_and_credentials_are_not(monkeypatch):
    class FakeResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, _limit): return json.dumps({
            "success": False, "code": 1004, "msg": "sign invalid secret-value-123"
        }).encode()
    class FakeOpener:
        def open(self, *_args, **_kwargs): return FakeResponse()
    monkeypatch.setattr(integrations.urllib.request, "build_opener", lambda *_args: FakeOpener())
    with pytest.raises(RuntimeError, match="tuya_api_rejected_request:1004") as exc:
        integrations._json_request("https://openapi.tuyaeu.com/v1.0/token?grant_type=1", {})
    assert "secret-value-123" not in str(exc.value)


def test_tuya_reports_devices_individually_when_one_status_request_fails(monkeypatch):
    calls = []
    def request(config, path, token=None):
        calls.append((path, token))
        if path == "/v1.0/token?grant_type=1":
            return {"success": True, "result": {"access_token": "temporary-token"}}
        if "bad-device" in path:
            raise RuntimeError("tuya_http_404")
        return {"success": True, "result": [{"code": "switch", "value": True}]}
    monkeypatch.setattr(integrations, "_tuya_request", request)
    result = integrations.read_tuya({
        "region": "eu_central", "client_id": "client", "client_secret": "secret-value-123",
        "devices": [{"device_id": "good-device", "name": "Good"},
                    {"device_id": "bad-device", "name": "Bad"}],
    })
    assert [item["connection_state"] for item in result] == ["api_responded", "failed"]
    assert result[0]["status"] == [{"code": "switch", "value": True}]
    assert result[1]["reason"] == "tuya_http_404"
    assert len(calls) == 3


def test_tesla_config_keeps_credentials_private_and_validates_selected_vehicle_ids():
    tesla = integrations.validate_tesla_config({
        "region": "europe", "client_id": "tesla-client",
        "refresh_token": "refresh-token-value", "vehicle_ids": ["12345678901234567"],
    }, existing={})
    config = {"tesla": tesla}
    public = integrations.public_tesla_config(config)
    assert public["configured"] is True
    assert public["vehicle_ids"] == ["12345678901234567"]
    assert "refresh-token-value" not in json.dumps(public)
    assert integrations.public_config(config).get("tesla") is None
    assert public["purpose"] == "ev_charging_status_read_only"
    assert integrations.validate_tesla_config({
        "region": "europe", "client_id": "tesla-client",
        "refresh_token": "refresh-token-value", "vehicle_ids": ["12345678901234567"],
    }, config)["vehicle_ids"] == ["12345678901234567"]


@pytest.mark.parametrize("region,vehicle_ids", [("other", ["123"]), ("europe", []), ("europe", ["../other"]), ("europe", ["123", "456"])])
def test_tesla_config_rejects_invalid_region_or_vehicle_ids(region, vehicle_ids):
    with pytest.raises(ValueError):
        integrations.validate_tesla_config({
            "region": region, "client_id": "tesla-client",
            "refresh_token": "refresh-token-value", "vehicle_ids": vehicle_ids,
        }, existing={})


def test_tesla_read_refreshes_token_and_returns_only_selected_non_location_data(monkeypatch):
    calls = []

    def fake_http(url, *, token=None, form=None):
        calls.append((url, token, form))
        if form:
            return {"access_token": "short-lived", "refresh_token": "rotated-refresh"}
        if url.endswith("/api/1/vehicles"):
            return {"response": [
                {"id": 123, "id_s": "123", "vin": "VIN0001", "display_name": "Solar Tesla", "state": "online"},
                {"id": 456, "id_s": "456", "vin": "VIN0002", "display_name": "Other Tesla", "state": "online"},
            ]}
        return {"response": {
            "charge_state": {"battery_level": 80}, "climate_state": {"is_climate_on": False},
            "vehicle_state": {"odometer": 1234, "location": "must-not-return"},
            "vehicle_config": {"car_type": "model3"}, "drive_state": {"latitude": 1.0},
        }}

    monkeypatch.setattr(integrations, "_tesla_http", fake_http)
    persisted = []
    result, rotated = integrations.read_tesla({
        "region": "europe", "client_id": "client",
        "refresh_token": "old-refresh", "vehicle_ids": ["123"],
    }, persisted.append)
    assert rotated == "rotated-refresh"
    assert persisted == ["rotated-refresh"]
    assert len(result["vehicles"]) == 1
    assert result["vehicles"][0]["name"] == "Solar Tesla"
    assert "location" not in json.dumps(result)
    assert "latitude" not in json.dumps(result)
    assert "climate_state" not in json.dumps(result)
    assert "vehicle_state" not in json.dumps(result)
    assert "vehicle_config" not in json.dumps(result)
    assert "battery_range" not in json.dumps(result)
    assert result["control_commands_sent"] is False
    assert all(call[1] != "old-refresh" for call in calls)
    assert calls[-1][0].endswith("/api/1/vehicles/123/vehicle_data")


def test_tesla_ev_read_persists_rotated_token_without_overwriting_other_integrations(tmp_path, monkeypatch):
    monkeypatch.setattr(integrations, "_data_dir", lambda: tmp_path)
    integrations.save_config({
        "deye": {"host": "192.168.8.10", "port": 502, "unit_id": 1},
        "tesla": {"region": "europe", "client_id": "client", "refresh_token": "old-refresh-token", "vehicle_ids": ["123"]},
    })
    def fake_http(url, *, token=None, form=None):
        if form: return {"access_token": "access", "refresh_token": "new-refresh-token"}
        if url.endswith("/api/1/vehicles"):
            return {"response": [{"id": 123, "id_s": "123", "vin": "VIN1234", "display_name": "Tesla EV"}]}
        return {"response": {"charge_state": {"battery_level": 70, "charging_state": "Charging"}}}
    monkeypatch.setattr(integrations, "_tesla_http", fake_http)

    result = integrations.read_tesla_ev(integrations.load_config()["tesla"])
    stored = integrations.load_config()
    assert result["vehicles"][0]["charge_state"]["battery_level"] == 70
    assert stored["tesla"]["refresh_token"] == "new-refresh-token"
    assert stored["deye"]["host"] == "192.168.8.10"
