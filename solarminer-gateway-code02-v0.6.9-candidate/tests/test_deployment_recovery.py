from __future__ import annotations
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from solarminer_gateway.deployment_recovery import DeploymentReleaseSwitch, DeploymentRecoveryError


def release(root: Path, name: str, marker: str) -> Path:
    path = root / "releases" / name
    path.mkdir(parents=True)
    (path / "VERSION").write_text(marker)
    return path


def test_switch_commits_only_after_health_check_and_rolls_back_on_failure(tmp_path: Path):
    root = tmp_path / "deployment"
    release(root, "v1", "1")
    release(root, "v2", "2")
    manager = DeploymentReleaseSwitch(root)
    (root / "current").symlink_to("releases/v1")
    with pytest.raises(DeploymentRecoveryError, match="rolled_back"):
        manager.switch("releases/v2", health_check=lambda _path: False)
    assert os.readlink(root / "current") == "releases/v1"


def test_kill9_after_atomic_symlink_switch_is_recovered_to_previous_release(tmp_path: Path):
    root = tmp_path / "deployment"
    release(root, "v1", "1")
    release(root, "v2", "2")
    (root / "current").symlink_to("releases/v1")
    code = r'''import os,signal,sys
from pathlib import Path
from solarminer_gateway.deployment_recovery import DeploymentReleaseSwitch
root=Path(sys.argv[1])
def fault(stage):
    if stage == "after_switch": os.kill(os.getpid(), signal.SIGKILL)
DeploymentReleaseSwitch(root).switch("releases/v2", fault_hook=fault)
'''
    env = dict(os.environ)
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    child = subprocess.run([sys.executable, "-c", code, str(root)], env=env, timeout=10, check=False)
    assert child.returncode == -signal.SIGKILL
    assert os.readlink(root / "current") == "releases/v2"
    result = DeploymentReleaseSwitch(root).recover_pending()
    assert result["status"] == "recovered"
    assert result["actions"][0]["action"] == "ROLLBACK_POINTER_RESTORED"
    assert os.readlink(root / "current") == "releases/v1"


def test_kill9_before_switch_cleans_pending_pointer_without_changing_active(tmp_path: Path):
    root = tmp_path / "deployment"
    release(root, "v1", "1")
    release(root, "v2", "2")
    (root / "current").symlink_to("releases/v1")
    code = r'''import os,signal,sys
from pathlib import Path
from solarminer_gateway.deployment_recovery import DeploymentReleaseSwitch
root=Path(sys.argv[1])
def fault(stage):
    if stage == "before_switch": os.kill(os.getpid(), signal.SIGKILL)
DeploymentReleaseSwitch(root).switch("releases/v2", fault_hook=fault)
'''
    env = dict(os.environ)
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    child = subprocess.run([sys.executable, "-c", code, str(root)], env=env, timeout=10, check=False)
    assert child.returncode == -signal.SIGKILL
    assert os.readlink(root / "current") == "releases/v1"
    result = DeploymentReleaseSwitch(root).recover_pending()
    assert result["status"] == "recovered"
    assert result["actions"][0]["action"] == "ROLLBACK_NO_SWITCH_NEEDED"
    assert os.readlink(root / "current") == "releases/v1"
    assert not list(root.glob(".current.pending-*"))


def test_non_symlink_active_path_is_never_overwritten(tmp_path: Path):
    root = tmp_path / "deployment"
    release(root, "v1", "1")
    release(root, "v2", "2")
    (root / "current").write_text("do-not-overwrite")
    manager = DeploymentReleaseSwitch(root)
    with pytest.raises(DeploymentRecoveryError, match="not_symlink"):
        manager.switch("releases/v2")
    assert (root / "current").read_text() == "do-not-overwrite"


def test_corrupt_complete_journal_record_blocks_recovery(tmp_path: Path):
    root = tmp_path / "deployment"
    release(root, "v1", "1")
    (root / "current").symlink_to("releases/v1")
    (root / "deployment-journal.jsonl").write_text('{"event":"PREPARED"}\n{not-json}\n')
    manager = DeploymentReleaseSwitch(root)
    with pytest.raises(DeploymentRecoveryError, match="journal_corrupt"):
        manager.recover_pending()
