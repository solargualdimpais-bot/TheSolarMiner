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


def test_parser_accepts_free_row_with_extra_empty_metadata_and_metric_units():
    output = """:\n:1000MB:140000MB:139000MB::free;\n:140000MB:140001MB:1MB:free;\n"""
    regions = provision.parse_free_regions(output)
    assert regions == [(954, 133514, 132560)]


def test_parser_accepts_free_row_reported_in_gibibytes():
    output = ":1.00GiB:130.00GiB:129.00GiB:free;"
    assert provision.parse_free_regions(output) == [(1024, 133120, 132096)]


def test_parser_accepts_locale_decimal_comma():
    output = ":1,00mib:130,00gib:129,00gib:free;"
    assert provision.parse_free_regions(output) == [(1, 133120, 132096)]


def test_parser_selects_130_gib_free_extent_among_alignment_gaps():
    output = """BYT;
/dev/sda:243000MiB:scsi:512:512:gpt:disk;
:0.00MiB:1.00MiB:1.00MiB:free;
5:1000.00MiB:60000.00MiB:59000.00MiB:ext4:Gateway:;
:60000.00MiB:193000.00MiB:133000.00MiB:free;
:242999.00MiB:243000.00MiB:1.00MiB:free;
"""
    assert provision.choose_free_region(output) == (60000, 193000, 133000)


def test_human_parted_fallback_finds_130_gib_free_extent():
    output = """Model: disk (scsi)
Disk /dev/sda: 243000MiB
Partition Table: gpt
Number  Start       End         Size        File system  Name    Flags
        0.00MiB     1.00MiB     1.00MiB     Free Space
5       1.00MiB     60000MiB   59999MiB    ext4         Gateway
        60000MiB    193000MiB  133000MiB   Free Space
        242999MiB   243000MiB  1.00MiB     Free Space
"""
    assert provision.choose_free_region_rows(
        provision.parse_human_free_regions(output)
    ) == (60000, 193000, 133000)


def test_free_space_detection_uses_read_only_human_fallback(monkeypatch):
    calls = []
    machine_table = PARTED.replace("129999.00MiB:free", "129999.00Unknown:free")
    human_table = """Model: disk (scsi)
Disk /dev/sda: 243000MiB
Partition Table: gpt
        60000MiB 193000MiB 133000MiB Free Space
"""

    def fake_run(args, *, check=True, env=None):
        calls.append((args, env))
        return human_table

    monkeypatch.setattr(provision, "run", fake_run)
    assert provision.discover_free_region("/dev/sda", machine_table) == (
        60000, 193000, 133000
    )
    assert len(calls) == 1
    assert calls[0][0] == ["parted", "--script", "/dev/sda", "unit", "MiB", "print", "free"]
    assert calls[0][1]["LC_ALL"] == "C"


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


def test_partition_listing_uses_compatible_lsblk_pairs_options(monkeypatch):
    calls = []
    output = 'NAME="/dev/sda1" TYPE="part" PARTLABEL="SOLARMiner_DATA" FSTYPE="ext4" UUID="data-uuid"'
    monkeypatch.setattr(provision, "run", lambda args: calls.append(args) or output)
    assert provision.partition_rows("/dev/sda") == [
        ("/dev/sda1", "SOLARMiner_DATA", "ext4", "data-uuid")
    ]
    assert "--pairs" in calls[0]
    assert "--list" not in calls[0]


def test_partition_uuid_uses_portable_blkid_value_options(monkeypatch):
    calls = []
    monkeypatch.setattr(provision, "run", lambda args: calls.append(args) or "data-uuid\n")
    assert provision.partition_uuid("/dev/sda6") == "data-uuid"
    assert calls == [["blkid", "--output", "value", "--match-tag", "UUID", "/dev/sda6"]]
    assert "--no-encode" not in calls[0]


def test_existing_named_ext4_partition_is_reused_without_a_size_limit(monkeypatch):
    calls = []
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])
    monkeypatch.setattr(provision, "run", lambda args: calls.append(args) or "")
    rows = [("/dev/sda6", "solarminer_data", "ext4", "data-uuid")]
    partition = provision.find_existing_data_partition(rows)
    assert partition == rows[0]
    assert provision.ensure_ext4_data_partition(partition[0], partition[2], partition[3]) == "data-uuid"
    assert calls == []


def test_existing_named_non_ext4_partition_is_formatted_as_ext4(monkeypatch):
    calls = []
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])

    def fake_run(args, **_kwargs):
        calls.append(args)
        return "formatted-uuid" if args[0] == "blkid" else ""

    monkeypatch.setattr(provision, "run", fake_run)
    uuid = provision.ensure_ext4_data_partition("/dev/sda6", "vfat", "")
    assert uuid == "formatted-uuid"
    assert calls == [
        ["mkfs.ext4", "-F", "-L", "SOLARMINER_DATA", "/dev/sda6"],
        ["blkid", "--output", "value", "--match-tag", "UUID", "/dev/sda6"],
    ]


def test_named_non_ext4_partition_mounted_elsewhere_is_never_formatted(monkeypatch):
    calls = []
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: ["/"])
    monkeypatch.setattr(provision, "run", lambda args: calls.append(args) or "")
    with pytest.raises(RuntimeError, match="montada noutro local"):
        provision.ensure_ext4_data_partition("/dev/sda5", "ntfs", "")
    assert calls == []


def test_named_partition_already_mounted_at_data_path_is_reused(monkeypatch):
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: ["/var/lib/solarminer"])
    assert provision.ensure_ext4_data_partition(
        "/dev/sda6", "ext4", "data-uuid"
    ) == "data-uuid"


def test_ext4_partition_without_uuid_fails_without_formatting(monkeypatch):
    calls = []
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])
    monkeypatch.setattr(provision, "run", lambda args: calls.append(args) or "")
    with pytest.raises(RuntimeError, match="ext4 não tem UUID legível"):
        provision.ensure_ext4_data_partition("/dev/sda6", "ext4", "")
    assert calls == [["blkid", "--output", "value", "--match-tag", "UUID", "/dev/sda6"]]


def test_duplicate_data_partition_labels_are_rejected():
    rows = [
        ("/dev/sda6", "SOLARMINER_DATA", "ext4", "uuid-a"),
        ("/dev/sda7", "solarminer_data", "ext4", "uuid-b"),
    ]
    with pytest.raises(RuntimeError, match="mais de uma partição"):
        provision.find_existing_data_partition(rows)


def test_fstab_entry_is_idempotent(tmp_path, monkeypatch):
    fstab = tmp_path / "fstab"
    fstab.write_text("UUID=root / ext4 defaults 0 1\n", encoding="utf-8")
    monkeypatch.setattr(provision, "FSTAB", fstab)
    monkeypatch.setattr(provision, "MOUNTPOINT", Path("/var/lib/solarminer"))
    monkeypatch.setattr(provision.os, "chown", lambda *_args: None, raising=False)
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
