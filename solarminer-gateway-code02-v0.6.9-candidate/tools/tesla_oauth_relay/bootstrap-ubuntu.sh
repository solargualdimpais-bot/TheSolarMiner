#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this bootstrap with sudo or as root." >&2
  exit 1
fi
if [[ $# -ne 2 ]]; then
  echo "Usage: sudo bash bootstrap-ubuntu.sh <public-domain> <certificate-email>" >&2
  exit 2
fi

# The release workflow publishes the source tree under this stable repository path.
BASE_URL=${SOLARMINER_RELAY_SOURCE_URL:-https://raw.githubusercontent.com/solargualdimpais-bot/TheSolarMiner/main/solarminer-gateway-code02-v0.6.9-candidate/tools/tesla_oauth_relay}
DOWNLOAD_DIR=$(mktemp -d /tmp/solarminer-tesla-relay.XXXXXX)
trap 'rm -rf "$DOWNLOAD_DIR"' EXIT HUP INT TERM
for name in relay.py run_relay.py requirements.txt solarminer-tesla-relay.service install-ubuntu.sh; do
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
    "$BASE_URL/$name" --output "$DOWNLOAD_DIR/$name"
done

# The installer re-executes with this directory as its source. Secrets are generated only after TLS setup.
bash "$DOWNLOAD_DIR/install-ubuntu.sh" "$1" "$2"
