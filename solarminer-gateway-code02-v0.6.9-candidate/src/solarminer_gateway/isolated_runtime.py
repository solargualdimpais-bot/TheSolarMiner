"""Systemd sandbox policy helpers for connector workers.

A Python venv is dependency isolation, not a security boundary. This module
renders restrictive per-connector service units and refuses to claim active
isolation when systemd/cgroup enforcement is unavailable. It does not execute
untrusted code in-process or grant access to the Gateway SQLite database.
"""
from __future__ import annotations

import ipaddress
import re
import hashlib
from pathlib import Path

CONNECTOR_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


def validate_connector_id(connector_id: str) -> str:
    if not isinstance(connector_id, str) or not CONNECTOR_ID_RE.fullmatch(connector_id):
        raise ValueError("invalid_connector_id")
    return connector_id


def render_systemd_unit(connector_id: str, executable: str, worker_args: list[str],
                        state_dir: str, allowed_target_ip: str | None = None,
                        memory_max: str = "128M", tasks_max: int = 32) -> str:
    """Render a service with explicit file/process/network boundaries.

    The caller must install this as a root-owned unit and provision a dedicated
    unprivileged account. Only one explicitly configured device IP may be
    allowed; otherwise all IP network access is denied.
    """
    connector_id = validate_connector_id(connector_id)
    executable_path = Path(executable)
    state_path = Path(state_dir)
    if not executable_path.is_absolute() or not state_path.is_absolute():
        raise ValueError("absolute_paths_required")
    if "\n" in str(executable_path) or "\n" in str(state_path) or any("\n" in a for a in worker_args):
        raise ValueError("newline_not_allowed")
    if not re.fullmatch(r"[1-9][0-9]*[KMG]", memory_max):
        raise ValueError("invalid_memory_limit")
    if isinstance(tasks_max, bool) or not isinstance(tasks_max, int) or not 1 <= tasks_max <= 256:
        raise ValueError("invalid_tasks_limit")
    account_name = "smc-" + hashlib.sha256(connector_id.encode("ascii")).hexdigest()[:16]
    network_allow = ""
    if allowed_target_ip is not None:
        ip = ipaddress.ip_address(allowed_target_ip)
        if not (ip.is_private or ip.is_link_local) or ip.is_loopback or ip.is_multicast or ip.is_unspecified:
            raise ValueError("private_device_ip_required")
        prefix = 32 if ip.version == 4 else 128
        network_allow = f"IPAddressAllow={ip}/{prefix}\n"
    args = " ".join(_systemd_quote(a) for a in worker_args)
    return f"""[Unit]
Description=SolarMiner isolated connector {connector_id}
After=network.target

[Service]
Type=exec
User={account_name}
Group={account_name}
ExecStart={_systemd_quote(str(executable_path))}{(' ' + args) if args else ''}
WorkingDirectory=/var/lib/solarminer/connectors/{connector_id}
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
RestrictNamespaces=yes
RestrictRealtime=yes
MemoryDenyWriteExecute=yes
SystemCallArchitectures=native
SystemCallFilter=@system-service
SystemCallFilter=~@privileged @resources
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
IPAddressDeny=any
{network_allow}ReadWritePaths={state_path}
MemoryMax={memory_max}
TasksMax={tasks_max}
CPUQuota=50%
Restart=no
TimeoutStartSec=15
TimeoutStopSec=5
KillMode=control-group

"""


def _systemd_quote(value: str) -> str:
    # systemd ExecStart uses its own quoting rules; reject rather than attempt
    # complex shell parsing. No shell is involved in ExecStart.
    if not value or any(ch in value for ch in "\n\r\x00"):
        raise ValueError("invalid_exec_argument")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def isolation_requirements() -> dict[str, object]:
    return {
        "requires_systemd_system_manager": True,
        "requires_cgroup_v2_or_supported_systemd_resource_control": True,
        "requires_root_owned_unit_and_dedicated_unprivileged_account": True,
        "python_venv_is_security_boundary": False,
        "database_access": "not granted; only explicit state path writable",
        "network_default": "denied; allow only configured private device IP",
        "status_without_operational_verification": "POLICY_RENDERED_NOT_OPERATIONALLY_VALIDATED",
    }
