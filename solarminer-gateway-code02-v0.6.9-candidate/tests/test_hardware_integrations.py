import json
import hashlib

import pytest

from solarminer_gateway import integrations, huawei_router, tuya_dps_registry


def test_tuya_local_dps_prefers_tuya_dp_id_to_channel_suffix():
    device = {
        "functions": [
            {"code": "switch_1", "type": "Boolean", "dp_id": 7},
            {"code": "switch_2", "type": "Boolean", "dpId": 9},
        ],
    }
    assert integrations._tuya_local_dps(device, "switch_1") == "7"
    assert integrations._tuya_local_dps(device, "switch_2") == "9"
    with pytest.raises(ValueError, match="tuya_local_datapoint_mapping_required"):
        integrations._tuya_local_dps({"functions": []}, "switch_2")


def test_tuya_multichannel_switch_requires_real_dp_mapping():
    device = {"functions": [
        {"code": f"switch_{index}", "type": "Boolean"}
        for index in range(1, 7)
    ]}
    with pytest.raises(ValueError, match="tuya_local_datapoint_mapping_required"):
        integrations._tuya_local_dps(device, "switch_1")
    device["local_dps_map"] = {"switch_1": "7"}
    assert integrations._tuya_local_dps(device, "switch_1") == "7"
    with pytest.raises(ValueError, match="tuya_local_datapoint_mapping_required"):
        integrations._tuya_local_dps({"channel_count": 6}, "switch_1")


def test_tuya_kg_standard_six_switch_profile_maps_only_full_declared_channels():
    device = {"category": "kg", "functions": [
        {"code": f"switch_{index}", "type": "Boolean"} for index in range(1, 7)
    ]}
    assert [integrations._tuya_local_dps(device, f"switch_{i}") for i in range(1, 7)] == ["1", "2", "3", "4", "5", "6"]
    incomplete = {"category": "kg", "functions": device["functions"][:-1]}
    with pytest.raises(ValueError, match="tuya_local_datapoint_mapping_required"):
        integrations._tuya_local_dps(incomplete, "switch_1")


def test_tuya_product_catalog_keys_profile_by_product_and_channel_count_without_live_values():
    device = {
        "product_id": "kg-six-product",
        "product_name": "KG Six Channel",
        "category": "kg",
        "device_kind": "multi_switch",
        "channel_count": 6,
        "schema_source": "TUYA_DEVICE_SPEC",
        "functions": [{"code": f"switch_{index}", "type": "Boolean", "dp_id": index}
                      for index in range(1, 7)] + [
            {"code": "switch_all", "type": "Boolean", "dp_id": 13},
            {"code": "pair_1_mode", "type": "Enum", "dp_id": 113,
             "values": {"range": ["switch", "curtain"]}},
        ],
        "status_spec": [{"code": f"switch_{index}", "type": "Boolean", "dp_id": index}
                        for index in range(1, 7)],
        "current_status": [{"code": "switch_1", "dps_id": 1, "value": True}],
    }
    profile = tuya_dps_registry.product_profile(device)
    assert profile["product_id"] == "kg-six-product"
    assert profile["category"] == "kg"
    assert profile["channel_count"] == 6
    assert profile["functions"]["switch_1"] == 1
    assert next(row for row in profile["dps"] if row["dps_id"] == 1)["semantic_code"] == "switch_1"
    assert all("raw_value" not in row for row in profile["dps"])
    bounded = integrations._bounded_tuya_product_schemas({"kg-six-product": {
        **profile, "dps_profile": profile, "functions": device["functions"],
        "status_spec": device["status_spec"], "cached_at": 10,
    }})
    assert bounded["kg-six-product"]["channel_count"] == 6
    assert bounded["kg-six-product"]["dps_profile"]["product_id"] == "kg-six-product"
    public = integrations.public_config({"tuya": {
        "client_id": "client-public", "client_secret": "must-not-leak", "devices": [device],
        "product_schemas": bounded,
    }})["tuya"]
    assert public["devices"][0]["dps_knowledge"]["channel_count"] == 6
    assert public["devices"][0]["product_profile"]["product_id"] == "kg-six-product"
    assert public["product_catalog"]["kg-six-product"]["dps_profile"]["category"] == "kg"
    assert "must-not-leak" not in json.dumps(public)


def test_tuya_local_status_does_not_guess_when_schema_codes_conflict_for_same_dps(monkeypatch):
    monkeypatch.setattr(integrations, "_tuya_probe_local_status", lambda _device: (
        None, {"dps": {"1": True, "2": False}}, "3.3"))
    device = {
        "device_id": "kg-conflict",
        "category": "kg",
        "functions": [
            {"code": "switch_1", "type": "Boolean", "dp_id": 1},
            {"code": "switch_2", "type": "Boolean", "dp_id": 1},
        ],
        "status_spec": [{"code": "switch_2", "type": "Boolean", "dp_id": 2}],
    }
    reading = integrations._tuya_local_status(device)
    assert reading["status"] == [
        {"code": "dps_1", "dps_id": 1, "value": True},
        {"code": "dps_2", "dps_id": 2, "value": False},
    ]
    knowledge = tuya_dps_registry.analyze_device({**device, "current_status": reading["status"]})
    assert knowledge["mapping_conflicts"] == [{"dps_id": 1, "codes": ["switch_1", "switch_2"]}]
    assert next(row for row in knowledge["dps"] if row["dps_id"] == 1)["semantic_code"] == "unknown"
    with pytest.raises(ValueError, match="tuya_local_datapoint_mapping_required"):
        integrations._tuya_local_dps(device, "switch_1")


def test_tuya_command_rejection_reports_target_dps_and_sanitized_device_hint(monkeypatch):
    class LocalDevice:
        def set_socketTimeout(self, _value): pass
        def set_retry(self, _value): pass
        def set_status(self, _on, switch=1):
            return {"Error": "DPS 2 is not writable: local protocol!"}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda _device: LocalDevice())
    device = {"device_id": "relay-1", "local_key": "local-key-123", "local_ip": "192.168.1.20",
              "functions": [{"code": "switch_2", "type": "Boolean", "dp_id": 2}]}
    with pytest.raises(RuntimeError, match=r"tuya_lan_command_rejected:dps_2:DPS_2_is_not_writable_local_protocol"):
        integrations.control_tuya_switch({"devices": [device]}, "relay-1", True, "switch_2")


def test_tuya_dps_registry_keeps_dp18_scoped_and_unknown_read_only():
    observed_energy = {"current_status": [
        {"dps_id": dp, "code": f"dps_{dp}", "value": value}
        for dp, value in ((1, True), (9, 0), (17, 62), (18, 6081), (19, 14008), (20, 2302))
    ]}
    suggestion = tuya_dps_registry.analyze_device(observed_energy)
    assert suggestion["preset_id"] is None
    assert suggestion["confidence"] == "SUGGESTED"
    energy = tuya_dps_registry.analyze_device({**observed_energy, "dps_preset_id": "energy_monitor_switch"})
    assert energy["preset_id"] == "energy_monitor_switch"
    assert next(row for row in energy["dps"] if row["dps_id"] == 18)["semantic_code"] == "current"
    assert energy["write_authorized"] is False
    assert energy["raw_dps"]["18"] == 6081
    qccdz = tuya_dps_registry.analyze_device({"category": "qccdz", "current_status": [
        {"dps_id": 18, "code": "dps_18", "value": True}
    ]})
    assert qccdz["preset_id"] == "qccdz_ev_charger"
    assert next(row for row in qccdz["dps"] if row["dps_id"] == 18)["semantic_code"] == "switch"
    unknown = tuya_dps_registry.analyze_device({"current_status": [{"dps_id": 250, "value": {"x": 1}}]})
    unknown_row = next(row for row in unknown["dps"] if row["dps_id"] == 250)
    assert unknown_row["semantic_code"] == "unknown"
    assert unknown_row["write_supported"] is False
    assert unknown["raw_dps"]["250"] == {"x": 1}


def test_owner_product_dps_override_changes_meaning_and_only_enables_type_safe_switches():
    profile = {
        "product-a": {"custom_dps_overrides": {
            "7": {"label": "Tensão", "semantic_code": "voltage", "unit": "V", "data_type": "number", "scale": 10},
            "8": {"label": "Corrente", "semantic_code": "current", "unit": "A", "data_type": "number", "scale": 100},
            "9": {"label": "Interruptor", "semantic_code": "switch", "data_type": "boolean", "write_enabled": True},
        }},
        "product-b": {"custom_dps_overrides": {"7": {"label": "Tensão antiga", "semantic_code": "voltage", "unit": "V"}}},
    }
    device = {"device_id": "device-a", "product_id": "product-a", "functions": [],
              "current_status": [{"dps_id": 7, "code": "dps_7", "value": 2310},
                                 {"dps_id": 8, "code": "dps_8", "value": 145},
                                 {"dps_id": 9, "code": "dps_9", "value": False}]}
    enriched = integrations._tuya_apply_product_dps_overrides(device, profile)
    assert enriched["switch_code"] == "switch_9"
    assert enriched["local_dps_map"]["switch_9"] == "9"
    assert tuya_dps_registry.analyze_device({**device, "product_dps_overrides": profile["product-a"]["custom_dps_overrides"]})["dps"][0]["display_name"] == "Tensão"
    other = integrations._tuya_apply_product_dps_overrides({**device, "product_id": "product-b"}, profile)
    assert not other.get("switch_code")


def test_owner_product_switch_mapping_routes_command_to_observed_boolean_dp(monkeypatch):
    sent = {}
    class LocalDevice:
        def set_status(self, value, switch):
            sent.update(value=value, dps=switch)
            return {"dps": {str(switch): value}}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda _device: LocalDevice())
    config = {
        "devices": [{"device_id": "switch-unit", "product_id": "product-switch", "local_key": "secret",
                     "local_ip": "192.168.1.30", "local_protocol": "3.3",
                     "current_status": [{"dps_id": 9, "code": "dps_9", "value": False}],
                     "functions": [], "status_spec": []}],
        "product_schemas": {"product-switch": {"custom_dps_overrides": {
            "9": {"label": "Interruptor", "semantic_code": "switch", "data_type": "boolean", "write_enabled": True}
        }}},
    }
    result = integrations.control_tuya_switch(config, "switch-unit", True)
    assert result["switch_code"] == "switch_9"
    assert sent == {"value": True, "dps": 9}


def test_bounded_product_catalog_preserves_owner_dps_overrides():
    bounded = integrations._bounded_tuya_product_schemas({"pid": {
        "dps_profile": {"product_id": "pid", "dps": [{"dps_id": 18}]},
        "custom_dps_overrides": {"18": {"label": "Interruptor", "semantic_code": "switch", "write_enabled": True}},
    }})
    assert bounded["pid"]["custom_dps_overrides"]["18"]["label"] == "Interruptor"


def test_tuya_community_catalog_is_exact_product_scoped_and_never_authorizes_writes():
    ev_profile = tuya_dps_registry.analyze_device({
        "category": "qccdz", "product_id": "tj9l3ghsjnbdjom6",
        "current_status": [{"dps_id": 18, "code": "dps_18", "value": False}],
    })
    dp18 = next(row for row in ev_profile["dps"] if row["dps_id"] == 18)
    assert dp18["semantic_code"] != "switch"
    assert "factory_reset" in dp18["display_name"]
    assert dp18["confidence"] == "COMMUNITY_REFERENCE"
    assert dp18["write_supported"] is False
    assert ev_profile["write_authorized"] is False
    by_id = {row["dps_id"]: row for row in ev_profile["dps"]}
    assert by_id[3]["display_name"] == "charger state"
    assert by_id[14]["display_name"] == "charging_mode"
    assert by_id[106]["semantic_code"] == "current_x"
    assert all(row["write_supported"] is False for row in by_id.values())

    different_product = tuya_dps_registry.analyze_device({
        "category": "qccdz", "product_id": "unlisted-ev-product",
        "current_status": [{"dps_id": 18, "code": "dps_18", "value": False}],
    })
    other_dp18 = next(row for row in different_product["dps"] if row["dps_id"] == 18)
    assert other_dp18["semantic_code"] == "switch"
    assert other_dp18["confidence"] == "OWNER_CONFIRMED"
    assert other_dp18["write_supported"] is False


def test_tuya_qccdz_owner_reference_labels_are_ev_scoped_and_read_only():
    status = [{"dps_id": dp, "code": f"dps_{dp}", "value": value}
              for dp, value in ((3, "charging"), (10, 0), (14, "charge_now"),
                                (15, 1), (16, False), (18, True), (25, 2),
                                (27, "online"), (101, "connect"), (106, 4))]
    report = tuya_dps_registry.analyze_device({"category": "qccdz", "current_status": status})
    by_id = {row["dps_id"]: row for row in report["dps"]}
    assert by_id[3]["semantic_code"] == "charger_state"
    assert by_id[10]["semantic_code"] == "alarms_faults"
    assert by_id[14]["semantic_code"] == "charging_mode"
    assert by_id[18]["semantic_code"] == "switch"
    assert by_id[25]["semantic_code"] == "last_session_energy"
    assert by_id[106]["semantic_code"] == "total_energy"
    assert all(row["write_supported"] is False for row in by_id.values())
    assert report["write_authorized"] is False


def test_tuya_dlq_category_uses_product_schema_ids_for_breaker_semantics():
    device = {
        "category": "dlq",
        "product_id": "breaker-product-a",
        "functions": [
            {"code": "relay_state", "name": "Estado do relé", "type": "Boolean", "dp_id": 7},
            {"code": "switch", "name": "Switch", "type": "Boolean", "dp_id": 12},
        ],
        "status_spec": [
            {"code": "daily_energy", "name": "Daily electricity", "type": "Raw", "dp_id": 38},
            {"code": "cur_voltage_a", "name": "Phase A voltage", "type": "Integer", "dp_id": 44},
        ],
        "current_status": [
            {"dps_id": 7, "code": "dps_7", "value": True},
            {"dps_id": 38, "code": "dps_38", "value": "today-series"},
            {"dps_id": 44, "code": "dps_44", "value": 2291},
        ],
    }
    report = tuya_dps_registry.analyze_device(device)
    by_id = {item["dps_id"]: item for item in report["dps"]}
    assert by_id[7]["semantic_code"] == "switch"
    assert by_id[7]["function_code"] == "relay_state"
    assert by_id[38]["semantic_code"] == "daily_energy"
    assert by_id[44]["semantic_code"] == "voltage_phase_a"
    assert by_id[44]["function_code"] == "cur_voltage_a"
    assert report["write_authorized"] is False


def test_tuya_dps_registry_suggests_hybrid_entities_without_writes():
    status = [{"dps_id": dp, "code": f"dps_{dp}", "value": value}
              for dp, value in [(1, False), (2, False), (3, False), (4, False), (5, False), (6, False),
                                (13, False), (14, "memory"), (107, "rturn"),
                                (113, "switch"), (114, "curtain"), (115, "curtain")]]
    suggestion = tuya_dps_registry.analyze_device({"category": "kg", "current_status": status})
    assert suggestion["preset_id"] == "six_channel_hybrid"
    assert suggestion["selection_source"] == "kg_category_and_six_channels"
    suggested_dps = {row["dps_id"]: row for row in suggestion["dps"]}
    assert suggested_dps[13]["semantic_code"] == "master_switch"
    assert suggested_dps[13]["data_type"] == "boolean"
    assert suggested_dps[13]["confidence"] == "DOCUMENTED"
    assert suggested_dps[14]["semantic_code"] == "power_on_state"
    assert suggested_dps[14]["data_type"] == "enum"
    assert suggested_dps[14]["confidence"] == "DOCUMENTED"
    assert suggestion["write_authorized"] is False
    assert all(row["write_supported"] is False for row in suggested_dps.values())
    result = suggestion
    assert result["preset_id"] == "six_channel_hybrid"
    assert result["write_authorized"] is False
    assert result["dynamic_entities"] == [
        {"entity_type": "switch", "channel": 1, "source_dps": [1]},
        {"entity_type": "switch", "channel": 2, "source_dps": [2]},
        {"entity_type": "cover", "pair": 2, "source_dps": [3, 4], "supported_controls": [],
         "note": "Cortina detetada; posição e comandos não inferidos."},
        {"entity_type": "cover", "pair": 3, "source_dps": [5, 6], "supported_controls": [],
         "note": "Cortina detetada; posição e comandos não inferidos."},
    ]


def test_tuya_kg_six_channel_category_selects_read_only_profile_without_pair_modes():
    status = [{"dps_id": dp, "code": f"dps_{dp}", "value": False}
              for dp in range(1, 7)]
    result = tuya_dps_registry.analyze_device({"category": "KG", "channel_count": 6,
                                                "current_status": status})
    assert result["preset_id"] == "six_channel_hybrid"
    assert result["selection_source"] == "kg_category_and_six_channels"
    assert result["write_authorized"] is False
    assert result["dynamic_entities"] == []


def test_tuya_kg_pair_mode_setting_is_only_sent_for_declared_switch_curtain_enum(monkeypatch):
    calls = []
    class LocalDevice:
        def set_socketTimeout(self, value): pass
        def set_retry(self, value): pass
        def status(self): pytest.fail("pair-mode command must not read DPS")
        def set_value(self, dps, value):
            calls.append((dps, value))
            return {"dps": {str(dps): value}}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda device: LocalDevice())
    device = {"device_id": "kg-six", "category": "kg", "local_ip": "192.168.1.20",
              "local_key": "local-key-123", "functions": [
                  {"code": "pair_1_mode", "type": "Enum", "dp_id": 113,
                   "values": {"range": ["switch", "curtain"]}},
              ]}
    result = integrations.control_tuya_setting({"devices": [device]}, "kg-six", "pair_1_mode", "curtain")
    assert calls == [(113, "curtain")]
    assert result["state_confirmed"] is False
    device["functions"][0]["values"]["range"] = ["switch", "blind"]
    with pytest.raises(ValueError, match="tuya_setting_not_supported"):
        integrations.control_tuya_setting({"devices": [device]}, "kg-six", "pair_1_mode", "blind")
    assert calls == [(113, "curtain")]


def test_qccdz_ev_charger_uses_its_dps_18_switch_profile():
    device = {"category": "qccdz", "functions": []}
    profile = integrations.classify_tuya_device(device)
    assert profile["device_kind"] == "ev_charger"
    assert profile["channel_count"] == 1
    assert integrations._tuya_local_dps(device, "switch") == "18"
    assert integrations._tuya_local_dps(device, "switch_1") == "18"
    with pytest.raises(ValueError, match="tuya_local_datapoint_mapping_required"):
        integrations._tuya_local_dps({"category": "qld", "functions": []}, "switch")


def test_qccdz_local_status_names_dps_18_as_switch(monkeypatch):
    class Client:
        pass

    monkeypatch.setattr(integrations, "_tuya_probe_local_status",
                        lambda device: (Client(), {"dps": {"18": True}}, "3.3"))
    result = integrations._tuya_local_status({"device_id": "ev-1", "category": "qccdz", "functions": []})
    assert result["status"] == [{"code": "switch", "dps_id": 18, "value": True}]


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
    assert client.login_state == "authenticated"


def test_huawei_login_falls_back_to_admin_username_xml_when_password_only_body_is_rejected():
    client = huawei_router.HuaweiHiLinkClient({"host": "192.168.8.1", "password": "router-password"})
    client.token = "tok-info-value"
    client._load_token = lambda: None
    bodies = []

    def request(path, *, body=None, token=False):
        if path == "api/user/state-login":
            return b"<response><State>1</State><password_type>4</password_type></response>", {}
        if path == "api/user/login":
            bodies.append(huawei_router.ET.fromstring(body))
            if len(bodies) == 1:
                return b"<response><code>108006</code></response>", {}
            return b"<response>OK</response>", {"__RequestVerificationTokenone": "rotated"}
        raise AssertionError(path)

    client._request = request
    client._login()
    assert bodies[0].find("Username") is None
    assert bodies[1].findtext("Username") == "admin"
    assert bodies[0].findtext("Password") == bodies[1].findtext("Password")
    assert client.token == "rotated"
    assert client.login_state == "authenticated"


def test_huawei_inventory_diagnostics_distinguish_successful_login_from_denied_host_list():
    client = huawei_router.HuaweiHiLinkClient({
        "host": "192.168.8.1", "password": "router-password",
        "discovered_device": {"model": "B636-336", "software_version": "2.0.0.41"},
    })
    client._login = lambda: setattr(client, "login_state", "authenticated")
    client._load_token = lambda: None

    def request(path, *, body=None, token=False):
        return b"<response><error><code>100003</code></error></response>", {}

    client._request = request
    with pytest.raises(huawei_router.HuaweiRouterError, match="huawei_router_hosts_unavailable") as caught:
        client.clients()
    assert caught.value.diagnostics["login_state"] == "authenticated"
    assert caught.value.diagnostics["device_profile"] == "B636-336"
    assert caught.value.diagnostics["software_version"] == "2.0.0.41"
    assert caught.value.diagnostics["failure_class"] == "authorization_or_session"


def test_huawei_api_requests_wait_two_and_a_half_seconds_between_calls(monkeypatch):
    client = huawei_router.HuaweiHiLinkClient({"host": "192.168.8.1", "password": "router-password"})
    sleeps = []
    monkeypatch.setattr(huawei_router.time, "sleep", sleeps.append)
    client.last_request_completed_at = huawei_router.time.monotonic()
    client._wait_for_request_slot()
    assert len(sleeps) == 1
    assert 2.0 <= sleeps[0] <= 2.5


def test_huawei_session_token_info_parses_cookie_and_token_from_xml():
    client = huawei_router.HuaweiHiLinkClient({"host": "192.168.8.1", "password": "router-password"})
    client._request = lambda *_args, **_kwargs: (
        b"<SesTokInfo><SesInfo>SessionID=Abc123+_==</SesInfo><TokInfo>tok-123</TokInfo></SesTokInfo>", {})
    client._load_token()
    assert client.session_id == "Abc123+_=="
    assert client.token == "tok-123"


def test_huawei_rotating_session_headers_update_token_and_cookie():
    client = huawei_router.HuaweiHiLinkClient({"host": "192.168.8.1", "password": "router-password"})
    client.token = "old-token"
    client.session_id = "old-session"
    client._refresh_session_headers({
        "__RequestVerificationTokenone": "new-token#metadata",
        "Set-Cookie": "SessionID=new-session; Path=/",
    })
    assert client.token == "new-token"
    assert client.session_id == "new-session"


def test_huawei_device_information_tries_both_read_only_endpoints_and_omits_identifiers():
    client = huawei_router.HuaweiHiLinkClient({"host": "192.168.8.1", "password": "router-password"})
    calls = []
    responses = {
        "api/device/information": b"<response><ProductFamily>B636-336</ProductFamily><SoftwareVersion>3.0.0.1</SoftwareVersion><IMEI>private-id</IMEI></response>",
        "api/device/basic_information": b"<response><HardwareVersion>WL1B636M</HardwareVersion><WebUIVersion>WEBUI 3.0.0.1</WebUIVersion></response>",
    }

    def request(path, *, body=None, token=False):
        calls.append(path)
        return responses[path], {}

    client._request = request
    result = client.device_information()
    assert calls == ["api/device/information", "api/device/basic_information"]
    assert result["model"] == "B636-336"
    assert result["software_version"] == "3.0.0.1"
    assert result["hardware_version"] == "WL1B636M"
    assert "private-id" not in json.dumps(result)
    assert result["probe_status"] == "identified"


def test_huawei_device_information_retries_after_login_required():
    client = huawei_router.HuaweiHiLinkClient({"host": "192.168.8.1", "password": "router-password"})
    calls = []

    def request(path, *, body=None, token=False):
        calls.append(path)
        if len([item for item in calls if item == path]) == 1:
            return b"<response><error><code>100003</code></error></response>", {}
        if path == "api/device/information":
            return b"<response><ProductName>B636-336</ProductName></response>", {}
        return b"<response><HardwareVersion>HW1</HardwareVersion></response>", {}

    client._request = request
    client._login = lambda: setattr(client, "login_state", "authenticated")
    result = client.device_information()
    assert result["model"] == "B636-336"
    assert result["hardware_version"] == "HW1"
    assert result["authenticated"] is True


def test_huawei_discovered_profile_survives_credential_edits_and_is_public_without_secrets():
    old = {"huawei_router": {"host": "192.168.8.1", "username": "admin", "password": "huawei-password-test-value",
                              "discovered_device": {"model": "B636-336", "software_version": "3.0.0.1"}}}
    updated = integrations.validate_config({"huawei_router": {"host": "192.168.8.1", "username": "root"}}, old)
    public = integrations.public_config(updated)
    assert updated["huawei_router"]["discovered_device"]["model"] == "B636-336"
    assert public["huawei_router"]["discovered_device"]["software_version"] == "3.0.0.1"
    assert "huawei-password-test-value" not in json.dumps(public)


def test_huawei_inventory_checks_lan_wifi_and_dhcp_endpoints_and_merges_hosts():
    client = huawei_router.HuaweiHiLinkClient({"host": "192.168.8.1", "password": "router-password"})
    client._login = lambda: None
    client._load_token = lambda: None
    calls = []
    responses = {
        "api/lan/HostInfo": b"<response><Hosts><Host><HostName>Wired</HostName><MacAddress>AA:BB:CC:DD:EE:01</MacAddress><IpAddress>192.168.8.20</IpAddress></Host></Hosts></response>",
        "api/system/HostInfo": b"<response><error><code>100002</code></error></response>",
        "api/wlan/host-list": b"<response><Hosts><Host><HostName>Wifi</HostName><MACAddress>AA:BB:CC:DD:EE:02</MACAddress><IPAddress>192.168.8.21</IPAddress></Host></Hosts></response>",
        "api/dhcp/dhcp-host-info": b"<response><error><code>100002</code></error></response>",
    }

    def request(path, *, body=None, token=False):
        calls.append(path)
        return responses[path], {}

    client._request = request
    hosts = client.clients()
    assert calls == ["api/lan/HostInfo", "api/system/HostInfo", "api/wlan/host-list", "api/dhcp/dhcp-host-info"]
    assert {(host["mac"], host["ip"], host["name"]) for host in hosts} == {
        ("AA:BB:CC:DD:EE:01", "192.168.8.20", "Wired"),
        ("AA:BB:CC:DD:EE:02", "192.168.8.21", "Wifi"),
    }
    assert client.last_diagnostics["endpoints_succeeded"] == ["api/lan/HostInfo", "api/wlan/host-list"]
    assert client.last_diagnostics["endpoint_errors"]["api/dhcp/dhcp-host-info"] == "huawei_router_api_error_100002"


def test_huawei_inventory_uses_detected_b636_profile_and_reports_profile_source():
    client = huawei_router.HuaweiHiLinkClient({
        "host": "192.168.8.1", "password": "router-password",
        "discovered_device": {"model": "B636-336", "software_version": "3.0.0.1"},
    })
    client._login = lambda: None
    client._request = lambda path, *, body=None, token=False: (
        b"<response><error><code>100002</code></error></response>", {})
    with pytest.raises(huawei_router.HuaweiRouterError):
        client.clients()
    assert client.last_diagnostics["device_profile"] == "B636-336"


def test_huawei_inventory_refreshes_session_once_after_no_right_response():
    client = huawei_router.HuaweiHiLinkClient({"host": "192.168.8.1", "password": "router-password"})
    client._login = lambda: None
    client._load_token = lambda: None
    calls = []

    def request(path, *, body=None, token=False):
        calls.append(path)
        if path == "api/lan/HostInfo" and calls.count(path) == 1:
            return b"<response><error><code>100003</code></error></response>", {}
        return b"<response><Hosts/></response>", {}

    client._request = request
    assert client.clients() == []
    assert calls.count("api/lan/HostInfo") == 2
    assert client.last_diagnostics["endpoints_succeeded"] == [
        "api/lan/HostInfo", "api/system/HostInfo", "api/wlan/host-list", "api/dhcp/dhcp-host-info"]


def test_huawei_inventory_keeps_ip_when_firmware_omits_mac():
    parsed = huawei_router.HuaweiHiLinkClient._parse_hosts(
        huawei_router.ET.fromstring(b"<response><Host><HostName>Unknown device</HostName><IpAddress>192.168.8.30</IpAddress></Host></response>")
    )
    assert parsed == [{"mac": "", "ip": "192.168.8.30", "name": "Unknown device"}]


def test_huawei_inventory_merges_gateway_neighbor_cache_without_duplicate_or_public_hosts():
    hosts, added = huawei_router.merge_gateway_neighbor_hosts(
        [{"mac": "AA:BB:CC:DD:EE:01", "ip": "192.168.8.20", "name": "router record"}],
        {
            "AA:BB:CC:DD:EE:01": "192.168.8.20",
            "AA:BB:CC:DD:EE:02": "192.168.8.21",
            "AA:BB:CC:DD:EE:03": "8.8.8.8",
        },
    )
    assert added == 1
    assert len(hosts) == 2
    assert {item["ip"] for item in hosts} == {"192.168.8.20", "192.168.8.21"}


def test_huawei_inventory_marks_gateway_discoveries_with_their_source():
    hosts, added = huawei_router.merge_gateway_neighbor_hosts(
        [], {"AA:BB:CC:DD:EE:22": "192.168.8.22"}, source="gateway_active_lan_scan")
    assert added == 1
    assert hosts[0]["source"] == "gateway_active_lan_scan"


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
    ({"category": "evse", "product_name": "AC wallbox charger", "functions": []}, "ev_charger", 0),
    ({"category": "qccdz", "product_name": "AC charger", "functions": []}, "ev_charger", 1),
    ({"category": "unknown", "name": "Carregador EV garagem", "functions": []}, "ev_charger", 0),
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


def test_ev_charger_profile_is_specific_and_exposes_ev_label():
    profile = integrations.classify_tuya_device({
        "category": "evse", "product_name": "AC Wallbox Charger", "functions": [],
    })
    assert profile["device_kind"] == "ev_charger"
    assert profile["device_kind_label"] == "Carregador EV"
    assert profile["channel_count"] == 0


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
        "dps_preset_id": "six_channel_hybrid",
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
    assert public_device["dps_preset_id"] == "six_channel_hybrid"
    assert public_device["dps_knowledge"]["preset_id"] == "six_channel_hybrid"
    invalid_preset = {"tuya": {**edited_payload["tuya"], "devices": [{**edited_payload["tuya"]["devices"][0], "dps_preset_id": "invented"}]}}
    with pytest.raises(ValueError, match="invalid_tuya_dps_preset"):
        integrations.validate_config(invalid_preset, existing=existing)
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


def test_antminer_control_probe_reapplies_current_target_without_changing_mining_state(monkeypatch):
    calls = []

    def request(host, port, path, **kwargs):
        calls.append((path, kwargs))
        if path == "/api/v1/auth/login":
            return {"token": "session-token"}
        assert kwargs["token"] == "session-token"
        if path == "/api/v1/performance/tuner-state":
            return {"mode_state": {"powertargetmodestate": {"current_target": {"watt": 2500}}}}
        assert path == "/api/v1/performance/power-target"
        assert kwargs["method"] == "PUT" and kwargs["payload"] == {"watt": 2500}
        return {"watt": 2500}

    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.test_antminer_control({"host": "192.168.8.69", "password": "secret"})
    assert result == {"action": "test_control", "previous_target_watt": 2500, "applied_watt": 2500,
                      "connection_state": "control_verified", "control_command_sent": True,
                      "mining_state_changed": False}
    assert [path for path, _ in calls] == ["/api/v1/auth/login", "/api/v1/performance/tuner-state",
                                          "/api/v1/performance/power-target"]


def test_antminer_control_probe_sends_no_write_without_a_current_positive_target(monkeypatch):
    calls = []

    def request(_host, _port, path, **_kwargs):
        calls.append(path)
        if path == "/api/v1/auth/login": return {"token": "session-token"}
        return {"mode_state": {"powertargetmodestate": {"current_target": {"watt": 0}}}}

    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    with pytest.raises(RuntimeError, match="antminer_control_probe_target_unavailable"):
        integrations.test_antminer_control({"host": "192.168.8.69", "password": "secret"})
    assert calls == ["/api/v1/auth/login", "/api/v1/performance/tuner-state"]


def test_antminer_control_probe_accepts_documented_power_targets_above_2900_watts(monkeypatch):
    calls = []

    def request(_host, _port, path, **kwargs):
        calls.append((path, kwargs))
        if path == "/api/v1/auth/login": return {"token": "session-token"}
        if path == "/api/v1/performance/tuner-state":
            return {"mode_state": {"powertargetmodestate": {"current_target": {"watt": 3730}}}}
        assert kwargs["method"] == "PUT" and kwargs["payload"] == {"watt": 3730}
        return {"watt": 3730}

    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.test_antminer_control({"host": "192.168.8.69", "password": "secret"})
    assert result["connection_state"] == "control_verified"
    assert result["previous_target_watt"] == result["applied_watt"] == 3730


def test_antminer_control_probe_accepts_snake_case_tuner_state_and_string_watts(monkeypatch):
    calls = []

    def request(_host, _port, path, **kwargs):
        calls.append((path, kwargs))
        if path == "/api/v1/auth/login": return {"token": "session-token"}
        if path == "/api/v1/performance/tuner-state":
            return {"mode_state": {"power_target_mode_state": {"current_target": {"watt": "2500"}}}}
        assert kwargs["method"] == "PUT" and kwargs["payload"] == {"watt": 2500}
        return {"watt": "2500"}

    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.test_antminer_control({"host": "192.168.8.69", "password": "secret"})
    assert result["connection_state"] == "control_verified"
    assert result["previous_target_watt"] == result["applied_watt"] == 2500
    assert result["mining_state_changed"] is False
    assert len(calls) == 3


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


def test_antminer_password_only_config_defaults_braiins_username_to_root():
    configured = integrations.validate_config({"antminer": {
        "host": "192.168.8.69", "port": 4028, "rest_port": 80, "password": "secret"
    }}, existing={})
    assert configured["antminer"]["username"] == "root"
    assert integrations.public_config(configured)["antminer_control_configured"] is True


def test_antminer_control_authenticates_with_fixed_root_and_password_only(monkeypatch):
    calls = []

    def request(host, port, path, **kwargs):
        calls.append((host, port, path, kwargs))
        if path == "/api/v1/auth/login":
            return {"token": "session-token"}
        return True

    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.control_antminer({"host": "192.168.8.69", "password": "secret"}, "start")
    assert calls[0][3]["payload"] == {"username": "root", "password": "secret"}
    assert result["control_command_sent"] is True


def test_antminer_power_target_read_uses_tuner_state_instead_of_unsupported_get(monkeypatch):
    calls = []

    def request(_host, _port, path, **kwargs):
        calls.append((path, kwargs))
        if path.endswith("/auth/login"):
            return {"token": "temporary-token"}
        return {"mode_state": {"powertargetmodestate": {"current_target": {"watt": 2500}}}}

    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.antminer_management({"host": "192.168.8.69", "password": "secret"}, "power_target")
    assert result["state"] == "read"
    assert calls[-1][0] == "/api/v1/performance/tuner-state"
    assert calls[-1][1]["method"] == "GET"
    assert result["data"]["mode_state"]["powertargetmodestate"]["current_target"]["watt"] == 2500


def test_antminer_management_reads_documented_sections_and_redacts_pool_secrets(monkeypatch):
    calls = []
    def request(host, port, path, **kwargs):
        calls.append((host, port, path, kwargs))
        if path.endswith("/auth/login"):
            return {"token": "temporary-token"}
        return [{"uid": "pool-a", "pools": [{"url": "stratum+tcp://example:3333",
                "user": "worker", "password": "private"}]}]
    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.antminer_management({"host": "192.168.8.69", "password": "secret"}, "pools")
    assert result["state"] == "read"
    assert result["data"][0]["pools"][0]["password"] == "[guardado no minerador]"
    assert calls[-1][2] == "/api/v1/pools/"
    assert calls[-1][3]["method"] == "GET"


def test_antminer_management_reads_default_advanced_settings_and_deletes_pool_without_body(monkeypatch):
    calls = []
    def request(_host, _port, path, **kwargs):
        calls.append((path, kwargs))
        if path.endswith("/auth/login"):
            return {"token": "temporary-token"}
        return {"state": "ok"}
    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    integrations.antminer_management({"host": "192.168.8.69", "password": "secret"}, "advanced_settings")
    assert calls[-1][1]["query"] == {"include_default": "true"}
    integrations.antminer_management({"host": "192.168.8.69", "password": "secret"},
                                      "delete_pool_group", resource_id="pool-group-1")
    assert calls[-1][0] == "/api/v1/pools/pool-group-1"
    assert calls[-1][1]["method"] == "DELETE"
    assert calls[-1][1]["payload"] is None


def test_antminer_api_explorer_only_allows_paths_and_methods_from_device_openapi(monkeypatch):
    calls = []
    specification = {"paths": {"/api/v1/actions/start": {"put": {}},
                                "/api/v1/pools/{pool_id}": {"get": {}, "put": {"requestBody": {
                                    "required": True, "content": {"application/json": {}}}}}}}
    def request(_host, _port, path, **kwargs):
        calls.append((path, kwargs))
        if path.endswith("/auth/login"):
            return {"token": "temporary-token"}
        if path == "/api/v1/docs/openapi.json":
            return specification
        return {"password": "should-be-redacted"}
    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.antminer_management({"host": "192.168.8.69", "password": "secret"}, "api_call",
                                               payload={"method": "PUT", "path": "/api/v1/pools/group-1",
                                                        "body": {"enabled": True}, "query": {}})
    assert result["state"] == "command_accepted"
    assert result["data"]["password"] == "[guardado no minerador]"
    assert calls[-1][0] == "/api/v1/pools/group-1"
    assert calls[-1][1]["method"] == "PUT"
    with pytest.raises(ValueError, match="antminer_api_operation_not_documented"):
        integrations.antminer_management({"host": "192.168.8.69", "password": "secret"}, "api_call",
                                          payload={"method": "GET", "path": "/api/v1/shell"})


def test_antminer_management_writes_only_catalogued_operations_and_reports_acceptance(monkeypatch):
    calls = []
    def request(host, port, path, **kwargs):
        calls.append((path, kwargs))
        if path.endswith("/auth/login"):
            return {"token": "temporary-token"}
        return {"mode": "manual", "password": "should-not-leak"}
    monkeypatch.setattr(integrations, "_bos_rest_request", request)
    result = integrations.antminer_management({"host": "192.168.8.69", "password": "secret"},
                                               "cooling_mode", payload={"manual": {"fan_speed": 70}})
    assert result["state"] == "command_accepted"
    assert result["command_sent"] is True
    assert result["data"]["password"] == "[guardado no minerador]"
    assert calls[-1][0] == "/api/v1/cooling/mode"
    assert calls[-1][1]["method"] == "PUT"
    with pytest.raises(ValueError, match="antminer_management_operation_unsupported"):
        integrations.antminer_management({"host": "192.168.8.69", "password": "secret"}, "shell")


def test_antminer_management_rejects_invalid_payloads_before_contact(monkeypatch):
    monkeypatch.setattr(integrations, "_bos_rest_request", lambda *_args, **_kwargs: pytest.fail("must not contact miner"))
    with pytest.raises(ValueError, match="power_target_out_of_range"):
        integrations.antminer_management({"host": "192.168.8.69", "password": "secret"},
                                          "set_power_target", payload={"watt": 50000})
    with pytest.raises(ValueError, match="antminer_management_payload_invalid"):
        integrations.antminer_management({"host": "192.168.8.69", "password": "secret"},
                                          "pools_batch", payload={"not": "a list"})


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


def test_tuya_local_protocol_fallback_probes_33_then_34_then_35_and_remembers_match(monkeypatch):
    attempted = []
    class LocalDevice:
        def __init__(self, protocol): self.protocol = protocol
        def status(self):
            attempted.append(self.protocol)
            if self.protocol != "3.4":
                raise RuntimeError("protocol_mismatch")
            return {"dps": {"1": True}}
    monkeypatch.setattr(integrations, "_tuya_lan_client",
                        lambda device: LocalDevice(device["local_protocol"]))
    device = {"device_id": "relay-1", "name": "Relay", "local_key": "local-key-123",
              "local_ip": "192.168.8.44", "local_protocol": "3.3"}
    result = integrations._tuya_local_status(device)
    assert attempted == ["3.3", "3.4"]
    assert device["local_protocol"] == "3.4"
    assert result["local_protocol"] == "3.4"
    assert result["status"] == [{"code": "dps_1", "dps_id": 1, "value": True}]


def test_tuya_local_protocol_reuses_confirmed_protocol_before_fallbacks(monkeypatch):
    attempted = []
    class LocalDevice:
        def __init__(self, protocol): self.protocol = protocol
        def status(self):
            attempted.append(self.protocol)
            return {"dps": {"1": False}}
    monkeypatch.setattr(integrations, "_tuya_lan_client",
                        lambda device: LocalDevice(device["local_protocol"]))
    device = {"device_id": "relay-known-protocol", "local_key": "local-key-123",
              "local_ip": "192.168.8.44", "local_protocol": "3.5"}
    result = integrations._tuya_local_status(device)
    assert attempted == ["3.5"]
    assert result["local_protocol"] == "3.5"
    assert result["status"] == [{"code": "dps_1", "dps_id": 1, "value": False}]


def test_tuya_local_protocol_fallback_reports_all_attempts_without_cloud(monkeypatch):
    attempted = []
    class LocalDevice:
        def __init__(self, protocol): self.protocol = protocol
        def status(self):
            attempted.append(self.protocol)
            raise TimeoutError("offline")
    monkeypatch.setattr(integrations, "_tuya_lan_client",
                        lambda device: LocalDevice(device["local_protocol"]))
    monkeypatch.setattr(integrations, "_tuya_request", lambda *args, **kwargs: pytest.fail("Tuya fallback used Cloud"))
    with pytest.raises(RuntimeError, match="tuya_protocol_probe_failed:3.3,3.4,3.5"):
        integrations._tuya_local_status({"device_id": "relay-1", "local_key": "local-key-123",
                                         "local_ip": "192.168.8.44", "local_protocol": "3.3"})
    assert attempted == ["3.3", "3.4", "3.5"]


def test_tuya_successful_protocol_and_mac_resolved_ip_are_saved_without_exposing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(integrations, "_data_dir", lambda: tmp_path)
    integrations.save_config({"tuya": {"devices": [{
        "device_id": "relay-1", "local_key": "private-local-key", "local_protocol": "3.3",
        "local_mac": "AA:BB:CC:DD:EE:FF",
    }]}})
    integrations._persist_tuya_protocols({"relay-1": "3.5"}, {"relay-1": "192.168.8.44"})
    stored = integrations.load_config()["tuya"]["devices"][0]
    assert stored["local_protocol"] == "3.5"
    assert stored["local_ip"] == "192.168.8.44"
    assert "private-local-key" not in json.dumps(integrations.public_config())


def test_tuya_mac_only_configuration_resolves_private_ip_from_lan_scan(monkeypatch):
    monkeypatch.setattr(integrations, "_TUYA_MAC_SCAN_CACHE", (0.0, {}))
    monkeypatch.setattr(integrations, "tinytuya", type("TinyTuyaFake", (), {
        "deviceScan": staticmethod(lambda **_kwargs: {
            "relay-1": {"mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.8.44"}
        })
    }))
    assert integrations._tuya_resolve_local_ip({"local_mac": "aa-bb-cc-dd-ee-ff"}) == "192.168.8.44"


def test_tuya_switch_control_posts_only_configured_switch_without_immediate_readback(monkeypatch):
    calls = []
    class LocalDevice:
        def set_socketTimeout(self, value): pass
        def set_retry(self, value): pass
        def status(self): pytest.fail("switch command must not read DPS")
        def set_status(self, on, switch=1):
            calls.append(("set_status", on, switch))
            return {"dps": {str(switch): on}}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda device: LocalDevice())
    monkeypatch.setattr(integrations, "_persist_tuya_protocols", lambda *args, **kwargs: None)
    monkeypatch.setattr(integrations, "_tuya_local_status", lambda device: pytest.fail("switch command must not trigger an immediate status read"))
    monkeypatch.setattr(integrations, "_tuya_request", lambda *args, **kwargs: pytest.fail("Tuya control used Cloud"))
    result = integrations.control_tuya_switch({
        "region": "eu_central",
        "devices": [{"device_id": "device_123", "name": "AQS 1", "switch_code": "switch_1",
                      "functions": [{"code": "switch_1", "type": "Boolean", "dp_id": 1}],
                      "local_key": "local-key-123", "local_ip": "192.168.8.44"}],
    }, "device_123", True)
    assert calls == [("set_status", True, 1)]
    assert result["state_confirmed"] is False
    assert result["observed_on"] is None
    assert result["connection_state"] == "command_accepted_awaiting_independent_scan"
    assert result["source"] == "TUYA_LAN"


def test_tuya_switch_command_uses_saved_protocol_without_reading_status(monkeypatch):
    commands = []
    class LocalDevice:
        def __init__(self, protocol): self.protocol = protocol
        def status(self): pytest.fail("switch command must not read DPS")
        def set_socketTimeout(self, _value): pass
        def set_retry(self, _value): pass
        def set_status(self, on, switch=1):
            commands.append((self.protocol, on, switch))
            return {"dps": {str(switch): on}}
    monkeypatch.setattr(integrations, "_tuya_lan_client",
                        lambda device: LocalDevice(device["local_protocol"]))
    monkeypatch.setattr(integrations, "_tuya_local_status",
                        lambda _device: pytest.fail("switch command must not trigger an immediate status read"))
    monkeypatch.setattr(integrations, "_persist_tuya_protocols", lambda *_args, **_kwargs: None)
    result = integrations.control_tuya_switch({"devices": [{
        "device_id": "relay-1", "name": "Relay", "switch_code": "switch_1",
        "functions": [{"code": "switch_1", "type": "Boolean", "dp_id": 1}],
        "local_key": "local-key-123", "local_ip": "192.168.8.44", "local_protocol": "3.4",
    }]}, "relay-1", True)
    assert commands == [("3.4", True, 1)]
    assert result["state_confirmed"] is False


def test_kg_six_channel_switch_all_uses_dps_13_when_schema_omits_master_function(monkeypatch):
    calls = []
    class LocalDevice:
        def set_socketTimeout(self, _value): pass
        def set_retry(self, _value): pass
        def status(self): pytest.fail("switch-all command must not read DPS")
        def set_status(self, on, switch=1):
            calls.append((on, switch))
            return {"dps": {str(switch): on}}
    functions = [{"code": f"switch_{index}", "type": "Boolean", "dp_id": index}
                 for index in range(1, 7)]
    device = {"device_id": "kg-six", "category": "kg", "functions": functions,
              "local_key": "local-key-123", "local_ip": "192.168.8.44", "local_protocol": "3.3"}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda _device: LocalDevice())
    result = integrations.control_tuya_switch({"devices": [device]}, "kg-six", True, "switch_all")
    assert calls == [(True, 13)]
    assert result["switch_code"] == "switch_all"
    assert result["command_accepted"] is True


def test_tuya_switch_all_inference_is_not_allowed_for_non_kg_devices(monkeypatch):
    calls = []
    device = {"device_id": "other-six", "category": "other",
              "functions": [{"code": f"switch_{index}", "type": "Boolean", "dp_id": index}
                            for index in range(1, 7)],
              "local_key": "local-key-123", "local_ip": "192.168.8.44"}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda _device: calls.append("client"))
    with pytest.raises(ValueError, match="tuya_switch_function_code_not_configured"):
        integrations.control_tuya_switch({"devices": [device]}, "other-six", True, "switch_all")
    assert calls == []


def test_tuya_switch_control_rejects_unconfigured_device_without_request(monkeypatch):
    calls = []
    monkeypatch.setattr(integrations, "_tuya_request", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(ValueError, match="tuya_device_not_configured"):
        integrations.control_tuya_switch({"client_id": "client", "client_secret": "private-secret", "devices": []},
                                          "unlisted", True)
    assert calls == []


def test_tuya_level_control_sends_percent_without_reading_back(monkeypatch):
    calls = []
    class LocalDevice:
        def set_socketTimeout(self, value): pass
        def set_retry(self, value): pass
        def status(self): pytest.fail("level command must not read DPS")
        def set_value(self, dps, value):
            calls.append(("set_value", dps, value))
            return {"dps": {str(dps): value}}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda device: LocalDevice())
    monkeypatch.setattr(integrations, "_tuya_local_status", lambda device: pytest.fail("level command must not read DPS"))
    monkeypatch.setattr(integrations, "_tuya_request", lambda *args, **kwargs: pytest.fail("Tuya level control used Cloud"))
    result = integrations.control_tuya_level({
        "region": "eu_central",
        "devices": [{"device_id": "device_123", "name": "Estore", "level_code": "position", "level_min": 10, "level_max": 1010, "local_dps_map": {"position": "2"}, "local_key": "local-key-123", "local_ip": "192.168.8.44"}],
    }, "device_123", 50)
    assert calls == [("set_value", 2, 510)]
    assert result["command_accepted"] is True
    assert result["state_confirmed"] is False
    assert result["observed_value"] is None
    assert result["source"] == "TUYA_LAN"


def test_tuya_level_control_rejects_unconfigured_device_without_request(monkeypatch):
    calls = []
    monkeypatch.setattr(integrations, "_tuya_request", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(ValueError, match="tuya_device_not_configured"):
        integrations.control_tuya_level({"client_id": "client", "client_secret": "secret", "devices": []}, "unlisted", 25)
    assert calls == []


def test_tuya_setting_control_writes_only_a_declared_countdown_value(monkeypatch):
    calls = []
    class LocalDevice:
        def set_socketTimeout(self, value): pass
        def set_retry(self, value): pass
        def status(self): pytest.fail("setting command must not read DPS")
        def set_value(self, dps, value):
            calls.append((dps, value))
            return {"dps": {str(dps): value}}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda device: LocalDevice())
    monkeypatch.setattr(integrations, "_tuya_local_status", lambda device: pytest.fail("setting command must not read DPS"))
    monkeypatch.setattr(integrations, "_tuya_request", lambda *args, **kwargs: pytest.fail("Tuya setting control used Cloud"))
    config = {"devices": [{"device_id": "breaker-1", "local_ip": "192.168.1.10", "local_key": "local-key-123",
                           "local_dps_map": {"countdown_1": "7"},
                           "functions": [{"code": "countdown_1", "name": "Countdown", "type": "Integer", "values": '{"min":0,"max":3600,"step":1}'}]}]}
    result = integrations.control_tuya_setting(config, "breaker-1", "countdown_1", 120)
    assert calls == [(7, 120)]
    assert result["state_confirmed"] is False
    assert result["observed_value"] is None
    assert result["source"] == "TUYA_LAN"


def test_tuya_setting_control_rejects_undeclared_or_out_of_range_values(monkeypatch):
    config = {"devices": [{"device_id": "breaker-1", "functions": [{"code": "countdown", "name": "Countdown", "type": "Integer", "values": '{"min":0,"max":60}'}]}]}
    monkeypatch.setattr(integrations, "_tuya_lan_client", lambda device: pytest.fail("Invalid setting sent to device"))
    with pytest.raises(ValueError, match="tuya_setting_value_out_of_range"):
        integrations.control_tuya_setting(config, "breaker-1", "countdown", 61)
    with pytest.raises(ValueError, match="tuya_setting_not_declared"):
        integrations.control_tuya_setting(config, "breaker-1", "child_lock", True)


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


def test_tesla_local_mac_can_be_saved_without_fleet_credentials_and_preserves_existing_fleet():
    local_only = integrations.validate_tesla_config({"local_mac": "4c:fc:aa:d5:86:68"}, existing={})
    assert local_only == {"region": "europe", "local_mac": "4C:FC:AA:D5:86:68"}
    public = integrations.public_tesla_config({"tesla": local_only})
    assert public["local_mac"] == "4C:FC:AA:D5:86:68"
    assert public["configured"] is False

    previous = {"tesla": {"region": "europe", "client_id": "client-id",
                           "refresh_token": "refresh-token-value", "vehicle_ids": ["12345678901234567"]}}
    updated = integrations.validate_tesla_config({"local_mac": "4C:FC:AA:D5:86:68"}, existing=previous)
    assert updated["refresh_token"] == "refresh-token-value"
    assert updated["vehicle_ids"] == ["12345678901234567"]


def test_tesla_local_mac_rejects_malformed_address():
    with pytest.raises(ValueError, match="invalid_tesla_local_mac"):
        integrations.validate_tesla_config({"local_mac": "not-a-mac"}, existing={})


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
