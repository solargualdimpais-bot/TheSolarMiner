from pathlib import Path


def test_restricted_update_broker_allows_ip_sockets_for_nginx_validation():
    service = Path(__file__).parents[1] / "packaging" / "solarminer-update-broker@.service"
    contents = service.read_text(encoding="utf-8")
    families = next(
        line.partition("=")[2].split()
        for line in contents.splitlines()
        if line.startswith("RestrictAddressFamilies=")
    )

    assert set(families) == {"AF_UNIX", "AF_INET", "AF_INET6"}


def test_owner_console_includes_bounded_nginx_proxy_error_tail():
    root = Path(__file__).parents[1]
    broker = (root / "src" / "solarminer_gateway" / "update_broker.py").read_text(encoding="utf-8")
    service = (root / "packaging" / "solarminer-update-broker@.service").read_text(encoding="utf-8")

    assert 'NGINX_ERROR_LOG = "/var/log/nginx/error.log"' in broker
    assert "NGINX_ERROR_LOG_MAX_BYTES = 8_000" in broker
    assert "def _read_fixed_root_log(path: str, max_bytes: int)" in broker
    assert "not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0" in broker
    assert 'logs += "\\n\\n--- Recent Nginx proxy errors ---\\n" + nginx_errors' in broker
    assert "ReadWritePaths=/opt/solarminer /var/lib/solarminer /var/log/nginx /run" in service


def test_fresh_usb_installer_reuses_data_volume_and_classifies_owner_without_recreating_it():
    root = Path(__file__).parents[1]
    installer = (root / "packaging" / "install-from-usb.sh").read_text(encoding="utf-8")
    provisioner = (root / "packaging" / "provision-data-volume.py").read_text(encoding="utf-8")
    resetter = (root / "packaging" / "reset-data-volume.py").read_text(encoding="utf-8")
    assert 'LABEL = "SOLARMINER_DATA"' in provisioner
    assert 'if filesystem.lower() == "ext4"' in provisioner
    assert '["wipefs", "--all", partition]' in provisioner
    assert 'Owner não identificável em {partition}' in provisioner
    assert 'marker = Path("/var/lib/solarminer/initialized.marker")' in installer
    assert 'print("active")' in installer
    assert 'ESTADO DO OWNER: foi encontrado um Owner ativo na base de dados persistente.' in installer
    assert 'Palavra-passe de um Owner registado (entrada visível):' in installer
    assert 'stored_hash.strip()' in installer
    assert 'if not owners:' in installer
    assert 'print("reset_data")' in installer
    assert 'return input().strip() == "APAGAR DADOS"' in installer
    assert 'Palavra-passe de um Owner registado (entrada visível)' in installer
    assert 'OWNER_STATE=fresh' in installer
    assert 'LABEL = "SOLARMINER_DATA"' in resetter
    assert 'MARKER.read_text(encoding="ascii").strip() != old_uuid' in resetter
    assert 'mkfs.ext4", "-F", "-L", LABEL' in resetter
    assert '"TYPE", str(source_path)' in resetter
    assert 'OWNER_STATE=$(python3' in installer
    assert 'recovery)' not in installer
    assert 'There is no active Owner with a verifiable password hash' in installer
    assert 'solarminer-gateway owner-password' in installer
