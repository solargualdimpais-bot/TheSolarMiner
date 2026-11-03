from solarminer_gateway import network_scanner
from pathlib import Path


def test_gateway_sandbox_allows_netlink_interface_enumeration_and_raw_arp():
    service = Path(__file__).parents[1] / "packaging" / "solarminer-gateway.service"
    contents = service.read_text(encoding="utf-8")
    families = next(line.partition("=")[2].split() for line in contents.splitlines()
                    if line.startswith("RestrictAddressFamilies="))
    assert {"AF_NETLINK", "AF_PACKET", "AF_INET", "AF_UNIX"}.issubset(families)
    assert "AmbientCapabilities=CAP_NET_RAW" in contents


def test_arp_request_is_an_ethernet_broadcast_for_target_ip():
    frame = network_scanner._build_arp_request(
        "02:11:22:33:44:55", "192.168.10.2", "192.168.10.5")
    assert frame[:6] == b"\xff" * 6
    assert frame[6:12] == bytes.fromhex("021122334455")
    assert frame[12:14] == b"\x08\x06"
    assert frame[20:22] == b"\x00\x01"
    assert frame[38:42] == bytes((192, 168, 10, 5))


def test_arp_reply_parser_returns_sender_mac_and_ip():
    ethernet = bytes.fromhex("001122334455aabbccddeeff0806")
    arp = bytes.fromhex("0001080006040002aabbccddeeffc0a80a05") + bytes.fromhex("001122334455c0a80a02")
    assert network_scanner._parse_arp_reply(ethernet + arp) == (
        "192.168.10.5", "AA:BB:CC:DD:EE:FF")


def test_arp_resolution_uses_udp_bound_to_the_gateway_interface(monkeypatch):
    calls = []

    class FakeSocket:
        def bind(self, address):
            calls.append(("bind", address))

        def sendto(self, payload, address):
            calls.append(("sendto", payload, address))

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(network_scanner.socket, "socket", lambda *_args: FakeSocket())
    assert network_scanner._trigger_arp_resolution("192.168.10.5", "192.168.10.2") is True
    assert calls == [
        ("bind", ("192.168.10.2", 0)),
        ("sendto", b"\x00", ("192.168.10.5", 9)),
        ("close",),
    ]


def test_mdns_parser_maps_local_hostname_and_manufacturer_to_ipv4():
    import struct

    def name(value):
        return b"".join(bytes((len(label),)) + label.encode("ascii") for label in value.split(".")) + b"\x00"

    owner = name("logger.local")
    address = struct.pack("!HHIH", 1, 1, 120, 4) + bytes((192, 168, 10, 44))
    txt_value = b"manufacturer=Deye"
    txt = struct.pack("!HHIH", 16, 1, 120, len(txt_value) + 1) + bytes((len(txt_value),)) + txt_value
    packet = struct.pack("!HHHHHH", 0, 0x8400, 0, 2, 0, 0) + owner + address + owner + txt

    ips, descriptions = network_scanner._mdns_records(packet)
    assert ips == {"logger.local": "192.168.10.44"}
    assert descriptions["192.168.10.44"]["hostname"] == "logger.local"
    assert descriptions["192.168.10.44"]["manufacturer"] == "Deye"


def test_scan_reports_tcp_ping_and_neighbor_hosts_without_scanning_gateway_address(monkeypatch):
    monkeypatch.setattr(network_scanner, "_attached_ipv4_networks", lambda: ([
        {"interface": "eth0", "address": "192.168.10.2", "network": "192.168.10.0/29"},
    ], None))
    monkeypatch.setattr(network_scanner, "default_gateway_ips", lambda: {"192.168.10.1"})
    monkeypatch.setattr(network_scanner, "_trigger_arp_resolution", lambda _ip, _source: True)
    monkeypatch.setattr(network_scanner, "_active_arp_sweep", lambda _interface, _source, _targets: {
        "192.168.10.1": "AA:BB:CC:DD:EE:01", "192.168.10.5": "AA:BB:CC:DD:EE:05",
    })
    monkeypatch.setattr(network_scanner, "_ssdp_discovery", lambda _source: {})
    monkeypatch.setattr(network_scanner, "_mdns_discovery", lambda _source: {})
    monkeypatch.setattr(network_scanner.time, "sleep", lambda _seconds: None)

    def probe(ip, _ports, _timeout):
        return (ip, [80] if ip == "192.168.10.3" else []) if ip in {"192.168.10.1", "192.168.10.3"} else None

    monkeypatch.setattr(network_scanner, "_probe", probe)
    monkeypatch.setattr(network_scanner, "_ping", lambda ip: ip == "192.168.10.4")
    monkeypatch.setattr(network_scanner, "_neighbor_macs", lambda: {
        "192.168.10.1": "AA:BB:CC:DD:EE:01",
        "192.168.10.5": "AA:BB:CC:DD:EE:05",
    })

    report = network_scanner.scan_attached_networks()

    assert report["scanned_count"] == 5
    assert [host["ip"] for host in report["hosts"]] == [
        "192.168.10.1", "192.168.10.3", "192.168.10.4", "192.168.10.5",
    ]
    assert report["hosts"][0]["is_router"] is True
    assert report["hosts"][0]["discovery_methods"] == ["arp_sweep"]
    assert report["hosts"][1]["open_ports"] == [80]
    assert report["hosts"][2]["discovery_methods"] == ["icmp"]
    assert report["hosts"][3]["mac"] == "AA:BB:CC:DD:EE:05"


def test_scan_exposes_missing_interface_discovery(monkeypatch):
    monkeypatch.setattr(network_scanner, "_attached_ipv4_networks", lambda: ([], "interface_discovery_failed"))
    monkeypatch.setattr(network_scanner, "default_gateway_ips", lambda: set())
    report = network_scanner.scan_attached_networks()
    assert report["networks"] == []
    assert report["hosts"] == []
    assert report["scan_error"] == "interface_discovery_failed"


def test_raw_arp_socket_failure_is_logged_and_falls_back_without_aborting(monkeypatch):
    monkeypatch.setattr(network_scanner, "_attached_ipv4_networks", lambda: ([
        {"interface": "eth0", "address": "192.168.10.2", "network": "192.168.10.0/30"},
    ], None))
    monkeypatch.setattr(network_scanner, "default_gateway_ips", lambda: {"192.168.10.1"})
    monkeypatch.setattr(network_scanner, "_active_arp_sweep", lambda *_args: (_ for _ in ()).throw(OSError("raw socket denied")))
    monkeypatch.setattr(network_scanner, "_trigger_arp_resolution", lambda *_args: True)
    monkeypatch.setattr(network_scanner, "_neighbor_macs", lambda: {"192.168.10.1": "AA:BB:CC:DD:EE:01"})
    monkeypatch.setattr(network_scanner, "_ssdp_discovery", lambda _source: {})
    monkeypatch.setattr(network_scanner, "_mdns_discovery", lambda _source: {})
    monkeypatch.setattr(network_scanner, "_probe", lambda *_args: None)
    monkeypatch.setattr(network_scanner, "_ping", lambda _ip: False)
    monkeypatch.setattr(network_scanner.time, "sleep", lambda _seconds: None)

    report = network_scanner.scan_attached_networks()

    assert report["scan_warnings"] == ["active_arp_unavailable"]
    assert [host["ip"] for host in report["hosts"]] == ["192.168.10.1"]


def test_interface_discovery_uses_ioctl_when_ip_returns_no_addresses(monkeypatch):
    expected = {("eth0", "192.168.8.0/24"): {
        "interface": "eth0", "address": "192.168.8.2", "network": "192.168.8.0/24"}}
    monkeypatch.setattr(network_scanner, "_run_ip_json", lambda *_args: [])
    monkeypatch.setattr(network_scanner, "_ioctl_ipv4_interfaces", lambda: expected)
    networks, error = network_scanner._attached_ipv4_networks()
    assert networks == list(expected.values())
    assert error is None


def test_interface_discovery_distinguishes_no_address_from_enumeration_failure(monkeypatch):
    monkeypatch.setattr(network_scanner, "_run_ip_json", lambda *_args: [])
    monkeypatch.setattr(network_scanner, "_ioctl_ipv4_interfaces", lambda: {})
    assert network_scanner._attached_ipv4_networks() == ([], "no_ipv4_address_on_interfaces")

    def fail_ip(*_args):
        raise OSError("ip command unavailable")

    monkeypatch.setattr(network_scanner, "_run_ip_json", fail_ip)
    assert network_scanner._attached_ipv4_networks() == ([], "interface_discovery_failed")


def test_large_networks_are_reported_as_skipped_without_materializing_all_hosts(monkeypatch):
    monkeypatch.setattr(network_scanner, "_attached_ipv4_networks", lambda: ([
        {"interface": "eth0", "address": "10.0.0.2", "network": "10.0.0.0/8"},
    ], None))
    monkeypatch.setattr(network_scanner, "default_gateway_ips", lambda: set())
    report = network_scanner.scan_attached_networks()
    assert report["scanned_count"] == 0
    assert report["skipped_networks"] == ["10.0.0.0/8"]
