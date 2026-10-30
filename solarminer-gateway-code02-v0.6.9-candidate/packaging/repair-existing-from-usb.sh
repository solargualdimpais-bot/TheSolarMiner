#!/bin/sh
# Install and activate a signed Gateway repair package from USB, as root.
set -eu

[ "$(id -u)" -eq 0 ] || { echo "Executa como root: sh repair-existing-from-usb.sh" >&2; exit 1; }
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET_VERSION=0.6.100
PACKAGE="$HERE/solarminer-gateway_${TARGET_VERSION}_amd64.deb"
MANIFEST="$HERE/solarminer-release.json"
PUBLIC_KEY="$HERE/release-pubkey.pem"
LOG=/var/log/solarminer-usb-repair.log
mkdir -p /var/log; touch "$LOG"; chmod 0600 "$LOG"
log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" | tee -a "$LOG"; }
fail() { log "ERROR: $*"; exit 1; }

[ "$(dpkg --print-architecture)" = amd64 ] || fail "Gateway não é amd64."
. /etc/os-release
[ "${ID:-}" = debian ] && [ "${VERSION_ID%%.*}" -ge 13 ] || fail "É necessário Debian 13 ou posterior."
[ "$(dpkg-query -W -f='${db:Status-Status}' solarminer-gateway 2>/dev/null || true)" = installed ] || fail "SolarMiner Gateway não está instalado."
for file in "$PACKAGE" "$MANIFEST" "$PUBLIC_KEY" /etc/solarminer/release-pubkey.pem /var/lib/solarminer/gateway.db; do
  [ -s "$file" ] && [ ! -L "$file" ] || fail "Ficheiro necessário ausente/inseguro: $(basename "$file")"
done
[ "$(dpkg-deb -f "$PACKAGE" Package)" = solarminer-gateway ] || fail "Pacote inesperado."
[ "$(dpkg-deb -f "$PACKAGE" Version)" = "$TARGET_VERSION" ] || fail "Versão do pacote não corresponde ao destino esperado ($TARGET_VERSION)."
[ "$(dpkg-deb -f "$PACKAGE" Architecture)" = amd64 ] || fail "Arquitetura não corresponde."

log "A validar assinatura Ed25519, chave confiada e SHA-256."
python3 - "$MANIFEST" "$PUBLIC_KEY" /etc/solarminer/release-pubkey.pem "$PACKAGE" "$TARGET_VERSION" <<'PY' || fail "Assinatura/integridade recusada; sistema não alterado."
import hashlib, json, pathlib, sys
from cryptography.hazmat.primitives import serialization

mf, bundle_key, trusted_key, package = map(pathlib.Path, sys.argv[1:5])
version = sys.argv[5]
try:
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    required = {"schema_version", "release_id", "version", "package_name", "package_url", "package_size", "sha256", "signature_algorithm", "signature", "compatibility"}
    if not isinstance(manifest, dict) or not required.issubset(manifest):
        raise ValueError("campos obrigatórios em falta")
    key = serialization.load_pem_public_key(bundle_key.read_bytes())
    trusted = serialization.load_pem_public_key(trusted_key.read_bytes())
    der = lambda item: item.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    name = f"solarminer-gateway_{version}_amd64.deb"
    url = f"https://github.com/solargualdimpais-bot/TheSolarMiner/releases/download/gateway-v{version}/{name}"
    if der(key) != der(trusted): raise ValueError("chave da pen diferente da chave confiada no Gateway")
    if manifest["schema_version"] != 1 or manifest["version"] != version or manifest["release_id"] != f"gateway-v{version}": raise ValueError("identidade da release inválida")
    if manifest["package_name"] != name or package.name != name or manifest["package_url"] != url: raise ValueError("pacote/origem não autorizados")
    if type(manifest["package_size"]) is not int or manifest["package_size"] != package.stat().st_size: raise ValueError("tamanho do pacote não corresponde")
    if manifest["signature_algorithm"] != "Ed25519" or manifest["compatibility"] != {"architecture": "amd64", "debian_min": "13", "python_min": "3.13"}: raise ValueError("algoritmo ou compatibilidade não suportados")
    if not isinstance(manifest["sha256"], str) or hashlib.sha256(package.read_bytes()).hexdigest() != manifest["sha256"].lower(): raise ValueError("SHA-256 do pacote não corresponde")
    signature = bytes.fromhex(manifest["signature"])
    if len(signature) != 64: raise ValueError("assinatura Ed25519 inválida")
    unsigned = {field: value for field, value in manifest.items() if field != "signature"}
    key.verify(signature, json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
except Exception as exc:
    print(f"Validação recusada: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY

OLD_VERSION=$(dpkg-query -W -f='${Version}' solarminer-gateway)
dpkg --compare-versions "$OLD_VERSION" lt "$TARGET_VERSION" || fail "Gateway já está na correção ou numa versão posterior."
OLD_PACKAGE="$HERE/solarminer-gateway_${OLD_VERSION}_amd64.deb"
OLD_MANIFEST="$HERE/solarminer-release-${OLD_VERSION}.json"
[ -s "$OLD_PACKAGE" ] && [ ! -L "$OLD_PACKAGE" ] && [ -s "$OLD_MANIFEST" ] && [ ! -L "$OLD_MANIFEST" ] || fail "A pen não contém o pacote assinado da versão instalada ($OLD_VERSION), necessário para rollback seguro."
[ "$(dpkg-deb -f "$OLD_PACKAGE" Package)" = solarminer-gateway ] && [ "$(dpkg-deb -f "$OLD_PACKAGE" Version)" = "$OLD_VERSION" ] && [ "$(dpkg-deb -f "$OLD_PACKAGE" Architecture)" = amd64 ] || fail "O pacote de rollback não corresponde à versão instalada."
python3 - "$OLD_MANIFEST" "$PUBLIC_KEY" /etc/solarminer/release-pubkey.pem "$OLD_PACKAGE" "$OLD_VERSION" <<'PY' || fail "Pacote anterior/assinatura de rollback inválidos; nada foi alterado."
import hashlib, json, pathlib, sys
from cryptography.hazmat.primitives import serialization
mf, bundle_key, trusted_key, package = map(pathlib.Path, sys.argv[1:5])
version = sys.argv[5]
try:
    m = json.loads(mf.read_text(encoding="utf-8"))
    key = serialization.load_pem_public_key(bundle_key.read_bytes())
    trusted = serialization.load_pem_public_key(trusted_key.read_bytes())
    der = lambda item: item.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    name = f"solarminer-gateway_{version}_amd64.deb"
    if der(key) != der(trusted): raise ValueError("release key differs from Gateway trust key")
    if m.get("version") != version or m.get("release_id") != f"gateway-v{version}" or m.get("package_name") != name: raise ValueError("rollback release identity mismatch")
    if m.get("package_url") != f"https://github.com/solargualdimpais-bot/TheSolarMiner/releases/download/gateway-v{version}/{name}": raise ValueError("rollback URL mismatch")
    if type(m.get("package_size")) is not int or m["package_size"] != package.stat().st_size: raise ValueError("rollback package size mismatch")
    if hashlib.sha256(package.read_bytes()).hexdigest() != m.get("sha256"): raise ValueError("rollback package hash mismatch")
    signature = bytes.fromhex(m["signature"])
    unsigned = {field: value for field, value in m.items() if field != "signature"}
    key.verify(signature, json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
except Exception as exc:
    print(f"Rollback validation refused: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
CURRENT=/opt/solarminer/current
BASE=/opt/solarminer/releases
[ -d /opt/solarminer ] && [ ! -L /opt/solarminer ] && [ -d "$BASE" ] && [ ! -L "$BASE" ] || fail "Layout de releases não é seguro para reparação."
[ ! -e "$CURRENT" ] || [ -L "$CURRENT" ] || fail "O caminho da release ativa não é uma ligação simbólica segura."
# In RECOVERY_BLOCKED the active pointer may be broken or point at the failed
# candidate. The package recorded by dpkg is the known rollback version.
OLD_RELEASE="$BASE/$OLD_VERSION"
OLD_RELEASE_NAME=$OLD_VERSION
[ -d "$OLD_RELEASE" ] && [ ! -L "$OLD_RELEASE" ] || fail "A release instalada $OLD_VERSION não está disponível para rollback."
[ -f "$OLD_RELEASE/usr/lib/solarminer-gateway/solarminer_gateway/app.py" ] && [ -f "$OLD_RELEASE/usr/share/solarminer/pwa/index.html" ] || fail "A release instalada está incompleta; sistema não alterado."

TAILSCALE_SETUP="$HERE/install-tailscale.sh"
[ -s "$TAILSCALE_SETUP" ] && [ ! -L "$TAILSCALE_SETUP" ] || fail "Instalador de Tailscale não encontrado na pen."
log "A instalar/verificar Tailscale oficial antes da atualização SolarMiner."
sh "$TAILSCALE_SETUP" >>"$LOG" 2>&1 || fail "Instalação/verificação Tailscale falhou. Consulta $LOG"

BACKUP_DIR=/var/lib/solarminer/backups
install -d -o root -g root -m 0700 "$BACKUP_DIR"
BACKUP="$BACKUP_DIR/gateway-before-usb-repair-$(date -u '+%Y%m%dT%H%M%SZ').sqlite3"
python3 - "$BACKUP" <<'PY' || fail "Backup SQLite falhou."
import os, sqlite3, sys
with sqlite3.connect("/var/lib/solarminer/gateway.db") as source, sqlite3.connect(sys.argv[1]) as target:
    source.backup(target)
os.chmod(sys.argv[1], 0o600)
with sqlite3.connect(sys.argv[1]) as check:
    if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok": raise SystemExit(1)
PY
log "Backup SQLite criado: $BACKUP"

systemctl stop solarminer-gateway.service || fail "Não foi possível parar o serviço."
SUCCESS=0
rollback() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ "$status" -ne 0 ] && [ "$SUCCESS" -eq 0 ]; then
    log "Falha; a repor release $OLD_RELEASE_NAME e backup SQLite."
    systemctl stop solarminer-gateway.service >/dev/null 2>&1 || true
    rm -f /opt/solarminer/.current-usb-rollback
    if ln -s "releases/$OLD_RELEASE_NAME" /opt/solarminer/.current-usb-rollback; then
      mv -Tf /opt/solarminer/.current-usb-rollback "$CURRENT" || log "ERROR: não foi possível repor a ligação da release anterior."
    else
      log "ERROR: não foi possível preparar a ligação para rollback."
    fi
    rm -f /var/lib/solarminer/gateway.db-wal /var/lib/solarminer/gateway.db-shm
    python3 - "$BACKUP" >>"$LOG" 2>&1 <<'PY' || true
import os, pwd, sqlite3, sys
source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect("/var/lib/solarminer/gateway.db")
try:
    source.backup(target)
    target.commit()
finally:
    target.close()
    source.close()
account = pwd.getpwnam("solarminer")
os.chown("/var/lib/solarminer/gateway.db", account.pw_uid, account.pw_gid)
os.chmod("/var/lib/solarminer/gateway.db", 0o600)
PY
    DEBIAN_FRONTEND=noninteractive apt-get install -y --allow-downgrades "$OLD_PACKAGE" >>"$LOG" 2>&1 || log "ERROR: dpkg não confirmou a reposição do pacote $OLD_VERSION."
    systemctl start solarminer-gateway.service >/dev/null 2>&1 || true
    log "Rollback de aplicação/base de dados/pacote tentado; backup original preservado em $BACKUP. Consulta $LOG."
  fi
  exit "$status"
}
trap rollback EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# A failed online activation may leave current pointing at the candidate that
# could not start. Restore the package-recorded release before dpkg runs
# postinst; postinst restarts the service and must start the known-good code.
log "A selecionar a release anterior conhecida $OLD_RELEASE_NAME antes de atualizar os helpers locais."
rm -f /opt/solarminer/.current-usb-repair
ln -s "releases/$OLD_RELEASE_NAME" /opt/solarminer/.current-usb-repair
mv -Tf /opt/solarminer/.current-usb-repair "$CURRENT"

log "A instalar o pacote assinado da pen; o updater online não será usado."
DEBIAN_FRONTEND=noninteractive apt-get install -y "$PACKAGE" >>"$LOG" 2>&1 || fail "Instalação Debian falhou. Consulta $LOG; o rollback será tentado."
systemctl stop solarminer-gateway.service || fail "Não foi possível parar o serviço antes da ativação."
NEW_RELEASE="$BASE/$TARGET_VERSION"
[ -d "$NEW_RELEASE" ] && [ ! -L "$NEW_RELEASE" ] || fail "Pacote não criou uma release segura em $NEW_RELEASE."
case "$(readlink -f "$NEW_RELEASE")" in "$BASE"/*) ;; *) fail "A release nova aponta para fora da pasta autorizada." ;; esac
ln -s "releases/$TARGET_VERSION" /opt/solarminer/.current-usb-new
mv -Tf /opt/solarminer/.current-usb-new "$CURRENT"
systemctl start solarminer-gateway.service || fail "Serviço não iniciou; rollback será executado."

attempt=0
while [ "$attempt" -lt 30 ]; do
  if python3 - "$TARGET_VERSION" <<'PY' >/dev/null 2>&1
import json, ssl, sys, urllib.request
context = ssl.create_default_context(cafile="/var/lib/solarminer/server.crt")
with urllib.request.urlopen("https://127.0.0.1:8443/api/v1/health", context=context, timeout=3) as response:
    data = json.load(response)
if response.status != 200 or data.get("package_version") != sys.argv[1]: raise SystemExit(1)
PY
  then
    SUCCESS=1
    log "Instalação, ativação e health check de $TARGET_VERSION concluídos."
    log "A release anterior $OLD_RELEASE_NAME e o backup $BACKUP foram preservados."
    exit 0
  fi
  attempt=$((attempt + 1)); sleep 2
done
fail "Health check não confirmou $TARGET_VERSION; rollback será tentado. Consulta $LOG."
