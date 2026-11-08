#!/bin/sh
# SolarMiner Gateway first-install USB bootstrap for Debian 13 amd64.
# Run as root: sh install-from-usb.sh
set -eu

[ "$(id -u)" -eq 0 ] || { echo "Inicia sessão como root e executa: sh install-from-usb.sh" >&2; exit 1; }
LOG=/var/log/solarminer-first-install.log
PERSISTENT_LOG=""
mkdir -p /var/log
touch "$LOG"
chmod 0600 "$LOG"
log() {
  line=$(printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*")
  if [ -n "$PERSISTENT_LOG" ]; then printf '%s\n' "$line" | tee -a "$LOG" "$PERSISTENT_LOG"; else printf '%s\n' "$line" | tee -a "$LOG"; fi
}
fail() {
  log "ERROR: $*"
  if [ -n "$PERSISTENT_LOG" ] && [ -s "$LOG" ]; then
    tail -n 120 "$LOG" > "${PERSISTENT_LOG}.failure-context"
    chmod 0600 "${PERSISTENT_LOG}.failure-context"
  fi
  exit 1
}
command -v dpkg >/dev/null 2>&1 || fail "Debian/dpkg não encontrado."
command -v dpkg-deb >/dev/null 2>&1 || fail "dpkg-deb não encontrado."
command -v apt-get >/dev/null 2>&1 || fail "apt-get não encontrado."
command -v python3 >/dev/null 2>&1 || fail "Python 3 não encontrado."
[ "$(dpkg --print-architecture)" = "amd64" ] || fail "Este pacote destina-se apenas a AMD64."
[ -r /etc/os-release ] || fail "Não foi possível identificar Debian."
. /etc/os-release
[ "${ID:-}" = "debian" ] || fail "Este instalador exige Debian."
case "${VERSION_ID:-}" in
  ''|*[!0-9.]*|.*|*.) fail "Versão Debian inválida." ;;
esac
[ "${VERSION_ID%%.*}" -ge 13 ] || fail "Este instalador exige Debian 13 (Trixie) ou posterior."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,13) else 1)' || fail "É necessário Python 3.13 ou posterior."
command -v openssl >/dev/null 2>&1 || {
  log "A instalar OpenSSL a partir dos repositórios Debian oficiais."
  apt-get update >>"$LOG" 2>&1 || fail "apt-get update falhou. Consulta $LOG"
  DEBIAN_FRONTEND=noninteractive apt-get install -y openssl ca-certificates >>"$LOG" 2>&1 || fail "Não foi possível instalar OpenSSL. Consulta $LOG"
}
if dpkg-query -W -f='${db:Status-Status}' solarminer-gateway 2>/dev/null | grep -qx installed; then
  fail "SolarMiner Gateway já está instalado; este é apenas o instalador inicial."
fi

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MANIFEST="$HERE/solarminer-release.json"
PUBLIC_KEY="$HERE/release-pubkey.pem"
DATA_PROVISIONER="$HERE/provision-data-volume.py"
for file in "$MANIFEST" "$PUBLIC_KEY" "$DATA_PROVISIONER"; do
  [ -s "$file" ] || fail "Ficheiro necessário em falta na pen: $(basename "$file")"
  [ ! -L "$file" ] || fail "Não são aceites ficheiros simbólicos: $(basename "$file")"
done
PACKAGE_VERSION=$(python3 - "$MANIFEST" <<'PY'
import json, pathlib, re, sys
try:
    manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    version = manifest["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", version):
        raise ValueError("versão inválida")
    if manifest.get("release_id") != "gateway-v" + version:
        raise ValueError("identidade da release inválida")
    print(version)
except (OSError, ValueError, TypeError, KeyError) as exc:
    print(f"Manifesto inválido: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
) || fail "Não foi possível identificar com segurança a versão do pacote no manifesto."
PACKAGE_NAME="solarminer-gateway_${PACKAGE_VERSION}_amd64.deb"
PACKAGE="$HERE/$PACKAGE_NAME"
[ -s "$PACKAGE" ] || fail "Ficheiro necessário em falta na pen: $PACKAGE_NAME"
[ ! -L "$PACKAGE" ] || fail "Não são aceites ficheiros simbólicos: $PACKAGE_NAME"
[ "$(dpkg-deb -f "$PACKAGE" Architecture)" = amd64 ] || fail "Pacote não é amd64."
[ "$(dpkg-deb -f "$PACKAGE" Package)" = solarminer-gateway ] || fail "Pacote inesperado."
[ "$(dpkg-deb -f "$PACKAGE" Version)" = "$PACKAGE_VERSION" ] || fail "Versão do pacote não corresponde ao manifesto."

WORK=$(mktemp -d /tmp/solarminer-bootstrap.XXXXXX)
CREATED_TRUST=0
INSTALLED_PACKAGE=0
cleanup() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ "$status" -ne 0 ]; then
    log "Falha; a reverter a instalação inicial."
    if [ "$INSTALLED_PACKAGE" -eq 1 ]; then
      systemctl stop solarminer-gateway.service >/dev/null 2>&1 || true
      dpkg --purge solarminer-gateway >>"$LOG" 2>&1 || true
    fi
    if [ "$CREATED_TRUST" -eq 1 ]; then
      rm -f /etc/solarminer/release-pubkey.pem /etc/solarminer/update-sources.json
      rmdir /etc/solarminer 2>/dev/null || true
    fi
    log "Rollback terminado. Consulta $LOG"
  fi
  rm -rf "$WORK"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

log "A validar manifesto, assinatura Ed25519 e pacote antes de instalar."
python3 - "$MANIFEST" "$PUBLIC_KEY" "$PACKAGE" "$PACKAGE_VERSION" "$WORK" <<'PY'
import hashlib, json, os, pathlib, sys
manifest_path, key_path, package_path = map(pathlib.Path, sys.argv[1:4])
version = sys.argv[4]
work_dir = pathlib.Path(sys.argv[5])
try:
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"schema_version", "release_id", "version", "min_compatible_version",
                "changelog", "package_name", "package_url", "package_size", "sha256",
                "signature_algorithm", "signature", "compatibility", "migration_requirements"}
    if not isinstance(m, dict) or not required.issubset(m):
        raise ValueError("campos obrigatórios do manifesto em falta")
    if m["schema_version"] != 1 or m["signature_algorithm"] != "Ed25519":
        raise ValueError("esquema ou algoritmo não suportado")
    if m["version"] != version or m["release_id"] != "gateway-v" + version:
        raise ValueError("versão/release não corresponde a este instalador")
    minimum = m["min_compatible_version"]
    if not isinstance(minimum, str) or not __import__("re").fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", minimum):
        raise ValueError("versão mínima de compatibilidade inválida")
    if tuple(map(int, minimum.split("."))) > tuple(map(int, version.split("."))):
        raise ValueError("versão mínima incompatível")
    if m["package_name"] != package_path.name or pathlib.Path(m["package_name"]).name != m["package_name"]:
        raise ValueError("nome de pacote inválido")
    if not isinstance(m["package_size"], int) or m["package_size"] != package_path.stat().st_size:
        raise ValueError("tamanho do pacote não corresponde")
    digest = hashlib.sha256(package_path.read_bytes()).hexdigest()
    if not isinstance(m["sha256"], str) or digest.lower() != m["sha256"].lower():
        raise ValueError("SHA-256 do pacote não corresponde")
    compat = m["compatibility"]
    if not isinstance(compat, dict) or compat.get("architecture") != "amd64" or compat.get("debian_min") != "13" or compat.get("python_min") != "3.13":
        raise ValueError("compatibilidade do manifesto não corresponde ao Gateway")
    import urllib.parse
    u = urllib.parse.urlsplit(m["package_url"])
    expected_path = f"/solargualdimpais-bot/TheSolarMiner/releases/download/{m['release_id']}/{m['package_name']}"
    if u.scheme != "https" or u.hostname != "github.com" or u.port is not None or u.path != expected_path or u.query or u.fragment or u.username or u.password:
        raise ValueError("origem do pacote não autorizada")
    signature = bytes.fromhex(m["signature"])
    unsigned = {k: v for k, v in m.items() if k != "signature"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    (work_dir / "manifest.canonical").write_bytes(canonical)
    (work_dir / "manifest.signature").write_bytes(signature)
except (OSError, ValueError, TypeError, KeyError) as exc:
    print(f"Validação recusada: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
openssl pkey -pubin -in "$PUBLIC_KEY" -noout >/dev/null 2>&1 || fail "Chave pública Ed25519 inválida."
openssl pkeyutl -verify -pubin -inkey "$PUBLIC_KEY" -rawin -in "$WORK/manifest.canonical" -sigfile "$WORK/manifest.signature" >/dev/null 2>&1 || fail "Assinatura Ed25519 inválida; nada foi instalado."
log "Assinatura e hash válidos."
if [ -e /etc/solarminer/release-pubkey.pem ] || [ -e /etc/solarminer/update-sources.json ]; then
  fail "Já existem configurações SolarMiner; a instalação inicial não irá sobrescrevê-las."
fi
TAILSCALE_SETUP="$HERE/install-tailscale.sh"
[ -s "$TAILSCALE_SETUP" ] && [ ! -L "$TAILSCALE_SETUP" ] || fail "Instalador oficial de Tailscale não encontrado na pen."
log "A instalar ferramentas oficiais de particionamento e ext4, se necessário."
apt-get update >>"$LOG" 2>&1 || fail "apt-get update falhou antes de preparar a partição de dados. Consulta $LOG"
DEBIAN_FRONTEND=noninteractive apt-get install -y parted e2fsprogs util-linux >>"$LOG" 2>&1 || fail "Não foi possível instalar as ferramentas de partição. Consulta $LOG"
log "A preparar automaticamente a partição de dados no espaço não atribuído do disco do Debian."
python3 "$DATA_PROVISIONER" >>"$LOG" 2>&1 || fail "Não foi possível preparar em segurança a partição de dados. Consulta $LOG"
PERSISTENT_LOG="/var/lib/solarminer/install/first-install-$(date -u '+%Y%m%dT%H%M%SZ').log"
install -d -o root -g root -m 0700 /var/lib/solarminer/install
touch "$PERSISTENT_LOG"
chmod 0600 "$PERSISTENT_LOG"
cat "$LOG" >> "$PERSISTENT_LOG"
log "A partir daqui o registo também fica guardado na partição persistente de dados."
log "A instalar o cliente Tailscale oficial para Debian 13 AMD64."
sh "$TAILSCALE_SETUP" >>"$LOG" 2>&1 || fail "A instalação do Tailscale falhou. Consulta $LOG"

CREATED_TRUST=1
install -d -o root -g root -m 0755 /etc/solarminer
install -o root -g root -m 0644 "$PUBLIC_KEY" /etc/solarminer/release-pubkey.pem
python3 - <<'PY'
import json, os, tempfile
path = "/etc/solarminer/update-sources.json"
repo = "https://github.com/solargualdimpais-bot/TheSolarMiner"
doc = {"repositories": {repo: {
    "manifest_url": repo + "/releases/latest/download/solarminer-release.json",
    "manifest_origins": ["https://github.com", "https://release-assets.githubusercontent.com"],
    "package_origins": ["https://github.com", "https://release-assets.githubusercontent.com"]
}}}
fd, tmp = tempfile.mkstemp(prefix=".update-sources.", dir="/etc/solarminer")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(doc, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chown(tmp, 0, 0)
    os.chmod(tmp, 0o640)
    os.replace(tmp, path)
finally:
    try: os.unlink(tmp)
    except FileNotFoundError: pass
PY
CREATED_TRUST=1

log "A instalar pacote e dependências assinados."
apt-get update >>"$LOG" 2>&1 || fail "apt-get update falhou. Consulta $LOG"
INSTALLED_PACKAGE=1
DEBIAN_FRONTEND=noninteractive apt-get install -y "$PACKAGE" >>"$LOG" 2>&1 || fail "Instalação do pacote falhou. Consulta $LOG"
log "A verificar se a base persistente já tem um Owner ativo."
OWNER_STATE=$(python3 - <<'PY'
import sqlite3
from pathlib import Path

database = Path("/var/lib/solarminer/gateway.db")
if not database.is_file():
    print("empty")
else:
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if "users" not in tables:
                if tables:
                    raise sqlite3.DatabaseError(
                        "Persistent database has tables but no users table; refusing to treat it as a clean database"
                    )
                active_owner = None
            else:
                active_owner = connection.execute(
                    "SELECT 1 FROM users WHERE role='owner' AND status='active' LIMIT 1"
                ).fetchone()
    except sqlite3.Error as exc:
        raise SystemExit(f"Não foi possível verificar a base persistente com segurança: {exc}")
    print("active" if active_owner else "empty")
PY
) || fail "Não foi possível verificar o Owner existente; a instalação parou sem alterar a base de dados."
if [ "$OWNER_STATE" = "active" ]; then
  log "Owner ativo encontrado no disco persistente; a palavra-passe existente e os dados foram preservados. A ignorar o registo de Owner inicial."
else
  log "A configurar a palavra-passe inicial do Owner na consola local. O que escreveres será visível e não será guardado em texto simples."
  solarminer-gateway owner-password || fail "A configuração local da palavra-passe inicial falhou. Consulta $LOG"
fi
if command -v tailscale >/dev/null 2>&1; then
  log "A iniciar o Tailscale. A autorização do equipamento exige a tua conta Tailscale e será apresentada no terminal; não é guardada no log."
  tailscale up || log "Autorização Tailscale pendente; conclui o início de sessão com o URL apresentado pelo comando tailscale up."
fi
chown root:solarminer /etc/solarminer/update-sources.json
chmod 0640 /etc/solarminer/update-sources.json

log "A aguardar o serviço e a validar o health check local."
systemctl is-enabled --quiet solarminer-gateway.service || fail "O serviço não ficou ativo no arranque."
attempt=0
while [ "$attempt" -lt 60 ]; do
  if systemctl is-active --quiet solarminer-gateway.service &&
     python3 - <<'PY' >>"$LOG" 2>&1
import hashlib
import http.client
import json
import ssl
from pathlib import Path

try:
    certificate = Path("/var/lib/solarminer/server.crt")
    expected_der = ssl.PEM_cert_to_DER_cert(certificate.read_text(encoding="ascii"))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # This is a loopback readiness probe only. Pin the exact configured server
    # certificate instead of treating a CA-issued leaf certificate as a CA.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    connection = http.client.HTTPSConnection("127.0.0.1", 8443, context=context, timeout=1)
    connection.connect()
    actual_der = connection.sock.getpeercert(binary_form=True)
    if not hashlib.sha256(actual_der).digest() == hashlib.sha256(expected_der).digest():
        raise RuntimeError("Gateway presented a TLS certificate different from server.crt")
    connection.request("GET", "/api/v1/health")
    response = connection.getresponse()
    if response.status != 200:
        raise RuntimeError(f"health endpoint returned HTTP {response.status}")
    json.load(response)
    connection.close()
except Exception as exc:
    print(f"Local health probe failed: {type(exc).__name__}: {exc}", flush=True)
    raise SystemExit(1)
PY
  then
    log "Health check concluído com sucesso."
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done
[ "$attempt" -lt 60 ] || {
  {
    echo "--- diagnóstico local de Gateway/Nginx ---"
    echo "Gateway ativo: $(systemctl is-active solarminer-gateway.service 2>/dev/null || true)"
    echo "Nginx ativo: $(systemctl is-active nginx.service 2>/dev/null || true)"
    echo "Versão dpkg: $(dpkg-query -W -f='${Version}' solarminer-gateway 2>/dev/null || true)"
    journalctl --unit solarminer-gateway.service --lines=60 --no-pager 2>/dev/null || true
    nginx -t 2>&1 || true
  } | tee -a "$LOG" "$PERSISTENT_LOG"
  fail "Health check não passou dentro de 60 segundos. O detalhe da resposta e o estado local foram guardados nos registos persistentes."
}
log "Instalação inicial SolarMiner Gateway $PACKAGE_VERSION concluída."
log "O Gateway está configurado para verificar diariamente o repositório oficial; aplicar uma atualização continua a exigir ação Owner na PWA."
trap - EXIT HUP INT TERM
rm -rf "$WORK"


