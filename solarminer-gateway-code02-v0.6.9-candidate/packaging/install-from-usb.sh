#!/bin/sh
# SolarMiner Gateway first-install USB bootstrap for Debian 13 amd64.
# Run as root: sh install-from-usb.sh
set -eu

[ "$(id -u)" -eq 0 ] || { echo "Inicia sessão como root e executa: sh install-from-usb.sh" >&2; exit 1; }
LOG=/var/log/solarminer-first-install.log
mkdir -p /var/log
touch "$LOG"
chmod 0600 "$LOG"
log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" | tee -a "$LOG"; }
fail() { log "ERROR: $*"; exit 1; }
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
PACKAGE_NAME=solarminer-gateway_0.6.71_amd64.deb
PACKAGE="$HERE/$PACKAGE_NAME"
MANIFEST="$HERE/solarminer-release.json"
PUBLIC_KEY="$HERE/release-pubkey.pem"
for file in "$PACKAGE" "$MANIFEST" "$PUBLIC_KEY"; do
  [ -s "$file" ] || fail "Ficheiro necessário em falta na pen: $(basename "$file")"
  [ ! -L "$file" ] || fail "Não são aceites ficheiros simbólicos: $(basename "$file")"
done
[ "$(dpkg-deb -f "$PACKAGE" Architecture)" = amd64 ] || fail "Pacote não é amd64."
[ "$(dpkg-deb -f "$PACKAGE" Package)" = solarminer-gateway ] || fail "Pacote inesperado."
[ "$(dpkg-deb -f "$PACKAGE" Version)" = 0.6.71 ] || fail "Versão do pacote não corresponde ao instalador."

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
python3 - "$MANIFEST" "$PUBLIC_KEY" "$PACKAGE" "$WORK" <<'PY'
import hashlib, json, os, pathlib, sys
manifest_path, key_path, package_path, work_dir = map(pathlib.Path, sys.argv[1:])
try:
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"schema_version", "release_id", "version", "min_compatible_version",
                "changelog", "package_name", "package_url", "package_size", "sha256",
                "signature_algorithm", "signature", "compatibility", "migration_requirements"}
    if not isinstance(m, dict) or not required.issubset(m):
        raise ValueError("campos obrigatórios do manifesto em falta")
    version = "0.6.71"
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
log "A configurar a palavra-passe inicial do Owner na consola local. O que escreveres será visível e não será guardado em texto simples."
solarminer-gateway owner-password || fail "A configuração local da palavra-passe inicial falhou. Consulta $LOG"
if command -v tailscale >/dev/null 2>&1; then
  log "A iniciar o Tailscale. A autorização do equipamento exige a tua conta Tailscale e será apresentada no terminal; não é guardada no log."
  tailscale up || log "Autorização Tailscale pendente; conclui o início de sessão com o URL apresentado pelo comando tailscale up."
fi
chown root:solarminer /etc/solarminer/update-sources.json
chmod 0640 /etc/solarminer/update-sources.json

log "A aguardar o serviço e a validar o health check local."
systemctl is-enabled --quiet solarminer-gateway.service || fail "O serviço não ficou ativo no arranque."
attempt=0
while [ "$attempt" -lt 30 ]; do
  if systemctl is-active --quiet solarminer-gateway.service &&
     python3 - <<'PY' >/dev/null 2>&1
import json, ssl, urllib.request
ctx = ssl.create_default_context(cafile="/var/lib/solarminer/server.crt")
with urllib.request.urlopen("https://127.0.0.1:8443/api/v1/health", context=ctx, timeout=1) as response:
    if response.status != 200:
        raise SystemExit(1)
    json.load(response)
PY
  then
    log "Health check concluído com sucesso."
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done
[ "$attempt" -lt 30 ] || fail "Health check não passou dentro de 60 segundos."
log "Instalação inicial SolarMiner Gateway 0.6.71 concluída."
log "O Gateway está configurado para verificar diariamente o repositório oficial; aplicar uma atualização continua a exigir ação Owner na PWA."
trap - EXIT HUP INT TERM
rm -rf "$WORK"
