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
    output = 'NAME="/dev/sda1" TYPE="part" PARTLABEL="SOLARMiner_DATA" FSTYPE="ext4" UUID="data-uuid" SIZE="126000000000"'
    monkeypatch.setattr(provision, "run", lambda args: calls.append(args) or output)
    assert provision.partition_rows("/dev/sda") == [
        ("/dev/sda1", "SOLARMiner_DATA", "ext4", "data-uuid", "126000000000")
    ]
    assert "--pairs" in calls[0]
    assert "--list" not in calls[0]


def test_data_partition_fields_consumes_the_new_size_column():
    assert provision.data_partition_fields(
        ("/dev/sda3", "SOLARMINER_DATA", "", "", "129000000000")
    ) == ("/dev/sda3", "SOLARMINER_DATA", "", "")


def test_newly_created_partition_row_with_size_completes_initialization(monkeypatch):
    calls = []
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])
    monkeypatch.setattr(provision, "run", lambda args, **kwargs: calls.append(args) or "created-uuid\n")
    monkeypatch.setattr(
        provision.subprocess, "run",
        lambda args, **kwargs: type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    row = ("/dev/sda6", "SOLARMINER_DATA", "", "", "129000000000")
    assert provision.format_new_data_partition(row[0]) == "created-uuid"
    assert calls == [
        ["mkfs.ext4", "-F", "-L", "SOLARMINER_DATA", "/dev/sda6"],
        ["blkid", "--output", "value", "--match-tag", "UUID", "/dev/sda6"],
    ]


def test_new_partition_formats_without_blocking_on_stale_signatures(monkeypatch):
    calls = []
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])
    monkeypatch.setattr(provision, "run", lambda args, **kwargs: calls.append(args) or "created-uuid\n")
    monkeypatch.setattr(
        provision.subprocess, "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not inspect signatures")),
    )

    assert provision.format_new_data_partition("/dev/sda6") == "created-uuid"
    assert calls == [
        ["mkfs.ext4", "-F", "-L", "SOLARMINER_DATA", "/dev/sda6"],
        ["blkid", "--output", "value", "--match-tag", "UUID", "/dev/sda6"],
    ]


def test_clean_debian_partition_plus_unallocated_space_provisions_data_end_to_end(
    tmp_path, monkeypatch,
):
    """Exercise the exact clean-install layout that previously failed on USB."""
    commands = []
    initial_rows = [
        ("/dev/sda2", "SolarMiner Gateway", "ext4", "root-uuid", "64000000000")
    ]
    data_row = (
        "/dev/sda6", "SOLARMINER_DATA", "", "", "129000000000"
    )

    class FakeLock:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def flock(self, *_args): return None

    monkeypatch.setattr(provision, "fcntl", type("Fcntl", (), {
        "LOCK_EX": 1, "LOCK_NB": 2, "flock": staticmethod(lambda *_args: None)
    }))
    monkeypatch.setattr(provision.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(provision.sys, "platform", "linux")
    monkeypatch.setattr(provision, "require_tools", lambda: None)
    monkeypatch.setattr(provision, "root_disk", lambda: "/dev/sda")
    monkeypatch.setattr(provision, "partition_rows", lambda _disk: (
        initial_rows if not any(call[:3] == ["parted", "--script", "--align"]
                                for call in commands) else [*initial_rows, data_row]
    ))
    monkeypatch.setattr(provision.pathlib.Path, "is_symlink", lambda _self: False)
    monkeypatch.setattr(provision, "MOUNTPOINT", tmp_path / "solarminer")
    monkeypatch.setattr(provision, "MARKER", tmp_path / "etc" / "data-volume.uuid")
    monkeypatch.setattr(provision, "STATE", tmp_path / "solarminer-data-volume.state")
    monkeypatch.setattr(provision, "FSTAB", tmp_path / "etc" / "fstab")
    monkeypatch.setattr(provision.pathlib.Path, "mkdir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(provision, "write_fstab", lambda uuid: commands.append(["write-fstab", uuid]))
    monkeypatch.setattr(provision, "mount_data", lambda uuid: commands.append(["mount-data", uuid]))
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])

    def fake_run(args, **_kwargs):
        commands.append(args)
        if args[0] == "parted" and "print" in args:
            return PARTED.replace("/dev/nvme0n1", "/dev/sda")
        if args[0] == "findmnt" and "SOURCE" in args:
            return "/dev/sda2"
        if args[0] == "blkid":
            return "new-data-uuid"
        return ""

    monkeypatch.setattr(provision, "run", fake_run)
    monkeypatch.setattr(provision.subprocess, "run", lambda *_args, **_kwargs:
                        type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: FakeLock())

    assert provision.main() == 0
    assert ["parted", "--script", "--align", "optimal", "/dev/sda", "mkpart",
            provision.LABEL, "ext4", "70000MiB", "199999MiB"] in commands
    assert ["mkfs.ext4", "-F", "-L", provision.LABEL, "/dev/sda6"] in commands
    assert ["write-fstab", "new-data-uuid"] in commands
    assert ["mount-data", "new-data-uuid"] in commands
    assert provision.STATE.read_text(encoding="ascii").strip() == "created"


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
    rows = [("/dev/sda6", "solarminer_data", "ext4", "data-uuid", "126000000000")]
    partition = provision.find_existing_data_partition(rows)
    assert partition == rows[0]
    assert provision.ensure_ext4_data_partition(partition[0], partition[2], partition[3]) == "data-uuid"
    assert calls == []


def test_existing_named_non_ext4_partition_is_preserved_and_install_stops(monkeypatch):
    calls = []
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])
    monkeypatch.setattr(provision, "run", lambda args, **kwargs: calls.append(args) or "fresh-data-uuid\n")
    with pytest.raises(RuntimeError, match="SOLARMINER_DATA"):
        provision.ensure_ext4_data_partition("/dev/sda6", "vfat", "")
    assert calls == []


def test_existing_labelled_partition_without_filesystem_is_preserved(monkeypatch):
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])
    with pytest.raises(RuntimeError, match="SOLARMINER_DATA"):
        provision.ensure_ext4_data_partition("/dev/sda3", "", "")


def test_existing_named_partition_with_unknown_filesystem_is_preserved(monkeypatch):
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])
    with pytest.raises(RuntimeError, match="SOLARMINER_DATA"):
        provision.ensure_ext4_data_partition("/dev/sda3", "", "")


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


def test_ext4_partition_without_uuid_is_preserved_and_install_stops(monkeypatch):
    monkeypatch.setattr(provision, "mounted_targets", lambda _partition: [])
    monkeypatch.setattr(provision, "run", lambda *_args, **_kwargs: "")
    with pytest.raises(RuntimeError, match="SOLARMINER_DATA"):
        provision.ensure_ext4_data_partition("/dev/sda6", "ext4", "")


def test_duplicate_data_partition_labels_are_rejected():
    rows = [
        ("/dev/sda6", "SOLARMINER_DATA", "ext4", "uuid-a", "126000000000"),
        ("/dev/sda7", "solarminer_data", "ext4", "uuid-b", "126000000000"),
    ]
    with pytest.raises(RuntimeError, match="mais de uma partição"):
        provision.find_existing_data_partition(rows)


def test_unlabelled_large_ext4_partition_blocks_creation_of_replacement_data_volume():
    rows = [
        ("/dev/sda1", "", "ext4", "old-data-uuid", "126000000000"),
        ("/dev/sda2", "", "ext4", "root-uuid", "64000000000"),
    ]
    assert provision.find_unlabelled_large_ext4_partitions(rows, "/dev/sda2") == [rows[0]]


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
