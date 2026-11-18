# SolarMiner Gateway CODE02 v0.6.253

## Intelligence installation and recovery

- Add an Owner-only action to install, repair, or update Intelligence components from the PWA. It requests a fixed systemd unit through the root broker; the PWA cannot submit shell commands, paths, or alternate units. Gateway package updates remain in the existing Updates menu.
- Keep the existing Tailscale, MagicDNS HTTPS, certificate, and local Gateway health checks in the bootstrap. A failed prerequisite leaves the bootstrap failed with progress/error status instead of installing around it.
- Make the bootstrap repeatable so a partial first installation or an update can retry missing or mismatched Ollama, Qwen, Node, and OpenClaude components. Successful reruns restart and verify the resident service.
- Show independent installation state for Ollama, Qwen, Node, and OpenClaude in Owner. Model download stage, byte counts, and percentage continue to refresh automatically.
- Record manual recovery requests in the Gateway audit log and suppress duplicate requests while progress reports a running bootstrap.

## Validation

The release workflow must pass its Linux tests, PWA tests, Debian package build, signing, and USB bundle checks before this version is published. The physical Lenovo installation still needs confirmation on that machine.
