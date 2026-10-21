from pathlib import Path
import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from solarminer_gateway.identity import identity_fingerprint, provision_identity
from solarminer_gateway import cli


def test_identity_is_created_once_and_kept_stable(tmp_path):
    private = tmp_path / "gateway-identity.key"
    public = tmp_path / "gateway-identity.pub.pem"

    first = provision_identity(private, public)
    private_bytes = private.read_bytes()
    second = provision_identity(private, public)

    assert len(first) == 64
    assert second == first
    assert private.read_bytes() == private_bytes
    assert identity_fingerprint(private, public) == first
    if os.name == "posix":
        assert private.stat().st_mode & 0o777 == 0o600


def test_identity_refuses_to_replace_an_incomplete_pair(tmp_path):
    private = tmp_path / "gateway-identity.key"
    public = tmp_path / "gateway-identity.pub.pem"
    private.write_text("keep existing file", encoding="utf-8")

    with pytest.raises(RuntimeError, match="incomplete"):
        provision_identity(private, public)

    assert private.read_text(encoding="utf-8") == "keep existing file"
    assert not public.exists()


def test_identity_refuses_mismatched_existing_keys(tmp_path):
    private = tmp_path / "gateway-identity.key"
    public = tmp_path / "gateway-identity.pub.pem"
    first = Ed25519PrivateKey.generate()
    second = Ed25519PrivateKey.generate()
    private.write_bytes(first.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public.write_bytes(second.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    with pytest.raises(RuntimeError, match="does not match"):
        provision_identity(private, public)


def test_fingerprint_requires_matching_ed25519_pair(tmp_path):
    private = tmp_path / "gateway-identity.key"
    public = tmp_path / "gateway-identity.pub.pem"
    provision_identity(private, public)
    assert identity_fingerprint(Path(private), Path(public)) == identity_fingerprint(private, public)


def test_owner_bootstrap_cli_provisions_stable_service_identity(tmp_path, monkeypatch):
    private = tmp_path / "gateway-identity.key"
    public = tmp_path / "gateway-identity.pub.pem"
    monkeypatch.setattr(cli, "GATEWAY_PRIVATE_IDENTITY_PATH", private)
    monkeypatch.setattr(cli, "GATEWAY_PUBLIC_IDENTITY_PATH", public)
    monkeypatch.setattr(cli.shutil, "chown", lambda *_args, **_kwargs: None)

    first = cli.provision_gateway_identity()
    second = cli.provision_gateway_identity()

    assert first == second
    assert identity_fingerprint(private, public) == first
