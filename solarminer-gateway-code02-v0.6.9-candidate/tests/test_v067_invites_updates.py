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

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    gwpriv, gwpub = keypair()
    privpath, pubpath = tmp_path / "gw.key", tmp_path / "gw.pub"
    privpath.write_bytes(gwpriv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    privpath.chmod(0o600)
    pubpath.write_text(gwpub)
    monkeypatch.setenv("SOLARMINER_GATEWAY_IDENTITY_PRIVATE_KEY", str(privpath))
    monkeypatch.setenv("SOLARMINER_GATEWAY_IDENTITY_PUBLIC_KEY", str(pubpath))
    monkeypatch.setenv("SOLARMINER_PUBLIC_URL", "https://gateway.example.test")
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
    body=created.json(); assert len(body["qr_payload"]["fp"]) == 64
    assert body["qr_svg"].startswith("<svg") and "<path" in body["qr_svg"]
    assert body["token"] not in body["qr_svg"]
    listed=client.get("/api/v1/invites",headers=h).json()["invites"]
    assert listed[0]["state"] == "pending"
    assert "token" not in listed[0] and "token_hash" not in listed[0]
    revoked=client.post(f"/api/v1/invites/{body['invite_id']}/revoke",headers=h)
    assert revoked.status_code == 200
    assert client.post(f"/api/v1/invites/{body['invite_id']}/revoke",headers=h).status_code == 409

def test_invite_redeem_atomic_and_single_use(client):
    token=owner_session(client); h={"Authorization":f"Bearer {token}"}
    invite=client.post("/api/v1/invites",headers=h,json={"role":"operator","label":"new operator"}).json()
    priv,pub=keypair(); ts=int(time.time()); nonce="invite-redeem-nonce-0001"; username="operator-v067"
    mac="AA:BB:CC:DD:EE:44"; password="operator-password-v067-long"
    token_hash=hashlib.sha256(invite["token"].encode()).hexdigest()
    pub_der=serialization.load_pem_public_key(pub.encode()).public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    pub_hash=hashlib.sha256(pub_der).hexdigest()
    canonical="\n".join(["POST","/api/v1/invites/redeem",str(ts),nonce,token_hash,username,hashlib.sha256(password.encode()).hexdigest(),mac,pub_hash])
    body={"invite_token":invite["token"],"username":username,"password":password,"mac":mac,"client_pubkey_pem":pub,"signature":sig(priv,canonical),"timestamp":ts,"nonce":nonce}
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
    pub_hash=hashlib.sha256(pub_der).hexdigest(); token_digest=hashlib.sha256(invite["token"].encode()).hexdigest()
    def redeem(nonce):
        ts=int(time.time())
        canonical="\n".join(["POST","/api/v1/invites/redeem",str(ts),nonce,token_digest,username,hashlib.sha256(password.encode()).hexdigest(),mac,pub_hash])
        body={"invite_token":invite["token"],"username":username,"password":password,"mac":mac,"client_pubkey_pem":pub,"signature":sig(priv,canonical),"timestamp":ts,"nonce":nonce}
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
    tuya = client.post("/api/v1/integrations/hardware/tuya/read", headers=headers, json={"device_id": "tuya_device_b"})
    assert tuya.status_code == 200 and len(tuya.json()["tuya"]) == 1
    assert seen_tuya_configs == [["tuya_device_b"]]
    assert client.post("/api/v1/integrations/hardware/tuya/read", headers=headers,
                       json={"device_id": "not_configured"}).status_code == 404
    assert client.post("/api/v1/integrations/hardware/unknown/read", headers=headers, json={}).status_code == 404
    assert client.post("/api/v1/integrations/hardware/deye/read", headers=headers,
                       json={"device_id": "unexpected"}).status_code == 422


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
