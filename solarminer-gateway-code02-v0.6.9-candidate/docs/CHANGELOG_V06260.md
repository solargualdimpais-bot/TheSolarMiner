# SolarMiner Gateway CODE02 v0.6.260

## Battery input telemetry and Owner recovery consistency

- Read the two Deye low-voltage battery input channels and expose SOC, voltage, signed current, power and temperature per channel when those registers are returned.
- Treat the inverter's configured input count as an upper bound, then mark a bank detected only when its channel also reports a plausible live battery voltage. Persist detected channels as separate energy equipment and mark previously known channels offline when a successful poll no longer sees them.
- Aggregate signed power/current and charge/discharge power only across detected channels. Do not label one bank's SOC as the pack-wide SOC when multiple banks are live and there are no validated capacity weights; report pack energy above cutoff as unavailable in that case.
- Read the Deye cutoff SOC when fresh. Keep the register map explicitly marked as live-unverified; the Deye map is a community candidate and still needs validation against the exact inverter firmware/logger.
- Replace the PWA's nonfunctional remote Owner recovery form with an explicit local-only notice. The backend and security tests deliberately prohibit HTTP recovery endpoints; the PWA still lets the first Owner save the one-time recovery key offline.
- Validate the Ollama `/api/tags` response schema before enumerating models. A malformed response (including a missing or non-list `models` value) now produces a degraded, stage-specific diagnostic instead of raising `TypeError` and failing the whole status request; the Owner view shows the safe reason and HTTP status where available.
- Set `HOME` explicitly for the system bootstrap and its systemd unit so Ollama CLI checks do not panic or misidentify an already-installed runtime when launched outside an interactive shell.
- Replace the Qwen smoke check's 16-token `/api/generate` prompt and literal `OK` match with `/api/chat`, thinking disabled, and validation that a completed non-empty assistant response was returned. This reduces false negatives when the model spends output tokens on reasoning.
- Bump the packaged Gateway and PWA versions/cache so installed PWAs can fetch these changes.

## Validation limits

Automated tests can verify register decoding, persistence, arithmetic and UI behavior. They do not prove the channel assignments or scaling on a physical Deye, and they do not replace an end-to-end test on the Gateway hardware.
The bootstrap smoke check is covered by regression tests, but this release has not yet been validated with the real Qwen runtime or the full OpenClaude/MCP/PWA path on the Lenovo M720q.
