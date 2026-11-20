from pathlib import Path


def test_postinst_creates_intelligence_group_before_using_it():
    postinst = (Path(__file__).parents[1] / "packaging" / "postinst").read_text(encoding="utf-8")
    create_group = "if ! getent group solarminer-intelligence >/dev/null 2>&1; then addgroup --system solarminer-intelligence; fi"
    create_user = "if ! getent passwd solarminer-intelligence >/dev/null 2>&1; then adduser --system --ingroup solarminer-intelligence"
    use_group = "install -d -o root -g solarminer-intelligence -m 0750 /var/lib/solarminer-intelligence"

    assert create_group in postinst
    assert create_user in postinst
    assert postinst.index(create_group) < postinst.index(use_group)
    assert postinst.index(create_user) < postinst.index(use_group)


def test_usb_repair_suppresses_gateway_restart_until_new_release_pointer_is_active():
    root = Path(__file__).parents[1]
    postinst = (root / "packaging" / "postinst").read_text(encoding="utf-8")
    repair = (root / "packaging" / "repair-existing-from-usb.sh").read_text(encoding="utf-8")
    marker = "/run/solarminer/usb-repair-in-progress"

    assert marker in postinst
    assert 'RUN_DIR=/run/solarminer' in repair
    assert 'REPAIR_MARKER="$RUN_DIR/usb-repair-in-progress"' in repair
    assert postinst.index("initialize_installed_manifest") < postinst.index(marker)
    assert postinst.index(marker) < postinst.index("systemctl restart solarminer-gateway.service")
    assert repair.index(": > \"$REPAIR_MARKER\"") < repair.index("apt-get install -y \"$PACKAGE\"")
    pointer_switch = repair.index("mv -Tf /opt/solarminer/.current-usb-new \"$CURRENT\"")
    gateway_start = repair.index("systemctl start solarminer-gateway.service || fail", pointer_switch)
    marker_cleanup = repair.rindex("rm -f \"$REPAIR_MARKER\"")
    assert pointer_switch < gateway_start < marker_cleanup


def test_agent_writable_paths_exist_before_systemd_mount_namespace():
    root = Path(__file__).parents[1]
    postinst = (root / "packaging" / "postinst").read_text(encoding="utf-8")
    service = (root / "packaging" / "solarminer-intelligence.service").read_text(encoding="utf-8")
    work = "install -d -o solarminer-intelligence -g solarminer-intelligence -m 0750 /var/lib/solarminer-intelligence/work"
    home = "install -d -o solarminer-intelligence -g solarminer-intelligence -m 0700 /var/lib/solarminer-intelligence/home"
    timer_enable = "systemctl enable --now solarminer-intelligence-bootstrap.timer"

    assert work in postinst and home in postinst
    assert postinst.index(work) < postinst.index(timer_enable)
    assert postinst.index(home) < postinst.index(timer_enable)
    assert "ReadWritePaths=/var/lib/solarminer-intelligence/work /var/lib/solarminer-intelligence/home" in service
    assert "ConditionPathExists=/var/lib/solarminer-intelligence/agent-ready" in service
    assert "ConditionPathIsDirectory=/var/lib/solarminer-intelligence/work" in service
    assert "ConditionPathIsDirectory=/var/lib/solarminer-intelligence/home" in service


def test_intelligence_service_waits_for_bootstrap_credentials():
    service = (Path(__file__).parents[1] / "packaging" / "solarminer-intelligence.service").read_text(encoding="utf-8")
    assert "ConditionPathExists=/etc/solarminer/intelligence-agent.env" in service
    assert "EnvironmentFile=/etc/solarminer/intelligence-agent.env" in service
    bootstrap = (Path(__file__).parents[1] / "packaging" / "solarminer-intelligence-bootstrap").read_text(encoding="utf-8")
    ready = 'install -o root -g root -m 0644 /dev/null "$READY_FILE"'
    start = "systemctl restart solarminer-intelligence.service"
    assert ready in bootstrap
    assert bootstrap.index(ready) < bootstrap.index(start)
    assert 'rm -f "$READY_FILE"' in bootstrap


def test_bootstrap_service_can_install_system_runtime_after_security_checks():
    root = Path(__file__).parents[1]
    service = (root / "packaging" / "solarminer-intelligence-bootstrap.service").read_text(encoding="utf-8")
    postinst = (root / "packaging" / "postinst").read_text(encoding="utf-8")
    timer_enable = "systemctl enable --now solarminer-intelligence-bootstrap.timer"
    for forbidden in ("PrivateTmp=", "ProtectSystem=", "ProtectHome=", "ReadWritePaths="):
        assert forbidden not in service
    assert "NoNewPrivileges=true" in service
    assert "Environment=HOME=/root" in service
    assert "TimeoutStartSec=2h" in service
    assert "Tailscale and TLS" in service
    assert "install -d -o root -g root -m 0755 /opt/solarminer/intelligence" in postinst
    assert "install -d -o root -g root -m 0750 /var/lib/solarminer/intelligence" in postinst
    assert postinst.index("/opt/solarminer/intelligence") < postinst.index(timer_enable)
    assert postinst.index("/var/lib/solarminer/intelligence") < postinst.index(timer_enable)
    assert postinst.index("mountpoint -q /var/lib/solarminer") < postinst.index("/var/lib/solarminer/intelligence")


def test_bootstrap_ollama_checks_have_home_and_smoke_test_accepts_qwen_thinking_model():
    root = Path(__file__).parents[1]
    bootstrap = (root / "packaging" / "solarminer-intelligence-bootstrap").read_text(encoding="utf-8")
    assert 'export HOME="${HOME:-/root}"' in bootstrap
    assert "http://127.0.0.1:11434/api/chat" in bootstrap
    assert '\\"think\\":false' in bootstrap
    assert '\\"num_predict\\":32' in bootstrap
    assert "message.get(\"content\")" in bootstrap
    assert "OLLAMA_SMOKE_EMPTY_ASSISTANT_CONTENT" in bootstrap
    assert "OLLAMA_SMOKE_GENERATION_NOT_COMPLETE" in bootstrap
    assert "api/generate" not in bootstrap


def test_bootstrap_uses_packaged_zstd_instead_of_mutating_apt_sources():
    root = Path(__file__).parents[1]
    control = (root / "packaging" / "control").read_text(encoding="utf-8")
    bootstrap = (root / "packaging" / "solarminer-intelligence-bootstrap").read_text(encoding="utf-8")
    assert "zstd" in next(line for line in control.splitlines() if line.startswith("Depends:"))
    assert "command -v zstd" in bootstrap
    assert "apt-get update" not in bootstrap
    assert "apt-get install" not in bootstrap


def test_online_update_unit_cannot_be_killed_before_its_rollback_window():
    root = Path(__file__).parents[1] / "packaging"
    service = (root / "solarminer-update-apply@.service").read_text(encoding="utf-8")
    recovery = (root / "solarminer-recovery.service").read_text(encoding="utf-8")
    assert "TimeoutStartSec=20min" in service
    assert "TimeoutStartSec=5min" in recovery


def test_gateway_orders_privileged_component_verifier_socket_before_start():
    service = (Path(__file__).parents[1] / "packaging" / "solarminer-gateway.service").read_text(encoding="utf-8")
    assert "After=network.target solarminer-recovery.service solarminer-intelligence-bootstrap-broker.socket" in service
    assert "Wants=solarminer-intelligence-bootstrap-broker.socket" in service


def test_usb_release_bundles_the_previous_gateway_release_for_rollback():
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "gateway-release.yml").read_text(encoding="utf-8")
    rollback_lists = [line for line in workflow.splitlines() if "for VERSION in" in line]
    assert len(rollback_lists) == 2
    assert all("0.6.271" in line for line in rollback_lists)


def test_upgrade_drains_stale_admin_terminal_sessions_before_reopening_socket():
    postinst = (Path(__file__).parents[1] / "packaging" / "postinst").read_text(encoding="utf-8")
    stop_socket = postinst.index("systemctl stop solarminer-admin-terminal.socket")
    stop_instances = postinst.index("systemctl stop 'solarminer-admin-terminal@*.service'")
    reset_instances = postinst.index("systemctl reset-failed 'solarminer-admin-terminal@*.service'")
    reopen_socket = postinst.index("systemctl enable --now solarminer-admin-terminal.socket")
    assert stop_socket < stop_instances < reset_instances < reopen_socket


def test_bootstrap_publishes_download_progress_for_owner_console():
    bootstrap = (Path(__file__).parents[1] / "packaging" / "solarminer-intelligence-bootstrap").read_text(encoding="utf-8")
    for expected in ("/api/pull", '"percent":percent', '"downloaded_bytes":downloaded',
                     '"total_bytes":total', '"stage":"downloading_model"',
                     'write_status failed "$CURRENT_STAGE"'):
        assert expected in bootstrap


def test_intelligence_bootstrap_can_retry_partial_install_and_apply_pinned_component_updates():
    root = Path(__file__).parents[1]
    bootstrap = (root / "packaging" / "solarminer-intelligence-bootstrap").read_text(encoding="utf-8")
    assert '[ ! -e "$STATE" ] ||' not in bootstrap
    assert '!= "v$NODE_VERSION"' in bootstrap
    assert 'OPENCLAUDE_EXISTING' in bootstrap
    assert 'systemctl restart solarminer-intelligence.service' in bootstrap
    assert 'systemctl start --no-block solarminer-intelligence-bootstrap.service' not in bootstrap
    service = (root / "packaging" / "solarminer-intelligence-bootstrap.service").read_text(encoding="utf-8")
    assert "TimeoutStartSec=2h" in service


def test_openclaude_ollama_sdk_pin_matches_real_sdk_release_contract_test():
    root = Path(__file__).parents[1]
    bootstrap = (root / "packaging" / "solarminer-intelligence-bootstrap").read_text(encoding="utf-8")
    workflow = (root.parent / ".github" / "workflows" / "gateway-release.yml").read_text(encoding="utf-8")
    contract_test = root / "tools" / "solarminer_intelligence_mcp" / "openclaude-ollama-contract.mjs"

    assert "OPENCLAUDE_VERSION=0.36.0" in bootstrap
    assert "@twigpine/openclaude@0.36.0" in workflow
    assert "patch-openclaude-sdk-errors.mjs" in bootstrap
    assert "error_message" in (root / "src" / "solarminer_gateway" / "app.py").read_text(encoding="utf-8")
    assert "LogsDirectory=solarminer-intelligence" in (root / "packaging" / "solarminer-intelligence.service").read_text(encoding="utf-8")
    assert contract_test.is_file()
    assert "think" in contract_test.read_text(encoding="utf-8")


def test_gateway_release_version_is_consistent_across_package_entrypoints():
    root = Path(__file__).parents[1]
    assert "Version: 0.6.275" in (root / "packaging" / "control").read_text(encoding="utf-8")
    assert 'PACKAGE_VERSION = "0.6.275"' in (root / "src" / "solarminer_gateway" / "app.py").read_text(encoding="utf-8")
    assert "TARGET_VERSION=0.6.275" in (root / "packaging" / "repair-existing-from-usb.sh").read_text(encoding="utf-8")
