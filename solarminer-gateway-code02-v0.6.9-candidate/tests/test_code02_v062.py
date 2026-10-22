from __future__ import annotations
import hashlib, json, os, socket, sqlite3, subprocess, sys, time
from pathlib import Path
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from solarminer_gateway import energy_registry as energy, worker_ipc as ipc, signed_activation as activation


def dbmem():
    c=sqlite3.connect(":memory:"); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); energy.ensure_schema(c); activation.ensure_schema(c); return c


def profile(c):
    return energy.upsert_equipment(c,{"category":"inversores","name":"Deye experimental","manufacturer":"Deye","model":"SUN-15K-SG05LP3-EU","connector_id":"deye-modbus-tcp","protocol":"Modbus TCP","declared_capabilities":["read_raw_fc03"],"implemented_capabilities":["read_raw_fc03"],"verified_capabilities":[],"limitations":["Mapa de registos candidato; compatibilidade não confirmada"],"config":{"map_status":"CANDIDATE"}})


def test_worker_ipc_accepts_only_allowlisted_health_request():
    msg={"protocol_version":1,"request_id":"abc","operation":"health","arguments":{}}
    assert ipc.validate_request(msg)==msg

@pytest.mark.parametrize("msg",[
    {}, {"protocol_version":2,"request_id":"a","operation":"health","arguments":{}},
    {"protocol_version":1,"request_id":"a","operation":"exec","arguments":{"cmd":"id"}},
    {"protocol_version":1,"request_id":"a","operation":"health","arguments":{"x":1}},
    {"protocol_version":1,"request_id":"a","operation":"deye_fc03_read","arguments":{"host":"192.168.1.3","function_code":16}},
])
def test_worker_ipc_rejects_invalid_or_unallowlisted_requests(msg):
    with pytest.raises(ipc.IPCError): ipc.validate_request(msg)


def test_worker_ipc_frames_json_and_rejects_unterminated_frame():
    left,right=socket.socketpair()
    try:
        left.sendall(ipc.encode_message({"a":1})); assert ipc.recv_message(right)=={"a":1}
    finally:left.close();right.close()
    left,right=socket.socketpair()
    try:
        left.sendall(b'{"a":1}'); left.shutdown(socket.SHUT_WR)
        with pytest.raises(ipc.IPCError): ipc.recv_message(right)
    finally:left.close();right.close()


def test_worker_ipc_peer_uid_is_verified():
    left,right=socket.socketpair()
    try:
        ipc.verify_peer(left,os.getuid())
        with pytest.raises(ipc.IPCError,match="ipc_peer_uid_denied"): ipc.verify_peer(left,os.getuid()+1)
    finally:left.close();right.close()


def test_worker_process_serves_health_over_unix_socket_and_exits_cleanly(tmp_path):
    sock=tmp_path/"worker.sock"
    env={**os.environ,"PYTHONPATH":str(Path(ipc.__file__).resolve().parents[1]),"SOLARMINER_CONNECTOR_ID":"test-worker"}
    proc=subprocess.Popen([sys.executable,"-m","solarminer_gateway.connector_worker","--socket",str(sock),"--gateway-uid",str(os.getuid())],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+4
        while time.monotonic()<deadline and not sock.exists():
            if proc.poll() is not None: pytest.fail("worker exited before IPC socket was ready")
            time.sleep(0.01)
        assert sock.exists()
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(2); client.connect(str(sock))
            result=ipc.request(client,"health",{})
        assert result["worker"]=="ready" and result["connector_id"]=="test-worker"
        assert result["hardware_commands_sent"] is False
    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=3)


def test_equipment_profile_lists_all_required_categories_and_unknown_defaults():
    c=dbmem(); item=profile(c)
    assert set(energy.CATEGORIES)=={"inversores","baterias","mineradoras","ev","aqs","soalho-radiante"}
    assert item["connection_state"]=="UNKNOWN" and item["verified_capabilities"]==[]
    assert energy.get_equipment(c,item["id"])["trust_summary"]["UNKNOWN"]==0


def test_equipment_profile_rejects_invalid_category_or_capability_shape():
    c=dbmem()
    with pytest.raises(ValueError,match="invalid_energy_category"): energy.upsert_equipment(c,{"category":"other","name":"x"})
    with pytest.raises(ValueError,match="invalid_declared_capabilities"): energy.upsert_equipment(c,{"category":"ev","name":"x","declared_capabilities":[1]})


def test_readings_keep_source_unit_timestamp_and_trust_without_promoting_confidence():
    c=dbmem(); item=profile(c)
    r=energy.add_reading(c,item["id"],{"field":"pv1_raw_registers","value":[123,456],"unit":None,"source":"simulator","trust":"SIMULATED","evidence":{"fixture":"unit-test"}})
    assert r["trust"]=="SIMULATED" and json.loads(r["value_json"])==[123,456]
    assert energy.get_equipment(c,item["id"])["readings"][0]["trust"]=="SIMULATED"


def test_physical_trust_cannot_be_set_by_direct_reading_insert_api():
    c=dbmem(); item=profile(c)
    with pytest.raises(ValueError,match="physical_corroboration_requires_test_evidence"):
        energy.add_reading(c,item["id"],{"field":"soc","value":50,"source":"modbus","trust":"PHYSICALLY_CORROBORATED"})


def test_unknown_trust_and_invalid_field_are_rejected():
    c=dbmem(); item=profile(c)
    with pytest.raises(ValueError,match="invalid_trust_class"): energy.add_reading(c,item["id"],{"field":"soc","value":50,"source":"sim","trust":"TRUST_ME"})
    with pytest.raises(ValueError,match="invalid_reading_field"): energy.add_reading(c,item["id"],{"field":"bad field","value":1,"source":"sim","trust":"SIMULATED"})


def test_safe_physical_test_requires_admin_approval_and_records_evidence():
    c=dbmem(); item=profile(c)
    proposal={"title":"Comparação passiva de potência","hypothesis":"O valor de potência acompanha um consumo conhecido","affected_fields":["grid_power_w"],"source_reference":"Procedimento local aprovado pelo técnico","initial_confidence":"CANDIDATE","expected_result":"Variação dentro da tolerância definida pelo técnico","preconditions":["Instalação estável e sem alarmes"],"risks":["Interromper se surgir alarme ou instabilidade"],"instrumentation":["Medidor independente apropriado"],"manual_steps":["Registar leituras sem alterar cablagem nem proteções","Comparar com medidor independente"],"stop_conditions":["Alarme, cheiro a queimado, aquecimento ou divergência perigosa"]}
    test=energy.propose_test(c,item["id"],"admin-1",proposal); assert test["state"]=="PROPOSED"
    with pytest.raises(PermissionError): energy.approve_test(c,test["id"],"admin-1",False)
    energy.add_reading(c,item["id"],{"field":"grid_power_w","value":320,"unit":"W","source":"live_connector","trust":"LIVE_UNVERIFIED","observed_at":"2026-10-18T12:00:00+00:00"})
    energy.approve_test(c,test["id"],"admin-1",True)
    test=energy.record_test_event(c,test["id"],"admin-1","BEFORE",{"grid_power_w":320},"Valor inicial")
    energy.add_reading(c,item["id"],{"field":"grid_power_w","value":360,"unit":"W","source":"live_connector","trust":"LIVE_UNVERIFIED","observed_at":"2026-10-18T12:01:00+00:00"})
    test=energy.record_test_event(c,test["id"],"admin-1","AFTER",{"grid_power_w":360},"Registado manualmente",result="PASS")
    assert test["state"]=="PASS" and test["evidence"]
    reading=energy.latest_readings(c,item["id"])[0]
    assert reading["trust"]=="PHYSICALLY_CORROBORATED"
    assert reading["evidence"]["physical_test_id"]==test["id"]
    assert test["result"]["corroborated_fields"]==["grid_power_w"]


@pytest.mark.parametrize("step",["Desligar painéis fotovoltaicos", "Abrir quadro elétrico", "Manipular condutores energizados", "Desativar BMS"])
def test_dangerous_physical_procedure_is_blocked(step):
    c=dbmem(); item=profile(c)
    p={"title":"Teste perigoso","hypothesis":"h","affected_fields":["pv1"],"source_reference":"comunitária","initial_confidence":"CANDIDATE","expected_result":"x","preconditions":["x"],"risks":["y"],"instrumentation":["z"],"manual_steps":[step],"stop_conditions":["parar"]}
    test=energy.propose_test(c,item["id"],"admin",p)
    assert test["state"]=="BLOCKED"
    with pytest.raises(ValueError,match="physical_test_not_approvable"): energy.approve_test(c,test["id"],"admin",True)


def test_physical_pass_never_promotes_simulated_reading():
    c=dbmem(); item=profile(c)
    p={"title":"Observação passiva","hypothesis":"h","affected_fields":["soc"],"source_reference":"doc","initial_confidence":"CANDIDATE","expected_result":"x","preconditions":["x"],"risks":["x"],"instrumentation":["x"],"manual_steps":["Observar valores no ecrã do equipamento"],"stop_conditions":["Interromper se houver alarme"]}
    t=energy.propose_test(c,item["id"],"admin",p); energy.add_reading(c,item["id"],{"field":"soc","value":50,"source":"fixture","trust":"SIMULATED"}); energy.approve_test(c,t["id"],"admin",True)
    energy.record_test_event(c,t["id"],"admin","AFTER",{"soc":50},result="PASS")
    assert energy.latest_readings(c,item["id"])[0]["trust"]=="SIMULATED"


def test_physical_test_result_rejects_unknown_values():
    c=dbmem(); item=profile(c)
    p={"title":"Teste passivo","hypothesis":"h","affected_fields":["soc"],"source_reference":"doc","initial_confidence":"CANDIDATE","expected_result":"x","preconditions":["x"],"risks":["x"],"instrumentation":["x"],"manual_steps":["Observar valores no ecrã do equipamento"],"stop_conditions":["Interromper se houver alarme"]}
    t=energy.propose_test(c,item["id"],"admin",p); energy.approve_test(c,t["id"],"admin",True)
    with pytest.raises(ValueError,match="invalid_physical_test_result"): energy.record_test_event(c,t["id"],"admin","AFTER",{},result="MAYBE")


def signed_fixture(tmp_path):
    artifact=tmp_path/"connector.bin"; artifact.write_bytes(b"test artifact bytes")
    manifest={"schema_version":1,"connector_id":"test-connector","version":"1.2.3","artifact_sha256":hashlib.sha256(artifact.read_bytes()).hexdigest()}
    raw=json.dumps(manifest,separators=(",",":"),sort_keys=True).encode(); mp=tmp_path/"manifest.json"; mp.write_bytes(raw)
    key=Ed25519PrivateKey.generate(); pub=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    pp=tmp_path/"trusted.pub"; pp.write_text(pub.hex()); sp=tmp_path/"manifest.sig"; sp.write_text(key.sign(raw).hex())
    return artifact,mp,sp,pp,manifest


def test_signed_activation_verifies_signature_and_artifact_hash(tmp_path):
    a,m,s,p,manifest=signed_fixture(tmp_path)
    assert activation.verify_signed_artifact(str(m),str(s),str(p),str(a))==manifest
    a.write_bytes(b"tampered")
    with pytest.raises(ValueError,match="activation_artifact_hash_mismatch"): activation.verify_signed_artifact(str(m),str(s),str(p),str(a))


def test_signed_activation_rejects_invalid_signature(tmp_path):
    a,m,s,p,_=signed_fixture(tmp_path); s.write_text("00"*64)
    with pytest.raises(ValueError,match="activation_signature_invalid_or_untrusted"): activation.verify_signed_artifact(str(m),str(s),str(p),str(a))


def test_lifecycle_requires_hash_dependencies_isolation_and_health_before_active(tmp_path):
    a,m,s,p,manifest=signed_fixture(tmp_path); verified=activation.verify_signed_artifact(str(m),str(s),str(p),str(a)); c=dbmem()
    op=activation.create_operation(c,verified,str(a),"admin")
    with pytest.raises(ValueError,match="dependency_hashes_not_verified"): activation.transition(c,op["operation_id"],"VENV_READY",{})
    activation.transition(c,op["operation_id"],"VENV_READY",{"dependency_hashes_verified":True})
    with pytest.raises(ValueError,match="isolation_not_operationally_verified"): activation.transition(c,op["operation_id"],"ACTIVATED",{"isolation_enforced":False})
    activation.transition(c,op["operation_id"],"ACTIVATED",{"isolation_enforced":True,"systemd_unit_verified":True})
    with pytest.raises(ValueError,match="worker_health_or_contract_not_verified"): activation.transition(c,op["operation_id"],"ACTIVE",{"health_check_passed":False})
    result=activation.transition(c,op["operation_id"],"ACTIVE",{"health_check_passed":True,"interface_contract_passed":True})
    assert result["state"]=="ACTIVE"


def test_lifecycle_rejects_invalid_transitions_and_recovers_incomplete_without_claiming_filesystem_rollback(tmp_path):
    a,m,s,p,manifest=signed_fixture(tmp_path); c=dbmem(); verified=activation.verify_signed_artifact(str(m),str(s),str(p),str(a)); op=activation.create_operation(c,verified,str(a),"admin")
    with pytest.raises(ValueError,match="invalid_lifecycle_transition"): activation.transition(c,op["operation_id"],"ACTIVE",{})
    plan=activation.recovery_plan(c,"test-connector")
    assert plan["action"]=="ROLLBACK_REQUIRED" and plan["filesystem_or_systemd_changed"] is False


def test_energy_api_uses_existing_auth_rbac_and_audit(tmp_path, monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from solarminer_gateway import app as gateway
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    with TestClient(gateway.app) as client:
        assert client.get("/api/v1/energy/categories").status_code == 401
        token=gateway.BOOTSTRAP_PATH.read_text().strip(); key=Ed25519PrivateKey.generate()
        pub=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        ts=int(time.time()); nonce="energy-bootstrap-nonce-01"; mac="AA:BB:CC:DD:EE:71"
        canonical=f"BOOTSTRAP\nenergyowner\n{mac}\n{ts}\n{nonce}"
        created=client.post("/api/v1/bootstrap/owner",json={"bootstrap_token":token,"username":"energyowner","password":"a-long-energy-passphrase-01","mac":mac,"public_key_pem":pub,"signature":key.sign(canonical.encode()).hex(),"timestamp":ts,"nonce":nonce})
        assert created.status_code==201
        ts=int(time.time()); nonce="energy-login-nonce-01"; device=created.json()["device_id"]
        canonical=f"LOGIN\nenergyowner\n{device}\n{ts}\n{nonce}"
        login=client.post("/api/v1/auth/login",json={"username":"energyowner","password":"a-long-energy-passphrase-01","device_id":device,"timestamp":ts,"nonce":nonce,"signature":key.sign(canonical.encode()).hex()})
        assert login.status_code==200
        headers={"Authorization":"Bearer "+login.json()["access_token"]}
        categories=client.get("/api/v1/energy/categories",headers=headers).json()
        assert [c["id"] for c in categories["categories"]]==["inversores","baterias","mineradoras","ev","aqs","soalho-radiante"]
        created_profile=client.post("/api/v1/energy/equipment",headers=headers,json={"category":"inversores","name":"Deye experimental","manufacturer":"Deye","model":"SUN-15K-SG05LP3-EU","connector_id":"deye-modbus-tcp","protocol":"Modbus TCP","limitations":["mapa candidato"]})
        assert created_profile.status_code==201, created_profile.text
        equipment_id=created_profile.json()["id"]
        reading=client.post(f"/api/v1/energy/equipment/{equipment_id}/readings",headers=headers,json={"field":"pv1_raw","value":[12,34],"source":"simulator","trust":"SIMULATED"})
        assert reading.status_code==201
        forbidden=client.post(f"/api/v1/energy/equipment/{equipment_id}/readings",headers=headers,json={"field":"pv1","value":1,"source":"test","trust":"PHYSICALLY_CORROBORATED"})
        assert forbidden.status_code==422
        detail=client.get(f"/api/v1/energy/equipment/{equipment_id}",headers=headers).json()
        assert detail["readings"][0]["trust"]=="SIMULATED"
        assert client.get("/api/v1/energy/engine",headers=headers).status_code==200
        configured=client.put("/api/v1/energy/engine/config",headers=headers,json={"battery_capacity_kwh":18,"minimum_soc_percent":20,"maximum_soc_percent":95})
        assert configured.status_code==200 and configured.json()["battery_capacity_kwh"]==18
        assert client.put("/api/v1/energy/engine/config",headers=headers,json={"battery_capacity_kwh":18,"minimum_soc_percent":98,"maximum_soc_percent":95}).status_code==422
        monkeypatch.setattr(gateway.hardware_integrations,"load_config",lambda:{"tuya":{"devices":[{"device_id":"switch1","switch_code":"switch_1"}]}})
        def fake_tuya_control(_config, device_id, on):
            if device_id != "switch1": raise ValueError("tuya_device_not_configured")
            return {"device_id":device_id,"requested_on":on,"state_confirmed":True,"control_command_sent":True}
        monkeypatch.setattr(gateway.hardware_integrations,"control_tuya_switch",fake_tuya_control)
        tuya_owner=client.post("/api/v1/integrations/tuya/switch",headers=headers,json={"device_id":"switch1","on":True})
        assert tuya_owner.status_code==200 and tuya_owner.json()["state_confirmed"] is True
        assert client.post("/api/v1/integrations/tuya/switch",headers=headers,json={"device_id":"other","on":True}).status_code==422
        invalid_load=client.put("/api/v1/energy/engine/config",headers=headers,json={"loads":[{"id":"aqs1","name":"AQS 1","kind":"water_heater","control_type":"tuya_breaker","rated_power_w":1500,"tuya_device_id":"switch1","tuya_switch_code":"wrong_code"}]})
        assert invalid_load.status_code==422
        valid_load=client.put("/api/v1/energy/engine/config",headers=headers,json={"loads":[{"id":"aqs1","name":"AQS 1","kind":"water_heater","control_type":"tuya_breaker","rated_power_w":1500,"tuya_device_id":"switch1","tuya_switch_code":"switch_1"}]})
        assert valid_load.status_code==200 and valid_load.json()["loads"][0]["name"]=="AQS 1"
        viewer_id="00000000-0000-4000-8000-000000000071"; viewer_token="energy-viewer-session-token"
        with gateway.db() as conn:
            conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?,?,?,?)",
                         (viewer_id,"energy-account","energyviewer","unused-hash","viewer","active",gateway.utcnow()))
            conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,?,?)",
                         (viewer_id,device,"active",gateway.utcnow()))
            conn.execute("INSERT INTO sessions(token_sha256,user_id,device_id,created_at,expires_at,credential_version) VALUES(?,?,?,?,?,1)",
                         (gateway.token_hash(viewer_token),viewer_id,device,int(time.time()),int(time.time())+3600))
        viewer_headers={"Authorization":"Bearer "+viewer_token}
        assert client.get("/api/v1/energy/engine",headers=viewer_headers).status_code==200
        assert client.put("/api/v1/energy/engine/config",headers=viewer_headers,json={"battery_capacity_kwh":18,"minimum_soc_percent":20,"maximum_soc_percent":95}).status_code==403
        assert client.post("/api/v1/integrations/tuya/switch",headers=viewer_headers,json={"device_id":"switch1","on":False}).status_code==403
        with gateway.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM audit WHERE action LIKE 'energy.%'").fetchone()[0]>=2


def test_worker_source_has_no_database_or_shell_execution_surface():
    source=Path(ipc.__file__).with_name("connector_worker.py").read_text()
    assert "sqlite3" not in source and "subprocess" not in source
    assert "os.system" not in source and "shell=True" not in source


def test_signed_lifecycle_refuses_unverified_manifest_dict(tmp_path):
    _artifact,_manifest,_signature,_public,manifest=signed_fixture(tmp_path)
    with pytest.raises(ValueError,match="verified_signed_manifest_required"):
        activation.create_operation(dbmem(),manifest,str(_artifact),"admin")


def test_physical_result_is_only_accepted_with_after_observation():
    c=dbmem(); item=profile(c)
    p={"title":"Observação passiva","hypothesis":"h","affected_fields":["soc"],"source_reference":"doc","initial_confidence":"CANDIDATE","expected_result":"x","preconditions":["x"],"risks":["x"],"instrumentation":["x"],"manual_steps":["Observar valores no ecrã do equipamento"],"stop_conditions":["Interromper se houver alarme"]}
    t=energy.propose_test(c,item["id"],"admin",p); energy.approve_test(c,t["id"],"admin",True)
    with pytest.raises(ValueError,match="test_result_requires_after_phase"):
        energy.record_test_event(c,t["id"],"admin","BEFORE",{},result="PASS")
    assert energy.get_test(c,t["id"])["state"]=="APPROVED"
