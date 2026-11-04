"""Documented Shelly product capabilities stored as versioned Gateway profiles.

Profiles describe advertised UI groups and protocol capabilities. A profile never
grants a command by itself: live device capabilities and connector allowlists do.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

VINTAGE_SOURCE = "https://kb.shelly.cloud/knowledge-base/shelly-vintage-device-smart-control"
GEN1_SOURCE = "https://shelly-api-docs.shelly.cloud/gen1/"
BLU_SOURCE = "https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen2/ShellyBluGw/"

PROFILES: tuple[dict[str, Any], ...] = (
    {
        "manufacturer": "Shelly", "protocol": "shelly_http_gen1", "product_code": "shelly_vintage_gen1",
        "product_name": "Shelly Vintage", "generation": 1, "device_kind": "dimmable_bulb",
        "capabilities": ["light.on_off", "light.brightness", "meter.power", "meter.energy", "timer.auto_on", "timer.auto_off", "schedule.weekly", "light.night_mode", "actions.output_on_off"],
        "metrics": [{"key":"power","label":"Potência","unit":"W","source":"/status meters[0].power"},{"key":"energy","label":"Energia","unit":"Wh","source":"/status meters[0].total"},{"key":"brightness","label":"Brilho","unit":"%","source":"/status lights[0].brightness"},{"key":"state","label":"Estado","unit":"","source":"/status lights[0].ison"}],
        "commands": [{"key":"light.turn","label":"Ligar/desligar","method":"GET /light/0?turn=on|off","verified":True},{"key":"light.brightness","label":"Brilho","method":"GET /light/0?brightness=0..100","verified":True},{"key":"light.transition","label":"Transição","method":"GET /light/0?transition=0..5000","verified":True}],
        "settings_sections": [
            {"key":"timer","label":"Timer","endpoint":"/settings/light/0","fields":["auto_on","auto_off"],"readable":True,"writable":True},
            {"key":"weekly_schedule","label":"Weekly Schedule","endpoint":"/settings/light/0","fields":["schedule","schedule_rules"],"readable":True,"writable":True,"limits":{"max_rules":20}},
            {"key":"night_mode","label":"Night Mode","endpoint":"/settings/night_mode","fields":["enabled","start_time","end_time","brightness"],"readable":True,"writable":True},
            {"key":"actions","label":"Actions","endpoint":"/settings/actions","fields":["out_on_url","out_off_url"],"readable":True,"writable":True,"network_required":True},
            {"key":"internet_security","label":"Internet & Security","endpoint":"/settings","fields":["wifi","access_point","login_restriction","cloud"],"readable":True,"writable":False,"note":"Leitura protegida; credenciais e rede não são expostas pelo catálogo."},
            {"key":"settings","label":"Settings","endpoint":"/settings/light/0","fields":["default_state","transition","device_name","timezone","firmware","reboot","factory_reset"],"readable":True,"writable":False,"note":"Ações disruptivas ficam fora do controlo normal da PWA."},
            {"key":"charts_activity","label":"Charts & Activity","endpoint":"/status","fields":["power_history","energy_total","activity_log"],"readable":True,"writable":False},
        ],
        "sources": [VINTAGE_SOURCE, GEN1_SOURCE], "confidence": "manufacturer_documented",
    },
    {
        "manufacturer": "Shelly", "protocol": "shelly_rpc", "product_code": "shelly_blu_gateway_gwf_kz01",
        "product_name": "Shelly BLU Gateway (GWF-KZ01 / SNGW-BT01)", "generation": 2, "device_kind": "bluetooth_gateway",
        "capabilities": ["bluetooth.scan_via_script", "bluetooth.bthome_bridge", "rpc.local"],
        "metrics": [{"key":"bridge_online","label":"Ponte","unit":"","source":"Shelly.GetStatus"},{"key":"bluetooth_sensors","label":"Sensores BLU","unit":"","source":"BluGw.GetStatus / scanner BLE"}],
        "commands": [{"key":"bluetooth.discover","label":"Procurar sensores BLU","method":"Gateway BLE scanner via bridge","verified":True}],
        "settings_sections": [
            {"key":"bluetooth","label":"Bluetooth & sensores","endpoint":"BluGw.GetStatus","fields":["bluetooth_status","paired_sensors","scanner"],"readable":True,"writable":False},
            {"key":"network","label":"Internet & Security","endpoint":"Wifi.GetConfig / Shelly.GetConfig","fields":["wifi","device_info"],"readable":True,"writable":False},
            {"key":"mqtt","label":"MQTT","endpoint":"Mqtt.GetConfig","fields":["enable","server","topic_prefix"],"readable":True,"writable":False,"optional":True,"note":"Opcional; a integração LAN não depende de MQTT."},
            {"key":"scripts","label":"Scripts","endpoint":"Script.List","fields":["scripts"],"readable":True,"writable":False,"note":"Scripts existentes não são substituídos pelo SolarMiner."},
            {"key":"settings","label":"Settings","endpoint":"Shelly.GetConfig","fields":["device_name","firmware","reboot"],"readable":True,"writable":False},
        ],
        "sources": [BLU_SOURCE, "https://shelly-api-docs.shelly.cloud/gen2/Scripts/APIs/BLE/"], "confidence": "manufacturer_documented",
    },
)


def ensure_schema(conn: Any) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS shelly_product_profiles(
      manufacturer TEXT NOT NULL, protocol TEXT NOT NULL, product_code TEXT NOT NULL,
      product_name TEXT NOT NULL, generation INTEGER NOT NULL, device_kind TEXT NOT NULL,
      capabilities_json TEXT NOT NULL, metrics_json TEXT NOT NULL, commands_json TEXT NOT NULL,
      settings_sections_json TEXT NOT NULL, sources_json TEXT NOT NULL, confidence TEXT NOT NULL,
      updated_at TEXT NOT NULL, PRIMARY KEY(manufacturer,protocol,product_code))""")
    now = datetime.now(timezone.utc).isoformat()
    for profile in PROFILES:
        conn.execute("""INSERT OR IGNORE INTO shelly_product_profiles
          (manufacturer,protocol,product_code,product_name,generation,device_kind,capabilities_json,metrics_json,commands_json,settings_sections_json,sources_json,confidence,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            profile["manufacturer"], profile["protocol"], profile["product_code"], profile["product_name"],
            profile["generation"], profile["device_kind"], json.dumps(profile["capabilities"]),
            json.dumps(profile["metrics"]), json.dumps(profile["commands"]),
            json.dumps(profile["settings_sections"]), json.dumps(profile["sources"]), profile["confidence"], now))


def list_profiles(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM shelly_product_profiles ORDER BY product_name COLLATE NOCASE, product_code").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for key in ("capabilities", "metrics", "commands", "settings_sections", "sources"):
            item[key] = json.loads(item.pop(f"{key}_json"))
        result.append(item)
    return result
