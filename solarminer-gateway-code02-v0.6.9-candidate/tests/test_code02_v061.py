from __future__ import annotations

import hashlib
import json
import socket
import struct
from pathlib import Path

import pytest

from solarminer_gateway import deye_modbus as deye
from solarminer_gateway import isolated_runtime as isolation
from solarminer_gateway import connector_dependencies as deps


class FakeSocket:
    def __init__(self, response=b"", fail_send=None):
        self.response = bytearray(response)
        self.request = b""
        self.fail_send = fail_send
        self.timeout = None
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def settimeout(self, value): self.timeout = value
    def sendall(self, data):
        if self.fail_send:
            raise self.fail_send
        self.request = data
    def recv(self, count):
        result = bytes(self.response[:count])
        del self.response[:count]
        return result


def modbus_response(registers, transaction=1, unit=1, function=3):
    if function == 0x83:
        pdu = bytes([0x83, 2])
    else:
        raw = b"".join(struct.pack(">H", n) for n in registers)
        pdu = bytes([function, len(raw)]) + raw
    return struct.pack(">HHHB", transaction, 0, len(pdu) + 1, unit) + pdu


def test_deye_fc03_reads_raw_values_and_never_claims_metrics():
    fake = FakeSocket(modbus_response([0, 32768, 65535]))
    result = deye.read_holding_registers("192.168.1.44", 100, 3, socket_factory=lambda *a, **k: fake)
    assert result.raw_registers == (0, 32768, 65535)
    assert result.state == "RAW_READ_ONLY_UNMAPPED"
    assert result.units == result.scaling == "UNKNOWN"
    assert result.model_compatibility == "NOT_VERIFIED"
    assert result.hardware_validation == "NOT_VALIDATED_ON_HARDWARE"
    assert fake.request[7] == 0x03
    assert fake.request[8:] == struct.pack(">HH", 100, 3)
    assert result.as_dict()["control_commands_sent"] is False


def test_deye_only_emits_fc03():
    fake = FakeSocket(modbus_response([42]))
    deye.read_holding_registers("192.168.1.44", 1, 1, socket_factory=lambda *a, **k: fake)
    assert fake.request[7] == 0x03
    assert fake.request[7] not in {0x05, 0x06, 0x0F, 0x10, 0x16, 0x17}


@pytest.mark.parametrize("host", ["8.8.8.8", "127.0.0.1", "0.0.0.0", "224.0.0.1", "not-an-ip"])
def test_deye_rejects_unsafe_or_nonliteral_hosts(host):
    with pytest.raises(ValueError):
        deye.read_holding_registers(host, 0, 1)


@pytest.mark.parametrize("kwargs", [
    {"port": 0}, {"port": 65536}, {"unit_id": 248}, {"unit_id": -1},
    {"timeout": 0.01}, {"timeout": 6}, {"start_address": -1},
    {"start_address": 65536}, {"count": 0}, {"count": 126},
    {"start_address": 65535, "count": 2},
])
def test_deye_rejects_invalid_request_parameters(kwargs):
    params = {"host": "192.168.1.20", "start_address": 1, "count": 1}
    params.update(kwargs)
    with pytest.raises(ValueError):
        deye.read_holding_registers(**params)


def test_deye_rejects_invalid_mbap_header():
    fake = FakeSocket(modbus_response([1], transaction=99))
    with pytest.raises(deye.ModbusProtocolError, match="invalid_mbap_header"):
        deye.read_holding_registers("192.168.1.20", 1, 1, socket_factory=lambda *a, **k: fake)


def test_deye_rejects_invalid_payload_length():
    response = struct.pack(">HHHB", 1, 0, 4, 1) + bytes([3, 1, 0])
    fake = FakeSocket(response)
    with pytest.raises(deye.ModbusProtocolError, match="invalid_register_payload_length"):
        deye.read_holding_registers("192.168.1.20", 1, 1, socket_factory=lambda *a, **k: fake)


def test_deye_maps_modbus_exception_without_claiming_success():
    fake = FakeSocket(modbus_response([], function=0x83))
    with pytest.raises(deye.ModbusExceptionResponse) as error:
        deye.read_holding_registers("192.168.1.20", 1, 1, socket_factory=lambda *a, **k: fake)
    assert error.value.exception_code == 2


def test_deye_connection_timeout_is_distinguished():
    fake = FakeSocket(fail_send=socket.timeout())
    with pytest.raises(deye.ModbusTimeout):
        deye.read_holding_registers("192.168.1.20", 1, 1, socket_factory=lambda *a, **k: fake)


def test_deye_does_not_decode_unverified_map():
    with pytest.raises(RuntimeError, match="model_specific_register_map_not_verified"):
        deye.documented_metrics()


def test_isolation_unit_enforces_filesystem_process_and_network_boundaries():
    unit = isolation.render_systemd_unit("deye-modbus-tcp", "/var/lib/solarminer/connectors/deye-modbus-tcp/venv/bin/python",
        ["-I", "-m", "solarminer_gateway.deye_worker"], "/var/lib/solarminer/connectors/deye-modbus-tcp/state", "192.168.1.44")
    for expected in ["NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes",
                     "PrivateDevices=yes", "IPAddressDeny=any", "IPAddressAllow=192.168.1.44/32",
                     "MemoryMax=128M", "TasksMax=32", "KillMode=control-group", "ReadWritePaths=/var/lib/solarminer/connectors/deye-modbus-tcp/state"]:
        assert expected in unit
    assert "gateway.db" not in unit


@pytest.mark.parametrize("connector_id", ["../x", "Upper", "x", "has space", "a" * 65])
def test_isolation_rejects_invalid_connector_ids(connector_id):
    with pytest.raises(ValueError, match="invalid_connector_id"):
        isolation.render_systemd_unit(connector_id, "/usr/bin/python3", [], "/tmp/state")


def test_isolation_denies_network_by_default_and_requires_absolute_paths():
    unit = isolation.render_systemd_unit("test-plugin", "/usr/bin/python3", [], "/var/lib/test/state")
    assert "IPAddressDeny=any" in unit
    assert "IPAddressAllow=" not in unit
    with pytest.raises(ValueError, match="absolute_paths_required"):
        isolation.render_systemd_unit("test-plugin", "python3", [], "/var/lib/test/state")


def test_isolation_rejects_public_network_allow_rule():
    with pytest.raises(ValueError, match="private_device_ip_required"):
        isolation.render_systemd_unit("test-plugin", "/usr/bin/python3", [], "/var/lib/test/state", "8.8.8.8")


def test_isolation_uses_single_host_prefix_for_ipv6_allow_rule():
    unit = isolation.render_systemd_unit("test-plugin", "/usr/bin/python3", [],
        "/var/lib/test/state", "fd12:3456::44")
    assert "IPAddressAllow=fd12:3456::44/128" in unit


def test_isolation_policy_does_not_equate_venv_with_security_boundary():
    assert isolation.isolation_requirements()["python_venv_is_security_boundary"] is False


def test_dependency_manifest_checks_wheel_hash_and_source(tmp_path):
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    wheel = wheelhouse / "example_pkg-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"synthetic wheel bytes for test")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    manifest = {"schema_version": 1, "dependencies": [{"name": "example-pkg", "version": "1.2.3",
        "filename": wheel.name, "sha256": digest, "source": "https://pypi.org/project/example-pkg/"}]}
    assert deps.validate_manifest(manifest, wheelhouse)[0]["sha256"] == digest
    manifest["dependencies"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="dependency_wheel_hash_mismatch"):
        deps.validate_manifest(manifest, wheelhouse)


def test_dependency_manifest_rejects_untrusted_source_and_path_traversal(tmp_path):
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    wheel = wheelhouse / "a.whl"
    wheel.write_bytes(b"wheel")
    base = {"name": "a", "version": "1.0", "filename": "a.whl",
            "sha256": hashlib.sha256(b"wheel").hexdigest(), "source": "file:///trusted/wheelhouse"}
    bad_source = {"schema_version": 1, "dependencies": [{**base, "source": "http://evil.invalid/a.whl"}]}
    with pytest.raises(ValueError, match="dependency_source_untrusted"):
        deps.validate_manifest(bad_source, wheelhouse)
    bad_path = {"schema_version": 1, "dependencies": [{**base, "filename": "../a.whl"}]}
    with pytest.raises(ValueError, match="dependency_wheel_filename_invalid"):
        deps.validate_manifest(bad_path, wheelhouse)


def test_dependency_manifest_requires_exact_schema_and_hash(tmp_path):
    with pytest.raises(ValueError, match="dependency_manifest_schema_invalid"):
        deps.validate_manifest({"schema_version": 2, "dependencies": []}, tmp_path)
    with pytest.raises(ValueError, match="dependency_metadata_invalid"):
        deps.validate_manifest({"schema_version": 1, "dependencies": [{"name": "a", "version": "1", "filename": "a.whl", "sha256": "bad", "source": "https://pypi.org"}]}, tmp_path)


def test_dependency_manifest_rejects_duplicate_normalized_package_names(tmp_path):
    wheels = []
    entries = []
    for name, version, filename in [("Example_Pkg", "1.0", "one.whl"), ("example-pkg", "2.0", "two.whl")]:
        path = tmp_path / filename
        path.write_bytes(filename.encode())
        entries.append({"name": name, "version": version, "filename": filename,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "source": "https://pypi.org/project/example-pkg/"})
    with pytest.raises(ValueError, match="duplicate_dependency_package"):
        deps.validate_manifest({"schema_version": 1, "dependencies": entries}, tmp_path)


def test_dependency_install_creates_separate_venvs_without_global_pip(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    manifest = tmp_path / "deps.json"
    manifest.write_text(json.dumps({"schema_version": 1, "dependencies": []}), encoding="utf-8")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    root = tmp_path / "connectors"
    commands = []
    def fake_run(cmd, **kwargs):
        commands.append((cmd, kwargs))
        if "venv" in cmd:
            venv_path = Path(cmd[-1])
            (venv_path / "bin").mkdir(parents=True)
            executable = venv_path / "bin" / "python"
            executable.write_text("fake interpreter")
            executable.chmod(0o755)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    a = deps.install_offline("connector-a", manifest, wheelhouse, sys.executable, root, run=fake_run)
    b = deps.install_offline("connector-b", manifest, wheelhouse, sys.executable, root, run=fake_run)
    assert a["venv"] != b["venv"]
    assert Path(a["venv"]).is_dir() and Path(b["venv"]).is_dir()
    assert a["system_python_modified"] == b["system_python_modified"] == "false"
    assert len(commands) == 4
    create_commands = [cmd for cmd, _ in commands if "venv" in cmd]
    pip_commands = [cmd for cmd, _ in commands if "pip" in cmd]
    assert len(create_commands) == len(pip_commands) == 2
    assert all(cmd[0] == sys.executable and cmd[1:3] == ["-I", "-m"] for cmd in create_commands)
    for cmd, kwargs in [(cmd, kw) for cmd, kw in commands if "pip" in cmd]:
        assert "--no-index" in cmd and "--require-hashes" in cmd and "--no-deps" in cmd
        assert kwargs["check"] is False and kwargs["timeout"] == 300
        assert cmd[0] != sys.executable


def test_dependency_install_failure_removes_only_new_venv_and_manifest(tmp_path):
    import sys
    from types import SimpleNamespace
    manifest = tmp_path / "deps.json"
    manifest.write_text(json.dumps({"schema_version": 1, "dependencies": []}), encoding="utf-8")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    root = tmp_path / "connectors"
    def fake_run(cmd, **kwargs):
        if "venv" in cmd:
            venv_path = Path(cmd[-1])
            (venv_path / "bin").mkdir(parents=True)
            executable = venv_path / "bin" / "python"
            executable.write_text("fake interpreter")
            executable.chmod(0o755)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="failed")
    with pytest.raises(RuntimeError, match="offline_dependency_install_failed"):
        deps.install_offline("connector-fail", manifest, wheelhouse, sys.executable, root, run=fake_run)
    assert not (root / "connector-fail" / "venv").exists()
    assert not (root / "connector-fail" / "requirements-hashed.txt").exists()


def test_dependency_venv_creation_failure_cleans_partial_state(tmp_path):
    import sys
    from types import SimpleNamespace
    manifest = tmp_path / "deps.json"
    manifest.write_text(json.dumps({"schema_version": 1, "dependencies": []}), encoding="utf-8")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    root = tmp_path / "connectors"
    def fake_run(cmd, **kwargs):
        if "venv" in cmd:
            partial = Path(cmd[-1])
            partial.mkdir(parents=True)
            return SimpleNamespace(returncode=1, stdout="", stderr="venv failed")
        raise AssertionError("pip must not run when venv creation fails")
    with pytest.raises(RuntimeError, match="connector_venv_creation_failed"):
        deps.install_offline("connector-fail", manifest, wheelhouse, sys.executable, root, run=fake_run)
    assert not (root / "connector-fail" / "venv").exists()
    assert not (root / "connector-fail" / "requirements-hashed.txt").exists()
