"""Fail-closed signed connector lifecycle journal.

The public key is an administrator-provisioned trust anchor; no key is generated,
replaced, or trusted by this module. Systemd enforcement must be independently
verified before ACTIVE can be reached.
"""
from __future__ import annotations
import hashlib, json, os, re, sqlite3, uuid
from pathlib import Path
from datetime import datetime, timezone
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_VERIFIED_SEAL = object()

class VerifiedManifest(dict):
    """Verification result with an in-process seal; direct construction is rejected."""
    def __init__(self, data, seal=None):
        if seal is not _VERIFIED_SEAL:
            raise ValueError("verified_signed_manifest_required")
        super().__init__(data)
        self._verification_seal = seal
    @property
    def is_verified(self):
        return self._verification_seal is _VERIFIED_SEAL

STATES={"PREPARED","VENV_READY","ACTIVATED","ACTIVE","FAILED","ABANDONED"}
TRANSITIONS={"PREPARED":{"VENV_READY","FAILED","ABANDONED"},"VENV_READY":{"ACTIVATED","FAILED","ABANDONED"},"ACTIVATED":{"ACTIVE","FAILED","ABANDONED"},"ACTIVE":{"FAILED","ABANDONED"},"FAILED":{"ABANDONED"},"ABANDONED":set()}
ID_RE=re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def ensure_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS connector_lifecycle(
      operation_id TEXT PRIMARY KEY, connector_id TEXT NOT NULL, version TEXT NOT NULL,
      state TEXT NOT NULL, artifact_path TEXT NOT NULL, artifact_sha256 TEXT NOT NULL,
      previous_version TEXT, actor_id TEXT NOT NULL, evidence_json TEXT NOT NULL,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_connector_lifecycle_connector ON connector_lifecycle(connector_id,updated_at);
    """)
def verify_signed_artifact(manifest_path: str, signature_path: str, public_key_path: str, artifact_path: str) -> dict:
    for p in (manifest_path,signature_path,public_key_path,artifact_path):
        if not Path(p).is_absolute(): raise ValueError("absolute_paths_required")
    manifest_raw=Path(manifest_path).read_bytes(); signature=bytes.fromhex(Path(signature_path).read_text("ascii").strip())
    public_raw=Path(public_key_path).read_bytes()
    try: key=Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_raw.decode("ascii").strip())); key.verify(signature,manifest_raw)
    except (ValueError,UnicodeError,InvalidSignature) as exc: raise ValueError("activation_signature_invalid_or_untrusted") from exc
    try: manifest=json.loads(manifest_raw)
    except (ValueError,UnicodeError) as exc: raise ValueError("activation_manifest_invalid") from exc
    if not isinstance(manifest,dict) or set(manifest)!={"schema_version","connector_id","version","artifact_sha256"} or manifest.get("schema_version")!=1: raise ValueError("activation_manifest_schema_invalid")
    if not isinstance(manifest.get("connector_id"),str) or not ID_RE.fullmatch(manifest["connector_id"]): raise ValueError("activation_connector_id_invalid")
    if not isinstance(manifest.get("version"),str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", manifest["version"]): raise ValueError("activation_version_invalid")
    expected=manifest.get("artifact_sha256")
    if not isinstance(expected,str) or not re.fullmatch(r"[0-9a-f]{64}",expected): raise ValueError("activation_hash_invalid")
    actual=hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
    if actual!=expected: raise ValueError("activation_artifact_hash_mismatch")
    return VerifiedManifest(manifest, _VERIFIED_SEAL)

def create_operation(conn, manifest:dict, artifact_path:str, actor_id:str, previous_version:str|None=None)->dict:
    if not isinstance(manifest, VerifiedManifest) or not manifest.is_verified: raise ValueError("verified_signed_manifest_required")
    ensure_schema(conn); oid=str(uuid.uuid4()); stamp=now(); digest=manifest["artifact_sha256"]
    conn.execute("INSERT INTO connector_lifecycle VALUES(?,?,?,?,?,?,?,?,?,?,?)",(oid,manifest["connector_id"],manifest["version"],"PREPARED",str(Path(artifact_path)),digest,previous_version,actor_id,json.dumps({"signature_verified":True,"sha256_verified":True,"isolation_verified":False,"health_check_passed":False},sort_keys=True),stamp,stamp))
    return dict(conn.execute("SELECT * FROM connector_lifecycle WHERE operation_id=?",(oid,)).fetchone())
def transition(conn, operation_id:str, state:str, evidence:dict|None=None)->dict:
    if state not in STATES: raise ValueError("invalid_lifecycle_state")
    row=conn.execute("SELECT * FROM connector_lifecycle WHERE operation_id=?",(operation_id,)).fetchone()
    if not row: raise LookupError("lifecycle_operation_not_found")
    if state not in TRANSITIONS[row["state"]]: raise ValueError("invalid_lifecycle_transition")
    details=json.loads(row["evidence_json"]); evidence=evidence or {}
    if state=="VENV_READY" and evidence.get("dependency_hashes_verified") is not True: raise ValueError("dependency_hashes_not_verified")
    if state=="ACTIVATED" and evidence.get("isolation_enforced") is not True: raise ValueError("isolation_not_operationally_verified")
    if state=="ACTIVE" and (evidence.get("health_check_passed") is not True or evidence.get("interface_contract_passed") is not True): raise ValueError("worker_health_or_contract_not_verified")
    details.update(evidence); conn.execute("UPDATE connector_lifecycle SET state=?,evidence_json=?,updated_at=? WHERE operation_id=?",(state,json.dumps(details,sort_keys=True),now(),operation_id))
    return dict(conn.execute("SELECT * FROM connector_lifecycle WHERE operation_id=?",(operation_id,)).fetchone())
def recovery_plan(conn, connector_id:str)->dict:
    ensure_schema(conn); rows=conn.execute("SELECT * FROM connector_lifecycle WHERE connector_id=? ORDER BY updated_at DESC",(connector_id,)).fetchall()
    active=next((dict(r) for r in rows if r["state"]=="ACTIVE"),None)
    incomplete=[dict(r) for r in rows if r["state"] in {"PREPARED","VENV_READY","ACTIVATED"}]
    return {"connector_id":connector_id,"active":active,"incomplete":incomplete,"action":"KEEP_PREVIOUS_ACTIVE_AND_MARK_INCOMPLETE_FAILED" if incomplete and active else ("ROLLBACK_REQUIRED" if incomplete else "NO_RECOVERY_REQUIRED"),"filesystem_or_systemd_changed":False}
