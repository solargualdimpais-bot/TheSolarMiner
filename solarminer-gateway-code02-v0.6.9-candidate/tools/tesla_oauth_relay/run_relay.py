"""Run the public Tesla OAuth callback directly over HTTPS, without a proxy."""

from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    certificate = os.environ["SOLARMINER_RELAY_TLS_CERT"]
    private_key = os.environ["SOLARMINER_RELAY_TLS_KEY"]
    uvicorn.run(
        "relay:app",
        host="0.0.0.0",
        port=443,
        ssl_certfile=certificate,
        ssl_keyfile=private_key,
        access_log=False,
        server_header=False,
    )
