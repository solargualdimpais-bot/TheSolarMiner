import hashlib, json, os, time
from pathlib import Path
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from solarminer_gateway import app as gateway
from solarminer_gateway.updates import canonical_manifest, verify_manifest, UpdateValidationError
import pytest


def keypair():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public

def sig(private, text): return private.sign(text.encode()).hex()


def test_runtime_package_version_matches_debian_metadata_and_usb_repair_target():
    root = Path(__file__).resolve().parents[1]
    control = (root / "packaging" / "control").read_text(encoding="utf-8")
    package_version = next(line.split(":", 1)[1].strip()
                           for line in control.splitlines() if line.startswith("Version:"))
    repair = (root / "packaging" / "repair-existing-from-usb.sh").read_text(encoding="utf-8")
    assert gateway.PACKAGE_VERSION == package_version
    assert f"TARGET_VERSION={package_version}" in repair

def test_tuya_pid_dps_validation_identifies_invalid_row_and_field(client):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    response = client.put("/api/v1/integrations/tuya/product-dps-map", headers=headers, json={
        "product_id": "test-pid",
        "rows": [
            {"dps_id": 1, "label_pt": "Interruptor", "source": "unknown", "data_type": "bool", "semantic_code": "switch"},
            {"dps_id": 20, "label_pt": "Tensão", "source": "unknown", "data_type": "tipo inválido", "semantic_code": "voltage"},
        ],
    })
    assert response.status_code == 422
    assert response.json()["detail"] == "tuya_pid_dps_row_invalid|row=2|dps=20|field=data_type|reason=unsupported_value"

def test_tuya_pid_dps_accepts_portuguese_type_labels(client):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    response = client.put("/api/v1/integrations/tuya/product-dps-map", headers=headers, json={
        "product_id": "test-pid-portuguese-types",
        "rows": [
            {"dps_id": 1, "label_pt": "Interruptor", "source": "unknown", "data_type": "Booleano", "semantic_code": "switch"},
            {"dps_id": 9, "label_pt": "Temporizador", "source": "unknown", "data_type": "Valor numérico", "unit": "s", "scale": 1, "semantic_code": "countdown"},
            {"dps_id": 40, "label_pt": "Luz", "source": "unknown", "data_type": "Enumeração", "semantic_code": "unknown"},
        ],
    })
    assert response.status_code == 200, response.text
    assert response.json()["dps_count"] == 3

def test_tuya_pid_dps_partial_update_only_replaces_the_submitted_dps(client):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    first = client.put("/api/v1/integrations/tuya/product-dps-map", headers=headers, json={
        "product_id": "partial-pid",
        "rows": [
            {"dps_id": 1, "label_pt": "Interruptor", "source": "unknown", "data_type": "bool", "semantic_code": "switch"},
            {"dps_id": 23, "label_pt": "Calibração", "source": "unknown", "data_type": "value", "scale": 1, "semantic_code": "unknown"},
        ],
    })
    assert first.status_code == 200, first.text
    updated = client.put("/api/v1/integrations/tuya/product-dps-map", headers=headers, json={
        "product_id": "partial-pid", "partial": True,
        "rows": [{"dps_id": 23, "label_pt": "Calibração corrente", "source": "unknown", "data_type": "value", "scale": 0.001, "semantic_code": "current"}],
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["dps_count"] == 2
    with gateway.db() as conn:
        stored = {row["dps_id"]: json.loads(row["payload_json"]) for row in conn.execute("SELECT dps_id,payload_json FROM tuya_pid_dps_editor WHERE product_id='partial-pid'")}
    assert stored[1]["label_pt"] == "Interruptor"
    assert stored[23]["label_pt"] == "Calibração corrente"
    assert stored[23]["scale"] == 0.001

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    monkeypatch.setenv("SOLARMINER_DATA_DIR", str(tmp_path / "data"))
    gwpriv, gwpub = keypair()
    privpath, pubpath = tmp_path / "gw.key", tmp_path / "gw.pub"
    privpath.write_bytes(gwpriv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    privpath.chmod(0o600)
    pubpath.write_text(gwpub)
    monkeypatch.setenv("SOLARMINER_GATEWAY_IDENTITY_PRIVATE_KEY", str(privpath))
    monkeypatch.setenv("SOLARMINER_GATEWAY_IDENTITY_PUBLIC_KEY", str(pubpath))
    with TestClient(gateway.app) as c:
        yield c

def owner_session(client):
    token = gateway.BOOTSTRAP_PATH.read_text().strip()
    priv, pub = keypair(); ts=int(time.time()); nonce="bootstrap-v067-owner-nonce"
    canonical=f"BOOTSTRAP\nowner-v067\nAA:BB:CC:DD:EE:01\n{ts}\n{nonce}"
    r=client.post("/api/v1/bootstrap/owner",json={"bootstrap_token":token,"username":"owner-v067","password":"owner-password-v067-long","mac":"AA:BB:CC:DD:EE:01","public_key_pem":pub,"signature":sig(priv,canonical),"timestamp":ts,"nonce":nonce})
    assert r.status_code == 201, r.text
    ts=int(time.time()); nonce="login-v067-owner-nonce"
    canonical=f"LOGIN\nowner-v067\n{r.json()['device_id']}\n{ts}\n{nonce}"
    login=client.post("/api/v1/auth/login",json={"username":"owner-v067","password":"owner-password-v067-long","device_id":r.json()['device_id'],"timestamp":ts,"nonce":nonce,"signature":sig(priv,canonical)})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]

def test_owner_invite_create_list_and_revoke(client):
    token=owner_session(client); h={"Authorization":f"Bearer {token}"}
    created=client.post("/api/v1/invites",headers=h,json={"role":"viewer","label":"phone test"})
    assert created.status_code == 201, created.text
    body=created.json(); assert len(body["invite_code"]["fp"]) == 64
    assert body["invite_code"]["exp"] == body["expires_at"]
    assert "qr_svg" not in body and "qr_payload" not in body
    listed=client.get("/api/v1/invites",headers=h).json()["invites"]
    assert listed[0]["state"] == "pending"
    assert "token" not in listed[0] and "token_hash" not in listed[0]
    revoked=client.post(f"/api/v1/invites/{body['invite_id']}/revoke",headers=h)
    assert revoked.status_code == 200
    assert client.post(f"/api/v1/invites/{body['invite_id']}/revoke",headers=h).status_code == 409

def test_invite_code_does_not_depend_on_a_gateway_public_url(client, monkeypatch):
    monkeypatch.delenv("SOLARMINER_PUBLIC_URL", raising=False)
    token=owner_session(client); h={"Authorization":f"Bearer {token}"}
    response=client.post("/api/v1/invites",headers=h,json={"role":"viewer","label":"lan-or-tailnet"})
    assert response.status_code == 201, response.text
    assert response.json()["invite_code"]["token"]

def test_owner_energy_engine_configuration_round_trip(client):
    token = owner_session(client)
    headers = {"Authorization": f"Bearer {token}"}
    configured = [{"id": "pv-string-roof-1", "name": "Telhado", "manufacturer": "Example",
                   "panel_count": 8, "panel_power_w": 450, "mppt": 1,
                   "nominal_power_kw": 3.6, "active": True}]
    saved = client.put("/api/v1/energy/engine/config", headers=headers,
                       json={"pv_strings": configured, "battery_capacity_kwh": 10})
    assert saved.status_code == 200, saved.text
    assert saved.json()["pv_strings"] == configured
    loaded = client.get("/api/v1/energy/engine/config", headers=headers)
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["pv_strings"] == configured
    assert loaded.json()["battery_capacity_kwh"] == 10

def test_invite_redeem_atomic_and_single_use(client):
    token=owner_session(client); h={"Authorization":f"Bearer {token}"}
    invite=client.post("/api/v1/invites",headers=h,json={"role":"operator","label":"new operator"}).json()
    priv,pub=keypair(); ts=int(time.time()); nonce="invite-redeem-nonce-0001"; username="operator-v067"
    mac="AA:BB:CC:DD:EE:44"; password="operator-password-v067-long"
    token_hash=hashlib.sha256(invite["invite_code"]["token"].encode()).hexdigest()
    pub_der=serialization.load_pem_public_key(pub.encode()).public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    pub_hash=hashlib.sha256(pub_der).hexdigest()
    canonical="\n".join(["POST","/api/v1/invites/redeem",str(ts),nonce,token_hash,username,hashlib.sha256(password.encode()).hexdigest(),mac,pub_hash])
    body={"invite_token":invite["invite_code"]["token"],"username":username,"password":password,"mac":mac,"client_pubkey_pem":pub,"signature":sig(priv,canonical),"timestamp":ts,"nonce":nonce}
    response=client.post("/api/v1/invites/redeem",json=body)
    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "operator"
    again=client.post("/api/v1/invites/redeem",json=body)
    assert again.status_code in (400,409)
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username=?",(username,)).fetchone()[0] == 1
        assert conn.execute("SELECT used_at FROM invites WHERE id=?",(invite["invite_id"],)).fetchone()[0] is not None

def test_invite_role_privilege_and_gateway_identity_fail_closed(client, monkeypatch):
    token=owner_session(client); h={"Authorization":f"Bearer {token}"}
    assert client.post("/api/v1/invites",headers=h,json={"role":"owner","label":"bad"}).status_code == 422
    monkeypatch.setenv("SOLARMINER_GATEWAY_IDENTITY_PUBLIC_KEY", "/no/such/key")
    assert client.post("/api/v1/invites",headers=h,json={"role":"viewer","label":"blocked"}).status_code == 503

def test_update_manifest_signature_verification():
    priv,pem=keypair(); pub=serialization.load_pem_public_key(pem.encode())
    manifest={"schema_version":1,"release_id":"r-1","version":"0.6.8","min_compatible_version":"0.6.7","changelog":["fix"],"package_name":"solarminer.deb","package_url":"https://releases.example.test/solarminer.deb","package_size":10,"sha256":"a"*64,"signature_algorithm":"Ed25519","compatibility":{},"migration_requirements":[]}
    manifest["signature"]=priv.sign(canonical_manifest(manifest)).hex()
    assert verify_manifest(manifest,pub,"0.6.7")["signature_valid"] is True
    tampered=dict(manifest); tampered["version"]="9.9.9"
    with pytest.raises(UpdateValidationError): verify_manifest(tampered,pub,"0.6.7")
    malformed_version=dict(manifest); malformed_version["version"]="0.6.8;touch /tmp/no"
    with pytest.raises(UpdateValidationError, match="manifest_version_invalid"):
        verify_manifest(malformed_version,pub,"0.6.7")


def test_update_manifest_compatibility_accepts_current_and_older_supported_release():
    private, pem = keypair()
    public = serialization.load_pem_public_key(pem.encode())
    manifest = {
        "schema_version": 1, "release_id": "gateway-v0.6.10", "version": "0.6.10",
        "min_compatible_version": "0.6.9", "changelog": ["fix"],
        "package_name": "solarminer-gateway_0.6.10_amd64.deb",
        "package_url": "https://github.com/solarminer/releases/download/gateway-v0.6.10/package.deb",
        "package_size": 10, "sha256": "a" * 64, "signature_algorithm": "Ed25519",
        "compatibility": {}, "migration_requirements": [],
    }
    manifest["signature"] = private.sign(canonical_manifest(manifest)).hex()
    assert verify_manifest(manifest, public, "0.6.9")["compatible"] is True
    assert verify_manifest(manifest, public, "0.6.10")["compatible"] is True
    with pytest.raises(UpdateValidationError, match="installed_version_not_compatible"):
        verify_manifest(manifest, public, "0.6.8")


def test_update_manifest_rejects_downgrade():
    private, pem = keypair()
    public = serialization.load_pem_public_key(pem.encode())
    manifest = {
        "schema_version": 1, "release_id": "gateway-v0.6.8", "version": "0.6.8",
        "min_compatible_version": "0.6.7", "changelog": ["old"],
        "package_name": "solarminer.deb", "package_url": "https://releases.example.test/solarminer.deb",
        "package_size": 10, "sha256": "a" * 64, "signature_algorithm": "Ed25519",
        "compatibility": {}, "migration_requirements": [],
    }
    manifest["signature"] = private.sign(canonical_manifest(manifest)).hex()
    with pytest.raises(UpdateValidationError, match="release_version_is_older"):
        verify_manifest(manifest, public, "0.6.9")


def test_gateway_identity_challenge_proves_key_possession(client):
    ts=int(time.time()); nonce="gateway-identity-test-nonce"
    response=client.get("/api/v1/gateway/identity",params={"timestamp":ts,"nonce":nonce})
    assert response.status_code == 200, response.text
    data=response.json(); pub=serialization.load_pem_public_key(data["public_key_pem"].encode())
    pub.verify(bytes.fromhex(data["signature"]),f"GET\n/api/v1/gateway/identity\n{ts}\n{nonce}".encode())
    assert len(data["fingerprint_sha256"]) == 64

def test_invite_management_is_owner_only_for_admin_operator_viewer(client):
    owner_token=owner_session(client); headers={"Authorization":f"Bearer {owner_token}"}
    roles=["admin","operator","viewer"]
    with gateway.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for role in roles:
            uid, did = f"test-{role}-user", f"test-{role}-device"
            dpriv, dpub=keypair()
            der=serialization.load_pem_public_key(dpub.encode()).public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
            conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?,?,'active',?)",(uid,uid,uid,gateway.PASSWORDS.hash("a-long-test-password-"+role),role,gateway.utcnow()))
            conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?,'declared','active',?)",(did,dpub,hashlib.sha256(der).hexdigest(),"AA:BB:CC:DD:EE:"+{"admin":"11","operator":"12","viewer":"13"}[role],gateway.utcnow()))
            conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)",(uid,did,gateway.utcnow()))
            raw="session-token-for-"+role
            conn.execute("INSERT INTO sessions(token_sha256,user_id,device_id,created_at,expires_at,credential_version) VALUES(?,?,?,?,?,1)",(gateway.token_hash(raw),uid,did,int(time.time()),int(time.time())+3600))
        conn.commit()
    for role in roles:
        h={"Authorization":f"Bearer session-token-for-{role}"}
        assert client.post("/api/v1/invites",headers=h,json={"role":"viewer","label":"should fail"}).status_code == 403
        assert client.get("/api/v1/invites",headers=h).status_code == 403

def test_two_concurrent_invite_redemptions_only_create_one_account(client):
    from concurrent.futures import ThreadPoolExecutor
    token=owner_session(client); h={"Authorization":f"Bearer {token}"}
    invite=client.post("/api/v1/invites",headers=h,json={"role":"viewer","label":"race"}).json()
    priv,pub=keypair(); username="race-v067"; mac="AA:BB:CC:DD:EE:55"; password="race-password-v067-long"
    pub_der=serialization.load_pem_public_key(pub.encode()).public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    pub_hash=hashlib.sha256(pub_der).hexdigest(); token_digest=hashlib.sha256(invite["invite_code"]["token"].encode()).hexdigest()
    def redeem(nonce):
        ts=int(time.time())
        canonical="\n".join(["POST","/api/v1/invites/redeem",str(ts),nonce,token_digest,username,hashlib.sha256(password.encode()).hexdigest(),mac,pub_hash])
        body={"invite_token":invite["invite_code"]["token"],"username":username,"password":password,"mac":mac,"client_pubkey_pem":pub,"signature":sig(priv,canonical),"timestamp":ts,"nonce":nonce}
        return client.post("/api/v1/invites/redeem",json=body).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(redeem,["race-invite-nonce-0001","race-invite-nonce-0002"]))
    assert statuses.count(201) == 1, statuses
    assert len([x for x in statuses if x in (400,409)]) == 1, statuses
    with gateway.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username=?",(username,)).fetchone()[0] == 1

def test_update_check_reports_not_configured_and_apply_stays_disabled(client, monkeypatch):
    monkeypatch.delenv("SOLARMINER_RELEASE_MANIFEST_URL", raising=False)
    token=owner_session(client); headers={"Authorization":f"Bearer {token}"}
    check=client.get("/api/v1/system/update/check",headers=headers)
    assert check.status_code == 200
    assert check.json()["status"] == "not_configured"
    assert check.json()["activation_available"] is False
    status=client.get("/api/v1/system/update/status",headers=headers)
    assert status.status_code == 200 and status.json()["status"] == "IDLE"
    apply=client.post("/api/v1/system/update/apply",headers=headers,json={"version":"0.6.8","confirm":True})
    assert apply.status_code == 503
    assert "independent_recovery_deployment" in apply.json()["detail"]


def test_energy_categories_report_embedded_pwa_version(client):
    token=owner_session(client)
    response=client.get("/api/v1/energy/categories",headers={"Authorization":f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["pwa_source_available"] is True
    assert response.json()["integration_state"] == "API_READY_PWA_V0_5_7_SAME_ORIGIN"


def test_apply_queues_verified_operation_through_privileged_helper(client, monkeypatch):
    token = owner_session(client)
    with gateway.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        op = gateway._update_state_write(conn, "VERIFIED", "0.6.9", {
            "package_path": "/var/lib/solarminer/releases/verified/test.deb.verified",
            "manifest_path": "/var/lib/solarminer/releases/verified/test.deb.verified.manifest.json",
            "activation_available": True,
        })
        conn.commit()
    captured = []
    def fake_request(action, operation_id=None):
        captured.append((action, operation_id))
        return {"status": "APPLY_QUEUED", "operation_id": op, "target_version": "0.6.9",
                "status_url": "/api/v1/system/update/status", "health_check_seconds": 60}
    monkeypatch.setattr(gateway.update_helper_client, "request", fake_request)
    response = client.post("/api/v1/system/update/apply",
        headers={"Authorization": f"Bearer {token}"}, json={"version": "0.6.9", "confirm": True})
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "APPLY_QUEUED"
    assert response.json()["health_check_seconds"] == 60
    assert captured == [("enqueue", op)]


def test_repository_update_check_is_owner_only_and_passes_allowlisted_source(client, monkeypatch):
    token = owner_session(client)
    headers = {"Authorization": f"Bearer {token}"}
    seen = {}
    source = {"repository_url": "https://github.com/solarminer/releases",
              "manifest_url": "https://github.com/solarminer/releases/latest/manifest.json",
              "manifest_origins": {"https://github.com"},
              "package_origins": {"https://github.com"}}
    def load_source(url, path):
        seen["url"] = url
        return source
    def check_manifest(url, session, **kwargs):
        seen["manifest_url"] = url
        seen["kwargs"] = kwargs
        return {"status": "verified_staged", "available_version": "0.6.9",
                "signature_valid": True, "activation_available": True}
    monkeypatch.setattr(gateway.update_manager, "load_update_source", load_source)
    monkeypatch.setattr(gateway.update_manager, "list_update_sources", lambda path: [source])
    monkeypatch.setattr(gateway, "_check_system_update_manifest", check_manifest)

    initial = client.get("/api/v1/system/update/source", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["repository_url"] == source["repository_url"]
    response = client.post("/api/v1/system/update/check", headers=headers,
                           json={"repository_url": "https://github.com/solarminer/releases"})
    assert response.status_code == 200, response.text
    assert response.json()["available_version"] == "0.6.9"
    assert seen["url"] == source["repository_url"]
    assert seen["manifest_url"] == source["manifest_url"]
    assert seen["kwargs"]["repository_url"] == source["repository_url"]
    with gateway.db() as conn:
        saved = conn.execute("SELECT value FROM system_state WHERE key='update_repository_url'").fetchone()
    assert saved and saved["value"] == source["repository_url"]
    assert client.get("/api/v1/system/update/source", headers=headers).json()["repository_url"] == source["repository_url"]


def test_repository_update_check_rejects_non_owner_roles(client):
    owner_session(client)
    roles = ["admin", "operator", "viewer"]
    with gateway.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for role in roles:
            uid, did = f"update-{role}-user", f"update-{role}-device"
            _, dpub = keypair()
            der = serialization.load_pem_public_key(dpub.encode()).public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?,?,'active',?)",
                         (uid, uid, uid, gateway.PASSWORDS.hash("update-role-password-" + role), role, gateway.utcnow()))
            conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?,'declared','active',?)",
                         (did, dpub, hashlib.sha256(der).hexdigest(), "AA:BB:CC:DD:EE:" + {"admin":"21","operator":"22","viewer":"23"}[role], gateway.utcnow()))
            conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)",
                         (uid, did, gateway.utcnow()))
            raw = "update-session-token-" + role
            conn.execute("INSERT INTO sessions(token_sha256,user_id,device_id,created_at,expires_at,credential_version) VALUES(?,?,?,?,?,1)",
                         (gateway.token_hash(raw), uid, did, int(time.time()), int(time.time()) + 3600))
        conn.commit()
    for role in roles:
        response = client.post("/api/v1/system/update/check",
            headers={"Authorization": f"Bearer update-session-token-{role}"},
            json={"repository_url": "https://github.com/solarminer/releases"})
        assert response.status_code == 403, (role, response.text)
        source_response = client.get("/api/v1/system/update/source",
            headers={"Authorization": f"Bearer update-session-token-{role}"})
        assert source_response.status_code == 403, (role, source_response.text)


def test_repository_update_check_rejects_invalid_and_unconfigured_urls(client, monkeypatch):
    token = owner_session(client)
    headers = {"Authorization": f"Bearer {token}"}
    invalid = client.post("/api/v1/system/update/check", headers=headers,
                          json={"repository_url": "https://github.com/solarminer/releases/tree/main"})
    assert invalid.status_code == 200
    assert invalid.json()["status"] == "rejected"
    assert invalid.json()["signature_valid"] is False

    def reject_source(url, path):
        raise UpdateValidationError("repository_not_allowlisted")
    monkeypatch.setattr(gateway.update_manager, "load_update_source", reject_source)
    rejected = client.post("/api/v1/system/update/check", headers=headers,
                           json={"repository_url": "https://github.com/solarminer/releases"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["message"] == "repository_not_allowlisted"


def test_hardware_integration_config_is_owner_only_and_secrets_are_redacted(client, monkeypatch, tmp_path):
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path / "gateway-data")
    token = owner_session(client)
    headers = {"Authorization": f"Bearer {token}"}
    secret = "tuya-access-secret-123"
    saved = client.put("/api/v1/integrations/hardware", headers=headers, json={
        "deye": {"host": "192.168.8.10", "port": 502, "unit_id": 1, "model": "other"},
        "antminer": {"host": "192.168.8.20", "port": 4028, "model": "S19K Pro"},
        "tuya": {"region": "eu_central", "client_id": "tuya-client-id", "client_secret": secret,
                 "devices": [{"device_id": "tuya_device_123", "name": "Plug"}]},
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["tuya"]["configured"] is True
    assert secret not in saved.text
    read = client.get("/api/v1/integrations/hardware", headers=headers)
    assert read.status_code == 200
    assert read.json()["deye"]["host"] == "192.168.8.10"
    assert read.json()["antminer"]["port"] == 4028
    assert read.json()["tuya"]["device_ids"] == ["tuya_device_123"]
    assert secret not in read.text
    monkeypatch.setattr(gateway.hardware_integrations, "control_antminer", lambda config, action, watt=None: {
        "action": action, "requested_watt": watt, "applied_watt": watt,
        "connection_state": "control_applied", "control_command_sent": True,
    })
    control = client.post("/api/v1/integrations/antminer/control", headers=headers,
                          json={"action": "set_power_target", "watt": 2400})
    assert control.status_code == 200, control.text
    assert control.json()["applied_watt"] == 2400
    assert client.post("/api/v1/integrations/antminer/control", headers=headers,
                       json={"action": "reboot"}).status_code == 422
    tesla_secret = "tesla-refresh-secret-123"
    tesla_saved = client.put("/api/v1/energy/ev/tesla", headers=headers, json={
        "region": "europe", "client_id": "tesla-client-id", "refresh_token": tesla_secret,
        "vehicle_ids": ["12345678901234567"],
    })
    assert tesla_saved.status_code == 200, tesla_saved.text
    assert tesla_saved.json()["configured"] is True
    assert tesla_secret not in tesla_saved.text
    assert "tesla" not in client.get("/api/v1/integrations/hardware", headers=headers).json()
    generic_update = client.put("/api/v1/integrations/hardware", headers=headers, json={
        "deye": {"host": "192.168.8.11", "port": 502, "unit_id": 1, "model": "other"}
    })
    assert generic_update.status_code == 200, generic_update.text
    assert client.get("/api/v1/energy/ev/tesla", headers=headers).json()["configured"] is True
    monkeypatch.setattr(gateway.hardware_integrations, "read_tesla_ev", lambda config: {
        "vehicles": [{"name": "Tesla", "charge_state": {"battery_level": 61}}],
        "source": "TESLA_FLEET_API_EV_CHARGING_READ_ONLY", "trust": "LIVE_UNVERIFIED",
        "control_commands_sent": False, "observed_at": time.time(),
    })
    tesla_read = client.post("/api/v1/energy/ev/tesla/read", headers=headers, json={})
    assert tesla_read.status_code == 200, tesla_read.text
    assert tesla_read.json()["vehicles"][0]["charge_state"]["battery_level"] == 61
    invalid = client.put("/api/v1/integrations/hardware", headers=headers, json={
        "deye": {"host": "8.8.8.8", "port": 502, "unit_id": 1}
    })
    assert invalid.status_code == 422

    with gateway.db() as conn:
        uid, did = "hardware-admin", "hardware-admin-device"
        _, dpub = keypair()
        der = serialization.load_pem_public_key(dpub.encode()).public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'admin','active',?)",
                     (uid, uid, uid, gateway.PASSWORDS.hash("hardware-admin-password"), gateway.utcnow()))
        conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?,'declared','active',?)",
                     (did, dpub, hashlib.sha256(der).hexdigest(), "AA:BB:CC:DD:EE:77", gateway.utcnow()))
        conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)", (uid, did, gateway.utcnow()))
        raw = "hardware-admin-session-token"
        conn.execute("INSERT INTO sessions(token_sha256,user_id,device_id,created_at,expires_at,credential_version) VALUES(?,?,?,?,?,1)",
                     (gateway.token_hash(raw), uid, did, int(time.time()), int(time.time()) + 3600))
    admin_headers = {"Authorization": "Bearer hardware-admin-session-token"}
    assert client.get("/api/v1/integrations/hardware", headers=admin_headers).status_code == 403
    assert client.put("/api/v1/integrations/hardware", headers=admin_headers, json={}).status_code == 403
    assert client.post("/api/v1/integrations/hardware/read", headers=admin_headers, json={}).status_code == 403
    assert client.post("/api/v1/integrations/antminer/control", headers=admin_headers,
                       json={"action": "stop"}).status_code == 403
    assert client.post("/api/v1/integrations/hardware/deye/read", headers=admin_headers, json={}).status_code == 403
    assert client.post("/api/v1/integrations/hardware/antminer/read", headers=admin_headers, json={}).status_code == 403
    assert client.get("/api/v1/energy/ev/tesla", headers=admin_headers).status_code == 403
    assert client.put("/api/v1/energy/ev/tesla", headers=admin_headers, json={}).status_code == 403
    assert client.post("/api/v1/energy/ev/tesla/read", headers=admin_headers, json={}).status_code == 403


def test_hardware_provider_read_is_independent_and_owner_only(client, monkeypatch, tmp_path):
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path / "gateway-data")
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    saved = client.put("/api/v1/integrations/hardware", headers=headers, json={
        "deye": {"host": "192.168.8.10", "port": 502, "unit_id": 1, "model": "other"},
        "antminer": {"host": "192.168.8.69", "port": 4028, "rest_port": 80, "model": "S19K Pro"},
        "tuya": {"region": "eu_central", "client_id": "tuya-client-id", "client_secret": "tuya-secret-123", "devices": [
            {"device_id": "tuya_device_a", "name": "AQS", "switch_code": "switch_1"},
            {"device_id": "tuya_device_b", "name": "Soalho", "switch_code": "switch_1"},
        ]},
    })
    assert saved.status_code == 200
    monkeypatch.setattr(gateway.hardware_integrations, "read_deye", lambda config: {
        "connection_state": "mapped_registers_response", "metrics": [], "host": config["host"],
    })
    monkeypatch.setattr(gateway.hardware_integrations, "read_antminer", lambda host, port: {
        "connection_state": "api_responded", "host": host, "port": port,
        "data": {
            "summary": {"SUMMARY": [{"GHS 5s": 120000, "GHS av": 118000}]},
            "tunerstatus": {"TUNERSTATUS": [{"ApproximateMinerPowerConsumption": 2300, "PowerLimit": 2500}]},
        }, "control_commands_sent": False,
    })
    seen_tuya_configs = []
    monkeypatch.setattr(gateway.hardware_integrations, "read_tuya", lambda config: (
        seen_tuya_configs.append([device["device_id"] for device in config["devices"]]) or [
            {"device_id": device["device_id"], "name": device["name"], "connection_state": "api_responded"}
            for device in config["devices"]
        ]
    ))
    deye = client.post("/api/v1/integrations/hardware/deye/read", headers=headers, json={})
    assert deye.status_code == 200 and deye.json()["provider"] == "deye"
    miner = client.post("/api/v1/integrations/hardware/antminer/read", headers=headers, json={})
    assert miner.status_code == 200 and miner.json()["antminer"]["connection_state"] == "api_responded"
    miner_equipment = client.get("/api/v1/energy/equipment?category=mineradoras", headers=headers).json()["equipment"]
    miner_readings = {reading["field"]: reading["value"] for reading in miner_equipment[0]["readings"]}
    assert miner_readings["miner_hashrate_5s_ghs"] == 120000
    assert miner_readings["miner_power_w"] == 2300
    assert miner_readings["miner_power_limit_w"] == 2500

    # The normal miner card must also receive the authenticated Braiins tuner
    # readings, even when the CGMiner endpoint does not report live values.
    monkeypatch.setattr(gateway.hardware_integrations, "antminer_management", lambda config, operation, **kwargs: {
        # This is the state value actually returned by integrations.antminer_management.
        "operation": operation, "state": "read", "command_sent": False,
        "data": {"mode_state": {"powertargetmodestate": {
            "current_target": {"watt": 1000},
            "profile": {"target": {"watt": 1800},
                        "measured_hashrate": {"gigahash_per_second": 42000},
                        "estimated_power_consumption": {"watt": 924}},
        }}},
    })
    tuner = client.post("/api/v1/integrations/antminer/management", headers=headers, json={"operation": "tuner"})
    assert tuner.status_code == 200 and tuner.json()["energy_readings_persisted"] == 4
    miner_equipment = client.get("/api/v1/energy/equipment?category=mineradoras", headers=headers).json()["equipment"]
    miner_readings = {reading["field"]: reading["value"] for reading in miner_equipment[0]["readings"]}
    assert miner_readings["miner_hashrate_avg_ghs"] == 42000
    assert miner_readings["miner_power_w"] == 924
    assert miner_readings["miner_power_limit_w"] == 1000
    assert miner_readings["miner_power_profile_w"] == 1800

    tuya = client.post("/api/v1/integrations/hardware/tuya/read", headers=headers, json={"device_id": "tuya_device_b"})
    assert tuya.status_code == 200 and len(tuya.json()["tuya"]) == 1
    assert seen_tuya_configs == [["tuya_device_b"]]
    assert client.post("/api/v1/integrations/hardware/tuya/read", headers=headers,
                       json={"device_id": "not_configured"}).status_code == 404
    assert client.post("/api/v1/integrations/hardware/unknown/read", headers=headers, json={}).status_code == 404
    assert client.post("/api/v1/integrations/hardware/deye/read", headers=headers,
                       json={"device_id": "unexpected"}).status_code == 422


def test_owner_can_map_a_dps_from_a_fresh_lan_read_even_when_product_schema_omits_it(client, monkeypatch):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    config = {"tuya": {"devices": [{"device_id": "breaker-1", "name": "Termoacumulador",
              "product_id": "breaker-product", "product": "dlq_breaker_model", "category": "dlq",
              "device_kind": "breaker", "functions": [],
              "status_spec": [], "current_status": []}], "product_schemas": {}}}
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: config)
    monkeypatch.setattr(gateway.hardware_integrations, "save_config", lambda value: value)
    monkeypatch.setattr(gateway.energy_engine, "read_tuya_telemetry", lambda conn, *, max_age_seconds: {
        "breaker-1": {"fresh": True, "connection_state": "local_responded",
                      "status": [{"code": "dps_17", "dps_id": 17, "value": 2301},
                                 {"code": "dps_19", "dps_id": 19, "value": 1465}]}
    })

    mapped = client.post("/api/v1/integrations/tuya/product-dps-description", headers=headers, json={
        "device_id": "breaker-1", "dps_id": 17, "description": "Tensão medida",
        "semantic_code": "voltage", "unit": "V", "scale": 10,
    })
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["product_id"] == "breaker-product"
    assert mapped.json()["dps_id"] == 17
    identity_key = gateway.hardware_integrations.tuya_product_identity_key(config["tuya"]["devices"][0])
    assert config["tuya"]["product_dps_maps"][identity_key]["custom_dps_overrides"]["17"]["semantic_code"] == "voltage"

    power = client.post("/api/v1/integrations/tuya/product-dps-description", headers=headers, json={
        "device_id": "breaker-1", "dps_id": 19, "description": "Potência instantânea",
        "semantic_code": "custom_label", "unit": "W", "scale": 10,
    })
    assert power.status_code == 200, power.text
    assert power.json()["semantic_code"] == "power"
    assert config["tuya"]["product_dps_maps"][identity_key]["custom_dps_overrides"]["19"]["semantic_code"] == "power"

    unknown = client.post("/api/v1/integrations/tuya/product-dps-description", headers=headers, json={
        "device_id": "breaker-1", "dps_id": 18, "description": "Corrente",
        "semantic_code": "current", "unit": "A", "scale": 1000,
    })
    assert unknown.status_code == 422
    assert unknown.json()["detail"] == "tuya_dps_not_in_product_schema"


def test_owner_dps19_power_edit_survives_reload_and_exact_handler_enrichment(client, monkeypatch, tmp_path):
    from solarminer_gateway import tuya_device_handler_catalog
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    product_id = "ma3oq4onxxwg91ky"
    handler = tuya_device_handler_catalog.profiles_by_product_id()[product_id]
    product = tuya_device_handler_catalog.product_schema(handler)
    product["dps_profile"]["dps"] = [row for row in product["dps_profile"]["dps"]
                                       if row["dps_id"] != 19]
    product["dps_profile"]["dps"].append({"dps_id": 19, "semantic_code": "custom_label",
        "display_name": "DPS 19", "data_type": "integer", "confidence": "EXACT_PRODUCT_HANDLER",
        "source": handler["source_file"]})
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path)
    gateway.hardware_integrations.save_config({"tuya": {"devices": [{"device_id": "breaker-19",
        "name": "Termoacumulador", "product_id": product_id, "product": "dlq_breaker_model",
        "category": "dlq", "device_kind": "breaker",
        "functions": [], "status_spec": [], "current_status": []}],
        "product_schemas": {product_id: product}}})
    monkeypatch.setattr(gateway.energy_engine, "read_tuya_telemetry", lambda conn, *, max_age_seconds: {
        "breaker-19": {"fresh": True, "connection_state": "local_responded",
                       "status": [{"code": "dps_19", "dps_id": 19, "value": 1465}]}
    })
    mapped = client.post("/api/v1/integrations/tuya/product-dps-description", headers=headers, json={
        "device_id": "breaker-19", "dps_id": 19, "description": "Potência instantânea",
        "semantic_code": "custom_label", "unit": "W", "scale": 10,
    })
    assert mapped.status_code == 200, mapped.text

    loaded = gateway.hardware_integrations.load_config()
    saved = loaded["tuya"]["product_dps_maps"][gateway.hardware_integrations.tuya_product_identity_key(
        loaded["tuya"]["devices"][0])]
    assert saved["custom_dps_overrides"]["19"]["semantic_code"] == "power"
    public = gateway.hardware_integrations.public_config(loaded)["tuya"]
    row = next(item for item in public["devices"][0]["product_profile"]["dps"]
               if item["dps_id"] == 19)
    assert row["display_name"] == "Potência instantânea"
    assert row["semantic_code"] == "power"
    assert row["unit"] == "W" and row["scale"] == 10
    knowledge = next(item for item in public["devices"][0]["dps_knowledge"]["dps"]
                     if item["dps_id"] == 19)
    assert knowledge["display_name"] == "Potência instantânea"
    assert knowledge["semantic_code"] == "power"
    assert knowledge["confidence"] == "OWNER_CUSTOM"
    hardware = client.get("/api/v1/integrations/hardware", headers=headers)
    assert hardware.status_code == 200
    normalized = hardware.json()["tuya"]["product_catalog"][product_id]["dps_profile"]["normalized_characteristics"]
    assert {item["code"] for item in normalized} >= {"power", "energy_import", "energy_export", "trip_reason"}


def test_tuya_cloud_inventory_sync_stores_local_key_only_on_gateway(client, monkeypatch, tmp_path):
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path / "gateway-data")
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    local_key = "private-tuya-local-key-value"
    monkeypatch.setattr(gateway.hardware_integrations, "synchronize_tuya_devices", lambda config, **kwargs: {
        "devices": [{"device_id": "tuya_cloud_1", "name": "AQS", "category": "cz",
                     "product_id": "product-1", "product_name": "Smart Plug", "online": False,
                     "ip": "192.168.8.40", "cloud_source": "TUYA_PROJECT", "local_key": local_key,
                     "functions": [{"code": "switch_1", "type": "Boolean"}],
                     "status_spec": [{"code": "cur_power", "type": "Integer"}],
                     "current_status": [], "last_synced_at": 123}],
        "device_count": 1, "local_keys_available": 1, "schema_failures": 0, "pages": 1,
    })
    saved = client.put("/api/v1/integrations/hardware", headers=headers, json={
        "tuya": {"region": "eu_central", "client_id": "tuya-client-id",
                 "client_secret": "tuya-secret-123", "uid": "tuya-user-123", "devices": []},
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["tuya"]["uid"] == "tuya-user-123"
    synced = client.post("/api/v1/integrations/tuya/sync", headers=headers, json={})
    assert synced.status_code == 200, synced.text
    assert synced.json()["device_count"] == 1
    assert synced.json()["local_keys_available"] == 1
    assert synced.json()["inventory"]["devices"][0]["device_id"] == "tuya_cloud_1"
    assert synced.json()["inventory"]["devices"][0]["local_key_available"] is True
    assert local_key not in synced.text
    stored = gateway.hardware_integrations.load_config()["tuya"]["devices"][0]
    assert stored["local_key"] == local_key
    assert stored["functions"][0]["code"] == "switch_1"
    assert stored["status_spec"][0]["code"] == "cur_power"


def test_tuya_sync_requires_uid_and_owner(client, monkeypatch, tmp_path):
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path / "gateway-data")
    owner_headers = {"Authorization": f"Bearer {owner_session(client)}"}
    client.put("/api/v1/integrations/hardware", headers=owner_headers, json={
        "tuya": {"region": "eu_central", "client_id": "tuya-client-id",
                 "client_secret": "tuya-secret-123", "devices": []},
    })
    missing_uid = client.post("/api/v1/integrations/tuya/sync", headers=owner_headers, json={})
    assert missing_uid.status_code == 409
    assert missing_uid.json()["detail"] == "tuya_uid_required"
    # Existing hardware route coverage asserts role separation; this route has
    # the same explicit revalidation, so exercise a revoked/non-owner session.
    with gateway.db() as conn:
        row = conn.execute("SELECT account_id FROM users WHERE username='owner-v067'").fetchone()
        conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'admin','active',?)",
                     ("tuya-admin", row[0], "tuya-admin", "unused", int(time.time())))
        _, public = keypair()
        der = serialization.load_pem_public_key(public.encode()).public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        conn.execute("INSERT INTO devices(id,public_key_pem,public_key_sha256,mac_declared,mac_status,status,created_at) VALUES(?,?,?,?,'declared','active',?)",
                     ("tuya-admin-device", public, hashlib.sha256(der).hexdigest(), "AA:BB:CC:DD:EE:78", gateway.utcnow()))
        conn.execute("INSERT INTO user_devices(user_id,device_id,status,created_at) VALUES(?,?,'active',?)",
                     ("tuya-admin", "tuya-admin-device", gateway.utcnow()))
        raw = "tuya-admin-session-token"
        conn.execute("INSERT INTO sessions(token_sha256,user_id,device_id,created_at,expires_at,credential_version) VALUES(?,?,?,?,?,1)",
                     (gateway.token_hash(raw), "tuya-admin", "tuya-admin-device", int(time.time()), int(time.time()) + 3600))
    denied = client.post("/api/v1/integrations/tuya/sync", headers={"Authorization": f"Bearer {raw}"}, json={})
    assert denied.status_code == 403


def test_tuya_sync_imports_local_key_and_device_capabilities(monkeypatch):
    config = {"region": "eu_central", "client_id": "client", "client_secret": "secret-value",
              "uid": "user-123", "devices": []}
    calls = []
    def request(_config, path, token=None, **kwargs):
        calls.append(path)
        if path == "/v1.0/token?grant_type=1":
            return {"result": {"access_token": "temporary-token"}}
        if path.startswith("/v2.0/cloud/thing/device?"):
            return {"result": [{"id": "tuya_1", "name": "Plug", "category": "cz",
                                "productId": "pid", "productName": "Plug Pro", "isOnline": False}]}
        if path == "/v2.0/cloud/thing/tuya_1":
            return {"result": {"id": "tuya_1", "local_key": "private-local-key-123",
                                "ip": "192.168.8.41", "is_online": False}}
        if path == "/v1.0/iot-03/devices/tuya_1/specification":
            return {"result": {"category": "cz", "functions": [{"code": "switch_1", "type": "Boolean", "values": "{}"}],
                                "status": [{"code": "cur_power", "type": "Integer", "values": "{}"}]}}
        if path == "/v1.0/iot-03/categories/cz/functions":
            return {"result": {"category": "cz", "functions": [{"code": "switch", "type": "Boolean", "name": "Switch"}]}}
        if path == "/v1.0/iot-03/categories/cz/status":
            return {"result": {"category": "cz", "status_list": [{"code": "cur_power", "type": "Integer", "name": "Power"}]}}
        raise AssertionError(path)
    original = gateway.hardware_integrations._tuya_request
    monkeypatch.setattr(gateway.hardware_integrations, "_tuya_request", request)
    result = gateway.hardware_integrations.synchronize_tuya_devices(config)
    monkeypatch.setattr(gateway.hardware_integrations, "_tuya_request", original)
    assert result["device_count"] == result["local_keys_available"] == 1
    device = result["devices"][0]
    assert device["online"] is False
    assert device["local_key"] == "private-local-key-123"
    assert device["functions"][0]["code"] == "switch_1"
    assert device["status_spec"][0]["code"] == "cur_power"
    assert result["product_schemas"]["pid"]["functions"][0]["code"] == "switch_1"
    assert device["schema_source"] == "TUYA_DEVICE_SPEC"
    # Sync imports capability metadata only; operational readings are obtained
    # from the device locally and must not be fetched through the Tuya cloud.
    assert "current_status" not in device
    assert "/v1.0/iot-03/devices/tuya_1/status" not in calls
    assert device["category_schema_source"] == "TUYA_CATEGORY_REFERENCE"
    assert "category_functions" not in device
    assert "category_status_spec" not in device
    assert result["category_schemas"]["cz"]["status_spec"][0]["code"] == "cur_power"
    assert calls[0] == "/v1.0/token?grant_type=1"


def test_tuya_sync_reuses_only_matching_cached_product_schema(monkeypatch):
    config = {"region": "eu_central", "client_id": "client", "client_secret": "secret-value",
              "uid": "user-123", "devices": [], "product_schemas": {
                  "pid-exact": {"category": "cz", "product_name": "Plug Pro",
                                "functions": [{"code": "switch_1", "name": "Relay A", "type": "Boolean", "dp_id": 6}],
                                "status_spec": [{"code": "cur_power", "name": "Power", "type": "Integer"}],
                                "cached_at": 123456},
              }}

    def request(_config, path, token=None, **kwargs):
        if path == "/v1.0/token?grant_type=1":
            return {"result": {"access_token": "temporary-token"}}
        if path.startswith("/v2.0/cloud/thing/device?"):
            return {"result": [{"id": "tuya_new_1", "name": "Plug copy", "category": "cz",
                                "productId": "pid-exact", "productName": "Plug Pro", "isOnline": True}]}
        if path == "/v2.0/cloud/thing/tuya_new_1":
            return {"result": {"id": "tuya_new_1", "local_key": "private-local-key-123",
                                "ip": "192.168.8.42", "is_online": True}}
        if path == "/v1.0/iot-03/devices/tuya_new_1/specification":
            raise RuntimeError("specification_temporarily_unavailable")
        if path == "/v1.0/iot-03/categories/cz/functions":
            return {"result": {"functions": [{"code": "switch_1", "type": "Boolean"}]}}
        if path == "/v1.0/iot-03/categories/cz/status":
            return {"result": {"status_list": [{"code": "cur_power", "type": "Integer"}]}}
        raise AssertionError(path)

    monkeypatch.setattr(gateway.hardware_integrations, "_tuya_request", request)
    result = gateway.hardware_integrations.synchronize_tuya_devices(config)
    device = result["devices"][0]
    assert device["product_id"] == "pid-exact"
    assert device["schema_source"] == "TUYA_PRODUCT_SCHEMA_CACHE"
    assert device["functions"][0]["dp_id"] == 6
    assert device["status_spec"][0]["code"] == "cur_power"
    assert result["product_schemas"]["pid-exact"]["category"] == "cz"


def test_tuya_lan_diagnostics_excludes_setup_failures_from_response_latency(client, monkeypatch):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: {"tuya": {"devices": [
        {"device_id": "moes-no-lan-target", "name": "MOES com IP cloud externo",
         "local_key": "local-key-valid", "ip": "8.8.8.8"},
    ]}})
    result = client.post("/api/v1/integrations/tuya/lan-diagnostics", headers=headers,
                         json={"rounds": 3})
    assert result.status_code == 200, result.text
    report = result.json()
    assert report["lan_testable_count"] == 0
    device = report["devices"][0]
    assert device["local_ip"] == ""
    assert device["local_key_configured"] is True
    assert device["success_count"] == 0
    assert device["average_latency_ms"] is None
    assert device["worst_latency_ms"] is None
    assert device["reason"] == "private_lan_target_required"


def test_tuya_lan_diagnostics_can_probe_one_device_for_three_read_only_rounds(client, monkeypatch, tmp_path):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path / "gateway-data")
    config = {"tuya": {"devices": [
        {"device_id": "target-device", "name": "Target", "local_ip": "192.168.1.30",
         "local_mac": "AA:BB:CC:DD:EE:30", "local_key": "key-target", "switch_code": "switch_1",
         "status_spec": [{"code": "switch_1", "name": "Switch"}, {"code": "cur_power", "name": "Power"}]},
        {"device_id": "other-device", "name": "Other", "local_ip": "192.168.1.31",
         "local_key": "key-other"},
    ]}}
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: config)
    calls = []
    def read_tuya(config):
        devices = config["devices"]
        calls.append([item["device_id"] for item in devices])
        return [{"device_id": item["device_id"], "connection_state": "local_responded",
                 "latency_ms": 12.0, "local_protocol": "3.4",
                 "status": [{"code": "switch_1", "value": True}]}
                for item in devices]
    monkeypatch.setattr(gateway.hardware_integrations, "read_tuya", read_tuya)
    response = client.post("/api/v1/integrations/tuya/lan-diagnostics", headers=headers,
                           json={"rounds": 3, "device_id": "target-device"})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["configured_count"] == 1
    assert calls == [["target-device"]] * 3
    device = report["devices"][0]
    assert device["success_count"] == 3
    assert device["rounds"] == 3
    assert device["average_latency_ms"] == 12.0
    assert device["connection_state"] == "local_responded"
    assert device["local_protocol"] == "3.4"
    assert device["status"] == [{"code": "switch_1", "value": True}]
    assert report["control_commands_sent"] is False
    assert report["confirmed_device_count"] == 1
    assert config["tuya"]["devices"][0]["local_verified"] is True
    inventory = client.get("/api/v1/device-inventory", headers=headers).json()["devices"]
    confirmed = next(item for item in inventory if item["source_device_id"] == "target-device")
    assert confirmed["confirmation_status"] == "confirmed"


def test_tuya_lan_reachability_checks_only_selected_private_ip_without_reading_status_or_cloud(client, monkeypatch):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: {"tuya": {"devices": [
        {"device_id": "target-device", "name": "Target", "local_ip": "192.168.1.30",
         "local_mac": "AA:BB:CC:DD:EE:30"},
        {"device_id": "other-device", "name": "Other", "local_ip": "192.168.1.31"},
    ]}})
    probes = []
    monkeypatch.setattr(gateway.hardware_integrations, "probe_tuya_lan_reachability",
                        lambda host: probes.append(host) or {"state": "lan_reachable", "host": host,
                                                               "port": 6668, "latency_ms": 4.2})
    monkeypatch.setattr(gateway.hardware_integrations, "read_tuya",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("DPS status must not be read")))
    response = client.post("/api/v1/integrations/tuya/lan-reachability", headers=headers,
                           json={"device_id": "target-device"})
    assert response.status_code == 200, response.text
    assert probes == ["192.168.1.30"]
    assert response.json() == {"device_id": "target-device", "connection_state": "lan_reachable",
                               "reason": None, "local_ip": "192.168.1.30", "local_mac": "AA:BB:CC:DD:EE:30",
                               "port": 6668, "latency_ms": 4.2, "status_read": False,
                               "dps_read": False, "cloud_requested": False}


def test_tuya_lan_reachability_requires_private_local_ip(client, monkeypatch):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: {"tuya": {"devices": [
        {"device_id": "mac-only", "name": "MAC only", "local_mac": "AA:BB:CC:DD:EE:30"},
    ]}})
    response = client.post("/api/v1/integrations/tuya/lan-reachability", headers=headers,
                           json={"device_id": "mac-only"})
    assert response.status_code == 200, response.text
    assert response.json()["reason"] == "private_lan_target_required"
    assert response.json()["status_read"] is False
    assert response.json()["cloud_requested"] is False


def test_tinytuya_lan_scanner_is_exported_by_bundled_package():
    assert callable(gateway.hardware_integrations.tinytuya.deviceScan)


def test_local_network_scan_matches_known_tuya_by_mac_and_updates_unique_ip_automatically(client, monkeypatch, tmp_path):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path)
    gateway.hardware_integrations.save_config({"tuya": {"devices": [
        {"device_id": "known-switch", "name": "Luz do jardim", "local_mac": "AA:BB:CC:DD:EE:21",
         "local_ip": "192.168.10.20"},
        {"device_id": "wrong-mac", "name": "Outro device", "local_mac": "AA:BB:CC:DD:EE:22",
         "local_ip": "192.168.10.22"},
    ]}})
    report = {"networks": [{"interface": "eth0", "address": "192.168.10.2", "network": "192.168.10.0/24"}],
              "scanned_count": 254, "responsive_count": 1, "hosts": [
                  {"ip": "192.168.10.21", "mac": "AA:BB:CC:DD:EE:21", "interface": "eth0",
                   "network": "192.168.10.0/24", "is_router": False, "open_ports": [80],
                   "discovery_methods": ["tcp"]},
              ], "skipped_networks": [], "address_limit": 4096,
              "method": "bounded_tcp_probe_and_kernel_neighbor_table", "router_ips": []}
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: report)

    scanned = client.post("/api/v1/network/scan", headers=headers, json={})
    assert scanned.status_code == 200, scanned.text
    match = scanned.json()["hosts"][0]["matched_devices"][0]
    assert {key: match[key] for key in ("device_id", "name", "provider", "device_type", "local_mac")} == {
        "device_id": "known-switch", "name": "Luz do jardim", "provider": "tuya",
        "device_type": "tuya", "local_mac": "AA:BB:CC:DD:EE:21"}
    assert match["inventory_key"] == "mac:AA:BB:CC:DD:EE:21"
    assert scanned.json()["configured_ip_update_count"] == 1
    saved = gateway.hardware_integrations.load_config()["tuya"]["devices"]
    assert saved[0]["local_ip"] == "192.168.10.21"

    applied = client.post("/api/v1/network/scan/apply", headers=headers, json={})
    assert applied.status_code == 200, applied.text
    assert applied.json()["updated_count"] == 0
    saved = gateway.hardware_integrations.load_config()["tuya"]["devices"]
    assert saved[0]["local_ip"] == "192.168.10.21"
    assert saved[1]["local_ip"] == "192.168.10.22"


def test_network_device_detail_save_uses_mac_and_persists_name(client, monkeypatch):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    report = {"hosts": [{"ip": "192.168.10.44", "mac": "AA:BB:CC:DD:EE:44",
                         "manufacturer": "Example", "model": "Bridge", "discovery_methods": ["arp_sweep"]}]}
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: report)
    monkeypatch.setattr(gateway.hardware_integrations, "probe_tuya_lan_reachability",
                        lambda ip: {"state": "lan_reachable", "host": ip, "port": 6668, "latency_ms": 3.0})

    response = client.post("/api/v1/network/devices/save", headers=headers,
                           json={"mac": "aa:bb:cc:dd:ee:44", "name": "Bridge da cave", "device_type": "router",
                                 "manufacturer": "Tuya", "product_id": "two-gang-dimmer"})

    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["device"]["mac"] == "AA:BB:CC:DD:EE:44"
    assert saved["device"]["name"] == "Bridge da cave"
    assert saved["device"]["device_type"] == "router"
    assert saved["device"]["last_ip"] == "192.168.10.44"
    assert saved["device"]["device_key"] == "mac:AA:BB:CC:DD:EE:44"
    assert saved["device"]["confirmation_status"] == "confirmed"
    assert saved["tuya_lan_probe"]["state"] == "lan_reachable"
    assert saved["ambiguous_ip"] is False
    listed = client.get("/api/v1/device-inventory", headers=headers)
    assert listed.status_code == 200, listed.text
    pending = [item for item in listed.json()["devices"] if item["mac"] == "AA:BB:CC:DD:EE:44"]
    assert len(pending) == 1
    assert pending[0]["name"] == "Bridge da cave"


def test_network_device_detail_save_never_updates_ambiguous_ip(client, monkeypatch):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    report = {"hosts": [
        {"ip": "192.168.10.80", "mac": "AA:BB:CC:DD:EE:95"},
        {"ip": "192.168.10.200", "mac": "AA:BB:CC:DD:EE:95"},
    ]}
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: report)

    response = client.post("/api/v1/network/devices/save", headers=headers,
                           json={"mac": "AA:BB:CC:DD:EE:95", "name": "Inversor", "device_type": "inverter"})

    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["device"]["name"] == "Inversor"
    assert saved["device"]["last_ip"] == ""
    assert saved["ambiguous_ip"] is True


def test_network_device_detail_save_updates_matching_tuya_name_and_unique_local_ip(client, monkeypatch, tmp_path):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path)
    gateway.hardware_integrations.save_config({"tuya": {"devices": [
        {"device_id": "known-breaker", "name": "Old name", "local_mac": "AA:BB:CC:DD:EE:21",
         "local_ip": "192.168.10.20"},
    ]}})
    report = {"hosts": [{"ip": "192.168.10.21", "mac": "AA:BB:CC:DD:EE:21"}]}
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: report)

    response = client.post("/api/v1/network/devices/save", headers=headers,
                           json={"mac": "AA:BB:CC:DD:EE:21", "name": "Disjuntor oficina", "device_type": "tuya"})

    assert response.status_code == 200, response.text
    saved = gateway.hardware_integrations.load_config()["tuya"]["devices"][0]
    assert saved["name"] == "Disjuntor oficina"
    assert saved["name_source"] == "local"
    assert saved["local_ip"] == "192.168.10.21"


def test_network_device_save_syncs_and_auto_links_tuya_local_key_by_read_only_dps(client, monkeypatch, tmp_path):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path / "gateway-data")
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: {
        "hosts": [{"ip": "192.168.10.61", "mac": "AA:BB:CC:DD:EE:61", "manufacturer": "Tuya"}]})
    secret_key = "test-local-key-never-return-this"
    monkeypatch.setattr(gateway.hardware_integrations, "synchronize_tuya_devices", lambda config, **kwargs: {
        "devices": [{"device_id": "cloud-dimmer-61", "product_id": "two-gang-dimmer",
                     "product_name": "Two Gang Dimmer", "local_key": secret_key,
                     "functions": [{"code": "switch_1", "type": "Boolean"}]}],
        "product_schemas": {}, "category_schemas": {}})
    monkeypatch.setattr(gateway.hardware_integrations, "_tuya_local_status", lambda candidate: {
        "connection_state": "local_responded", "local_protocol": "3.3",
        "status": [{"code": "switch_1", "dps_id": 1, "value": False}], "latency_ms": 4.0})
    monkeypatch.setattr(gateway.hardware_integrations, "probe_tuya_lan_reachability", lambda ip: {
        "state": "lan_reachable", "host": ip, "port": 6668, "latency_ms": 2.0})
    configured = client.put("/api/v1/integrations/hardware", headers=headers, json={"tuya": {
        "region": "eu_central", "client_id": "client-id", "client_secret": "client-secret",
        "uid": "account-id", "devices": []}})
    assert configured.status_code == 200, configured.text

    response = client.post("/api/v1/network/devices/save", headers=headers, json={
        "mac": "AA:BB:CC:DD:EE:61", "ip": "192.168.10.61", "name": "Cozinha Dimmer",
        "device_type": "dimmer", "manufacturer": "Tuya", "model": "Two Gang Dimmer",
        "product_id": "two-gang-dimmer"})

    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["tuya_association"] == {"state": "verified", "device_id": "cloud-dimmer-61"}
    assert saved["tuya_reading"]["status"][0]["value"] is False
    assert secret_key not in response.text
    persisted = gateway.hardware_integrations.load_config()["tuya"]["devices"][0]
    assert persisted["local_mac"] == "AA:BB:CC:DD:EE:61"
    assert persisted["local_ip"] == "192.168.10.61"
    assert persisted["local_control_state"] == "ready"
    assert persisted["local_verified"] is True
    assert persisted["name"] == "Cozinha Dimmer"


def test_network_device_save_refuses_ambiguous_tuya_key_match(client, monkeypatch, tmp_path):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path / "gateway-data")
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: {
        "hosts": [{"ip": "192.168.10.62", "mac": "AA:BB:CC:DD:EE:62", "manufacturer": "Tuya"}]})
    monkeypatch.setattr(gateway.hardware_integrations, "synchronize_tuya_devices", lambda config, **kwargs: {
        "devices": [{"device_id": f"cloud-dimmer-{index}", "product_id": "two-gang-dimmer",
                     "local_key": f"test-key-{index}-long"} for index in (1, 2)],
        "product_schemas": {}, "category_schemas": {}})
    monkeypatch.setattr(gateway.hardware_integrations, "_tuya_local_status", lambda candidate: {
        "connection_state": "local_responded", "status": [{"code": "switch_1", "value": False}]})
    monkeypatch.setattr(gateway.hardware_integrations, "probe_tuya_lan_reachability", lambda ip: {
        "state": "lan_reachable", "host": ip, "port": 6668})
    client.put("/api/v1/integrations/hardware", headers=headers, json={"tuya": {
        "region": "eu_central", "client_id": "client-id", "client_secret": "client-secret",
        "uid": "account-id", "devices": []}})

    response = client.post("/api/v1/network/devices/save", headers=headers, json={
        "mac": "AA:BB:CC:DD:EE:62", "name": "Dimmer", "device_type": "dimmer",
        "manufacturer": "Tuya", "model": "Two Gang Dimmer", "product_id": "two-gang-dimmer"})

    assert response.status_code == 200, response.text
    assert response.json()["tuya_association"]["state"] == "ambiguous_key_match"
    assert response.json()["device"]["confirmation_status"] == "confirmed"
    assert len(gateway.hardware_integrations.load_config()["tuya"]["devices"]) == 2


def test_local_network_apply_skips_mac_seen_at_multiple_ips(client, monkeypatch, tmp_path):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path)
    gateway.hardware_integrations.save_config({"tuya": {"devices": [
        {"device_id": "known-switch", "name": "Disjuntor", "local_mac": "AA:BB:CC:DD:EE:21",
         "local_ip": "192.168.10.20"},
    ]}})
    report = {"scanned_count": 254, "responsive_count": 1, "networks": [], "skipped_networks": [], "hosts": [
        {"ip": "192.168.10.21", "mac": "AA:BB:CC:DD:EE:21"},
        {"ip": "192.168.10.31", "mac": "AA:BB:CC:DD:EE:21"},
    ]}
    monkeypatch.setattr(gateway.network_scanner, "scan_attached_networks", lambda: report)

    scanned = client.post("/api/v1/network/scan", headers=headers, json={})
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["configured_ip_update_count"] == 0
    assert gateway.hardware_integrations.load_config()["tuya"]["devices"][0]["local_ip"] == "192.168.10.20"

    applied = client.post("/api/v1/network/scan/apply", headers=headers, json={})

    assert applied.status_code == 200, applied.text
    assert applied.json()["updated_count"] == 0
    assert applied.json()["ambiguous_mac_count"] == 1
    saved = gateway.hardware_integrations.load_config()["tuya"]["devices"]
    assert saved[0]["local_ip"] == "192.168.10.20"


def test_public_tuya_projection_never_labels_cloud_ip_as_local():
    projected = gateway.hardware_integrations.public_config({"tuya": {"devices": [
        {"device_id": "cloud-ip-only", "name": "Device", "ip": "87.10.20.30"},
    ]}})
    device = projected["tuya"]["devices"][0]
    assert device["local_ip"] == ""
    assert device["ip"] == ""


def test_hardware_status_keeps_recent_valid_tuya_sample_after_failed_attempt(client, monkeypatch):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "public_config", lambda: {"tuya": {"devices": [
        {"device_id": "dimmer", "name": "Dimmer", "local_ip": "192.168.1.20",
         "current_status": [], "local_control_state": "unavailable"}]}})
    monkeypatch.setattr(gateway.energy_engine, "read_tuya_telemetry", lambda conn, max_age_seconds: {
        "dimmer": {"verified": True, "fresh": True, "connection_state": "failed",
                   "observed_at": "2026-11-05T12:00:00+00:00", "last_attempt_at": "2026-11-05T12:00:01+00:00",
                   "reason": "temporary_lan_timeout", "status": [{"code": "cur_power", "dps_id": 19, "value": 425}]}})

    response = client.get("/api/v1/integrations/hardware", headers=headers)

    assert response.status_code == 200, response.text
    device = response.json()["tuya"]["devices"][0]
    assert device["current_connection_state"] == "local_responded"
    assert device["local_control_state"] == "ready"
    assert device["current_status"][0]["value"] == 425
    assert device["last_read_attempt_state"] == "failed"
    assert device["last_read_error"] == "temporary_lan_timeout"


def test_tuya_lan_discovery_matches_device_ids_or_mac_and_saves_only_private_addresses(client, monkeypatch, tmp_path):
    token = owner_session(client)
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path)
    gateway.hardware_integrations.save_config({"tuya": {"devices": [
        {"device_id": "moes-local", "name": "Luzes MOES", "local_key": "private-local-key-123"},
        {"device_id": "renamed-device", "name": "Gateway Cozinha", "local_key": "private-local-key-456",
         "local_mac": "AA:BB:CC:DD:EE:44"},
        {"device_id": "not-on-lan", "name": "Fora da LAN", "local_key": "other-local-key-123"},
    ]}})
    class Scanner:
        @staticmethod
        def deviceScan(**kwargs):
            assert kwargs == {"verbose": False, "maxretry": 10, "poll": False, "byID": True}
            return {
                "moes-local": {"gwId": "moes-local", "ip": "192.168.1.44", "version": "3.4"},
                "renamed-device": {"gwId": "renamed-device", "ip": "192.168.1.45", "version": "3.3",
                                   "mac": "AA:BB:CC:DD:EE:44"},
                "unknown-id": {"gwId": "unknown-id", "ip": "192.168.1.46", "version": "3.3",
                               "mac": "AA:BB:CC:DD:EE:55"},
                "foreign-device": {"gwId": "foreign-device", "ip": "8.8.8.8", "version": "3.3"},
            }
    monkeypatch.setattr(gateway.hardware_integrations, "tinytuya", Scanner)
    response = client.post("/api/v1/integrations/tuya/lan-discovery", headers=headers, json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["scanned_count"] == 3
    assert result["matched_count"] == 2
    assert result["cloud_used"] is False and result["commands_sent"] is False
    assert result["devices"] == [
        {"device_id": "moes-local", "name": "Luzes MOES", "ip": "192.168.1.44",
         "mac": "", "matched_by": "device_id", "local_key_available": True},
        {"device_id": "renamed-device", "name": "Gateway Cozinha", "ip": "192.168.1.45",
         "mac": "AA:BB:CC:DD:EE:44", "matched_by": "device_id", "local_key_available": True},
    ]
    saved = gateway.hardware_integrations.load_config()["tuya"]["devices"]
    assert saved[0]["local_ip"] == "192.168.1.44"
    assert saved[0]["local_protocol"] == "3.4"
    assert saved[1]["local_ip"] == "192.168.1.45"
    assert saved[1]["local_mac"] == "AA:BB:CC:DD:EE:44"
    assert "local_ip" not in saved[2]


def test_tuya_lan_discovery_passes_synced_ids_and_keys_to_bundled_scanner(client, monkeypatch, tmp_path):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path)
    gateway.hardware_integrations.save_config({"tuya": {"devices": [
        {"device_id": "cloud-device-1", "name": "Relay", "local_key": "private-local-key-123",
         "local_mac": "AA:BB:CC:DD:EE:10"},
    ]}})
    calls = []

    class ScannerModule:
        @staticmethod
        def devices(**kwargs):
            calls.append(kwargs)
            return {"cloud-device-1": {"gwId": "cloud-device-1", "ip": "192.168.1.10",
                                        "version": "3.3", "mac": "AA:BB:CC:DD:EE:10"}}

    class Driver:
        scanner = ScannerModule

        @staticmethod
        def deviceScan(**kwargs):
            raise AssertionError("the key-aware scanner should be used")

    monkeypatch.setattr(gateway.hardware_integrations, "tinytuya", Driver)
    response = client.post("/api/v1/integrations/tuya/lan-discovery", headers=headers, json={})
    assert response.status_code == 200, response.text
    assert response.json()["matched_count"] == 1
    assert calls == [{
        "verbose": False, "scantime": 10, "poll": False, "byID": True,
        "tuyadevices": [{"id": "cloud-device-1", "key": "private-local-key-123",
                         "mac": "AA:BB:CC:DD:EE:10"}],
        "wantids": ["cloud-device-1"],
    }]


def test_tuya_lan_discovery_can_match_manual_mac_from_neighbor_cache(client, monkeypatch, tmp_path):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path)
    gateway.hardware_integrations.save_config({"tuya": {"devices": [
        {"device_id": "cloud-id-differs", "name": "Relay by MAC", "local_key": "private-local-key-789",
         "local_mac": "AA:BB:CC:DD:EE:77"},
    ]}})
    arp_file = tmp_path / "arp"
    arp_file.write_text("IP address HW type Flags HW address Mask Device\n"
                        "192.168.1.77 0x1 0x2 aa:bb:cc:dd:ee:77 * wlan0\n"
                        "8.8.8.8 0x1 0x2 aa:bb:cc:dd:ee:88 * wlan0\n", encoding="ascii")
    read_arp_entries = gateway.local_arp_entries
    monkeypatch.setattr(gateway, "local_arp_entries", lambda: read_arp_entries(arp_file))
    class Scanner:
        @staticmethod
        def deviceScan(**kwargs):
            return {"unmatched": {"gwId": "unmatched", "ip": "192.168.1.78", "version": "3.3"}}
    monkeypatch.setattr(gateway.hardware_integrations, "tinytuya", Scanner)
    response = client.post("/api/v1/integrations/tuya/lan-discovery", headers=headers, json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["matched_count"] == 1
    assert result["devices"][0]["ip"] == "192.168.1.77"
    assert result["devices"][0]["matched_by"] == "mac"


def test_tuya_lan_discovery_falls_back_to_neighbor_cache_when_broadcast_scan_fails(client, monkeypatch, tmp_path):
    headers = {"Authorization": f"Bearer {owner_session(client)}"}
    monkeypatch.setattr(gateway.hardware_integrations, "_data_dir", lambda: tmp_path)
    gateway.hardware_integrations.save_config({"tuya": {"devices": [
        {"device_id": "known-id", "name": "Termoacumulador", "local_key": "private-key-321",
         "local_mac": "AA:BB:CC:DD:EE:99"},
    ]}})
    arp_file = tmp_path / "arp"
    arp_file.write_text("IP address HW type Flags HW address Mask Device\n"
                        "192.168.1.99 0x1 0x2 aa:bb:cc:dd:ee:99 * wlan0\n", encoding="ascii")
    read_arp_entries = gateway.local_arp_entries
    monkeypatch.setattr(gateway, "local_arp_entries", lambda: read_arp_entries(arp_file))
    class BrokenScanner:
        @staticmethod
        def deviceScan(**kwargs):
            raise OSError("broadcast unavailable")
    monkeypatch.setattr(gateway.hardware_integrations, "tinytuya", BrokenScanner)
    response = client.post("/api/v1/integrations/tuya/lan-discovery", headers=headers, json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["matched_count"] == 1
    assert result["scan_error"] == "OSError"
    assert result["devices"][0]["ip"] == "192.168.1.99"


def test_tuya_level_command_is_owner_only_and_rejects_invalid_payload(client, monkeypatch):
    token = owner_session(client)
    headers = {"Authorization": f"Bearer {token}"}
    calls = []
    monkeypatch.setattr(gateway.hardware_integrations, "control_tuya_level",
                        lambda *args: calls.append(args) or {"command_accepted": True})
    invalid = client.post("/api/v1/integrations/tuya/level", headers=headers,
                          json={"device_id": "configured-device", "percent": 101})
    assert invalid.status_code == 422
    assert calls == []
    accepted = client.post("/api/v1/integrations/tuya/level", headers=headers,
                           json={"device_id": "configured-device", "percent": 50})
    assert accepted.status_code == 200
    assert len(calls) == 1 and calls[0][1:] == ("configured-device", 50)
    with gateway.db() as conn:
        account_id = conn.execute("SELECT account_id FROM users WHERE username=?", ("owner-v067",)).fetchone()[0]
        conn.execute("INSERT INTO users(id,account_id,username,password_hash,role,status,created_at) VALUES(?,?,?,?, 'owner','active',?)",
                     ("second-active-owner", account_id, "second-owner", "unused-test-hash", int(time.time())))
        conn.execute("UPDATE users SET role='viewer' WHERE username=?", ("owner-v067",))
    denied = client.post("/api/v1/integrations/tuya/level", headers=headers,
                         json={"device_id": "configured-device", "percent": 50})
    assert denied.status_code in (401, 403)
    assert len(calls) == 1


def test_tuya_setting_command_is_owner_only_and_rejects_invalid_payload(client, monkeypatch):
    token = owner_session(client)
    headers = {"Authorization": f"Bearer {token}"}
    calls = []
    monkeypatch.setattr(gateway.hardware_integrations, "control_tuya_setting",
                        lambda *args: calls.append(args) or {"command_accepted": True, "state_confirmed": True})
    invalid = client.post("/api/v1/integrations/tuya/setting", headers=headers,
                          json={"device_id": "configured-device", "code": "countdown", "value": 999999})
    assert invalid.status_code == 200  # Endpoint delegates schema/range validation to the Gateway integration.
    assert len(calls) == 1
    malformed = client.post("/api/v1/integrations/tuya/setting", headers=headers,
                            json={"device_id": "configured-device", "code": "countdown", "value": {"seconds": 20}})
    assert malformed.status_code == 422
    assert len(calls) == 1
    denied = client.post("/api/v1/integrations/tuya/setting",
                         json={"device_id": "configured-device", "code": "countdown", "value": 20})
    assert denied.status_code in (401, 403)
    assert len(calls) == 1
