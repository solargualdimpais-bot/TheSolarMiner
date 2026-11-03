"""Read-only discovery of responsive hosts on networks directly attached to the Gateway."""
from __future__ import annotations

import concurrent.futures
import errno
import fcntl
import ipaddress
import json
import logging
import re
import select
import socket
import struct
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from typing import Any


LOG = logging.getLogger(__name__)
MAX_ADDRESSES = 4096
WORKERS = 128
TCP_PORTS = (80, 443, 22, 53, 8080)
TCP_TIMEOUT_SECONDS = 0.12
ARP_SETTLE_SECONDS = 1.0
DISCOVERY_LISTEN_SECONDS = 1.25
SSDP_GROUP = "239.255.255.250"
MDNS_GROUP = "224.0.0.251"
MDNS_SERVICES = (
    "_services._dns-sd._udp.local", "_http._tcp.local", "_workstation._tcp.local",
    "_device-info._tcp.local", "_googlecast._tcp.local", "_airplay._tcp.local",
    "_hap._tcp.local", "_ipp._tcp.local", "_printer._tcp.local", "_smb._tcp.local",
)
OUI_FILES = (
    Path("/usr/share/arp-scan/ieee-oui.txt"), Path("/usr/share/ieee-data/oui.txt"),
    Path("/usr/share/nmap/nmap-mac-prefixes"), Path("/usr/share/wireshark/manuf"),
)


def _run_ip_json(*args: str) -> Any:
    completed = subprocess.run(["ip", *args], check=True, capture_output=True,
                               text=True, timeout=3)
    return json.loads(completed.stdout or "[]")


def _attached_ipv4_networks() -> tuple[list[dict[str, str]], str | None]:
    """Return eligible IPv4 interface networks and a safe discovery error, if any."""
    command_failed = False
    try:
        # Do not ask `ip` to pre-filter by scope: interface metadata is not
        # consistent across virtual, bridge and appliance network drivers.
        rows = _run_ip_json("-j", "-4", "addr", "show")
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        command_failed = True
        rows = []
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
    # Some constrained systemd environments or older iproute2 builds can
    # return an empty JSON list even though Linux has an addressed interface.
    # AF_INET ioctl is allowed by the service sandbox and avoids Netlink/ip.
    if not found:
        found.update(_ioctl_ipv4_interfaces())
    error = None if found else (
        "interface_discovery_failed" if command_failed else "no_ipv4_address_on_interfaces")
    return list(found.values()), error


def _ioctl_ipv4_interfaces() -> dict[tuple[str, str], dict[str, str]]:
    """Fallback interface address enumeration using AF_INET ioctls."""
    ioctl_address = 0x8915  # SIOCGIFADDR
    ioctl_netmask = 0x891B  # SIOCGIFNETMASK
    found: dict[tuple[str, str], dict[str, str]] = {}
    try:
        names = [entry.name for entry in Path("/sys/class/net").iterdir()]
    except OSError:
        return found
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for name in names:
                try:
                    request = struct.pack("256s", name.encode("ascii")[:15])
                    address_raw = fcntl.ioctl(sock.fileno(), ioctl_address, request)
                    netmask_raw = fcntl.ioctl(sock.fileno(), ioctl_netmask, request)
                    address = ipaddress.IPv4Address(address_raw[20:24])
                    netmask = ipaddress.IPv4Address(netmask_raw[20:24])
                    interface = ipaddress.IPv4Interface(f"{address}/{netmask}")
                except (OSError, UnicodeEncodeError, ValueError):
                    continue
                network = interface.network
                if network.is_loopback or network.is_link_local or network.is_multicast:
                    continue
                key = (name, str(network))
                found[key] = {"interface": name, "address": str(address),
                              "network": str(network)}
    except OSError:
        return found
    return found


def attached_ipv4_networks() -> list[dict[str, str]]:
    """Return usable IPv4 interface networks and their local interface addresses."""
    return _attached_ipv4_networks()[0]


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


def _ping(ip: str) -> bool:
    """Use the system ping binary as a fallback for hosts that filter TCP probes."""
    try:
        completed = subprocess.run(["ping", "-n", "-c", "1", "-W", "1", ip],
                                   capture_output=True, timeout=0.7)
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _build_arp_request(source_mac: str, source_ip: str, target_ip: str) -> bytes:
    """Build a broadcast Ethernet ARP request for one IPv4 address."""
    source = bytes.fromhex(re.sub(r"[^0-9A-Fa-f]", "", source_mac))
    if len(source) != 6:
        raise ValueError("invalid_interface_mac")
    ethernet = struct.pack("!6s6sH", b"\xff" * 6, source, 0x0806)
    arp = struct.pack("!HHBBH6s4s6s4s", 1, 0x0800, 6, 4, 1, source,
                      socket.inet_aton(source_ip), b"\x00" * 6,
                      socket.inet_aton(target_ip))
    return ethernet + arp


def _parse_arp_reply(frame: bytes) -> tuple[str, str] | None:
    """Extract a valid sender IPv4/MAC pair from an Ethernet ARP reply."""
    if len(frame) < 42:
        return None
    try:
        _dst, _src, ethertype = struct.unpack_from("!6s6sH", frame, 0)
        htype, ptype, hlen, plen, opcode = struct.unpack_from("!HHBBH", frame, 14)
        if (ethertype, htype, ptype, hlen, plen, opcode) != (0x0806, 1, 0x0800, 6, 4, 2):
            return None
        mac = ":".join(f"{value:02X}" for value in frame[22:28])
        ip = socket.inet_ntoa(frame[28:32])
        if mac == "00:00:00:00:00:00" or mac.startswith(("01:", "33:33:")):
            return None
        return ip, mac
    except (OSError, struct.error, ValueError):
        return None


def _active_arp_sweep(interface: str, source_ip: str, targets: list[str]) -> dict[str, str]:
    """Send real Ethernet ARP requests and collect replies on the selected NIC."""
    packet_family = getattr(socket, "AF_PACKET", None)
    if packet_family is None:
        raise OSError("raw_packet_socket_unavailable")
    source_mac = Path("/sys/class/net", interface, "address").read_text(
        encoding="ascii").strip()
    sock = socket.socket(packet_family, socket.SOCK_RAW, socket.htons(0x0806))
    found: dict[str, str] = {}
    try:
        sock.bind((interface, 0))
        sent = 0
        send_error: OSError | None = None
        for ip in targets:
            try:
                sock.sendto(_build_arp_request(source_mac, source_ip, ip),
                            (interface, socket.htons(0x0806)))
                sent += 1
            except OSError as exc:
                send_error = exc
        if targets and not sent:
            raise OSError("active_arp_send_failed") from send_error
        deadline = time.monotonic() + ARP_SETTLE_SECONDS
        while time.monotonic() < deadline:
            ready, _, _ = select.select([sock], [], [], min(0.1, deadline - time.monotonic()))
            if not ready:
                continue
            try:
                frame = sock.recv(2048)
            except OSError:
                break
            reply = _parse_arp_reply(frame)
            if reply and reply[0] in targets:
                found[reply[0]] = reply[1]
    finally:
        sock.close()
    return found


def _ssdp_discovery(source_ip: str) -> dict[str, dict[str, str]]:
    """Collect UPnP/SSDP advertisements from one directly attached interface."""
    request = ("M-SEARCH * HTTP/1.1\r\n"
               f"HOST: {SSDP_GROUP}:1900\r\n"
               'MAN: "ssdp:discover"\r\n'
               "MX: 1\r\nST: ssdp:all\r\n\r\n").encode("ascii")
    found: dict[str, dict[str, str]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(source_ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.bind((source_ip, 0))
        sock.settimeout(0.2)
        sock.sendto(request, (SSDP_GROUP, 1900))
        deadline = time.monotonic() + DISCOVERY_LISTEN_SECONDS
        while time.monotonic() < deadline:
            try:
                payload, peer = sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            headers: dict[str, str] = {}
            for line in payload.decode("utf-8", "ignore").splitlines()[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()[:512]
            item = found.setdefault(peer[0], {})
            item["ssdp_server"] = headers.get("server", item.get("ssdp_server", ""))
            item["ssdp_name"] = headers.get("usn", item.get("ssdp_name", ""))
            item["ssdp_type"] = headers.get("st", item.get("ssdp_type", ""))
            item["ssdp_location"] = headers.get("location", item.get("ssdp_location", ""))
    except OSError:
        return found
    finally:
        sock.close()
    return found


def _dns_name(packet: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    cursor, end, jumps = offset, None, 0
    while cursor < len(packet) and jumps < 16:
        length = packet[cursor]
        if length == 0:
            cursor += 1
            return ".".join(labels).rstrip("."), end if end is not None else cursor
        if length & 0xC0 == 0xC0:
            if cursor + 1 >= len(packet):
                break
            pointer = ((length & 0x3F) << 8) | packet[cursor + 1]
            if end is None:
                end = cursor + 2
            cursor = pointer
            jumps += 1
            continue
        cursor += 1
        if cursor + length > len(packet):
            break
        labels.append(packet[cursor:cursor + length].decode("utf-8", "ignore"))
        cursor += length
    return "".join(labels).rstrip("."), end if end is not None else cursor


def _mdns_query(name: str) -> bytes:
    encoded = b"".join(bytes((len(label.encode("ascii")),)) + label.encode("ascii")
                       for label in name.split(".")) + b"\x00"
    return struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0) + encoded + struct.pack("!HH", 12, 1)


def _mdns_records(packet: bytes) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Return local A records and descriptive aliases parsed from an mDNS response."""
    ips: dict[str, str] = {}
    descriptions: dict[str, dict[str, str]] = {}
    try:
        _ident, _flags, questions, answers, authority, additional = struct.unpack_from("!HHHHHH", packet, 0)
        offset = 12
        for _ in range(questions):
            _name, offset = _dns_name(packet, offset)
            offset += 4
        records: list[tuple[str, int, bytes, int]] = []
        for _ in range(answers + authority + additional):
            owner, offset = _dns_name(packet, offset)
            rtype, _klass, _ttl, size = struct.unpack_from("!HHIH", packet, offset)
            offset += 10
            data_offset = offset
            data = packet[offset:offset + size]
            offset += size
            if len(data) != size:
                break
            records.append((owner.lower(), rtype, data, data_offset))
        aliases: dict[str, str] = {}
        for owner, rtype, data, data_offset in records:
            if rtype == 1 and len(data) == 4:
                ips[owner] = socket.inet_ntoa(data)
            elif rtype == 12:
                target, _ = _dns_name(packet, data_offset)
                aliases[target.lower()] = owner
            elif rtype == 33 and len(data) >= 7:
                target, _ = _dns_name(packet, data_offset + 6)
                aliases[target.lower()] = owner
            elif rtype == 16:
                parts: list[str] = []
                cursor = 0
                while cursor < len(data):
                    size = data[cursor]
                    cursor += 1
                    parts.append(data[cursor:cursor + size].decode("utf-8", "ignore"))
                    cursor += size
                meta = descriptions.setdefault(owner, {})
                for part in parts:
                    if "=" in part:
                        key, value = part.split("=", 1)
                        if key.lower() in {"model", "manufacturer", "product", "name", "fn"}:
                            meta[{"fn": "friendly_name", "name": "friendly_name", "product": "model"}.get(key.lower(), key.lower())] = value[:160]
        for host_name, ip in ips.items():
            desc = descriptions.setdefault(ip, {})
            desc.setdefault("hostname", host_name)
            desc.update(descriptions.get(host_name, {}))
            for alias, owner in aliases.items():
                if alias == host_name or alias.endswith("." + host_name):
                    desc.setdefault("mdns_name", alias)
                    owner_desc = descriptions.get(owner)
                    if owner_desc:
                        desc.update(owner_desc)
    except (struct.error, IndexError, ValueError):
        return {}, {}
    return ips, descriptions


def _mdns_discovery(source_ip: str) -> dict[str, dict[str, str]]:
    """Query common DNS-SD service types and collect local mDNS A/TXT responses."""
    found: dict[str, dict[str, str]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.bind(("", 5353))
        membership = socket.inet_aton(MDNS_GROUP) + socket.inet_aton(source_ip)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(source_ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        for name in MDNS_SERVICES:
            sock.sendto(_mdns_query(name), (MDNS_GROUP, 5353))
        sock.settimeout(0.2)
        deadline = time.monotonic() + DISCOVERY_LISTEN_SECONDS
        while time.monotonic() < deadline:
            try:
                packet, _peer = sock.recvfrom(9000)
            except socket.timeout:
                continue
            except OSError:
                break
            ips, descriptions = _mdns_records(packet)
            for name, ip in ips.items():
                if ip in found:
                    found[ip].update(descriptions.get(ip, {}))
                else:
                    found[ip] = descriptions.get(ip, {"hostname": name})
    except OSError:
        return found
    finally:
        sock.close()
    return found


@lru_cache(maxsize=1)
def _oui_database() -> dict[str, str]:
    vendors: dict[str, str] = {}
    for path in OUI_FILES:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            match = re.match(r"\s*([0-9A-Fa-f:-]{6,8})\s+(?:\(hex\)\s+)?(.+?)\s*$", line)
            if not match:
                continue
            assignment = re.sub(r"[^0-9A-F]", "", match.group(1).upper())[:6]
            if len(assignment) == 6:
                vendors.setdefault(assignment, match.group(2).strip())
    return vendors


def _mac_vendor(mac: str | None) -> str | None:
    if not mac:
        return None
    prefix = re.sub(r"[^0-9A-F]", "", mac.upper())[:6]
    return _oui_database().get(prefix) if len(prefix) == 6 else None


def _neighbor_macs(path: Path = Path("/proc/net/arp")) -> dict[str, str]:
    """Read resolved Linux neighbors; callers must independently confirm a live IP."""
    try:
        lines = path.read_text(encoding="ascii", errors="ignore").splitlines()[1:]
    except OSError:
        return {}
    result: dict[str, str] = {}
    for line in lines:
        fields = line.split()
        if len(fields) < 6 or fields[2].lower() != "0x2":
            continue
        ip, mac = fields[0], fields[3].upper()
        try:
            ipaddress.IPv4Address(ip)
        except ValueError:
            continue
        if re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", mac) and mac != "00:00:00:00:00:00":
            result[ip] = mac
    return result


def scan_attached_networks() -> dict[str, Any]:
    """Actively discover link-layer neighbors on directly attached private IPv4 LANs."""
    networks, interface_error = _attached_ipv4_networks()
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
    advertised: dict[str, dict[str, str]] = {}
    for item in route_rows:
        for ip, detail in _ssdp_discovery(item["address"]).items():
            advertised.setdefault(ip, {}).update(detail)
        for ip, detail in _mdns_discovery(item["address"]).items():
            advertised.setdefault(ip, {}).update(detail)
    responding: dict[str, dict[str, Any]] = {}
    scan_warnings: list[str] = []
    active_arp_macs: dict[str, str] = {}
    for item in route_rows:
        ips = [ip for ip, target in targets.items() if target["interface"] == item["interface"]
               and target["network"] == item["network"]]
        if not ips:
            continue
        try:
            active_arp_macs.update(_active_arp_sweep(item["interface"], item["address"], ips))
        except (OSError, ValueError, AttributeError) as exc:
            scan_warnings.append("active_arp_unavailable")
            LOG.warning("Active ARP scan unavailable on interface %s (%s)",
                        item["interface"], type(exc).__name__)

    # Only replies captured from raw Ethernet ARP during this scan are labeled
    # arp_sweep. TCP and ICMP probes below may cause Linux to resolve a neighbor;
    # that MAC can be used only for an IP that independently responded in this
    # scan, and is explicitly labeled as a neighbor-table result.
    mac_by_ip = active_arp_macs
    for ip in targets:
        if ip in mac_by_ip:
            responding[ip] = {"open_ports": [], "methods": ["arp_sweep"]}
        if ip in advertised:
            responding.setdefault(ip, {"open_ports": [], "methods": []})["methods"].extend(
                method for method in ("ssdp", "mdns")
                if (method == "ssdp" and any(key.startswith("ssdp_") for key in advertised[ip]))
                or (method == "mdns" and any(key in advertised[ip] for key in ("hostname", "manufacturer", "model", "friendly_name", "mdns_name")))
            )

    # TCP and ICMP remain secondary signals for unusual hosts or systems without an
    # exposed ARP table. They no longer determine whether an ordinary LAN host exists.
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(_probe, ip, TCP_PORTS, TCP_TIMEOUT_SECONDS)
                   for ip in targets if ip not in responding]
        for future in concurrent.futures.as_completed(futures):
            hit = future.result()
            if hit:
                ip, ports = hit
                responding[ip] = {"open_ports": ports, "methods": ["tcp"]}

        ping_futures = {executor.submit(_ping, ip): ip for ip in targets if ip not in responding}
        for future in concurrent.futures.as_completed(ping_futures):
            if future.result():
                responding[ping_futures[future]] = {"open_ports": [], "methods": ["icmp"]}

    neighbor_macs = _neighbor_macs()
    for ip, response in responding.items():
        if ip in mac_by_ip or not set(response["methods"]).intersection({"tcp", "icmp"}):
            continue
        neighbor_mac = neighbor_macs.get(ip)
        if neighbor_mac:
            mac_by_ip[ip] = neighbor_mac
            response["methods"].append("arp_neighbor")

    hosts = []
    for ip in sorted(responding, key=lambda value: int(ipaddress.IPv4Address(value))):
        iface = targets[ip]
        details = advertised.get(ip, {})
        mac = mac_by_ip.get(ip)
        mac_source = "active_arp" if ip in active_arp_macs else "neighbor_table" if mac else None
        hosts.append({"ip": ip, "mac": mac, "mac_source": mac_source, "hostname": details.get("hostname"),
                      "friendly_name": details.get("friendly_name"), "model": details.get("model"),
                      "manufacturer": details.get("manufacturer") or _mac_vendor(mac),
                      "interface": iface["interface"],
                      "network": iface["network"], "is_router": ip in gateways,
                      "open_ports": responding[ip]["open_ports"],
                      "service_details": details, "discovery_methods": sorted(set(responding[ip]["methods"]))})
    ips_by_mac: dict[str, list[str]] = {}
    for host in hosts:
        if host.get("mac"):
            ips_by_mac.setdefault(host["mac"], []).append(host["ip"])
    mac_ip_conflicts = [{"mac": mac, "ips": ips}
                        for mac, ips in sorted(ips_by_mac.items()) if len(ips) > 1]
    # Present one row per physical MAC. If live ARP says that MAC owns multiple
    # addresses, preserve the candidates as an explicit conflict and leave its
    # single-IP field empty so downstream persistence cannot pick one arbitrarily.
    conflicted = {item["mac"]: item["ips"] for item in mac_ip_conflicts}
    unique_hosts: list[dict[str, Any]] = []
    seen_macs: set[str] = set()
    for host in hosts:
        mac = host.get("mac")
        if not mac or mac not in conflicted:
            unique_hosts.append(host)
            continue
        if mac in seen_macs:
            continue
        seen_macs.add(mac)
        unique_hosts.append({**host, "ip": "", "ip_candidates": conflicted[mac], "mac_ip_conflict": True})
    hosts = unique_hosts
    scan_error = interface_error or ("no_eligible_private_ipv4_network" if not route_rows and not skipped else None)
    return {"networks": route_rows, "interface_addresses": networks,
            "scanned_count": len(targets), "responsive_count": len(hosts),
            "hosts": hosts, "skipped_networks": skipped, "address_limit": MAX_ADDRESSES,
            "method": "direct_ethernet_arp_tcp_icmp_ssdp_mdns", "router_ips": sorted(gateways),
            "scan_error": scan_error, "scan_warnings": sorted(set(scan_warnings)),
            "mac_ip_conflicts": mac_ip_conflicts}
