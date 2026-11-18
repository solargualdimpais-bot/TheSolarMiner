import json
import hashlib
from pathlib import Path

import pytest

from solarminer_gateway.system_components import (
    PROTOCOL_VERSION,
    REQUIRED_COMPONENTS,
    SystemComponentError,
    compatibility_status,
    initialize_installed_manifest,
    integrated_diagnostics,
    installed_component_status,
    reconcile,
    restore,
)


OPERATION = "12345678-1234-4234-8234-123456789abc"


def _package(tmp_path: Path) -> Path:
    root = tmp_path / "package"
    for relative in REQUIRED_COMPONENTS:
        relative = relative.replace("usr/lib/systemd/system/", "lib/systemd/system/")
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("test component\n")
    (root / "usr/bin/solarminer-new-broker").write_text("new helper\n")
    unit = root / "lib/systemd/system/solarminer-new.socket"
    unit.write_text("[Socket]\nListenStream=/run/solarminer/new.sock\n")
    return root


def _install_required_files(system: Path) -> list[str]:
    paths = []
    for relative in REQUIRED_COMPONENTS:
        target = system / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("installed component\n")
        paths.append("/" + relative.replace("usr/lib/systemd/system/", "lib/systemd/system/"))
    return paths


def test_reconcile_system_payload_and_restore_previous_files_atomically(tmp_path: Path):
    package = _package(tmp_path)
    deployment = tmp_path / "opt/solarminer"
    system = tmp_path / "system"
    helper = system / "usr/bin/solarminer-new-broker"
    unit = system / "usr/lib/systemd/system/solarminer-new.socket"
    stale = system / "usr/bin/solarminer-old-broker"
    helper.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("old helper\n")
    prior_files = ["usr/bin/solarminer-old-broker"]
    (deployment).mkdir(parents=True)
    (deployment / "system-components.json").write_text(json.dumps({
        "protocol": PROTOCOL_VERSION, "version": "0.6.257", "files": prior_files,
        "sha256": {"usr/bin/solarminer-old-broker": hashlib.sha256(b"old helper\n").hexdigest()},
    }))
    observed_snapshot = []

    snapshot = reconcile(package, deployment, "0.6.258", operation_id=OPERATION,
                         system_root=system, on_snapshot_ready=observed_snapshot.append)

    assert observed_snapshot == [snapshot]
    assert helper.read_text() == "new helper\n"
    assert unit.is_file()
    assert not stale.exists()
    assert json.loads((deployment / "system-components.json").read_text())["version"] == "0.6.258"

    restore(snapshot, deployment, system_root=system)
    assert not helper.exists()
    assert not unit.exists()
    assert stale.read_text() == "old helper\n"
    assert json.loads((deployment / "system-components.json").read_text())["version"] == "0.6.257"


def test_reconcile_refuses_symlink_component_in_signed_payload(tmp_path: Path):
    package = _package(tmp_path)
    target = package / "usr/bin/solarminer-bad-link"
    try:
        target.symlink_to("solarminer-new-broker")
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks requires privileges unavailable on this Windows runner")
    deployment = tmp_path / "opt/solarminer"
    deployment.mkdir(parents=True)

    with pytest.raises(SystemComponentError, match="system_component_not_regular_file"):
        reconcile(package, deployment, "0.6.258", operation_id=OPERATION,
                  system_root=tmp_path / "system")


def test_reconcile_refuses_signed_package_missing_a_required_broker_component(tmp_path: Path):
    package = _package(tmp_path)
    missing = package / "usr/bin/solarminer-update-broker"
    missing.unlink()
    deployment = tmp_path / "opt/solarminer"
    deployment.mkdir(parents=True)

    with pytest.raises(SystemComponentError, match="system_component_payload_incomplete"):
        reconcile(package, deployment, "0.6.258", operation_id=OPERATION,
                  system_root=tmp_path / "system")


def test_reconcile_ignores_unowned_paths_from_legacy_file_list(tmp_path: Path):
    package = _package(tmp_path)
    deployment = tmp_path / "opt/solarminer"
    deployment.mkdir(parents=True)

    reconcile(package, deployment, "0.6.258", operation_id=OPERATION,
              legacy_files=["etc/solarminer/server.key"], system_root=tmp_path / "system")
    assert not (tmp_path / "system/etc/solarminer/server.key").exists()


def test_installed_manifest_and_status_track_only_package_owned_components(tmp_path: Path):
    deployment = tmp_path / "opt/solarminer"
    system = tmp_path / "system"
    files = _install_required_files(system)
    helper = system / "usr/bin/solarminer-helper"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text("helper\n")
    assert installed_component_status(deployment, system_root=system)["status"] == "UNAVAILABLE"

    initialize_installed_manifest("0.6.258", deployment,
                                   list_files=lambda: files + ["/usr/bin/solarminer-helper", "/etc/solarminer/private.key"],
                                   system_root=system)

    status = installed_component_status(deployment, system_root=system)
    manifest = json.loads((deployment / "system-components.json").read_text())
    assert status == {"status": "OK", "version": "0.6.258", "protocol": PROTOCOL_VERSION, "reason": None}
    assert "usr/bin/solarminer-helper" in manifest["files"]
    assert all(item in manifest["files"] or
               item.replace("usr/lib/systemd/system/", "lib/systemd/system/") in manifest["files"]
               for item in REQUIRED_COMPONENTS)
    helper.write_text("unexpected change\n")
    assert installed_component_status(deployment, system_root=system)["reason"] == "system_component_hash_mismatch"


def test_installed_manifest_fails_when_dpkg_reports_a_missing_component(tmp_path: Path):
    deployment = tmp_path / "opt/solarminer"
    with pytest.raises(SystemComponentError, match="installed_system_component_missing"):
        initialize_installed_manifest("0.6.258", deployment,
                                      list_files=lambda: ["/usr/bin/solarminer-helper"],
                                      system_root=tmp_path / "system")


def test_installed_manifest_refuses_incomplete_dpkg_inventory(tmp_path: Path):
    system = tmp_path / "system"
    helper = system / "usr/bin/solarminer-helper"
    helper.parent.mkdir(parents=True)
    helper.write_text("helper\n")
    with pytest.raises(SystemComponentError, match="installed_system_component_inventory_incomplete"):
        initialize_installed_manifest("0.6.258", tmp_path / "opt/solarminer",
                                      list_files=lambda: ["/usr/bin/solarminer-helper"],
                                      system_root=system)


def test_compatibility_status_refuses_release_component_version_mismatch():
    assert compatibility_status("0.6.258", {
        "status": "OK", "version": "0.6.257", "protocol": PROTOCOL_VERSION,
    }) == {"status": "INCOMPATIBLE", "reason": "system_components_release_version_mismatch"}
    assert compatibility_status("0.6.258", {
        "status": "OK", "version": "0.6.258", "protocol": PROTOCOL_VERSION,
    }) == {"status": "OK", "reason": None}


def test_integrated_diagnostics_reports_versions_and_fixed_unit_states_without_secrets(tmp_path: Path):
    calls = []
    def runner(args, **_kwargs):
        calls.append(args)
        if args[0].endswith("dpkg-query"):
            return type("Result", (), {"returncode": 0, "stdout": "0.6.258\n"})()
        return type("Result", (), {"returncode": 0, "stdout": "active\n"})()

    result = integrated_diagnostics("0.6.258", deployment_root=tmp_path / "missing", runner=runner)
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "system_components_manifest_missing"
    assert result["debian_package_version"] == "0.6.258"
    assert result["active_release"] is None
    assert result["units"]["admin_terminal"]["state"] == "active"
    assert len(calls) == 1 + len(result["units"])
    assert "token" not in str(result).lower()
