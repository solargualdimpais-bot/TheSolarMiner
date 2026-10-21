#!/bin/sh
set -eu

fail() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "Executa este instalador como root; não uses sudo."
command -v dpkg >/dev/null 2>&1 || fail "dpkg não está instalado."
command -v dpkg-deb >/dev/null 2>&1 || fail "dpkg-deb não está instalado."
command -v apt-get >/dev/null 2>&1 || fail "apt-get não está disponível."
[ "$(dpkg --print-architecture)" = "amd64" ] || fail "Arquitetura incompatível: este pacote é apenas amd64."

if [ -r /etc/os-release ]; then
  . /etc/os-release
else
  fail "Não foi possível identificar o sistema operativo."
fi
[ "${ID:-}" = "debian" ] || fail "Este instalador exige Debian."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' \
  || fail "O Gateway exige Python 3.11 ou superior (Debian 12 ou posterior)."

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEB=${SOLARMINER_DEB:-}
if [ -z "$DEB" ]; then
  set -- "$HERE"/solarminer-gateway_*_amd64.deb
  [ -f "$1" ] || fail "Não encontrei solarminer-gateway_*_amd64.deb na pen."
  [ "$#" -eq 1 ] || fail "A pen contém mais do que um pacote; define SOLARMINER_DEB."
  DEB=$1
fi
[ -f "$DEB" ] || fail "Pacote Debian não encontrado: $DEB"
[ "$(dpkg-deb -f "$DEB" Architecture)" = "amd64" ] || fail "O pacote não é amd64."

printf 'URL HTTPS do repositório GitHub autorizado: '
IFS= read -r REPOSITORY_URL || fail "Não foi lido o URL."
CANONICAL_URL=$(python3 - "$REPOSITORY_URL" <<'PY'
import re, sys
from urllib.parse import urlsplit
value = sys.argv[1].strip()
try:
    u = urlsplit(value)
    port = u.port
except ValueError:
    raise SystemExit(2)
if (u.scheme != "https" or u.hostname != "github.com" or port is not None
        or u.username or u.password or u.query or u.fragment):
    raise SystemExit(2)
parts = u.path.strip("/").split("/")
if len(parts) != 2 or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", parts[0]) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", parts[1]):
    raise SystemExit(2)
print("https://github.com/" + parts[0].lower() + "/" + parts[1].lower())
PY
) || fail "O URL deve ser a raiz https://github.com/owner/repository."

KEY_SOURCE="$HERE/release-pubkey.pem"
[ -s "$KEY_SOURCE" ] || fail "Falta release-pubkey.pem na pen. Usa apenas a chave pública de release obtida por uma origem de confiança."
printf 'SHA-256 esperado do ficheiro da chave pública (obtido por canal independente): '
IFS= read -r EXPECTED_KEY_SHA256 || fail "Não foi lida a impressão digital."
case "$EXPECTED_KEY_SHA256" in
  *[!0-9a-fA-F]*|'') fail "A impressão digital deve conter 64 caracteres hexadecimais." ;;
esac
[ "${#EXPECTED_KEY_SHA256}" -eq 64 ] || fail "A impressão digital deve conter 64 caracteres hexadecimais."
ACTUAL_KEY_SHA256=$(sha256sum "$KEY_SOURCE" | cut -d ' ' -f 1)
[ "$(printf '%s' "$ACTUAL_KEY_SHA256" | tr 'A-F' 'a-f')" = "$(printf '%s' "$EXPECTED_KEY_SHA256" | tr 'A-F' 'a-f')" ] || fail "A impressão digital da chave não corresponde."

install -d -o root -g root -m 0755 /etc/solarminer
install -o root -g root -m 0644 "$KEY_SOURCE" /etc/solarminer/release-pubkey.pem
python3 - "$CANONICAL_URL" <<'PY'
import json, os, sys, tempfile
repo = sys.argv[1]
doc = {"repositories": {repo: {
    "manifest_url": repo + "/releases/latest/download/solarminer-release.json",
    "manifest_origins": ["https://github.com", "https://release-assets.githubusercontent.com"],
    "package_origins": ["https://github.com", "https://release-assets.githubusercontent.com"]
}}}
path = "/etc/solarminer/update-sources.json"
fd, tmp = tempfile.mkstemp(prefix=".update-sources.", dir="/etc/solarminer")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, sort_keys=True, separators=(",", ":"))
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o640)
    os.replace(tmp, path)
finally:
    try: os.unlink(tmp)
    except FileNotFoundError: pass
PY

printf 'A instalar pacote amd64 e dependências Debian…\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y "$DEB"
chown root:solarminer /etc/solarminer/update-sources.json
chmod 0640 /etc/solarminer/update-sources.json
printf '\nInstalação concluída. O timer verifica diariamente a origem aprovada.\n'
printf 'A PWA Owner permite verificar e selecionar apenas URLs presentes na allowlist root.\n'
printf 'A aplicação continua a exigir confirmação explícita do Owner.\n'
