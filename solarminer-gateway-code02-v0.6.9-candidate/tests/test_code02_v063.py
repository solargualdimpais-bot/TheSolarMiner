from __future__ import annotations
import hashlib, json, os, zipfile
from pathlib import Path
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from solarminer_gateway import signed_activation
from solarminer_gateway.runtime_manager import ConnectorWorkerRuntime, WorkerRuntimeError
from solarminer_gateway.update_transaction import AtomicReleaseStore, UpdateTransactionError


def signed_zip(tmp_path, connector_id="test-connector", version="1.0.0"):
    artifact = tmp_path / f"{version}.zip"
    with zipfile.ZipFile(artifact, "w") as zf:
        zf.writestr("connector.py", f"VERSION = {version!r}\n")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = {"schema_version": 1, "connector_id": connector_id, "version": version, "artifact_sha256": digest}
    raw = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    mp = tmp_path / f"{version}.json"; mp.write_bytes(raw)
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    pp = tmp_path / f"{version}.pub"; pp.write_text(pub.hex())
    sp = tmp_path / f"{version}.sig"; sp.write_text(key.sign(raw).hex())
    verified = signed_activation.verify_signed_artifact(str(mp), str(sp), str(pp), str(artifact))
    return artifact, verified


def test_worker_runtime_start_ipc_monitor_stop():
    runtime = ConnectorWorkerRuntime("test-connector", timeout=3)
    result = runtime.start()
    assert result["worker"] == "ready"
    assert result["connector_id"] == "test-connector"
    assert runtime.is_alive()
    assert runtime.call("health", {})["hardware_commands_sent"] is False
    runtime.stop()
    assert not runtime.is_alive()
    with pytest.raises(WorkerRuntimeError, match="worker_not_running"):
        runtime.call("health", {})


def test_worker_runtime_rejects_invalid_id_and_timeout():
    with pytest.raises(ValueError, match="invalid_connector_id"):
        ConnectorWorkerRuntime("../escape")
    with pytest.raises(ValueError, match="invalid_worker_timeout"):
        ConnectorWorkerRuntime("connector", timeout=99)


def test_atomic_store_activates_verified_archive_and_preserves_previous(tmp_path):
    store = AtomicReleaseStore(tmp_path / "store")
    first, manifest1 = signed_zip(tmp_path, version="1.0.0")
    result1 = store.activate(manifest1, first, lambda p: (p / "connector.py").is_file())
    assert result1["status"] == "ACTIVE_POINTER_COMMITTED"
    old = os.readlink(store.active_path("test-connector"))
    second, manifest2 = signed_zip(tmp_path, version="2.0.0")
    result2 = store.activate(manifest2, second, lambda p: (p / "connector.py").read_text().find("2.0.0") >= 0)
    assert result2["previous_target"] == old
    assert (store.active_path("test-connector").resolve() / "connector.py").read_text().find("2.0.0") >= 0
    assert "COMMITTED" in store.journal.read_text()


def test_atomic_store_rolls_back_after_post_switch_failure(tmp_path):
    store = AtomicReleaseStore(tmp_path / "store")
    first, m1 = signed_zip(tmp_path, version="1.0.0")
    store.activate(m1, first, lambda p: (p / "connector.py").is_file())
    previous = os.readlink(store.active_path("test-connector"))
    second, m2 = signed_zip(tmp_path, version="2.0.0")
    with pytest.raises(UpdateTransactionError, match="injected_post_switch_failure"):
        store.activate(m2, second, lambda p: (p / "connector.py").is_file(), fault_at="post_switch")
    assert os.readlink(store.active_path("test-connector")) == previous
    assert "ROLLBACK_POINTER_RESTORED" in store.journal.read_text()


@pytest.mark.parametrize("fault", ["staging", "validation", "pre_switch"])
def test_atomic_store_failures_before_switch_preserve_active(tmp_path, fault):
    store = AtomicReleaseStore(tmp_path / "store")
    first, m1 = signed_zip(tmp_path, version="1.0.0")
    store.activate(m1, first, lambda p: (p / "connector.py").is_file())
    previous = os.readlink(store.active_path("test-connector"))
    second, m2 = signed_zip(tmp_path, version="2.0.0")
    with pytest.raises(UpdateTransactionError):
        store.activate(m2, second, lambda p: (p / "connector.py").is_file(), fault_at=fault)
    assert os.readlink(store.active_path("test-connector")) == previous


def test_atomic_store_rejects_modified_artifact_and_unsigned_manifest(tmp_path):
    store = AtomicReleaseStore(tmp_path / "store")
    artifact, manifest = signed_zip(tmp_path)
    artifact.write_bytes(artifact.read_bytes() + b"tamper")
    with pytest.raises(UpdateTransactionError, match="artifact_hash_mismatch"):
        store.activate(manifest, artifact, lambda p: True)
    with pytest.raises(ValueError, match="verified_signed_manifest_required"):
        signed_activation.VerifiedManifest({"connector_id": "test", "version": "1"})


def test_atomic_store_rejects_zip_path_traversal(tmp_path):
    store = AtomicReleaseStore(tmp_path / "store")
    artifact = tmp_path / "evil.zip"
    with zipfile.ZipFile(artifact, "w") as zf: zf.writestr("../outside.txt", "bad")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = {"schema_version": 1, "connector_id": "test-connector", "version": "1.0.0", "artifact_sha256": digest}
    raw = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode(); mp=tmp_path/"evil.json"; mp.write_bytes(raw)
    key=Ed25519PrivateKey.generate(); pp=tmp_path/"evil.pub"; pp.write_text(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex())
    sp=tmp_path/"evil.sig"; sp.write_text(key.sign(raw).hex())
    verified=signed_activation.verify_signed_artifact(str(mp), str(sp), str(pp), str(artifact))
    with pytest.raises(UpdateTransactionError, match="unsafe_archive_path"):
        store.activate(verified, artifact, lambda p: True)


def test_atomic_store_keeps_active_pointers_per_connector(tmp_path):
    store = AtomicReleaseStore(tmp_path / "store")
    a1, m1 = signed_zip(tmp_path, connector_id="inverter-one", version="1.0.0")
    a2, m2 = signed_zip(tmp_path, connector_id="battery-two", version="1.0.0")
    store.activate(m1, a1, lambda p: (p / "connector.py").is_file())
    store.activate(m2, a2, lambda p: (p / "connector.py").is_file())
    assert store.active_path("inverter-one").resolve().name == "inverter-one-1.0.0"
    assert store.active_path("battery-two").resolve().name == "battery-two-1.0.0"
