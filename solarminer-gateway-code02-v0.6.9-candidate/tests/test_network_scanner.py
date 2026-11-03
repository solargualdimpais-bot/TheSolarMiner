from solarminer_gateway import network_scanner


def test_scan_reports_tcp_ping_and_neighbor_hosts_without_scanning_gateway_address(monkeypatch):
    monkeypatch.setattr(network_scanner, "attached_ipv4_networks", lambda: [
        {"interface": "eth0", "address": "192.168.10.2", "network": "192.168.10.0/29"},
    ])
    monkeypatch.setattr(network_scanner, "default_gateway_ips", lambda: {"192.168.10.1"})

    def probe(ip, _ports, _timeout):
        return (ip, [80] if ip == "192.168.10.3" else []) if ip in {"192.168.10.1", "192.168.10.3"} else None

    monkeypatch.setattr(network_scanner, "_probe", probe)
    monkeypatch.setattr(network_scanner, "_ping", lambda ip: ip == "192.168.10.4")
    monkeypatch.setattr(network_scanner, "_neighbor_macs", lambda: {"192.168.10.5": "AA:BB:CC:DD:EE:05"})

    report = network_scanner.scan_attached_networks()

    assert report["scanned_count"] == 5
    assert [host["ip"] for host in report["hosts"]] == [
        "192.168.10.1", "192.168.10.3", "192.168.10.4", "192.168.10.5",
    ]
    assert report["hosts"][0]["is_router"] is True
    assert report["hosts"][1]["open_ports"] == [80]
    assert report["hosts"][2]["discovery_methods"] == ["icmp"]
    assert report["hosts"][3]["mac"] == "AA:BB:CC:DD:EE:05"


def test_large_networks_are_reported_as_skipped_without_materializing_all_hosts(monkeypatch):
    monkeypatch.setattr(network_scanner, "attached_ipv4_networks", lambda: [
        {"interface": "eth0", "address": "10.0.0.2", "network": "10.0.0.0/8"},
    ])
    monkeypatch.setattr(network_scanner, "default_gateway_ips", lambda: set())
    report = network_scanner.scan_attached_networks()
    assert report["scanned_count"] == 0
    assert report["skipped_networks"] == ["10.0.0.0/8"]
