"""Bounded active discovery of hosts on directly connected private LANs."""
from __future__ import annotations

import concurrent.futures
import html
import ipaddress
import json
from pathlib import Path
import re
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


def _default_routes(route_output: str) -> list[dict[str, str]]:
    """Extract router next hops from Linux's IPv4 routing table."""
    try:
        routes = json.loads(route_output)
    except (TypeError, json.JSONDecodeError):
        return []
    found: dict[str, dict[str, str]] = {}
    for route in routes if isinstance(routes, list) else []:
        if not isinstance(route, dict) or route.get("dst", "default") != "default":
            continue
        try:
            address = ipaddress.ip_address(str(route.get("gateway") or ""))
        except ValueError:
            continue
        if address.version != 4 or not address.is_private:
            continue
        ip = str(address)
        found[ip] = {"ip": ip, "interface": str(route.get("dev") or "")[:32],
                     "classification": "default_gateway", "confidence": "confirmed_by_routing_table"}
    return [found[ip] for ip in sorted(found, key=lambda item: int(ipaddress.ip_address(item)))]


def _read_router_web_identity(address: str, timeout: float = 1.5) -> dict[str, str]:
    """Read only the public HTTP landing page; never follow redirects or submit credentials."""
    request = f"GET / HTTP/1.0\r\nHost: {address}\r\nAccept: text/html\r\nConnection: close\r\n\r\n".encode("ascii")
    try:
        with socket.create_connection((address, 80), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request)
            chunks: list[bytes] = []
            remaining = 16_384
            while remaining > 0:
                chunk = sock.recv(min(4096, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
    except OSError:
        return {"web_ui": "unavailable"}
    raw = b"".join(chunks).decode("latin-1", errors="ignore")
    headers, _, body = raw.partition("\r\n\r\n")
    status = re.match(r"HTTP/\d(?:\.\d)?\s+(\d{3})", headers)
    server = re.search(r"(?im)^Server:\s*([^\r\n]+)", headers)
    title = re.search(r"(?is)<title[^>]*>(.*?)</title\s*>", body)
    result = {"web_ui": "http", "http_status": status.group(1) if status else "unknown"}
    if server:
        result["server"] = re.sub(r"[^A-Za-z0-9 ._()+/-]", "", server.group(1))[:80]
    if title:
        clean_title = html.unescape(re.sub(r"<[^>]+>", " ", title.group(1)))
        clean_title = " ".join(clean_title.split())
        if clean_title:
            result["page_title"] = clean_title[:120]
    return result


def _probe(address: str, timeout: float) -> None:
    """A TCP attempt to a closed port still prompts ARP on a directly attached LAN."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect_ex((address, 80))
    except OSError:
        pass


def discover_private_lan_hosts(*, timeout: float = 0.25, arp_path: str | Path = "/proc/net/arp",
                              configured_router_ips: list[str] | None = None) -> dict[str, Any]:
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
    try:
        route_result = subprocess.run(
            ["ip", "-j", "-4", "route", "show", "default"],
            capture_output=True, text=True, timeout=4, check=False,
        )
        routers = _default_routes(route_result.stdout) if route_result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        routers = []
    route_ips = {router["ip"] for router in routers}
    for raw_ip in configured_router_ips or []:
        try:
            address = ipaddress.ip_address(str(raw_ip).strip())
        except ValueError:
            continue
        if address.version != 4 or not address.is_private:
            continue
        ip = str(address)
        if ip not in route_ips and not any(router["ip"] == ip for router in routers):
            routers.append({"ip": ip, "interface": "", "classification": "configured_router",
                            "confidence": "configured_by_owner"})
    addresses: set[str] = set()
    for network in networks:
        candidates = [str(address) for address in network.hosts()]
        if len(candidates) > MAX_SCAN_ADDRESSES:
            candidates = candidates[:MAX_SCAN_ADDRESSES]
            truncated = True
        addresses.update(candidates)
    addresses.update(router["ip"] for router in routers)
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
    host_ips = set(hosts.values())
    # Router identification is grounded in default routes or the owner's configured modem IP.
    for router in routers:
        router.update(_read_router_web_identity(router["ip"]))
        router["host_seen_in_scan"] = router["ip"] in host_ips
    return {
        "hosts": hosts,
        "routers": routers,
        "networks": [str(network) for network in networks],
        "scanned_count": len(addresses),
        "truncated": truncated,
    }
