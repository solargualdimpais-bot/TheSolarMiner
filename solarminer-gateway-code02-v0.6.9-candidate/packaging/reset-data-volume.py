#!/usr/bin/python3
"""Explicitly reformat only the mounted SolarMiner data volume."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

MOUNTPOINT = pathlib.Path("/var/lib/solarminer")
MARKER = pathlib.Path("/etc/solarminer/data-volume.uuid")
FSTAB = pathlib.Path("/etc/fstab")
LABEL = "SOLARMINER_DATA"


def run(args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(args, check=False, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if check and result.returncode:
        raise RuntimeError(f"{pathlib.Path(args[0]).name} falhou: "
                           f"{result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def reset_data_volume() -> None:
    if os.geteuid() != 0 or sys.platform != "linux":
        raise RuntimeError("A formatação só pode ser feita pelo instalador como root em Debian/Linux.")
    for command in ("findmnt", "mountpoint", "lsblk", "blkid", "umount", "mkfs.ext4", "mount"):
        if shutil.which(command) is None:
            raise RuntimeError(f"Ferramenta necessária em falta: {command}.")
    if subprocess.run(["mountpoint", "--quiet", str(MOUNTPOINT)], check=False).returncode:
        raise RuntimeError("A partição de dados não está montada; não vou escolher um disco por aproximação.")
    source = run(["findmnt", "--noheadings", "--output", "SOURCE", "--target", str(MOUNTPOINT)])
    source = source.split("[", 1)[0]
    source_path = pathlib.Path(os.path.realpath(source))
    if run(["lsblk", "--noheadings", "--output", "TYPE", str(source_path)]).splitlines()[0].strip() != "part":
        raise RuntimeError("O ponto de dados não corresponde a uma partição única; nada foi apagado.")
    if run(["blkid", "--output", "value", "--match-tag", "LABEL", str(source_path)]) != LABEL:
        raise RuntimeError("A partição montada não tem a etiqueta SOLARMINER_DATA; nada foi apagado.")
    if run(["blkid", "--output", "value", "--match-tag", "TYPE", str(source_path)]).lower() != "ext4":
        raise RuntimeError("A partição de dados não é ext4; nada foi apagado.")
    old_uuid = run(["blkid", "--output", "value", "--match-tag", "UUID", str(source_path)])
    if not old_uuid or not MARKER.is_file() or MARKER.read_text(encoding="ascii").strip() != old_uuid:
        raise RuntimeError("A identidade do volume não corresponde ao registo do instalador; nada foi apagado.")
    root_source = run(["findmnt", "--noheadings", "--output", "SOURCE", "--target", "/"]).split("[", 1)[0]
    if pathlib.Path(os.path.realpath(root_source)) == source_path:
        raise RuntimeError("O ponto de dados é a própria raiz do Debian; nada foi apagado.")
    fstab_lines = FSTAB.read_text(encoding="utf-8").splitlines() if FSTAB.exists() else []
    managed = []
    untouched = []
    for line in fstab_lines:
        fields = line.split("#", 1)[0].split()
        if len(fields) >= 2 and fields[1] == MOUNTPOINT.as_posix():
            managed.append(fields)
        else:
            untouched.append(line)
    if len(managed) != 1 or managed[0][0] != f"UUID={old_uuid}":
        raise RuntimeError("O registo fstab não corresponde à partição de dados; nada foi apagado.")
    print(f"A reformatar apenas {source_path} (SOLARMINER_DATA). A base, Owner, configurações, "
          "dispositivos, histórico e relatórios dessa partição serão eliminados.", flush=True)
    run(["sync"])
    run(["umount", str(MOUNTPOINT)])
    run(["mkfs.ext4", "-F", "-L", LABEL, str(source_path)])
    new_uuid = run(["blkid", "--output", "value", "--match-tag", "UUID", str(source_path)])
    if not new_uuid:
        raise RuntimeError("A partição foi formatada, mas não foi possível ler o novo UUID. Não prossigas.")
    updated = "\n".join(untouched).rstrip("\n")
    if updated:
        updated += "\n"
    updated += f"UUID={new_uuid} {MOUNTPOINT.as_posix()} ext4 defaults,noatime 0 2\n"
    FSTAB.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".fstab-solarminer-", dir=str(FSTAB.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, FSTAB)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    temporary_marker = MARKER.with_name(MARKER.name + ".tmp")
    temporary_marker.write_text(new_uuid + "\n", encoding="ascii")
    os.chmod(temporary_marker, 0o644)
    os.replace(temporary_marker, MARKER)
    MOUNTPOINT.mkdir(parents=True, exist_ok=True)
    run(["mount", str(MOUNTPOINT)])
    mounted_uuid = run(["findmnt", "--noheadings", "--output", "UUID", "--target", str(MOUNTPOINT)])
    if mounted_uuid != new_uuid:
        raise RuntimeError("A nova partição não foi montada no UUID esperado; não prossigas.")
    print("Partição SOLARMINER_DATA reformatada e montada vazia.", flush=True)


if __name__ == "__main__":
    try:
        reset_data_volume()
    except (OSError, RuntimeError, subprocess.CalledProcessError, IndexError) as exc:
        print(f"Formatação dos dados interrompida: {exc}", file=sys.stderr)
        raise SystemExit(1)
