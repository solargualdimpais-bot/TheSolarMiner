#!/bin/sh
set -eu

[ "$(id -u)" -eq 0 ] || { echo "Executa este instalador como root." >&2; exit 1; }
[ -r /etc/os-release ] || { echo "Não foi possível identificar Debian." >&2; exit 1; }
. /etc/os-release
[ "${ID:-}" = debian ] && [ "${VERSION_CODENAME:-}" = trixie ] || {
  echo "A instalação automática do Tailscale está preparada para Debian 13 Trixie AMD64." >&2
  exit 1
}
[ "$(dpkg --print-architecture)" = amd64 ] || { echo "O Gateway SolarMiner requer AMD64." >&2; exit 1; }

if ! command -v curl >/dev/null 2>&1 || ! command -v gpg >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl gnupg
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 \
  https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg \
  -o "$tmp/tailscale-archive-keyring.gpg"
curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 \
  https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list \
  -o "$tmp/tailscale.list"
[ -s "$tmp/tailscale-archive-keyring.gpg" ] || { echo "A chave oficial do repositório Tailscale está vazia." >&2; exit 1; }
grep -Fq 'https://pkgs.tailscale.com/stable/debian trixie main' "$tmp/tailscale.list" || {
  echo "A origem Tailscale não corresponde ao repositório oficial Debian Trixie." >&2; exit 1;
}
gpg --batch --show-keys "$tmp/tailscale-archive-keyring.gpg" >/dev/null 2>&1 || {
  echo "A chave oficial do repositório Tailscale não é válida." >&2; exit 1;
}
install -d -o root -g root -m 0755 /usr/share/keyrings /etc/apt/sources.list.d
install -o root -g root -m 0644 "$tmp/tailscale-archive-keyring.gpg" /usr/share/keyrings/tailscale-archive-keyring.gpg
install -o root -g root -m 0644 "$tmp/tailscale.list" /etc/apt/sources.list.d/tailscale.list
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y tailscale
systemctl enable --now tailscaled.service
