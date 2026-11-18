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


def test_intelligence_service_waits_for_bootstrap_credentials():
    service = (Path(__file__).parents[1] / "packaging" / "solarminer-intelligence.service").read_text(encoding="utf-8")
    assert "ConditionPathExists=/etc/solarminer/intelligence-agent.env" in service
    assert "EnvironmentFile=/etc/solarminer/intelligence-agent.env" in service


def test_bootstrap_service_can_install_system_runtime_after_security_checks():
    root = Path(__file__).parents[1]
    service = (root / "packaging" / "solarminer-intelligence-bootstrap.service").read_text(encoding="utf-8")
    postinst = (root / "packaging" / "postinst").read_text(encoding="utf-8")
    timer_enable = "systemctl enable --now solarminer-intelligence-bootstrap.timer"
    for forbidden in ("PrivateTmp=", "ProtectSystem=", "ProtectHome=", "ReadWritePaths="):
        assert forbidden not in service
    assert "NoNewPrivileges=true" in service
    assert "Tailscale and TLS" in service
    assert "install -d -o root -g root -m 0755 /opt/solarminer/intelligence" in postinst
    assert "install -d -o root -g root -m 0750 /var/lib/solarminer/intelligence" in postinst
    assert postinst.index("/opt/solarminer/intelligence") < postinst.index(timer_enable)
    assert postinst.index("/var/lib/solarminer/intelligence") < postinst.index(timer_enable)
    assert postinst.index("mountpoint -q /var/lib/solarminer") < postinst.index("/var/lib/solarminer/intelligence")


def test_bootstrap_uses_packaged_zstd_instead_of_mutating_apt_sources():
    root = Path(__file__).parents[1]
    control = (root / "packaging" / "control").read_text(encoding="utf-8")
    bootstrap = (root / "packaging" / "solarminer-intelligence-bootstrap").read_text(encoding="utf-8")
    assert "zstd" in next(line for line in control.splitlines() if line.startswith("Depends:"))
    assert "command -v zstd" in bootstrap
    assert "apt-get update" not in bootstrap
    assert "apt-get install" not in bootstrap
