# Gateway 0.6.209

- Wait for 60 seconds of continuous Deye no-response failures before searching the LAN for another IP.
- Rate-limit unsuccessful Deye IP rediscovery attempts to once per minute; a valid Modbus response cancels the failure timer.
- Reduce repeated Owner PWA requests: Home refreshes at most every 10 seconds and Tuya/Shelly status polling every 15 seconds while the page is visible.
