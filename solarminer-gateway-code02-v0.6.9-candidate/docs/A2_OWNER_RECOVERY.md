# CODE 01 / A2 — Owner recovery runbook

## Scope and trust model

A2 adds local owner recovery to A1b v0.4.2. It does not add HTTP recovery routes, an external service, a second session system, or a second RBAC authority. The owner remains an active owner throughout recovery; the last-active-owner invariant is unchanged.

Recovery commands require a real interactive terminal, OS root privileges, and a systemd check proving `solarminer-gateway.service` is not active. Stop the service before running any command. If the environment cannot establish that the service is stopped, do not bypass the check.

## Initial setup and upgrades

On a fresh USB installation, `solarminer-gateway owner-password` stores a temporary Argon2id verifier for the password chosen in the local console. The first PWA registration requires that password, an allowed HTTPS origin and fresh Ed25519 device proof. The bootstrap transaction consumes the temporary verifier while creating the Owner. Its success response contains a one-time `recovery_key`; the client shows it once and must not store it in logs, telemetry, support tickets, shell history, or temporary files. Store the key offline. The Gateway persists only a domain-separated SHA-256 verifier because the recovery key contains 32 CSPRNG bytes (256 bits of entropy); human-chosen account passwords use Argon2id.

An existing A1b database does not have a recoverable key because the old release never displayed one. While the owner still has the current password and an active associated device, stop the service and run:

```sh
systemctl stop solarminer-gateway.service
solarminer-gateway recovery-setup
```

The command asks for the current password without echo, the active device ID, and a signature over a fresh challenge. The associated device's private key stays on that device. This command creates a key or rotates an existing key; it requires explicit confirmation and invalidates the previous key.

## Offline recovery

Use when the owner has lost the password or authorized device but still has the offline recovery key:

```sh
systemctl stop solarminer-gateway.service
solarminer-gateway recovery
```

The command requests the recovery key through hidden interactive input, a new password twice, a new Ed25519 public key, a MAC value used only as metadata, and a signature over a fresh challenge. It does not accept the recovery key in arguments or environment variables. The new device signs the exact UTF-8 challenge message displayed by the command; its private key is never sent to or stored by the Gateway.

For a device that uses an OpenSSL-readable Ed25519 private-key file, the challenge can be signed locally without sending the private key anywhere. Copy the challenge fields printed by the CLI and write the exact message bytes without a trailing newline. For normal recovery/emergency the fields are the prefix, purpose, owner UUID and challenge hex, separated by newlines:

```sh
printf '%s\n%s\n%s\n%s' \
  'SOLARMiner-GATEWAY-DEVICE-PROOF-V1' 'recovery' '<owner-uuid>' '<challenge-hex>' > challenge.txt
openssl pkeyutl -sign -inkey /path/to/device-private.pem -rawin -in challenge.txt -out signature.bin
od -An -v -tx1 signature.bin | tr -d ' \n'
```

Use `emergency` as the purpose for emergency recovery. For `recovery-setup`, the signed fields are the prefix, `setup`, owner UUID, existing device UUID and challenge hex, in that order. Paste the resulting hexadecimal signature into the CLI. The example file contains only the public challenge, not the recovery key or private key.

On success, a single SQLite transaction changes the password verifier, increments `credential_version`, revokes previous owner sessions, revokes the owner's prior devices globally (including sessions and associations for any other account that shared those devices), registers the new device, consumes the old recovery key, creates a replacement verifier, and writes the success audit records. Any other account that shared a lost device must be enrolled on a different active device. The replacement key is displayed only after commit. The old password, sessions, and recovery key remain invalid.

## Emergency recovery

Use only if the offline recovery key is also lost:

```sh
sudo systemctl stop solarminer-gateway.service
sudo solarminer-gateway emergency-reset
```

This command requires root, a stopped service, an explicit `EMERGENCY-RESET` confirmation, a new password, and a fresh Ed25519 device proof. It creates a consistent SQLite backup using SQLite's backup API before mutation, verifies `PRAGMA integrity_check`, and stores it under `backup/emergency-<timestamp>-<id>/gateway-pre-emergency.db` relative to the database directory. The run directory is mode `0700`; the backup file is mode `0600` and root-owned when executed as root. Existing backup files/directories are not overwritten.

The procedure does not empty or recreate the database. It preserves users and unrelated data, updates the selected active owner's credentials, revokes sessions and prior device associations for that owner, registers the new device, rotates the recovery key, and writes success audit records in the same transaction. If the transaction or audit fails before commit, the mutation rolls back and the backup remains. The backup contains sensitive password/recovery verifiers and session hashes, not plaintext passwords, recovery keys, bearer tokens, or private device keys; keep it access-controlled.

## Failure after commit

If the transaction commits but the terminal cannot receive the replacement recovery key, the key cannot be reconstructed from its verifier. The CLI reports that the operation committed but delivery failed. Do not claim that the owner has the replacement key. Use the emergency procedure to rotate the key again; the database is not reset.

## Audit and secrets

Audit records distinguish started/attempted, denied/failed, and successful operations. Success events are inserted inside the protected transaction and are not committed ahead of the mutation. If a failed transaction rolls back, a best-effort failure event is written separately without secret material; if the database audit itself is unavailable, a non-secret warning is logged and the operation remains unsuccessful.

Passwords and recovery keys are read interactively without echo. They are never accepted as command-line arguments or environment variables. Private Ed25519 keys never enter the Gateway. The MAC address is declared metadata and is not treated as identity proof. No recovery key is accepted by any HTTP endpoint.

## Operational limitations

The A2 source tests do not replace installation and lifecycle validation on an isolated Debian VM with active systemd, nor hardware testing. The package must not be treated as validated on physical hardware until those tests have actually been run.
