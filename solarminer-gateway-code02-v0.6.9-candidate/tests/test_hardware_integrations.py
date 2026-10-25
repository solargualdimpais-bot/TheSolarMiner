import json
import hashlib

import pytest

from solarminer_gateway import integrations, huawei_router


def test_huawei_password_only_login_uses_admin_hash_without_username_xml():
    client = huawei_router.HuaweiHiLinkClient({"host": "192.168.8.1", "password": "router-password"})
    client.token = "tok-info-value"
    requests = []
    client._load_token = lambda: None

    def request(path, *, body=None, token=False):
        requests.append((path, body, token))
        if path == "api/user/state-login":
            return b"<response><State>1</State><password_type>4</password_type></response>", {}
        if path == "api/user/login":
            return b"<response>OK</response>", {"__RequestVerificationTokenone": "next-token"}
        raise AssertionError(f"Unexpected Huawei request: {path}")

    client._request = request
    client._login()

    login_request = next(item for item in requests if item[0] == "api/user/login")
    body = login_request[1]
    root = huawei_router.ET.fromstring(body)
    assert root.find("Username") is None
    assert root.findtext("password_type") == "4"
    password_hash = huawei_router.base64.b64encode(
        huawei_router.hashlib.sha256(b"router-password").hexdigest().encode("ascii")
    )
    challenge = b"admin" + password_hash + b"tok-info-value"
    expected = huawei_router.base64.b64encode(
        huawei_router.hashlib.sha256(challenge).hexdigest().encode("ascii")
    ).decode("ascii")
    assert root.findtext("Password") == expected
    assert client.token == "next-token"


def test_deye_cloud_config_keeps_credentials_private_and_supports_centers():
    config = integrations.validate_config({"deye_cloud": {
        "data_center": "india", "app_id": "app-123", "app_secret": "app-secret-123",
        "email": "owner@example.com", "password": "account-password",
    }}, existing={})
    public = integrations.public_config(config)
    assert config["deye_cloud"]["data_center"] == "india"
    assert public["deye_cloud"]["configured"] is True
    assert public["deye_cloud"]["secrets_returned"] is False
    assert "app-secret-123" not in json.dumps(public)
    assert "account-password" not in json.dumps(public)
    assert integrations.DEYE_CLOUD_BASES["india"].startswith("https://")


def test_deye_cloud_token_hash_and_station_history_requests(monkeypatch):
    calls = []
    progress = []

    def request(center, path, **kwargs):
        calls.append((center, path, kwargs))
        if path == "/account/token":
            assert kwargs["query"] == {"appId": "app-123"}
            assert kwargs["body"] == {
                "appSecret": "app-secret-123", "email": "owner@example.com",
                "password": hashlib.sha256(b"account-password").hexdigest(),
            }
            return {"success": True, "code": 1000000, "accessToken": "Bearer cloud-token"}
        assert kwargs["token"] == "Bearer cloud-token"
        if path == "/station/list":
            return {"success": True, "code": 1000000,
                    "stationList": [{"id": 12345, "name": "Casa"}], "total": 1}
        assert path == "/station/history/power"
        body = kwargs["body"]
        assert body["stationId"] == 12345
        assert body["endTimestamp"] - body["startTimestamp"] <= 7 * 86400
        return {"success": True, "code": 1000000, "stationDataItems": [
            {"timeStamp": "2026-10-24T10:00:00Z", "generationPower": 1500}
        ], "total": 1}

    monkeypatch.setattr(integrations, "_deye_cloud_request", request)
    config = {"data_center": "eu", "app_id": "app-123", "app_secret": "app-secret-123",
              "email": "owner@example.com", "password": "account-password"}
    stations = integrations.deye_cloud_list_stations(config)
    history = integrations.deye_cloud_history(config, "12345", days=90,
                                               progress_callback=lambda percent, message: progress.append((percent, message)))
    assert stations == [{"station_id": 12345, "name": "Casa"}]
    assert len(history) == 13
    assert all(item[0] == "eu" for item in calls)
    assert sum(path == "/account/token" for _, path, _ in calls) == 2
    assert integrations._deye_cloud_timestamp(history[0]["timeStamp"]) == "2026-10-24T10:00:00+00:00"
    assert progress[0][0] == 2 and "autenticar" in progress[0][1]
    assert progress[-1][0] == 78
    assert all(left[0] <= right[0] for left, right in zip(progress, progress[1:]))


def test_deye_cloud_history_splits_timed_out_intervals(monkeypatch):
    requests = []

    def request(center, path, **kwargs):
        if path == "/account/token":
            return {"success": True, "code": 1000000, "accessToken": "cloud-token"}
        start = kwargs["body"]["startTimestamp"]
        end = kwargs["body"]["endTimestamp"]
        requests.append((start, end))
        if end - start > 86400:
            raise RuntimeError("deye_cloud_upstream_timeout")
        return {"success": True, "code": 1000000, "stationDataItems": [], "total": 0}

    monkeypatch.setattr(integrations, "_deye_cloud_request", request)
    result = integrations.deye_cloud_history(
        {"data_center": "eu", "app_id": "id", "app_secret": "secret", "email": "e@example.com", "password": "pw"},
        12345, days=2,
    )
    assert result == []
    assert len(requests) > 3
    assert any(end - start > 86400 for start, end in requests)
    assert all(end - start <= 86400 for start, end in requests[-2:])


@pytest.mark.parametrize(("device", "expected_kind", "expected_channels"), [
    ({"category": "dlq", "product_name": "智能断路器", "functions": [
        {"code": "switch_1", "type": "Boolean"}, {"code": "trip_reset", "type": "Boolean"}]}, "breaker", 1),
    ({"category": "kg", "product_name": "six channel relay", "functions": [
        {"code": f"switch_{index}", "type": "Boolean"} for index in range(1, 7)]}, "multi_switch", 6),
    ({"category": "cl", "product_name": "curtain motor", "functions": []}, "blind", 0),
])
def test_tuya_device_profile_is_inferred_from_product_and_schema(device, expected_kind, expected_channels):
    profile = integrations.classify_tuya_device(device)
    assert profile["device_kind"] == expected_kind
    assert profile["channel_count"] == expected_channels
    assert profile["device_kind_label"]


def test_owner_can_override_tuya_device_profile_and_return_to_automatic():
    existing = {"tuya": {"client_id": "client", "client_secret": "secret-value-123", "devices": [{
        "device_id": "breaker_1", "name": "Disjuntor", "category": "dlq", "product_name": "断路器",
        "functions": [{"code": "switch_1", "type": "Boolean"}, {"code": "trip_reset", "type": "Boolean"}],
    }]}}
    edited = integrations.validate_config({"tuya": {"devices": [{
        "device_id": "breaker_1", "name": "Disjuntor", "device_kind_override": "breaker",
    }]}}, existing=existing)
    public = integrations.public_config(edited)["tuya"]["devices"][0]
    assert public["device_kind"] == "breaker"
    assert public["channel_count"] == 1
    auto = integrations.validate_config({"tuya": {"devices": [{
        "device_id": "breaker_1", "name": "Disjuntor", "device_kind_override": "auto",
    }]}}, existing=edited)
    assert "device_kind_override" not in auto["tuya"]["devices"][0]


@pytest.mark.parametrize("station_id,days", [("../x", 90), ("123", 91), (True, 90)])
def test_deye_cloud_history_rejects_invalid_station_or_range(station_id, days):
    with pytest.raises(ValueError):
        integrations.deye_cloud_history({"data_center": "eu"}, station_id, days=days)


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


def test_tuya_local_names_and_capability_aliases_are_bound_to_synced_schema():
    synced = {"tuya": {"region": "eu_central", "client_id": "client-id", "client_secret": "secret-value-123", "devices": [{
        "device_id": "device_123", "name": "Cloud name", "functions": [
            {"code": f"switch_{index}", "type": "Boolean", "name": f"Switch {index}"} for index in range(1, 7)
        ], "status_spec": [{"code": "relay_status", "type": "Enum", "name": "Relay status"}],
    }]}}
    existing = integrations.validate_config({"tuya": {"region": "eu_central", "client_id": "client-id", "client_secret": "secret-value-123", "devices": [{"device_id": "device_123", "name": "Cloud name"}]}}, existing={})
    existing["tuya"]["devices"][0]["functions"] = synced["tuya"]["devices"][0]["functions"]
    existing["tuya"]["devices"][0]["status_spec"] = synced["tuya"]["devices"][0]["status_spec"]
    edited_payload = {"tuya": {"region": "eu_central", "client_id": "client-id", "client_secret": "secret-value-123", "devices": [{
        "device_id": "device_123", "name": "Luzes da frente", "name_source": "local", "room": "Jardim", "floor": "Exterior",
        "channel_labels": {"switch_1": "Canteiro esquerdo", "switch_6": "Portão"},
        "capability_labels": {"switch_1": "Canteiro esquerdo", "relay_status": "Estado do relé"},
    }]}}
    updated = integrations.validate_config(edited_payload, existing=existing)
    public_device = integrations.public_config(updated)["tuya"]["devices"][0]
    assert public_device["name"] == "Luzes da frente"
    assert public_device["room"] == "Jardim" and public_device["floor"] == "Exterior"
    assert public_device["switch_channels"] == [f"switch_{index}" for index in range(1, 7)]
    assert public_device["channel_labels"]["switch_6"] == "Portão"
    assert public_device["capability_labels"]["relay_status"] == "Estado do relé"
    invalid = {"tuya": {**edited_payload["tuya"], "devices": [{**edited_payload["tuya"]["devices"][0], "capability_labels": {"not_synced": "Inventado"}}]}}
    with pytest.raises(ValueError, match="invalid_tuya_capability_label"):
        integrations.validate_config(invalid, existing=existing)


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
    assert calls == ["summary", "stats", "devs", "tunerstatus"]
    assert response["control_commands_sent"] is False
    assert response["commands"] == ["summary", "stats", "devs"]
    assert response["optional_commands"] == ["tunerstatus"]
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
        return {"token": "session-token"} if route.endswith("/auth/login") else False

    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.control_antminer({"host": "192.168.8.69", "username": "root", "password": "secret"}, action)
    assert result["connection_state"] == "control_applied"
    assert result["control_command_sent"] is True
    assert result["already_in_requested_state"] is False
    assert calls[-1][0] == path
    assert calls[-1][1]["method"] == "PUT"


def test_braiins_rest_accepts_boolean_action_response(monkeypatch):
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, _size): return b"false"

    class FakeOpener:
        def open(self, _request, timeout):
            assert timeout == 8.0
            return FakeResponse()

    monkeypatch.setattr(integrations.urllib.request, "build_opener", lambda *_args: FakeOpener())
    result = integrations._bos_rest_request("192.168.8.69", 80, "/api/v1/actions/start", method="PUT",
                                             token="session-token")
    assert result is False


def test_antminer_control_rejects_missing_credentials_and_out_of_range_power(monkeypatch):
    with pytest.raises(RuntimeError, match="antminer_control_credentials_required"):
        integrations.control_antminer({"host": "192.168.8.69"}, "start")
    config = {"host": "192.168.8.69", "username": "root", "password": "secret"}
    monkeypatch.setattr(integrations, "_bos_rest_request", lambda *_args, **_kwargs: {"token": "x"})
    with pytest.raises(ValueError, match="power_target_out_of_range"):
        integrations.control_antminer(config, "set_power_target", 0)
    with pytest.raises(ValueError, match="unsupported_antminer_control_action"):
        integrations.control_antminer(config, "reboot")


def test_deye_sg05lp3_reads_full_candidate_telemetry_without_fc43(monkeypatch):
    monkeypatch.setattr(integrations, "probe_tcp", lambda host, port, timeout: {"state": "tcp_reachable", "host": host, "port": port})
    monkeypatch.setattr(integrations.deye_modbus, "read_device_identification",
                        lambda *_args, **_kwargs: pytest.fail("FC43 must be skipped for DYDA_WiBLE"))
    reads = []
    blocks = {
        0: (5,), 108: (40, 50), 500: (2,),
        514: (12, 7, 256, 1, 512, 2, 33, 9, 1000, 3, 20, 0, 50, 1200, 4, 82, 0, 0, 0, 0, 3456, 5),
        586: (1250, 5378, 100, 0, 65250, 65006, 676),
        598: tuple([0] * 28),
        627: (2287, 2298, 2299, 630, 60, 10, 1458, 169, 33, 1660, 1660, 5000,
              0, 1458, 169, 33, 1660, 2290, 2299, 2294, 0, 0, 0, 1458, 169, 33, 1660, 1660, 5000),
        672: (1869, 173, 0, 0, 3935, 47, 2412, 50),
    }
    def read_registers(host, **kwargs):
        assert host == "192.168.8.10"
        reads.append((kwargs["start_address"], kwargs["count"], kwargs["port"], kwargs["unit_id"]))
        block = blocks[kwargs["start_address"]]
        assert len(block) == kwargs["count"]
        return type("Probe", (), {"raw_registers": block})()
    monkeypatch.setattr(integrations.deye_modbus, "read_holding_registers", read_registers)
    result = integrations.read_deye({"host": "192.168.8.10", "port": 502, "unit_id": 1, "model": "SUN-15K-SG05LP3-EU-SM2"})
    assert reads == [(0, 1, 502, 1), (108, 2, 502, 1), (500, 1, 502, 1),
                     (514, 22, 502, 1), (586, 7, 502, 1),
                     (598, 28, 502, 1), (627, 29, 502, 1), (672, 8, 502, 1)]
    assert result["metrics_decoded"] is True
    assert result["connection_state"] == "mapped_registers_response"
    assert result["device_type_code"] == 5
    assert result["status_code"] == 2
    metrics = {metric["field"]: metric for metric in result["metrics"]}
    assert (metrics["pv1_voltage"]["register"], metrics["pv1_voltage"]["value"], metrics["pv1_voltage"]["unit"]) == (40677, 393.5, "V")
    assert (metrics["pv1_current"]["register"], metrics["pv1_current"]["value"]) == (40678, 4.7)
    assert (metrics["pv1_input_power"]["value"], metrics["pv2_input_power"]["value"], metrics["pv_total_power"]["value"]) == (1869, 173, 2042)
    assert (metrics["battery_voltage"]["value"], metrics["battery_soc"]["value"]) == (53.78, 100)
    assert (metrics["battery_output_power"]["value"], metrics["battery_output_current"]["value"]) == (-286, -5.3)
    assert metrics["battery_charge_current"]["value"] == 5.3
    assert metrics["battery_discharge_current"]["value"] == 0
    assert metrics["battery_charge_power"]["value"] == 286
    assert metrics["battery_discharge_power"]["value"] == 0
    assert metrics["battery_daily_charge_energy"]["value"] == 1.2
    assert metrics["battery_daily_discharge_energy"]["value"] == 0.7
    assert metrics["battery_total_charge_energy"]["value"] == 6579.2
    assert metrics["battery_total_charge_energy"]["registers"] == [40517, 40518]
    assert metrics["battery_total_discharge_energy"]["value"] == 13158.4
    assert metrics["battery_max_charge_current"]["value"] == 40
    assert metrics["battery_max_discharge_current"]["value"] == 50
    assert metrics["pv_daily_energy"]["value"] == 8.2
    assert metrics["pv_total_energy"]["value"] == 33113.6
    assert metrics["pv_total_energy"]["registers"] == [40535, 40536]
    assert metrics["load_daily_energy"]["value"] == 5.0
    assert metrics["load_total_energy"]["value"] == 26334.4
    assert (metrics["inverter_power_total"]["value"], metrics["load_total_power"]["value"]) == (1660, 1660)
    assert metrics["grid_power_factor"]["register"] == 40622
    assert len(result["metrics"]) == 76
    checks = {item["field"]: item for item in result["quality_checks"]}
    assert checks["device_type"]["state"] == "protocol_value_mismatch"
    assert checks["pv1_power_vs_voltage_current"]["state"] == "consistent"
    assert checks["pv2_power_vs_voltage_current"]["state"] == "inconsistent"
    assert checks["grid_voltage_and_frequency"]["state"] == "all_zero_check_meter_or_logger_mapping"
    assert result["register_map"]["status"] == "COMMUNITY_MAP_LIVE_BLOCKS_CONFIRMED_NOT_MANUFACTURER_FIRMWARE_VALIDATED"
    assert result["trust"] == "LIVE_UNVERIFIED"
    assert result["control_commands_sent"] is False


def test_successful_deye_snapshot_is_persisted_for_pwa_energy_pages():
    import sqlite3
    from solarminer_gateway import app as gateway

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    energy = gateway.energy_registry
    energy.ensure_schema(conn)
    result = gateway._persist_deye_telemetry(conn, {
        "host": "192.168.8.10", "unit_id": 1, "model": "SUN-15K-SG05LP3-EU-SM2",
        "connection_state": "mapped_registers_response",
        "register_map": {"source": "https://example.test/map", "sha256": "abc", "protocol_reference": "protocol"},
        "metrics": [
            {"field": "pv_total_power", "value": 2048, "unit": "W", "category": "inversores",
             "register": 40673, "raw_value": 2048, "label": "Potência FV total", "derived": True},
            {"field": "battery_soc", "value": 100, "unit": "%", "category": "baterias",
             "register": 40589, "raw_value": 100, "label": "Carga da bateria"},
            {"field": "battery_total_charge_energy", "value": 6579.2, "unit": "kWh", "category": "baterias",
             "register": 40517, "registers": [40517, 40518], "raw_value": 65792,
             "label": "Energia acumulada de carga"},
        ],
    })
    assert result == 3
    equipment = energy.list_equipment(conn)
    assert {item["category"] for item in equipment} == {"inversores", "baterias"}
    inverter = next(item for item in equipment if item["category"] == "inversores")
    battery = next(item for item in equipment if item["category"] == "baterias")
    assert inverter["readings"][0]["field"] == "pv_total_power"
    assert inverter["readings"][0]["trust"] == "LIVE_UNVERIFIED"
    assert inverter["readings"][0]["evidence"]["register"] == 40673
    assert battery["readings"][0]["field"] == "battery_soc"
    cumulative = next(reading for reading in battery["readings"] if reading["field"] == "battery_total_charge_energy")
    assert cumulative["evidence"]["registers"] == [40517, 40518]
    conn.close()


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


def test_tuya_inventory_pagination_sorts_query_parameters_for_signature(monkeypatch):
    inventory_paths = []
    device_rows = [{"id": f"device_{index:02d}"} for index in range(44)]

    def request(config, path, token=None, *, method="GET", payload=None):
        if path == "/v1.0/token?grant_type=1":
            return {"result": {"access_token": "temporary-token"}}
        if path.startswith("/v2.0/cloud/thing/device?"):
            inventory_paths.append(path)
            page_start = (len(inventory_paths) - 1) * 20
            return {"result": device_rows[page_start:page_start + 20]}
        if path.startswith("/v2.0/cloud/thing/"):
            return {"result": {}}
        return {"result": []}

    monkeypatch.setattr(integrations, "_tuya_request", request)
    result = integrations.synchronize_tuya_devices({
        "region": "eu_central", "client_id": "client", "client_secret": "secret", "uid": "uid",
        "devices": [],
    })

    assert result["pages"] == 3
    assert len(result["devices"]) == 44
    assert inventory_paths[0] == "/v2.0/cloud/thing/device?page_size=20"
    assert inventory_paths[1] == "/v2.0/cloud/thing/device?last_id=device_19&page_size=20"
    assert inventory_paths[2] == "/v2.0/cloud/thing/device?last_id=device_39&page_size=20"


def test_tuya_reports_devices_individually_when_one_status_request_fails(monkeypatch):
    monkeypatch.setattr(integrations, "_tuya_request", lambda *args, **kwargs: pytest.fail("Tuya status read used Cloud"))
    def local_status(device):
        if device["device_id"] == "bad-device":
            raise RuntimeError("tuya_lan_unavailable")
        return {"device_id": device["device_id"], "name": device["name"], "status": [{"code": "switch", "value": True}],
                "connection_state": "local_responded", "source": "TUYA_LAN"}
    monkeypatch.setattr(integrations, "_tuya_local_status", local_status)
    result = integrations.read_tuya({
        "devices": [{"device_id": "good-device", "name": "Good"},
                    {"device_id": "bad-device", "name": "Bad"}],
    })
    assert [item["connection_state"] for item in result] == ["local_responded", "failed"]
    assert result[0]["status"] == [{"code": "switch", "value": True}]
    assert result[1]["reason"] == "tuya_lan_unavailable"
    assert all(item["source"] == "TUYA_LAN" for item in result)


def test_tuya_switch_control_posts_only_configured_switch_and_reads_back(monkeypatch):
    calls = []
    class LocalDevice:
        def set_socketTimeout(self, value): pass
        def set_retry(self, value): pass
        def set_status(self, on, switch=1):
            calls.append(("set_status", on, switch))
            return {"dps": {str(switch): on}}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda device: LocalDevice())
    monkeypatch.setattr(integrations, "_tuya_local_status", lambda device: {"status": [{"code": "switch_1", "value": True}]})
    monkeypatch.setattr(integrations, "_tuya_request", lambda *args, **kwargs: pytest.fail("Tuya control used Cloud"))
    result = integrations.control_tuya_switch({
        "region": "eu_central",
        "devices": [{"device_id": "device_123", "name": "AQS 1", "switch_code": "switch_1"}],
    }, "device_123", True)
    assert calls == [("set_status", True, 1)]
    assert result["state_confirmed"] is True
    assert result["source"] == "TUYA_LAN"


def test_tuya_switch_control_rejects_unconfigured_device_without_request(monkeypatch):
    calls = []
    monkeypatch.setattr(integrations, "_tuya_request", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(ValueError, match="tuya_device_not_configured"):
        integrations.control_tuya_switch({"client_id": "client", "client_secret": "private-secret", "devices": []},
                                          "unlisted", True)
    assert calls == []


def test_tuya_level_control_maps_percent_to_configured_range_and_reads_back(monkeypatch):
    calls = []
    class LocalDevice:
        def set_socketTimeout(self, value): pass
        def set_retry(self, value): pass
        def set_value(self, dps, value):
            calls.append(("set_value", dps, value))
            return {"dps": {str(dps): value}}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda device: LocalDevice())
    monkeypatch.setattr(integrations, "_tuya_local_status", lambda device: {"status": [{"code": "position", "value": 510}]})
    monkeypatch.setattr(integrations, "_tuya_request", lambda *args, **kwargs: pytest.fail("Tuya level control used Cloud"))
    result = integrations.control_tuya_level({
        "region": "eu_central",
        "devices": [{"device_id": "device_123", "name": "Estore", "level_code": "position", "level_min": 10, "level_max": 1010, "local_dps_map": {"position": "2"}}],
    }, "device_123", 50)
    assert calls == [("set_value", 2, 510)]
    assert result["command_accepted"] is True
    assert result["state_confirmed"] is True
    assert result["source"] == "TUYA_LAN"


def test_tuya_level_control_rejects_unconfigured_device_without_request(monkeypatch):
    calls = []
    monkeypatch.setattr(integrations, "_tuya_request", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(ValueError, match="tuya_device_not_configured"):
        integrations.control_tuya_level({"client_id": "client", "client_secret": "secret", "devices": []}, "unlisted", 25)
    assert calls == []


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
