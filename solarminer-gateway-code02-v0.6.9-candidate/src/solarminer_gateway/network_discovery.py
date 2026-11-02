"""Bounded active discovery of hosts on directly connected private LANs."""
from __future__ import annotations

import concurrent.futures
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
from typing import Any

MAX_SCAN_ADDRESSES = 4096
MAX_WORKERS = 128


def _private_lan_network_details(ip_output: str) -> tuple[list[ipaddress.IPv4Network], bool]:
    try:
        interfaces = json.loads(ip_output)
    except (TypeError, json.JSONDecodeError):
        return [], False
    networks: set[ipaddress.IPv4Network] = set()
    truncated = False
    for interface in interfaces if isinstance(interfaces, list) else []:
        name = str(interface.get("ifname", "")).lower()
        if (not name or name == "lo" or name.startswith(("tailscale", "docker", "br-", "veth"))
                or "UP" not in interface.get("flags", [])):
            continue
        for info in interface.get("addr_info", []):
            if info.get("family") != "inet":
                continue
            try:
                address = ipaddress.ip_address(info.get("local", ""))
                prefix = int(info.get("prefixlen", 0))
                if address.version != 4 or not address.is_private or address.is_loopback:
                    continue
                network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
                if network.num_addresses > MAX_SCAN_ADDRESSES:
                    network = ipaddress.ip_network((address, 20), strict=False)
                    truncated = True
                networks.add(network)
            except (ValueError, TypeError):
                continue
    return sorted(networks, key=lambda item: (int(item.network_address), item.prefixlen)), truncated


def _private_lan_networks(ip_output: str) -> list[ipaddress.IPv4Network]:
    """Return bounded private IPv4 ranges from directly attached interfaces."""
    return _private_lan_network_details(ip_output)[0]


def _probe(address: str, timeout: float) -> None:
    """A TCP attempt to a closed port still prompts ARP on a directly attached LAN."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect_ex((address, 80))
    except OSError:
        pass


def discover_private_lan_hosts(*, timeout: float = 0.25, arp_path: str | Path = "/proc/net/arp") -> dict[str, Any]:
    """Sweep bounded directly attached RFC1918 networks, then return learned MAC/IP pairs.

    This is best-effort discovery: hosts that sleep, filter all traffic, use
    client isolation, or sit behind another routed VLAN may not answer.
    """
    try:
        result = subprocess.run(
            ["ip", "-j", "-4", "addr", "show", "scope", "global"],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"hosts": {}, "networks": [], "scanned_count": 0, "truncated": False}
    if result.returncode != 0:
        return {"hosts": {}, "networks": [], "scanned_count": 0, "truncated": False}
    networks, truncated = _private_lan_network_details(result.stdout)
    addresses: set[str] = set()
    for network in networks:
        candidates = [str(address) for address in network.hosts()]
        if len(candidates) > MAX_SCAN_ADDRESSES:
            candidates = candidates[:MAX_SCAN_ADDRESSES]
            truncated = True
        addresses.update(candidates)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(lambda address: _probe(address, timeout), addresses))
    hosts: dict[str, str] = {}
    try:
        lines = Path(arp_path).read_text(encoding="ascii", errors="ignore").splitlines()[1:]
    except OSError:
        lines = []
    for line in lines:
        fields = line.split()
        if len(fields) < 6 or fields[2] != "0x2" or fields[0] not in addresses:
            continue
        try:
            mac = fields[3].upper().replace("-", ":")
            address = ipaddress.ip_address(fields[0])
        except ValueError:
            continue
        if address.version == 4 and address.is_private and len(mac) == 17:
            hosts[mac] = str(address)
    return {
        "hosts": hosts,
        "networks": [str(network) for network in networks],
        "scanned_count": len(addresses),
        "truncated": truncated,
    }
