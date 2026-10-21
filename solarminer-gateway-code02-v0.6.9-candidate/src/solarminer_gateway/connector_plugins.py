"""Built-in read-only connector primitives.

The TCP probe performs only a TCP connect/close handshake. It sends no application
payload and cannot claim protocol identity or device capabilities.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Any


def _validate_private_ip(host: str) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("ip_literal_required") from exc
    if not (address.is_private or address.is_link_local):
        raise ValueError("private_or_link_local_address_required")
    if address.is_multicast or address.is_unspecified or address.is_loopback:
        raise ValueError("target_address_not_allowed")
    return str(address)


def tcp_readonly_probe(host: str, port: int, timeout_seconds: float = 1.5) -> dict[str, Any]:
    """Check transport reachability only; no protocol command or payload is sent."""
    address = _validate_private_ip(host)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid_port")
    if not isinstance(timeout_seconds, (int, float)) or not 0.2 <= timeout_seconds <= 3.0:
        raise ValueError("invalid_timeout")
    try:
        with socket.create_connection((address, port), timeout=float(timeout_seconds)):
            return {
                "result": "TCP_REACHABLE",
                "host": address,
                "port": port,
                "protocol_identified": False,
                "device_capabilities_verified": False,
                "payload_sent": False,
            }
    except OSError as exc:
        return {
            "result": "TCP_UNREACHABLE",
            "host": address,
            "port": port,
            "error_type": type(exc).__name__,
            "protocol_identified": False,
            "device_capabilities_verified": False,
            "payload_sent": False,
        }
