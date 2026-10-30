from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import ssl
import subprocess
import time
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from solarminer_gateway.system_update_pipeline import PipelineError, SystemUpdatePipeline, _validate_deployment_root_permissions
from solarminer_gateway.updates import canonical_manifest


def _make_package(tmp_path: Path, version: str = "0.6.9") -> Path:
    tree = tmp_path / "deb-tree"
    (tree / "DEBIAN").mkdir(parents=True)
    (tree / "usr/lib/solarminer-gateway/solarminer_gateway").mkdir(parents=True)
    (tree / "usr/share/solarminer/pwa").mkdir(parents=True)
    (tree / "usr/lib/solarminer-gateway/solarminer_gateway/app.py").write_text("PACKAGE_VERSION = '" + version + "'\n")
    (tree / "usr/share/solarminer/pwa/index.html").write_text("<!doctype html><title>SolarMiner</title>")
    (tree / "usr/share/solarminer/pwa/manifest.webmanifest").write_text('{"name":"SolarMiner"}')
    (tree / "usr/share/solarminer/catalog.json").write_text('{}')
    (tree / "usr/share/solarminer/catalog.sig").write_text('signature')
    (tree / "usr/share/solarminer/catalog.pub").write_text('public-key')
    (tree / "DEBIAN/control").write_text(
        f"Package: solarminer-gateway\nVersion: {version}\nArchitecture: amd64\nMaintainer: Test\nDescription: test update package\n"
    )
    out = tmp_path / f"solarminer-gateway_{version}_amd64.deb"
    subprocess.run(["dpkg-deb", "--build", str(tree), str(out)], check=True, capture_output=True)
    return out



def test_deployment_root_requires_root_ownership():
    with pytest.raises(PipelineError, match="deployment_root_permissions_invalid"):
        _validate_deployment_root_permissions(SimpleNamespace(st_uid=12345, st_mode=0o40750))


def test_deployment_root_rejects_group_or_world_writable_permissions():
    with pytest.raises(PipelineError, match="deployment_root_permissions_invalid"):
        _validate_deployment_root_permissions(SimpleNamespace(st_uid=0, st_mode=0o40770))


def test_deployment_root_accepts_private_root_owned_permissions():
    _validate_deployment_root_permissions(SimpleNamespace(st_uid=0, st_mode=0o40750))

def _pipeline_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, version: str = "0.6.9"):
    root = tmp_path / "opt/solarminer"
    releases = root / "releases"
    previous = releases / "0.6.8"
    (previous / "usr/lib/solarminer-gateway/solarminer_gateway").mkdir(parents=True)
    (previous / "usr/lib/solarminer-gateway/solarminer_gateway/app.py").write_text("PACKAGE_VERSION='0.6.8'\n")
    (previous / "usr/share/solarminer/pwa").mkdir(parents=True)
    (previous / "usr/share/solarminer/pwa/index.html").write_text("old")
    (previous / "usr/share/solarminer/pwa/manifest.webmanifest").write_text('{}')
    root.mkdir(parents=True, exist_ok=True)
    (root / "current").symlink_to("releases/0.6.8")
    data = tmp_path / "var/lib/solarminer"
    verified = data / "releases/verified"
    verified.mkdir(parents=True)
    db = data / "gateway.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_migrations VALUES(6,'2026-10-19T00:00:00Z')")
        conn.execute("CREATE TABLE update_operations(id TEXT PRIMARY KEY,state TEXT NOT NULL,installed_version TEXT NOT NULL,target_version TEXT,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,details_json TEXT NOT NULL)")
    deb = _make_package(tmp_path, version)
    package = verified / (deb.name + ".verified")
    shutil.copyfile(deb, package)
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    key_path = tmp_path / "release-pubkey.pem"
    key_path.write_bytes(public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    os.chmod(key_path, 0o644)
    manifest = {
        "schema_version": 1, "release_id": "test-release", "version": version,
        "min_compatible_version": "0.6.8", "changelog": ["test"], "package_name": deb.name,
        "package_url": "https://releases.example.test/" + deb.name, "package_size": package.stat().st_size,
        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(), "signature_algorithm": "Ed25519",
        "compatibility": {}, "migration_requirements": [],
    }
    manifest["signature"] = private.sign(canonical_manifest(manifest)).hex()
    sidecar = package.with_suffix(package.suffix + ".manifest.json")
    sidecar.write_text(json.dumps(manifest))
    op_id = "9a4c0d83-1234-4eab-8c01-112233445566"
    details = {"package_path": str(package), "manifest_path": str(sidecar), "package_sha256": manifest["sha256"], "activation_available": True}
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO update_operations VALUES(?,?,?,?,?,?,?)",
                     (op_id, "VERIFIED", "0.6.8", version, int(time.time()), int(time.time()), json.dumps(details)))
    def runner(args, *, capture_output=True, text=True, timeout=15, check=False):
        if args[0] in {"/usr/bin/dpkg-deb", "/usr/bin/dpkg"}:
            if args[0] == "/usr/bin/dpkg" and args[1:] == ["--print-architecture"]:
                return subprocess.CompletedProcess(args, 0, "amd64\n", "")
            return subprocess.run(args, capture_output=capture_output, text=text, timeout=timeout, check=False)
        if args[0] == "/usr/bin/dpkg-query":
            return subprocess.CompletedProcess(args, 0, "installed", "")
        if args[0] == "/usr/bin/systemctl":
            if len(args) >= 3 and args[1] == "is-active" and args[2] == "solarminer-gateway.service":
                return subprocess.CompletedProcess(args, 3, "inactive\n", "")
            if len(args) >= 3 and args[1] == "is-active" and args[2] == "solarminer-recovery.timer":
                return subprocess.CompletedProcess(args, 0, "active\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")
    (data / "server.crt").write_text("test-certificate-placeholder")
    pipeline = SystemUpdatePipeline(root=root, data_dir=data, db_path=db, public_key=key_path, runner=runner)
    # These transaction tests focus on apply/rollback; permission policy is tested above.
    monkeypatch.setattr(pipeline, "_check_deployment_root_permissions", lambda: None)
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline._validate_root_owned_not_writable", lambda *_args: None)
    monkeypatch.setattr(pipeline, "preflight", lambda: {"status": "ready"})
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.os.geteuid", lambda: 0)
    return pipeline, root, previous, db, op_id


def test_apply_commits_only_after_release_health_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline, root, previous, db, op_id = _pipeline_fixture(tmp_path, monkeypatch)
    checked = []
    monkeypatch.setattr(pipeline, "_health", lambda expected, seconds: checked.append((expected, seconds)) or expected == "0.6.9")
    result = pipeline.apply(op_id)
    assert result["status"] == "COMMITTED"
    assert os.readlink(root / "current") == "releases/0.6.9"
    assert checked == [("0.6.9", 60)]
    record = json.loads((root / "update-state.json").read_text())
    assert record["state"] == "COMMITTED" and record["backup_path"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT state FROM update_operations WHERE id=?", (op_id,)).fetchone()[0] == "COMMITTED"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_health_check_has_a_hard_sixty_second_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = SystemUpdatePipeline(root=tmp_path / "opt/solarminer", health_timeout=60)
    now = [0.0]
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.ssl.create_default_context", lambda **kwargs: object())
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.urllib.request.urlopen",
                        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("service unavailable")))
    pipeline.clock = lambda: now[0]
    pipeline.sleep = lambda seconds: now.__setitem__(0, now[0] + seconds)
    assert pipeline._health("0.6.9", 60) is False
    assert now[0] >= 60.0
    assert pipeline._last_health_diagnostic["outcome"] == "endpoint_error"
    assert pipeline._last_health_diagnostic["attempts"] > 0


def test_health_check_records_reported_version_mismatch_without_payload_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = SystemUpdatePipeline(root=tmp_path / "opt/solarminer", health_timeout=1)
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.ssl.create_default_context", lambda **kwargs: object())

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, _limit): return b'{"status":"ok","package_version":"0.6.98","token":"hidden"}'

    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    now = [0.0]
    pipeline.clock = lambda: now[0]
    pipeline.sleep = lambda seconds: now.__setitem__(0, now[0] + seconds)
    assert pipeline._health("0.6.100", 1) is False
    assert pipeline._last_health_diagnostic == {
        "outcome": "package_version_mismatch", "http_status": 200,
        "reported_package_version": "0.6.98", "attempts": 1,
        "expected_package_version": "0.6.100",
    }


@pytest.mark.parametrize(
    ("reason", "expected_outcome"),
    [
        (ssl.SSLCertVerificationError("certificate verify failed"), "tls_error"),
        (TimeoutError("timed out"), "timeout"),
        (ConnectionRefusedError("connection refused"), "connection_error"),
    ],
)
def test_health_check_classifies_url_errors_without_persisting_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: BaseException, expected_outcome: str
):
    pipeline = SystemUpdatePipeline(root=tmp_path / "opt/solarminer", health_timeout=1)
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.ssl.create_default_context", lambda **kwargs: object())
    monkeypatch.setattr(
        "solarminer_gateway.system_update_pipeline.urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib.error.URLError(reason)),
    )
    now = [0.0]
    pipeline.clock = lambda: now[0]
    pipeline.sleep = lambda seconds: now.__setitem__(0, now[0] + seconds)
    assert pipeline._health("0.6.100", 1) is False
    diagnostic = pipeline._last_health_diagnostic
    assert diagnostic["outcome"] == expected_outcome
    assert diagnostic["attempts"] == 1
    assert "reason" not in diagnostic and "message" not in diagnostic


def test_queued_update_is_not_activated_without_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline, _root, _previous, _db, op_id = _pipeline_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "preflight", lambda: (_ for _ in ()).throw(PipelineError("independent_recovery_timer_not_active")))
    with pytest.raises(PipelineError, match="independent_recovery_timer_not_active"):
        pipeline.enqueue(op_id)


def test_recovery_defers_while_gateway_restart_update_worker_is_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = SystemUpdatePipeline(root=tmp_path / "opt/solarminer")
    op_id = "12345678-1234-4234-8234-123456789abc"
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.os.geteuid", lambda: 0)
    monkeypatch.setattr("solarminer_gateway.deployment_recovery.DeploymentReleaseSwitch.recover_pending",
                        lambda _self: {"status": "clean"})
    monkeypatch.setattr(pipeline, "_read_state", lambda: {"state": "SERVICE_RESTARTING", "operation_id": op_id})
    requested = []

    def active_apply_unit(args, **_kwargs):
        requested.append(args)
        return SimpleNamespace(returncode=0, stdout="active\n", stderr="")

    monkeypatch.setattr(pipeline, "_run", active_apply_unit)
    from contextlib import contextmanager

    @contextmanager
    def lock_must_not_be_taken():
        raise AssertionError("recovery must defer before waiting on the update lock")
        yield

    monkeypatch.setattr(pipeline, "_locked", lock_must_not_be_taken)
    result = pipeline.recover()
    assert result["status"] == "update_unit_active"
    assert result["state"] == "SERVICE_RESTARTING"
    assert requested == [["/usr/bin/systemctl", "is-active", f"solarminer-update-apply@{op_id}.service"]]


def test_apply_rolls_back_pointer_when_new_release_fails_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline, root, previous, _db, op_id = _pipeline_fixture(tmp_path, monkeypatch)
    answers = iter([False, True])
    def health(expected, _seconds):
        pipeline._last_health_diagnostic = {"outcome": "package_version_mismatch" if expected == "0.6.9" else "healthy",
                                            "reported_package_version": "0.6.8" if expected == "0.6.9" else expected}
        return next(answers)
    monkeypatch.setattr(pipeline, "_health", health)
    monkeypatch.setattr(pipeline, "_uid", lambda _name: 0)
    monkeypatch.setattr(pipeline, "_gid", lambda _name: 0)
    # The hosted runner is unprivileged; ownership transfer is mocked in this rollback test.
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.os.chown", lambda *_args: None)
    result = pipeline.apply(op_id)
    assert result["status"] == "ROLLED_BACK"
    assert os.readlink(root / "current") == "releases/0.6.8"
    state = json.loads((root / "update-state.json").read_text())
    assert state["state"] == "ROLLED_BACK"
    assert state["failure"] == "new_release_health_check_failed_after_60s"
    assert state["health_diagnostic"]["outcome"] == "package_version_mismatch"
    assert state["rollback_health_diagnostic"]["outcome"] == "healthy"
    with sqlite3.connect(_db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT state FROM update_operations WHERE id=?", (op_id,)).fetchone()[0] == "ROLLED_BACK"


def test_watchdog_rollback_restores_only_the_previous_active_release_and_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from solarminer_gateway.database_backup import create_database_backup
    pipeline, root, previous, db, op_id = _pipeline_fixture(tmp_path, monkeypatch, version="0.6.96")
    monkeypatch.setattr(pipeline, "_uid", lambda _name: 0)
    monkeypatch.setattr(pipeline, "_gid", lambda _name: 0)
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.os.chown", lambda *_args: None)
    prior_deb = _make_package(tmp_path / "prior", "0.6.8")
    verified_dir = pipeline.data_dir / "releases/verified"
    prior_package = verified_dir / (prior_deb.name + ".verified")
    shutil.copyfile(prior_deb, prior_package)
    prior_key = Ed25519PrivateKey.generate()
    pipeline.public_key.write_bytes(prior_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    prior_manifest = {
        "schema_version": 1, "release_id": "gateway-v0.6.8", "version": "0.6.8",
        "min_compatible_version": "0.6.7", "changelog": ["known good"],
        "package_name": prior_deb.name, "package_url": "https://releases.example.test/" + prior_deb.name,
        "package_size": prior_package.stat().st_size, "sha256": hashlib.sha256(prior_package.read_bytes()).hexdigest(),
        "signature_algorithm": "Ed25519", "compatibility": {}, "migration_requirements": [],
    }
    prior_manifest["signature"] = prior_key.sign(canonical_manifest(prior_manifest)).hex()
    prior_sidecar = prior_package.with_suffix(prior_package.suffix + ".manifest.json")
    prior_sidecar.write_text(json.dumps(prior_manifest))
    prior_op = "12345678-1234-4234-8234-123456789abc"
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO update_operations VALUES(?,?,?,?,?,?,?)", (
            prior_op, "COMMITTED", "0.6.7", "0.6.8", int(time.time()), int(time.time()),
            json.dumps({"package_path": str(prior_package), "pipeline": {"health_check": "passed"}}),
        ))
    current = root / "releases/0.6.96"
    (current / "usr/lib/solarminer-gateway/solarminer_gateway").mkdir(parents=True)
    (current / "usr/lib/solarminer-gateway/solarminer_gateway/app.py").write_text("new release")
    (current / "usr/share/solarminer/pwa").mkdir(parents=True)
    (current / "usr/share/solarminer/pwa/index.html").write_text("new")
    backup = create_database_backup(db, root / "backups")
    pipeline._switch(current)
    pipeline._record("COMMITTED", operation_id=op_id, target_version="0.6.96",
                     previous_target="releases/0.6.8", new_target="releases/0.6.96",
                     backup_path=backup["backup_path"], finished_at_utc="2026-10-27T00:00:00Z")

    result = pipeline.rollback_committed()

    assert result["state"] == "ROLLED_BACK"
    assert os.readlink(root / "current") == "releases/0.6.8"
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_watchdog_rollback_fails_closed_without_signed_health_attestation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from solarminer_gateway.database_backup import create_database_backup
    pipeline, root, _previous, db, op_id = _pipeline_fixture(tmp_path, monkeypatch, version="0.6.96")
    current = root / "releases/0.6.96"
    (current / "usr/lib/solarminer-gateway/solarminer_gateway").mkdir(parents=True)
    (current / "usr/lib/solarminer-gateway/solarminer_gateway/app.py").write_text("new release")
    (current / "usr/share/solarminer/pwa").mkdir(parents=True)
    (current / "usr/share/solarminer/pwa/index.html").write_text("new")
    backup = create_database_backup(db, root / "backups")
    pipeline._switch(current)
    pipeline._record("COMMITTED", operation_id=op_id, target_version="0.6.96",
                     previous_target="releases/0.6.8", new_target="releases/0.6.96",
                     backup_path=backup["backup_path"], finished_at_utc="2026-10-27T00:00:00Z")

    result = pipeline.rollback_committed()

    assert result == {"status": "skipped", "reason": "previous_release_has_no_verified_success_record"}
    assert os.readlink(root / "current") == "releases/0.6.96"


def test_recovery_reconciles_interrupted_switch_and_restores_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from solarminer_gateway.database_backup import create_database_backup
    pipeline, root, previous, db, op_id = _pipeline_fixture(tmp_path, monkeypatch)
    target = root / "releases/0.6.9"
    (target / "usr/lib/solarminer-gateway/solarminer_gateway").mkdir(parents=True)
    (target / "usr/lib/solarminer-gateway/solarminer_gateway/app.py").write_text("broken")
    (target / "usr/share/solarminer/pwa").mkdir(parents=True)
    (target / "usr/share/solarminer/pwa/index.html").write_text("new")
    (target / "usr/share/solarminer/pwa/manifest.webmanifest").write_text('{}')
    for catalog_file in ("catalog.json", "catalog.sig", "catalog.pub"):
        (target / "usr/share/solarminer" / catalog_file).write_text('test')
    backup = create_database_backup(db, root / "backups")
    pipeline._switch(target)
    pipeline._record("SWITCHED", operation_id=op_id, target_version="0.6.9",
                     previous_target="releases/0.6.8", new_target="releases/0.6.9",
                     backup_path=backup["backup_path"])
    monkeypatch.setattr(pipeline, "_uid", lambda _name: 0)
    monkeypatch.setattr(pipeline, "_gid", lambda _name: 0)
    # Recovery logic is exercised without requiring chown privileges on the CI runner.
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.os.chown", lambda *_args: None)
    result = pipeline.recover()
    assert result["status"] == "recovered"
    assert os.readlink(root / "current") == "releases/0.6.8"
    assert json.loads((root / "update-state.json").read_text())["state"] == "ROLLED_BACK"
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_recovery_retries_recovery_blocked_operation_with_valid_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from solarminer_gateway.database_backup import create_database_backup
    pipeline, root, previous, db, op_id = _pipeline_fixture(tmp_path, monkeypatch)
    target = root / "releases/0.6.9"
    target.mkdir(parents=True)
    backup = create_database_backup(db, root / "backups")
    pipeline._switch(target)
    pipeline._record("RECOVERY_BLOCKED", operation_id=op_id, target_version="0.6.9",
                     previous_target="releases/0.6.8", new_target="releases/0.6.9",
                     backup_path=backup["backup_path"], failure="PipelineError",
                     rollback_failure="TimeoutExpired")
    real_runner = pipeline.runner
    active_calls = [0]
    def runner(args, **kwargs):
        if args[0] == "/usr/bin/systemctl" and args[1:3] == ["is-active", "solarminer-gateway.service"]:
            active_calls[0] += 1
            if active_calls[0] == 1:
                return subprocess.CompletedProcess(args, 0, "active\n", "")
            return subprocess.CompletedProcess(args, 3, "inactive\n", "")
        return real_runner(args, **kwargs)
    pipeline.runner = runner
    monkeypatch.setattr(pipeline, "_health", lambda expected, seconds: expected == "0.6.8")
    monkeypatch.setattr(pipeline, "_uid", lambda _name: 0)
    monkeypatch.setattr(pipeline, "_gid", lambda _name: 0)
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.os.chown", lambda *_args: None)

    result = pipeline.recover()

    assert result["state"] == "ROLLED_BACK"
    assert os.readlink(root / "current") == "releases/0.6.8"
    assert json.loads((root / "update-state.json").read_text())["state"] == "ROLLED_BACK"
