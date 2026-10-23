# SolarMiner Gateway 0.6.61

- Use a robust median-based, bounded trend for household load forecasts so short noisy rises do not become a steadily increasing six-hour projection.
- Keep Home and Energy on the same Gateway-integrated battery SOC estimate, with consistent precision.
- Explain the missing PV nameplate capacity in the Owner production settings and invalidate cached daily forecasts when solar configuration changes.
- Do not reuse cached unavailable daily forecasts.
