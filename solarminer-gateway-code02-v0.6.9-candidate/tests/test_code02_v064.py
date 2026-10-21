from __future__ import annotations
import json, os, zipfile
from pathlib import Path
import pytest
from solarminer_gateway.connector_worker import execute
from fastapi.testclient import TestClient
from solarminer_gateway import app as gateway
from solarminer_gateway import worker_ipc
from solarminer_gateway.update_transaction import AtomicReleaseStore
from test_code02_v063 import signed_zip


def test_worker_tcp_probe_is_allowlisted_and_reports_no_payload(monkeypatch):
    class FakeSocket:
        def __enter__(self): return self
        def __exit__(self,*args): return False
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: FakeSocket())
    result=execute({"protocol_version":worker_ipc.PROTOCOL_VERSION,"request_id":"r1","operation":"tcp_probe","arguments":{"host":"192.168.1.10","port":502,"timeout":1.0}})
    assert result["reachable"] is True
    assert result["payload_sent"] is False
    assert result["hardware_commands_sent"] is False
    assert result["application_protocol_verified"] is False


def test_worker_tcp_probe_denies_public_loopback_and_invalid_ports():
    for host in ("8.8.8.8","127.0.0.1","224.0.0.1"):
        with pytest.raises(ValueError):
            execute({"protocol_version":worker_ipc.PROTOCOL_VERSION,"request_id":"r2","operation":"tcp_probe","arguments":{"host":host,"port":502,"timeout":1.0}})
    with pytest.raises(ValueError):
        execute({"protocol_version":worker_ipc.PROTOCOL_VERSION,"request_id":"r3","operation":"tcp_probe","arguments":{"host":"192.168.1.10","port":70000,"timeout":1.0}})


def test_update_recovery_rolls_back_pointer_after_simulated_process_restart(tmp_path):
    store=AtomicReleaseStore(tmp_path/'store')
    first,m1=signed_zip(tmp_path,version='1.0.0')
    store.activate(m1,first,lambda p:(p/'connector.py').is_file())
    previous=os.readlink(store.active_path('test-connector'))
    second,m2=signed_zip(tmp_path,version='2.0.0')
    # Stage and materialize the second release, then simulate a process dying
    # after active pointer replacement but before terminal journal event.
    store.activate(m2,second,lambda p:(p/'connector.py').is_file())
    active=store.active_path('test-connector')
    # Restore the old pointer then model a crash-interrupted activation journal.
    restore=store.root/'.manual-restore'; os.symlink(previous,restore); os.replace(restore,active)
    store._event('PREPARED',connector_id='test-connector',version='3.0.0',artifact_sha256='0'*64,previous=previous)
    target=store.releases/'test-connector-3.0.0'; target.mkdir(); (target/'connector.py').write_text("VERSION='3.0.0'\n")
    temp=store.root/'.crash-active'; os.symlink(os.path.relpath(target,store.root),temp); os.replace(temp,active)
    # New instance models restart, independent of in-memory state.
    restarted=AtomicReleaseStore(tmp_path/'store')
    result=restarted.recover_interrupted()
    assert result['status']=='RECOVERY_COMPLETE'
    assert os.readlink(restarted.active_path('test-connector'))==previous
    assert result['database_consistency_verified'] is False
    assert result['service_health_verified'] is False


def test_update_recovery_does_not_overwrite_non_symlink_active_path(tmp_path):
    store=AtomicReleaseStore(tmp_path/'store')
    store._event('PREPARED',connector_id='test-connector',version='2.0.0',artifact_sha256='0'*64,previous=None)
    active=store.active_path('test-connector'); active.mkdir()
    result=store.recover_interrupted()
    assert result['actions'][0]['action']=='BLOCKED_NON_SYMLINK_ACTIVE'
    assert active.is_dir()


def test_gateway_serves_pwa_from_same_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway, "BOOTSTRAP_PATH", tmp_path / "bootstrap.token")
    monkeypatch.setattr(gateway, "INSTANCE_MARKER", tmp_path / "initialized.marker")
    with TestClient(gateway.app) as client:
        home=client.get("/")
        assert home.status_code == 200
        assert "The Solar Miner" in home.text
        manifest=client.get("/manifest.webmanifest")
        assert manifest.status_code == 200
        assert manifest.json()["name"] == "The Solar Miner"
        assert client.get("/app.js").status_code == 200
        auth_client = client.get("/auth-client.js")
        assert auth_client.status_code == 200
        assert "Content-Security-Policy" in auth_client.headers
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.headers["Cache-Control"] == "no-store"
