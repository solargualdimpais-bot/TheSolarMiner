"""Provision the per-Gateway Ed25519 identity without rotating existing keys."""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def provision_identity(private_path: Path, public_path: Path) -> str:
    private_path = Path(private_path)
    public_path = Path(public_path)
    private_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    public_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    private_exists, public_exists = private_path.exists(), public_path.exists()
    # The private identity is stored on the persistent data volume while the
    # public half lives on the OS volume. Reinstalling Debian can therefore
    # leave a valid private key but remove its public counterpart. Recover the
    # public half from that private key without rotating or overwriting either
    # key. A public key without its private counterpart remains unrecoverable.
    if private_exists and not public_exists:
        private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        if not isinstance(private, Ed25519PrivateKey):
            raise RuntimeError("Existing Gateway private identity is not Ed25519")
        public_bytes = private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        fd, name = tempfile.mkstemp(prefix=f".{public_path.name}.", dir=public_path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o644)
                stream.write(public_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, public_path)
        except FileExistsError as exc:
            raise RuntimeError("Gateway public identity appeared during recovery; refusing to overwrite it") from exc
        finally:
            temporary.unlink(missing_ok=True)
        public_exists = True
    if private_exists != public_exists:
        raise RuntimeError("Gateway identity is incomplete; refusing to replace either key")

    if private_exists:
        private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        public = serialization.load_pem_public_key(public_path.read_bytes())
        if not isinstance(private, Ed25519PrivateKey) or not isinstance(public, Ed25519PublicKey):
            raise RuntimeError("Existing Gateway identity is not Ed25519")
        derived = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        configured = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        if derived != configured:
            raise RuntimeError("Existing Gateway identity key pair does not match")
        os.chmod(private_path, 0o600)
        os.chmod(public_path, 0o644)
        import hashlib
        return hashlib.sha256(configured).hexdigest()

    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public_bytes = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    created: list[Path] = []
    linked_private = False
    try:
        for destination, data, mode in ((private_path, private_bytes, 0o600), (public_path, public_bytes, 0o644)):
            fd, name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
            temp_path = Path(name)
            created.append(temp_path)
            with os.fdopen(fd, "wb") as stream:
                os.chmod(temp_path, mode)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        # Hard-link with exclusive creation so concurrent runs never overwrite an identity.
        os.link(created[0], private_path)
        linked_private = True
        os.link(created[1], public_path)
    except FileExistsError as exc:
        if linked_private:
            try:
                if private_path.stat().st_ino == created[0].stat().st_ino:
                    private_path.unlink()
            except FileNotFoundError:
                pass
        raise RuntimeError("Gateway identity appeared during provisioning; refusing to overwrite it") from exc
    except OSError:
        if linked_private:
            try:
                if private_path.stat().st_ino == created[0].stat().st_ino:
                    private_path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for temp_path in created:
            temp_path.unlink(missing_ok=True)
    import hashlib
    return hashlib.sha256(private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )).hexdigest()


def identity_fingerprint(private_path: Path, public_path: Path) -> str:
    private = serialization.load_pem_private_key(Path(private_path).read_bytes(), password=None)
    public = serialization.load_pem_public_key(Path(public_path).read_bytes())
    if not isinstance(private, Ed25519PrivateKey) or not isinstance(public, Ed25519PublicKey):
        raise RuntimeError("Gateway identity is not Ed25519")
    derived = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    configured = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if derived != configured:
        raise RuntimeError("Gateway identity key pair does not match")
    import hashlib
    return hashlib.sha256(configured).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision or inspect the local SolarMiner Gateway identity")
    parser.add_argument("action", choices=("provision", "fingerprint"))
    parser.add_argument("--private", default="/var/lib/solarminer/gateway-identity.key")
    parser.add_argument("--public", default="/etc/solarminer/gateway-identity.pub.pem")
    args = parser.parse_args()
    private_path, public_path = Path(args.private), Path(args.public)
    if args.action == "provision":
        fingerprint = provision_identity(private_path, public_path)
    else:
        fingerprint = identity_fingerprint(private_path, public_path)
    print(fingerprint)


if __name__ == "__main__":
    main()
