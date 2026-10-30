import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "provision-data-volume.py"
SPEC = importlib.util.spec_from_file_location("provision_data_volume", MODULE_PATH)
provision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision)


PARTED = """BYT;
/dev/nvme0n1:200000MiB:nvme:512:512:gpt:NVMe;
1:1.00MiB:1024.00MiB:1023.00MiB:fat32:EFI:boot, esp;
2:1024.00MiB:70000.00MiB:68976.00MiB:ext4:Gateway:;
:70000.00MiB:199999.00MiB:129999.00MiB:free;
"""


def test_parser_finds_only_unallocated_region_and_rounds_to_mib():
    assert provision.parse_free_regions(PARTED) == [(70000, 199999, 129999)]
    assert provision.choose_free_region(PARTED) == (70000, 199999, 129999)
    assert provision.partition_table_type(PARTED) == "gpt"


def test_refuses_non_gpt_partition_table():
    output = PARTED.replace(":gpt:NVMe;", ":msdos:NVMe;")
    assert provision.partition_table_type(output) == "msdos"


def test_parser_ignores_small_alignment_gaps():
    output = PARTED.replace("1:1.00MiB", ":0.00MiB:1.00MiB:1.00MiB:free;\n1:1.00MiB")
    assert provision.choose_free_region(output) == (70000, 199999, 129999)


def test_refuses_no_large_free_area():
    output = PARTED.replace("129999.00MiB:free", "1000.00MiB:free")
    with pytest.raises(RuntimeError, match="Nenhuma partição foi alterada"):
        provision.choose_free_region(output)


def test_refuses_multiple_large_free_areas():
    output = PARTED.replace("2:1024.00MiB", ":2000.00MiB:50000.00MiB:48000.00MiB:free;\n2:1024.00MiB")
    with pytest.raises(RuntimeError, match="Nenhuma partição foi alterada"):
        provision.choose_free_region(output)


def test_fstab_entry_is_idempotent(tmp_path, monkeypatch):
    fstab = tmp_path / "fstab"
    fstab.write_text("UUID=root / ext4 defaults 0 1\n", encoding="utf-8")
    monkeypatch.setattr(provision, "FSTAB", fstab)
    monkeypatch.setattr(provision, "MOUNTPOINT", Path("/var/lib/solarminer"))
    monkeypatch.setattr(provision.os, "chown", lambda *_args: None)
    provision.write_fstab("data-uuid")
    expected = fstab.read_text(encoding="utf-8")
    provision.write_fstab("data-uuid")
    assert fstab.read_text(encoding="utf-8") == expected
    assert "UUID=data-uuid /var/lib/solarminer ext4 defaults,noatime 0 2" in expected


def test_fstab_refuses_to_replace_existing_mount(tmp_path, monkeypatch):
    fstab = tmp_path / "fstab"
    fstab.write_text("UUID=other /var/lib/solarminer ext4 defaults 0 2\n", encoding="utf-8")
    monkeypatch.setattr(provision, "FSTAB", fstab)
    monkeypatch.setattr(provision, "MOUNTPOINT", Path("/var/lib/solarminer"))
    with pytest.raises(RuntimeError, match="fstab"):
        provision.write_fstab("data-uuid")
