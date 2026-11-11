from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_nginx_proxies_verify_backend_using_certificate_dns_san():
    nginx_config = (ROOT / "packaging/solarminer-gateway-nginx.conf").read_text()
    tailscale_script = (ROOT / "packaging/solarminer-tailscale-cert").read_text()
    tailscale_service = (ROOT / "packaging/solarminer-tailscale-cert.service").read_text()
    assert "ProtectSystem=strict" in tailscale_service
    assert "ReadWritePaths=/etc/solarminer /etc/nginx/conf.d /var/log /run" in tailscale_service
    assert "systemctl start nginx.service" in tailscale_script
    assert 'nginx_diagnostic=$(nginx -t 2>&1)' in tailscale_script
    assert "printf '%s\\n' \"$nginx_diagnostic\" | tee -a \"$LOG\"" in tailscale_script
    postinst = (ROOT / "packaging/postinst").read_text()
    usb_installer = (ROOT / "packaging/install-from-usb.sh").read_text()

    # postinst provisions DNS:localhost in the backend certificate. Nginx
    # must verify that DNS identity, rather than treating the upstream IP as a
    # DNS name when it validates the TLS certificate.
    assert 'DNS:localhost' in postinst
    # The API, static PWA, Owner console, terminal and long-running Deye
    # history import each use a TLS-verified backend location.
    assert nginx_config.count("proxy_ssl_name localhost;") == 5
    assert "location = /api/v1/integrations/deye-cloud/history/import" in nginx_config
    assert "proxy_read_timeout 600s;" in nginx_config
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
    # A clean USB install must verify the same HTTPS MagicDNS/SNI route used by
    # the PWA after the local Gateway health check has passed.
    assert 'systemctl start solarminer-tailscale-cert.service' in usb_installer
    assert '--resolve "$TAILSCALE_DNS:443:127.0.0.1"' in usb_installer
    assert '"https://$TAILSCALE_DNS/api/v1/health"' in usb_installer
    assert 'payload.get("status") != "ok"' in usb_installer
    assert 'if ! systemctl start solarminer-tailscale-cert.service;' in usb_installer
    assert 'AVISO: o teste HTTPS Tailscale ainda falha' in usb_installer
    assert 'ERRO TLS/Nginx (curl):' in usb_installer
    assert '|| fail "O HTTPS do endereço Tailscale não passou' not in usb_installer
    cert_timer = (ROOT / "packaging/solarminer-tailscale-cert.timer").read_text()
    assert "OnBootSec=30s" in cert_timer
    assert "OnUnitInactiveSec=2min" in cert_timer
