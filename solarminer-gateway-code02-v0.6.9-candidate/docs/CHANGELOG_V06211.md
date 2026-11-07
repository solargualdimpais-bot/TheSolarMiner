# Gateway 0.6.211

- Serve the I/O-free health endpoint directly on the ASGI event loop instead of the shared synchronous route thread pool. Slow hardware reads can no longer consume a worker slot needed by the watchdog liveness probe.
- Keeps the temporary watchdog action pause from 0.6.210: continue diagnostics but do not automatically restart services or roll back.
