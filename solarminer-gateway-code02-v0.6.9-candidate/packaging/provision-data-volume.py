#!/usr/bin/python3
"""Provision SolarMiner's persistent data partition from unused disk space."""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
try:
    import fcntl
except ImportError:  # Allows pure parsing tests to run on Windows.
    fcntl = None

MOUNTPOINT = pathlib.Path("/var/lib/solarminer")
FSTAB = pathlib.Path("/etc/fstab")
MARKER = pathlib.Path("/etc/solarminer/data-volume.uuid")
LABEL = "SOLARMINER_DATA"
MIN_FREE_MIB = 40 * 1024


def run(args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(args, check=False, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{pathlib.Path(args[0]).name} falhou: {detail}")
    return result.stdout.strip()


def require_tools() -> None:
    missing = [name for name in ("findmnt", "lsblk", "parted", "partprobe",
                                  "udevadm", "blkid", "mkfs.ext4", "mount",
                                  "mountpoint") if shutil.which(name) is None]
    if missing:
        raise RuntimeError("Ferramentas necessárias em falta: " + ", ".join(missing))


def root_disk() -> str:
    source = run(["findmnt", "--noheadings", "--output", "SOURCE", "--target", "/"])
    source = source.split("[", 1)[0]
    source_path = pathlib.Path(os.path.realpath(source))
    parent = run(["lsblk", "--noheadings", "--output", "PKNAME", str(source_path)]).strip()
    if not parent:
        raise RuntimeError("Não foi possível identificar o disco físico que contém o Debian.")
    disk = "/dev/" + parent.splitlines()[0].strip()
    device_type = run(["lsblk", "--noheadings", "--output", "TYPE", disk]).splitlines()[0].strip()
    removable = run(["lsblk", "--noheadings", "--output", "RM", disk]).splitlines()[0].strip()
    if device_type != "disk" or removable != "0":
        raise RuntimeError("O disco do Debian não foi identificado como disco interno fixo.")
    if pathlib.Path(os.path.realpath(disk)) == source_path:
        raise RuntimeError("A raiz do Debian ocupa o disco inteiro; não vou reparticionar.")
    return disk


def parse_free_regions(output: str) -> list[tuple[int, int, int]]:
    regions = []
    for line in output.splitlines():
        fields = line.rstrip(";").split(":")
        if len(fields) < 5 or fields[0] or fields[4] != "free":
            continue
        try:
            start = int(float(fields[1].removesuffix("MiB")) + 0.999999)
            end = int(float(fields[2].removesuffix("MiB")))
            size = int(float(fields[3].removesuffix("MiB")))
        except (ValueError, TypeError):
            continue
        if end > start and size > 0:
            regions.append((start, end, size))
    return regions


def choose_free_region(output: str) -> tuple[int, int, int]:
    candidates = [region for region in parse_free_regions(output)
                  if region[2] >= MIN_FREE_MIB]
    if len(candidates) != 1:
        raise RuntimeError(
            "Era esperada exatamente uma área livre de pelo menos 40 GiB "
            f"no disco do Debian; foram encontradas {len(candidates)}. "
            "Nenhuma partição foi alterada."
        )
    return candidates[0]


def partition_table_type(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("/dev/"):
            fields = line.rstrip(";").split(":")
            return fields[5] if len(fields) > 5 else ""
    return ""


def partition_rows(disk: str) -> list[tuple[str, str, str, str]]:
    output = run(["lsblk", "--paths", "--noheadings", "--pairs",
                  "--output", "NAME,TYPE,PARTLABEL,FSTYPE,UUID", disk])
    rows = []
    for line in output.splitlines():
        values = dict(re.findall(r'(\w+)="([^"]*)"', line))
        if values.get("TYPE") == "part":
            rows.append((values.get("NAME", ""), values.get("PARTLABEL", ""),
                         values.get("FSTYPE", ""), values.get("UUID", "")))
    return rows


def write_fstab(uuid: str) -> None:
    existing = FSTAB.read_text(encoding="utf-8") if FSTAB.exists() else ""
    managed = []
    for line in existing.splitlines():
        fields = line.split("#", 1)[0].split()
        if len(fields) >= 2 and fields[1] == MOUNTPOINT.as_posix():
            managed.append(fields)
    if managed:
        if len(managed) == 1 and managed[0][0] == f"UUID={uuid}":
            return
        raise RuntimeError("/etc/fstab já contém uma montagem diferente para os dados; não foi alterada.")
    updated = existing.rstrip("\n") + ("\n" if existing.strip() else "")
    updated += f"UUID={uuid} {MOUNTPOINT.as_posix()} ext4 defaults,noatime 0 2\n"
    fd, temporary = tempfile.mkstemp(prefix=".fstab-solarminer-", dir=str(FSTAB.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        if hasattr(os, "chown"):
            os.chown(temporary, 0, 0)
        os.replace(temporary, FSTAB)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def mount_data(uuid: str) -> None:
    MOUNTPOINT.mkdir(parents=True, exist_ok=True)
    already_mounted = subprocess.run(["mountpoint", "--quiet", str(MOUNTPOINT)], check=False)
    if already_mounted.returncode != 0:
        run(["mount", str(MOUNTPOINT)])
    mounted_uuid = run(["findmnt", "--noheadings", "--output", "UUID", "--target", str(MOUNTPOINT)])
    if mounted_uuid.strip() != uuid:
        raise RuntimeError("O volume montado não corresponde ao UUID esperado.")
    result = subprocess.run(["mountpoint", "--quiet", str(MOUNTPOINT)], check=False)
    if result.returncode != 0:
        raise RuntimeError("A partição de dados não ficou montada.")
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    temporary = MARKER.with_name(MARKER.name + ".tmp")
    temporary.write_text(uuid + "\n", encoding="ascii")
    os.chmod(temporary, 0o644)
    os.replace(temporary, MARKER)


def main() -> int:
    if os.geteuid() != 0:
        raise RuntimeError("Executa este instalador como root.")
    if sys.platform != "linux" or fcntl is None:
        raise RuntimeError("A preparação automática da partição só pode correr em Debian/Linux.")
    require_tools()
    pathlib.Path("/run/lock").mkdir(parents=True, exist_ok=True)
    with open("/run/lock/solarminer-data-volume.lock", "w", encoding="ascii") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        disk = root_disk()
        rows = partition_rows(disk)
        labelled = [row for row in rows if row[1] == LABEL]
        if len(labelled) > 1:
            raise RuntimeError("Há mais de uma partição com a etiqueta de dados SolarMiner.")
        if labelled:
            partition, _label, filesystem, uuid = labelled[0]
            if filesystem != "ext4" or not uuid:
                raise RuntimeError("A partição de dados existente não é ext4 ou não tem UUID; não foi formatada.")
        else:
            if MARKER.exists():
                raise RuntimeError("Existe registo de volume de dados, mas a partição marcada não foi encontrada.")
            if MOUNTPOINT.is_symlink():
                raise RuntimeError("/var/lib/solarminer é uma ligação simbólica; instalação interrompida.")
            if MOUNTPOINT.exists() and any(MOUNTPOINT.iterdir()):
                raise RuntimeError("/var/lib/solarminer já contém dados; instalação interrompida para os preservar.")
            table = run(["parted", "--machine", "--script", disk, "unit", "MiB", "print", "free"])
            if partition_table_type(table) != "gpt":
                raise RuntimeError("O disco do Debian não usa GPT; nenhuma partição foi alterada.")
            start, end, size = choose_free_region(table)
            print(f"A criar SOLARMiner_DATA apenas no espaço livre de {size // 1024} GiB do disco {disk}.", flush=True)
            run(["parted", "--script", "--align", "optimal", disk, "mkpart", LABEL, "ext4", f"{start}MiB", f"{end}MiB"])
            run(["partprobe", disk])
            run(["udevadm", "settle", "--timeout=30"])
            rows = partition_rows(disk)
            labelled = [row for row in rows if row[1] == LABEL]
            if len(labelled) != 1 or not labelled[0][0]:
                raise RuntimeError("A nova partição não apareceu com a etiqueta esperada; não foi formatada.")
            partition, _label, filesystem, _uuid = labelled[0]
            if filesystem:
                raise RuntimeError("A nova partição já contém um sistema de ficheiros; por segurança não foi formatada.")
            probe = subprocess.run(["blkid", "--probe", "--output", "value", "--match-tag", "TYPE", partition],
                                   check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if probe.returncode not in (0, 2):
                raise RuntimeError("Não foi possível verificar assinaturas existentes na nova partição.")
            if probe.returncode == 0 and probe.stdout.strip():
                raise RuntimeError("A nova partição contém uma assinatura existente; por segurança não foi formatada.")
            run(["mkfs.ext4", "-L", LABEL, partition])
            uuid = run(["blkid", "--no-encode", "--output", "value", "--match-tag", "UUID", partition]).strip()
            if not uuid:
                raise RuntimeError("Não foi possível ler o UUID da partição criada.")
        write_fstab(uuid)
        mount_data(uuid)
        print("Volume de dados SolarMiner preparado e montado em /var/lib/solarminer.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Preparação dos dados falhou: {exc}", file=sys.stderr)
        raise SystemExit(1)
