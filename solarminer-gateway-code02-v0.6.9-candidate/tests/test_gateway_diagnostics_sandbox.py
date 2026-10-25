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
