#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this installer with sudo or as root." >&2
  exit 1
fi
if [[ $# -ne 2 ]]; then
  echo "Usage: sudo bash install-ubuntu.sh <public-domain> <certificate-email>" >&2
  exit 2
fi

DOMAIN=${1,,}
EMAIL=$2
if [[ ! "$DOMAIN" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]]; then
  echo "Use a registered DNS name, not an IP address or a URL." >&2
  exit 2
fi
if [[ ! "$EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  echo "Provide a valid certificate-renewal email address." >&2
  exit 2
fi
if [[ ! -f /etc/os-release ]] || ! . /etc/os-release || [[ ${ID:-} != ubuntu ]]; then
  echo "This installer supports Ubuntu Server only." >&2
  exit 2
fi

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_DIR=/opt/solarminer-tesla-relay
CONFIG_DIR=/etc/solarminer-tesla-relay
ENV_FILE=/etc/solarminer-tesla-relay.env
KEY_FILE=/root/solarminer-tesla-relay-api-key
CERT_FILE=$CONFIG_DIR/fullchain.pem
PRIVATE_KEY_FILE=$CONFIG_DIR/privkey.pem

echo "Installing the Tesla OAuth relay for $DOMAIN."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  ca-certificates certbot curl openssl python3 python3-venv ufw

# Keep SSH reachable before enabling the host firewall. OCI must separately
# restrict TCP/22 to the administrator's current public IP.
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

if ! getent ahostsv4 "$DOMAIN" >/dev/null; then
  echo "DNS for $DOMAIN has no IPv4 address yet. Add an A record to this VM's public IPv4, wait for DNS, and rerun." >&2
  exit 3
fi

if ! id solarminer-relay >/dev/null 2>&1; then
  useradd --system --home-dir "$INSTALL_DIR" --create-home --shell /usr/sbin/nologin solarminer-relay
fi
install -d -o root -g root -m 0755 "$INSTALL_DIR"
install -d -o root -g root -m 0755 "$CONFIG_DIR"
install -d -o root -g root -m 0755 /etc/letsencrypt/renewal-hooks/deploy
install -m 0644 "$SOURCE_DIR/relay.py" "$INSTALL_DIR/relay.py"
install -m 0644 "$SOURCE_DIR/run_relay.py" "$INSTALL_DIR/run_relay.py"
install -m 0644 "$SOURCE_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --disable-pip-version-check --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --disable-pip-version-check -r "$INSTALL_DIR/requirements.txt"

certbot certonly --standalone --non-interactive --agree-tos --no-eff-email \
  --preferred-challenges http --email "$EMAIL" -d "$DOMAIN"

if [[ ! -s "$KEY_FILE" ]]; then
  openssl rand -hex 32 > "$KEY_FILE"
  chmod 0600 "$KEY_FILE"
fi
API_KEY=$(<"$KEY_FILE")
if [[ ${#API_KEY} -lt 32 || ! "$API_KEY" =~ ^[A-Fa-f0-9]+$ ]]; then
  echo "The stored relay key is invalid; refusing to start." >&2
  exit 4
fi

install -o solarminer-relay -g solarminer-relay -m 0644 "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$CERT_FILE"
install -o solarminer-relay -g solarminer-relay -m 0600 "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$PRIVATE_KEY_FILE"
cat > "$ENV_FILE" <<EOF
SOLARMINER_RELAY_API_KEY=$API_KEY
SOLARMINER_RELAY_TLS_CERT=$CERT_FILE
SOLARMINER_RELAY_TLS_KEY=$PRIVATE_KEY_FILE
EOF
chown root:root "$ENV_FILE"
chmod 0600 "$ENV_FILE"

cat > /etc/letsencrypt/renewal-hooks/deploy/solarminer-tesla-relay <<'HOOK'
#!/usr/bin/env bash
set -Eeuo pipefail
DOMAIN=$(awk -F= '/^SOLARMINER_RELAY_DOMAIN=/{print $2}' /etc/solarminer-tesla-relay.env)
install -o solarminer-relay -g solarminer-relay -m 0644 "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" /etc/solarminer-tesla-relay/fullchain.pem
install -o solarminer-relay -g solarminer-relay -m 0600 "/etc/letsencrypt/live/$DOMAIN/privkey.pem" /etc/solarminer-tesla-relay/privkey.pem
systemctl restart solarminer-tesla-relay.service
HOOK
chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/solarminer-tesla-relay
printf '\nSOLARMINER_RELAY_DOMAIN=%s\n' "$DOMAIN" >> "$ENV_FILE"
install -m 0644 "$SOURCE_DIR/solarminer-tesla-relay.service" /etc/systemd/system/solarminer-tesla-relay.service
systemctl daemon-reload
systemctl enable --now solarminer-tesla-relay.service

for attempt in $(seq 1 15); do
  if curl --silent --show-error --fail --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/health" >/dev/null; then
    break
  fi
  if [[ $attempt -eq 15 ]]; then
    echo "Relay did not pass its local HTTPS health check. Inspect: journalctl -u solarminer-tesla-relay.service" >&2
    exit 5
  fi
  sleep 2
done

echo "Relay installed and local HTTPS health check passed."
echo "Next: in SolarMiner Owner > Equipamentos > Tesla Fleet, enter https://$DOMAIN and the key stored in $KEY_FILE, then choose Guardar e testar relay."
echo "The key is shown only by this file; do not send it in chat or place it in Tesla Developer."
echo "OCI network rules must allow inbound TCP 443 and TCP 80 from the Internet; keep TCP 22 restricted to your administrator IP."
