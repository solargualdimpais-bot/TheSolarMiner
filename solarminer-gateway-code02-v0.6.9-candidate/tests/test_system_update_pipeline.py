from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
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


def test_queued_update_is_not_activated_without_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline, _root, _previous, _db, op_id = _pipeline_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "preflight", lambda: (_ for _ in ()).throw(PipelineError("independent_recovery_timer_not_active")))
    with pytest.raises(PipelineError, match="independent_recovery_timer_not_active"):
        pipeline.enqueue(op_id)


def test_apply_rolls_back_pointer_when_new_release_fails_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline, root, previous, _db, op_id = _pipeline_fixture(tmp_path, monkeypatch)
    answers = iter([False, True])
    monkeypatch.setattr(pipeline, "_health", lambda expected, seconds: next(answers))
    monkeypatch.setattr(pipeline, "_uid", lambda _name: 0)
    monkeypatch.setattr(pipeline, "_gid", lambda _name: 0)
    # The hosted runner is unprivileged; ownership transfer is mocked in this rollback test.
    monkeypatch.setattr("solarminer_gateway.system_update_pipeline.os.chown", lambda *_args: None)
    result = pipeline.apply(op_id)
    assert result["status"] == "ROLLED_BACK"
    assert os.readlink(root / "current") == "releases/0.6.8"
    assert json.loads((root / "update-state.json").read_text())["state"] == "ROLLED_BACK"
    with sqlite3.connect(_db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT state FROM update_operations WHERE id=?", (op_id,)).fetchone()[0] == "ROLLED_BACK"


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
