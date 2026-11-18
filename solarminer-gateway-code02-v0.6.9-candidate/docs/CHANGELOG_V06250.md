# SolarMiner Gateway CODE02 v0.6.250

## Intelligence bootstrap startup repair

- Create the Intelligence bootstrap runtime and state directories during Debian package configuration, before its timer can run. Refuse symlinked paths.
- Let the root one-shot bootstrap install its verified system runtime after its Tailscale and TLS health checks. Keep the long-running Intelligence agent under its separate unprivileged systemd sandbox.
- Package `zstd` as a declared, signed Debian dependency instead of running `apt-get update` and mutating the host from the bootstrap.
- Add regression checks for directory ordering, the bootstrap unit policy, and dependency handling.

The prior device report (`226/NAMESPACE`, missing environment file, and API `503`) is consistent with this startup chain failing before runtime setup. This source fix does not prove the exact post-rollback state of the physical Gateway. The next release must pass the Ubuntu CI build and package checks before it is used for a fresh installation. Physical installation and successful agent startup still require confirmation on the Lenovo.
