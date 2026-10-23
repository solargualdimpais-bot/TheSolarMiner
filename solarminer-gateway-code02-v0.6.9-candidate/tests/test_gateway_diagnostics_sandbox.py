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
