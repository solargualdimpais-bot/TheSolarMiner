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
        "antminer": {"host": "192.168.8.20", "port": 4028, "model": "S19K Pro"},
        "tuya": {"region": "eu_central", "client_id": "client-id", "client_secret": "secret-value-123", "devices": [{"device_id": "device_123", "name": "Tomada"}]},
    }, existing={})
    public = integrations.save_config(config)
    loaded = integrations.load_config()
    assert loaded["tuya"]["client_secret"] == "secret-value-123"
    assert public["tuya"]["configured"] is True
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
    assert all(frame.endswith(b"\n") for frame in frames)


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


def test_empty_hardware_configuration_is_reported_as_unconfigured():
    result = integrations.collect({})
    assert result["configuration"] == {"deye": "not_configured", "antminer": "not_configured"}
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
