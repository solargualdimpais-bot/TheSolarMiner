import json
from types import SimpleNamespace

from solarminer_gateway import network_discovery


def test_private_lan_networks_ignore_virtual_adapters_and_bound_large_ranges():
    interfaces = [
        {"ifname": "eth0", "flags": ["UP"], "addr_info": [
            {"family": "inet", "local": "192.168.8.4", "prefixlen": 24}]},
        {"ifname": "tailscale0", "flags": ["UP"], "addr_info": [
            {"family": "inet", "local": "100.90.0.2", "prefixlen": 24}]},
        {"ifname": "docker0", "flags": ["UP"], "addr_info": [
            {"family": "inet", "local": "172.17.0.1", "prefixlen": 16}]},
        {"ifname": "eth1", "flags": ["UP"], "addr_info": [
            {"family": "inet", "local": "10.8.2.4", "prefixlen": 8}]},
    ]
    assert [str(net) for net in network_discovery._private_lan_networks(json.dumps(interfaces))] == [
        "10.8.0.0/20", "192.168.8.0/24"]


def test_default_routes_identify_private_router_next_hops():
    routes = '[{"dst":"default","gateway":"192.168.8.1","dev":"eth0"},{"dst":"default","gateway":"8.8.8.8","dev":"eth1"}]'
    assert network_discovery._default_routes(routes) == [{
        "ip": "192.168.8.1", "interface": "eth0", "classification": "default_gateway",
        "confidence": "confirmed_by_routing_table",
    }]


def test_router_web_identity_reads_only_public_http_metadata(monkeypatch):
    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, _timeout):
            pass

        def sendall(self, request):
            assert request.startswith(b"GET / HTTP/1.0")
            assert b"Authorization:" not in request

        def recv(self, _size):
            data = (b"HTTP/1.0 200 OK\r\nServer: Huawei\r\n\r\n"
                    b"<html><title>Huawei B636 Router</title></html>")
            self.recv = lambda _next_size: b""
            return data

    monkeypatch.setattr(network_discovery.socket, "create_connection", lambda *_args, **_kwargs: FakeSocket())
    assert network_discovery._read_router_web_identity("192.168.8.1") == {
        "web_ui": "http", "http_status": "200", "server": "Huawei", "page_title": "Huawei B636 Router",
    }
def test_active_scan_probes_private_subnet_and_returns_learned_mac_ip_pairs(monkeypatch, tmp_path):
    interfaces = [{"ifname": "eth0", "flags": ["UP"], "addr_info": [
        {"family": "inet", "local": "192.168.8.2", "prefixlen": 30}]}]
    def fake_run(command, **_kwargs):
        if "route" in command:
            return SimpleNamespace(returncode=0, stdout='[{"dst":"default","gateway":"192.168.8.1","dev":"eth0"}]')
        return SimpleNamespace(returncode=0, stdout=json.dumps(interfaces))
    monkeypatch.setattr(network_discovery.subprocess, "run", fake_run)
    probed = []
    monkeypatch.setattr(network_discovery, "_probe", lambda address, _timeout: probed.append(address))
    monkeypatch.setattr(network_discovery, "_read_router_web_identity", lambda _address: {
        "web_ui": "http", "page_title": "Test Router"})
    arp = tmp_path / "arp"
    arp.write_text(
        "IP address HW type Flags HW address Mask Device\n"
        "192.168.8.1 0x1 0x2 AA:BB:CC:DD:EE:01 * eth0\n"
        "192.168.8.3 0x1 0x2 AA:BB:CC:DD:EE:03 * eth0\n",
        encoding="ascii",
    )
    result = network_discovery.discover_private_lan_hosts(arp_path=arp)
    assert set(probed) == {"192.168.8.1", "192.168.8.2"}
    assert result["hosts"] == {"AA:BB:CC:DD:EE:01": "192.168.8.1"}
    assert result["networks"] == ["192.168.8.0/30"]
    assert result["scanned_count"] == 2
    assert result["routers"] == [{
        "ip": "192.168.8.1", "interface": "eth0", "classification": "default_gateway",
        "confidence": "confirmed_by_routing_table", "web_ui": "http", "page_title": "Test Router",
        "host_seen_in_scan": True,
    }]
