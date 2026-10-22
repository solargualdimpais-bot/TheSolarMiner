from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_nginx_proxies_verify_backend_using_certificate_dns_san():
    nginx_config = (ROOT / "packaging/solarminer-gateway-nginx.conf").read_text()
    tailscale_script = (ROOT / "packaging/solarminer-tailscale-cert").read_text()
    postinst = (ROOT / "packaging/postinst").read_text()

    # postinst provisions DNS:localhost in the backend certificate. Nginx
    # must verify that DNS identity, rather than treating the upstream IP as a
    # DNS name when it validates the TLS certificate.
    assert 'DNS:localhost' in postinst
    assert nginx_config.count("proxy_ssl_name localhost;") == 3
    assert "proxy_ssl_name 127.0.0.1;" not in nginx_config
    assert "proxy_ssl_name localhost;" in tailscale_script
    assert "proxy_ssl_name 127.0.0.1;" not in tailscale_script

    # A Gateway upgraded from the old package must rewrite its existing
    # Tailscale vhost even when the public certificate is still valid.
    assert 'if [ "$certificate_changed" -eq 0 ] && cmp -s "$work/nginx.conf" "$CONFIG";' in tailscale_script
    assert 'if [ "$cert_valid" -ne 1 ]; then' in tailscale_script
    assert "systemctl enable --now solarminer-tailscale-cert.timer" in postinst
    assert "systemctl disable --now solarminer-public-tls-renew.timer" in postinst
    assert "systemctl enable --now solarminer-public-tls-renew.timer" not in postinst
