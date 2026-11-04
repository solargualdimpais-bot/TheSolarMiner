import sqlite3

from solarminer_gateway import shelly_product_registry as registry


def test_documented_vintage_and_blu_gateway_profiles_seed_idempotently():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    registry.ensure_schema(conn)
    first = registry.list_profiles(conn)
    registry.ensure_schema(conn)
    second = registry.list_profiles(conn)

    assert [item["product_code"] for item in first] == [item["product_code"] for item in second]
    assert {item["product_code"] for item in first} == {
        "shelly_vintage_gen1", "shelly_blu_gateway_gwf_kz01"
    }
    vintage = next(item for item in first if item["product_code"] == "shelly_vintage_gen1")
    assert {item["key"] for item in vintage["metrics"]} >= {"power", "energy", "brightness", "state"}
    assert {item["key"] for item in vintage["commands"]} >= {"light.turn", "light.brightness"}
    assert {item["key"] for item in vintage["settings_sections"]} >= {
        "timer", "weekly_schedule", "night_mode", "actions", "internet_security", "settings"
    }
    assert all(item["sources"] and item["confidence"] == "manufacturer_documented" for item in first)


def test_profile_seed_does_not_overwrite_owner_catalog_edits():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    registry.ensure_schema(conn)
    conn.execute("UPDATE shelly_product_profiles SET product_name='Nome editado' WHERE product_code='shelly_vintage_gen1'")
    registry.ensure_schema(conn)
    vintage = next(item for item in registry.list_profiles(conn) if item["product_code"] == "shelly_vintage_gen1")
    assert vintage["product_name"] == "Nome editado"
