"""Read-only discovery of responsive hosts on networks directly attached to the Gateway."""
from __future__ import annotations

import concurrent.futures
import errno
import ipaddress
import json
import socket
import subprocess
from pathlib import Path
from typing import Any


MAX_ADDRESSES = 4096
WORKERS = 128
TCP_PORTS = (80, 443, 22, 53, 8080)
TCP_TIMEOUT_SECONDS = 0.12


def _run_ip_json(*args: str) -> Any:
    completed = subprocess.run(["ip", *args], check=True, capture_output=True,
                               text=True, timeout=3)
    return json.loads(completed.stdout or "[]")


def attached_ipv4_networks() -> list[dict[str, str]]:
    """Return usable IPv4 interface networks and their local interface addresses."""
    try:
        rows = _run_ip_json("-j", "-4", "addr", "show", "scope", "global")
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return []
    found: dict[tuple[str, str], dict[str, str]] = {}
    for interface in rows if isinstance(rows, list) else []:
        if not isinstance(interface, dict):
            continue
        name = str(interface.get("ifname") or "")[:32]
        for item in interface.get("addr_info", []):
            if not isinstance(item, dict) or item.get("family") != "inet":
                continue
            try:
                address = ipaddress.IPv4Interface(f"{item['local']}/{item['prefixlen']}")
            except (KeyError, ValueError):
                continue
            network = address.network
            if network.is_loopback or network.is_link_local or network.is_multicast:
                continue
            key = (name, str(network))
            found[key] = {"interface": name, "address": str(address.ip), "network": str(network)}
    return list(found.values())


def default_gateway_ips() -> set[str]:
    """Read default IPv4 routes; these addresses are routers by route-table evidence."""
    try:
        rows = _run_ip_json("-j", "-4", "route", "show", "default")
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return set()
    return {str(row["gateway"]) for row in rows
            if isinstance(row, dict) and isinstance(row.get("gateway"), str)}


def _probe(ip: str, ports: tuple[int, ...], timeout: float) -> tuple[str, list[int]] | None:
    """A successful connection or a TCP refusal proves the host responded."""
    open_ports: list[int] = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((ip, port))
            if result == 0:
                open_ports.append(port)
                return ip, open_ports
            # ECONNREFUSED means the host answered even though the port is closed.
            if result == errno.ECONNREFUSED:
                return ip, open_ports
        except OSError:
            pass
        finally:
            sock.close()
    return None


def _neighbor_macs(path: Path = Path("/proc/net/arp")) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii", errors="ignore").splitlines()[1:]
    except OSError:
        return {}
    result: dict[str, str] = {}
    for line in lines:
        fields = line.split()
        if len(fields) < 6 or fields[2] != "0x2":
            continue
        try:
            ipaddress.IPv4Address(fields[0])
        except ValueError:
            continue
        mac = fields[3].upper()
        if len(mac) == 17 and mac.count(":") == 5:
            result[fields[0]] = mac
    return result


def _ping(ip: str) -> bool:
    """Use the system ping binary as a fallback for hosts that filter TCP probes."""
    try:
        completed = subprocess.run(["ping", "-n", "-c", "1", "-W", "1", ip],
                                   capture_output=True, timeout=0.7)
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def scan_attached_networks() -> dict[str, Any]:
    """Probe hosts in directly connected private IPv4 networks, without router login."""
    networks = attached_ipv4_networks()
    route_rows = []
    targets: dict[str, dict[str, str]] = {}
    skipped: list[str] = []
    remaining = MAX_ADDRESSES
    for item in networks:
        try:
            network = ipaddress.ip_network(item["network"], strict=False)
        except (KeyError, ValueError):
            continue
        if not network.is_private or network.version != 4:
            continue
        host_count = max(0, network.num_addresses - 2)
        if network.prefixlen >= 31:
            host_count = network.num_addresses
        if host_count > remaining:
            skipped.append(str(network))
            continue
        remaining -= host_count
        route_rows.append(item)
        for host in network.hosts():
            ip = str(host)
            if ip == item["address"]:
                continue
            targets[ip] = item

    gateways = default_gateway_ips()
    responding: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(_probe, ip, TCP_PORTS, TCP_TIMEOUT_SECONDS) for ip in targets]
        for future in concurrent.futures.as_completed(futures):
            hit = future.result()
            if hit:
                ip, ports = hit
                responding[ip] = {"open_ports": ports, "methods": ["tcp"]}

        ping_futures = {executor.submit(_ping, ip): ip for ip in targets if ip not in responding}
        for future in concurrent.futures.as_completed(ping_futures):
            if future.result():
                responding[ping_futures[future]] = {"open_ports": [], "methods": ["icmp"]}

    mac_by_ip = _neighbor_macs()
    for ip in mac_by_ip:
        if ip in targets and ip not in responding:
            responding[ip] = {"open_ports": [], "methods": ["arp_neighbor"]}
    hosts = []
    for ip in sorted(responding, key=lambda value: int(ipaddress.IPv4Address(value))):
        iface = targets[ip]
        hosts.append({"ip": ip, "mac": mac_by_ip.get(ip), "interface": iface["interface"],
                      "network": iface["network"], "is_router": ip in gateways,
                      "open_ports": responding[ip]["open_ports"],
                      "discovery_methods": responding[ip]["methods"]})
    return {"networks": route_rows, "scanned_count": len(targets), "responsive_count": len(hosts),
            "hosts": hosts, "skipped_networks": skipped, "address_limit": MAX_ADDRESSES,
            "method": "bounded_tcp_probe_and_kernel_neighbor_table", "router_ips": sorted(gateways)}
