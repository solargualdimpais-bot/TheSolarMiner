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


def test_active_scan_probes_private_subnet_and_returns_learned_mac_ip_pairs(monkeypatch, tmp_path):
    interfaces = [{"ifname": "eth0", "flags": ["UP"], "addr_info": [
        {"family": "inet", "local": "192.168.8.2", "prefixlen": 30}]}]
    monkeypatch.setattr(network_discovery.subprocess, "run", lambda *_args, **_kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps(interfaces)))
    probed = []
    monkeypatch.setattr(network_discovery, "_probe", lambda address, _timeout: probed.append(address))
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
