from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from solarminer_gateway import updates


def _trusted_test_stat(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_lstat = Path.lstat

    def lstat(self: Path):
        result = real_lstat(self)
        if self == path:
            return SimpleNamespace(st_mode=result.st_mode, st_uid=0, st_size=result.st_size)
        return result

    monkeypatch.setattr(Path, "lstat", lstat)


def _write_allowlist(path: Path, *, repository: str = "https://github.com/solarminer/releases") -> None:
    path.write_text(json.dumps({
        "repositories": {
            repository: {
                "manifest_url": "https://github.com/solarminer/releases/releases/latest/download/manifest.json",
                "manifest_origins": ["https://github.com", "https://release-assets.githubusercontent.com"],
                "package_origins": ["https://github.com", "https://release-assets.githubusercontent.com"],
            }
        }
    }), encoding="utf-8")
    path.chmod(0o644)


def test_normalize_github_repository_url_accepts_only_repository_root() -> None:
    assert updates.normalize_github_repository_url(
        "https://GitHub.com/SolarMiner/Releases/"
    ) == "https://github.com/solarminer/releases"


@pytest.mark.parametrize("value", [
    "http://github.com/solarminer/releases",
    "https://github.com.evil.test/solarminer/releases",
    "https://github.com/solarminer/releases/releases",
    "https://user:password@github.com/solarminer/releases",
    "https://github.com/solarminer/releases?token=secret",
    "https://github.com/solarminer//releases",
    "https://github.com/solarminer/releases///",
    "https://github.com/solarminer/releases#fragment",
])
def test_normalize_github_repository_url_rejects_untrusted_urls(value: str) -> None:
    with pytest.raises(updates.UpdateValidationError):
        updates.normalize_github_repository_url(value)


def test_load_update_source_resolves_only_administrator_allowlisted_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "sources.json"
    _write_allowlist(config)
    _trusted_test_stat(config, monkeypatch)

    source = updates.load_update_source("https://github.com/SolarMiner/Releases", config)

    assert source["repository_url"] == "https://github.com/solarminer/releases"
    assert source["manifest_url"].startswith("https://github.com/")
    assert source["manifest_origins"] == {"https://github.com", "https://release-assets.githubusercontent.com"}
    assert source["package_origins"] == {"https://github.com", "https://release-assets.githubusercontent.com"}


def test_load_update_source_rejects_repository_not_allowlisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "sources.json"
    _write_allowlist(config)
    _trusted_test_stat(config, monkeypatch)

    with pytest.raises(updates.UpdateValidationError, match="repository_not_allowlisted"):
        updates.load_update_source("https://github.com/other/repo", config)


def test_load_update_source_rejects_group_or_world_writable_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "sources.json"
    _write_allowlist(config)
    config.chmod(0o666)
    _trusted_test_stat(config, monkeypatch)

    with pytest.raises(updates.UpdateValidationError, match="configuration_unsafe"):
        updates.load_update_source("https://github.com/solarminer/releases", config)


def test_load_update_source_rejects_untrusted_manifest_origins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "sources.json"
    _write_allowlist(config)
    document = json.loads(config.read_text(encoding="utf-8"))
    document["repositories"]["https://github.com/solarminer/releases"]["manifest_origins"] = ["http://github.com"]
    config.write_text(json.dumps(document), encoding="utf-8")
    config.chmod(0o644)
    _trusted_test_stat(config, monkeypatch)

    with pytest.raises(updates.UpdateValidationError, match="update_origin_must_be_https_origin"):
        updates.load_update_source("https://github.com/solarminer/releases", config)
