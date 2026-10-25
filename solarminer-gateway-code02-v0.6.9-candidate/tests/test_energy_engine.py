from __future__ import annotations

import sqlite3
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from solarminer_gateway import energy_engine, energy_registry


def database():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    energy_registry.ensure_schema(conn)
    conn.execute("CREATE TABLE system_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    return conn


def insert_reading(conn, equipment_id, field, value, unit, observed_at):
    energy_registry.add_reading(conn, equipment_id, {
        "field": field, "value": value, "unit": unit, "observed_at": observed_at,
        "source": "DEYE_MODBUS_FC03_CANDIDATE_MAP", "trust": "LIVE_UNVERIFIED",
    })


def full_charge_samples(anchor_at, post_anchor_power=3600.0):
    voltage = [{"observed_at": (anchor_at-timedelta(minutes=13)).isoformat(), "value": 54.8}]
    power = [{"observed_at": (anchor_at-timedelta(minutes=13)).isoformat(), "value": -1000.0}]
    for minute in range(11):
        stamp = anchor_at + timedelta(minutes=minute)
        voltage.append({"observed_at": stamp.isoformat(), "value": 55.0})
        power.append({"observed_at": stamp.isoformat(), "value": 0.0})
    for minute in (11, 12):
        stamp = anchor_at + timedelta(minutes=minute)
        voltage.append({"observed_at": stamp.isoformat(), "value": 54.7})
        power.append({"observed_at": stamp.isoformat(), "value": post_anchor_power})
    return voltage, power, anchor_at + timedelta(minutes=12)


def test_solar_day_forecast_reports_missing_pv_capacity_as_a_setup_action():
    conn = database()
    result = energy_engine._solar_day_forecast(
        conn, {"id": "deye-inverter-test"}, {}, {"state": "available", "timezone": "UTC"},
        None, 0.85, {}, as_of=datetime.now(timezone.utc))
    assert result["state"] == "UNAVAILABLE"
    assert "potência nominal FV" in result["reason"]


def test_solar_day_forecast_distinguishes_missing_weather_from_missing_capacity():
    conn = database()
    result = energy_engine._solar_day_forecast(
        conn, {"id": "deye-inverter-test"}, {}, None, 12.0, 0.85, {},
        as_of=datetime.now(timezone.utc))
    assert result["state"] == "UNAVAILABLE"
    assert "Previsão meteorológica indisponível" in result["reason"]


def test_solar_day_forecast_records_comparison_snapshots_and_respects_cache():
    conn = database()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hourly = [{"observed_at": (now+timedelta(hours=hour)).isoformat(), "shortwave_radiation_w_m2": 500}
              for hour in range(0, 24-now.hour)]
    readings = {"pv_daily_energy": {"value": 2.0, "observed_at": now.isoformat()}}

    result = energy_engine._solar_day_forecast(
        conn, {"id": "deye-inverter-test"}, readings,
        {"state": "available", "timezone": "UTC", "hourly": hourly},
        9.0, 0.85, {}, as_of=now)

    assert result["state"] == "ESTIMATED"
    assert result["actual_today_kwh"] == 2.0
    rows = conn.execute("SELECT local_date,estimated_total_kwh,actual_today_kwh FROM energy_solar_day_forecasts").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == result["estimated_total_kwh"]
    assert rows[0][2] == 2.0

    cached = energy_engine._solar_day_forecast(
        conn, {"id": "deye-inverter-test"}, readings,
        {"state": "available", "timezone": "UTC", "hourly": hourly},
        9.0, 0.85, {}, as_of=now+timedelta(minutes=2))
    assert cached == result
    assert conn.execute("SELECT COUNT(*) FROM energy_solar_day_forecasts").fetchone()[0] == 1


def test_solar_configuration_change_invalidates_cached_day_estimate():
    conn = database()
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?)",
                 (energy_engine.SOLAR_DAY_FORECAST_KEY, json.dumps({"state":"ESTIMATED"})))
    energy_engine.save_config(conn, {"pv_capacity_kw": 9.0})
    assert conn.execute("SELECT 1 FROM system_state WHERE key=?",
                        (energy_engine.SOLAR_DAY_FORECAST_KEY,)).fetchone() is None


def test_load_forecast_flattens_stable_load_instead_of_inventing_a_rising_trend():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    series = [{"observed_at": (now-timedelta(minutes=5*index)).isoformat(),
               "value": 500 + (index % 3) * 8, "unit": "W"} for index in reversed(range(36))]
    result = energy_engine._bounded_load_forecast(series, 510, as_of=now)
    assert result["method"] == "robust_recent_median_with_bounded_slope"
    assert [item["value"] for item in result["hourly_values"]] == [0.51] * 6


def test_load_forecast_bounds_a_persistent_rising_trend():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    series = [{"observed_at": (now-timedelta(minutes=5*index)).isoformat(),
               "value": 500 + (35-index) * 20, "unit": "W"} for index in reversed(range(36))]
    result = energy_engine._bounded_load_forecast(series, 1200, as_of=now)
    assert result["one_hour_value"] <= 1.25
    assert result["six_hour_value"] <= 1.5


def test_engine_quarter_hour_projection_uses_daily_calibration_and_weighted_load_profile():
    now = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
    expected = [{"observed_at": (now+timedelta(hours=hour)).isoformat(), "value": 2.0, "unit": "kW"}
                for hour in range(1, 7)]
    potential = [{"observed_at": (now+timedelta(hours=hour)).isoformat(), "value": 3.0, "unit": "kW"}
                 for hour in range(1, 7)]
    result = energy_engine._engine_quarter_hour_projection(
        now, expected, potential,
        [{"load_power_w": 1000, "duration_hours": 6, "history_days": 3}],
        day_end=now+timedelta(hours=6), actual_today_kwh=5.0,
        expected_remaining_kwh=6.0, potential_remaining_kwh=9.0,
        confidence="MEDIUM_INDICATIVE")

    assert result["state"] == "ESTIMATED"
    assert result["cadence_minutes"] == 15
    assert result["source_resolution_minutes"] == 60
    assert result["confidence"] == "MEDIUM_INDICATIVE"
    assert result["values"][0]["forecast_at"] == "2026-10-25T10:15+00:00"
    assert result["values"][1]["forecast_at"] == "2026-10-25T10:30+00:00"
    assert result["values"][0]["solar_expected_power_kw"] == 1.0
    assert result["values"][0]["solar_potential_power_kw"] == 1.5
    assert result["values"][0]["load_power_kw"] == 1.0
    assert result["values"][0]["expected_net_cumulative_kwh"] == 0.0
    assert result["values"][0]["potential_net_cumulative_kwh"] == 0.125
    assert result["values"][0]["estimated_daily_pv_kwh"] == 5.25
    assert result["values"][0]["expected_net_remaining_kwh_6h"] == 0.0


def test_battery_autonomy_blends_current_load_with_weighted_same_hour_history():
    now = datetime(2026, 10, 24, 12, 5, tzinfo=timezone.utc)
    history = [{"observed_at": (now - timedelta(days=day, hours=hour)).isoformat(),
                "value": 100.0, "unit": "W"}
               for day in range(1, 8) for hour in range(24)]
    history.extend({"observed_at": (now - timedelta(minutes=minutes)).isoformat(),
                    "value": 1000.0, "unit": "W"}
                   for minutes in (1, 5, 10))

    result = energy_engine._estimate_battery_autonomy(1.0, 1000.0, history, as_of=now)

    assert result["state"] == "ESTIMATED"
    assert result["history_days_used"] == 7
    assert result["live_load_w"] == 1000.0
    assert result["hours"] < 2.0
    assert result["estimated_cutoff_at"] is not None


def test_battery_autonomy_is_unavailable_without_energy_or_load_profile():
    now = datetime(2026, 10, 24, 12, 5, tzinfo=timezone.utc)
    assert energy_engine._estimate_battery_autonomy(None, None, [], now)["state"] == "UNAVAILABLE"
    result = energy_engine._estimate_battery_autonomy(1.0, None, [], now)
    assert result["state"] == "UNAVAILABLE"
    assert result["reason"] == "no_positive_load_profile"


def test_engine_history_can_be_bounded_to_a_selected_past_window():
    conn = database()
    inverter = energy_registry.upsert_equipment(
        conn, {"category": "inversores", "name": "Deye"}, "deye-inverter-chart")
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    earlier = (now-timedelta(hours=3)).isoformat()
    insert_reading(conn, inverter["id"], "pv_total_power", 400, "W", earlier)
    insert_reading(conn, inverter["id"], "pv_daily_energy", 2.4, "kWh", earlier)
    insert_reading(conn, inverter["id"], "pv_total_power", 900, "W", (now-timedelta(hours=1)).isoformat())
    energy_engine._ensure_solar_forecast_history(conn)
    conn.execute("INSERT INTO energy_solar_day_forecasts(local_date,calculated_at,estimated_total_kwh,actual_today_kwh,remaining_estimate_kwh,confidence) VALUES(?,?,?,?,?,?)",
                 (earlier[:10], earlier, 8.2, 2.4, 5.8, "LOW_INDICATIVE"))

    result = energy_engine.build_summary(conn, history_hours=2, history_until=now-timedelta(hours=2))

    assert [point["value"] for point in result["history"]["pv_total_power"]] == [400]
    assert [point["value"] for point in result["history"]["pv_daily_energy"]] == [2.4]
    assert [point["value"] for point in result["history"]["solar_day_forecast"]] == [8.2]


def test_gateway_battery_soc_integrates_signed_power_from_rolling_voltage_peak():
    anchor_at = datetime.now(timezone.utc)-timedelta(minutes=12)
    voltage, discharge, now = full_charge_samples(anchor_at)
    _charge_voltage, charge, _ = full_charge_samples(anchor_at, -3600.0)

    estimated, details = energy_engine._estimate_battery_soc(voltage, discharge, 10.0, 20.0, 100.0)
    charged, _ = energy_engine._estimate_battery_soc(voltage, charge, 10.0, 20.0, 100.0)

    assert estimated == 99.1
    assert details["voltage_max_30d_v"] == 55.0
    assert details["bank_voltage_scope"] == "SHARED_PARALLEL_BUS"
    assert charged == 100.0


def test_persisted_battery_voltage_anchor_survives_rolling_history_window():
    conn = database()
    anchor_at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    voltage, power, start = full_charge_samples(anchor_at)

    first_soc, first_details = energy_engine._estimate_battery_soc_persistent(
        conn, voltage, power, 10.0, 20.0, 100.0, as_of=start)
    assert first_soc == 99.1
    assert first_details["voltage_max_30d_v"] == 55.0

    later = start + timedelta(seconds=30)
    later_power = power + [{"observed_at": later.isoformat(), "value": 3600.0}]
    # The original 55 V observation has now disappeared from the supplied
    # rolling window. The persisted full-charge anchor must not move down.
    later_voltage = [{"observed_at": start.isoformat(), "value": 54.7}]
    second_soc, second_details = energy_engine._estimate_battery_soc_persistent(
        conn, later_voltage, later_power, 10.0, 20.0, 100.0, as_of=later)
    assert second_soc == 98.8
    assert second_details["voltage_max_30d_v"] == 55.0

    # Re-reading the same telemetry is idempotent and cannot double-integrate.
    repeated_soc, _ = energy_engine._estimate_battery_soc_persistent(
        conn, later_voltage, later_power, 10.0, 20.0, 100.0, as_of=later)
    assert repeated_soc == second_soc


def test_energy_summary_uses_persisted_soc_energy_and_counter_history():
    conn = database()
    inverter = energy_registry.upsert_equipment(conn, {"category": "inversores", "name": "Deye", "model": "SUN-15K-SG05LP3-EU-SM2"}, "deye-inverter-test")
    battery = energy_registry.upsert_equipment(conn, {"category": "baterias", "name": "Deye battery", "manufacturer": "Deye"}, "deye-battery-test")
    energy_engine.save_config(conn, {"battery_capacity_kwh": 20, "minimum_soc_percent": 20, "maximum_soc_percent": 95})
    now = datetime.now(timezone.utc)
    anchor_at = now-timedelta(minutes=40)
    insert_reading(conn, battery["id"], "battery_voltage", 54.8, "V", (anchor_at-timedelta(minutes=1)).isoformat())
    insert_reading(conn, battery["id"], "battery_output_power", -1000, "W", (anchor_at-timedelta(minutes=1)).isoformat())
    for minute in range(11):
        stable_at = anchor_at+timedelta(minutes=minute)
        insert_reading(conn, battery["id"], "battery_voltage", 55.0, "V", stable_at.isoformat())
        insert_reading(conn, battery["id"], "battery_output_power", 0, "W", stable_at.isoformat())
    for minutes_ago, pv, load, reported_soc, battery_v in ((20, 900, 700, 75, 55.0), (10, 1200, 650, 77, 54.5), (0, 1500, 640, 80, 53.4)):
        stamp = (now - timedelta(minutes=minutes_ago)).isoformat(timespec="microseconds")
        insert_reading(conn, inverter["id"], "pv_total_power", pv, "W", stamp)
        insert_reading(conn, inverter["id"], "load_total_power", load, "W", stamp)
        insert_reading(conn, battery["id"], "battery_soc", reported_soc, "%", stamp)
        insert_reading(conn, battery["id"], "battery_voltage", battery_v, "V", stamp)
        insert_reading(conn, battery["id"], "battery_output_power", 100, "W", stamp)
    stamp = now.isoformat(timespec="microseconds")
    for field, value, unit in (("pv_daily_energy", 37.8, "kWh"),):
        insert_reading(conn, inverter["id"], field, value, unit, stamp)
    for field, value, unit in (("battery_output_current", -1.5, "A"),
                               ("battery_temperature", 25, "°C"), ("battery_max_charge_current", 100, "A")):
        insert_reading(conn, battery["id"], field, value, unit, stamp)

    result = energy_engine.build_summary(conn)
    assert result["current"]["battery_soc_percent"] == 94.79
    assert result["current"]["battery_soc_source"] == "gateway_energy_integrated"
    assert result["current"]["battery_soc_estimate"]["voltage_max_30d_v"] == 55.0
    assert result["current"]["battery_inverter_reported_soc_percent"] == 80
    assert result["current"]["battery_current_a"] == -1.5
    assert result["current"]["battery_energy_available_kwh_above_minimum"] == 14.958
    assert result["current"]["battery_charge_headroom_kwh_to_maximum"] == 0.042
    assert result["current"]["battery_at_configured_maximum"] is False
    assert result["latest_readings"]["pv_daily_energy"]["value"] == 37.8
    assert len(result["history"]["pv_total_power"]) == 3
    assert result["forecast"]["solar_power"]["confidence"] == "LOW_INDICATIVE"
    assert result["forecast"]["load_power"]["one_hour_value"] is not None
    assert result["forecast"]["battery_soc"]["one_hour_value"] is None
    assert result["limits"]["controls_enabled"] is False


@pytest.mark.parametrize("payload", [
    {"battery_capacity_kwh": -1, "minimum_soc_percent": 20, "maximum_soc_percent": 100},
    {"battery_capacity_kwh": 10, "minimum_soc_percent": 95, "maximum_soc_percent": 90},
    {"battery_capacity_kwh": float("nan"), "minimum_soc_percent": 20, "maximum_soc_percent": 100},
    {"battery_capacity_kwh": 10, "minimum_soc_percent": True, "maximum_soc_percent": 100},
    {"battery_capacity_kwh": 10, "minimum_soc_percent": 20, "maximum_soc_percent": 100, "unexpected": True},
])
def test_engine_rejects_invalid_battery_configuration(payload):
    with pytest.raises(ValueError):
        energy_engine.save_config(database(), payload)


def test_only_online_parallel_battery_banks_contribute_capacity():
    conn = database()
    banks = [{"id": f"bank-{index}", "name": f"Banco {index}", "capacity_kwh": 15,
              "minimum_soc_percent": 20, "maximum_soc_percent": 100, "active": index != 3}
             for index in range(1, 4)]
    saved = energy_engine.save_config(conn, {"battery_banks": banks})
    assert saved["battery_capacity_kwh"] == 30
    assert [bank["active"] for bank in saved["battery_banks"]] == [True, True, False]

    saved = energy_engine.save_config(conn, {"battery_banks": [dict(bank, active=False) for bank in banks]})
    assert saved["battery_capacity_kwh"] is None
    battery = energy_registry.upsert_equipment(conn, {"category": "baterias", "name": "Deye battery"}, "deye-battery-test")
    stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    insert_reading(conn, battery["id"], "battery_voltage", 55.0, "V", stamp)
    insert_reading(conn, battery["id"], "battery_output_power", 0, "W", stamp)
    summary = energy_engine.build_summary(conn)
    assert summary["current"]["battery_capacity_kwh"] is None
    assert summary["current"]["battery_soc_percent"] is None
    assert summary["current"]["battery_energy_available_kwh_above_minimum"] is None


def test_battery_energy_is_unknown_without_owner_declared_capacity():
    conn = database()
    battery = energy_registry.upsert_equipment(conn, {"category": "baterias", "name": "Deye battery"}, "deye-battery-test")
    insert_reading(conn, battery["id"], "battery_soc", 100, "%", datetime.now(timezone.utc).isoformat())
    result = energy_engine.build_summary(conn)
    assert result["current"]["battery_soc_percent"] is None
    assert result["current"]["battery_energy_available_kwh_above_minimum"] is None
    assert result["current"]["battery_soc_source"] == "unavailable"
    assert result["current"]["battery_at_configured_maximum"] is False


def test_offlining_parallel_bank_removes_its_proportional_energy_share():
    conn = database()
    banks = [
        {"id": "bank-large", "name": "Banco 1", "capacity_kwh": 20,
         "minimum_soc_percent": 0, "maximum_soc_percent": 100, "active": True},
        {"id": "bank-small", "name": "Banco 2", "capacity_kwh": 10,
         "minimum_soc_percent": 0, "maximum_soc_percent": 100, "active": True},
    ]
    energy_engine.save_config(conn, {"battery_banks": banks})
    # 15 kWh discharged from the 30 kWh aggregate means 15 kWh remains:
    # 10 kWh belongs to the 20 kWh bank and 5 kWh to the 10 kWh bank.
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?)", (
        energy_engine.BATTERY_ESTIMATOR_STATE_KEY,
        json.dumps({"anchor_at": "2026-10-23T00:00:00+00:00", "voltage_max_v": 55.0,
                    "integrated_net_discharge_kwh": 15.0, "last_power_at": "2026-10-23T01:00:00+00:00",
                    "last_power_w": 0.0, "last_sample_count": 2, "needs_reanchor": False}),
    ))

    saved = energy_engine.save_config(conn, {"battery_banks": [banks[0], dict(banks[1], active=False)]})
    state = json.loads(conn.execute("SELECT value FROM system_state WHERE key=?",
                                    (energy_engine.BATTERY_ESTIMATOR_STATE_KEY,)).fetchone()[0])
    remaining_energy = saved["battery_capacity_kwh"] - state["integrated_net_discharge_kwh"]

    assert saved["battery_capacity_kwh"] == 20
    assert state["integrated_net_discharge_kwh"] == 10
    assert remaining_energy == 10


def test_deye_reported_soc_alone_never_becomes_gateway_estimated_soc():
    conn = database()
    battery = energy_registry.upsert_equipment(conn, {"category": "baterias", "name": "Battery"}, "deye-battery-test")
    energy_engine.save_config(conn, {"battery_capacity_kwh": 30})
    insert_reading(conn, battery["id"], "battery_soc", 100, "%", datetime.now(timezone.utc).isoformat())
    current = energy_engine.build_summary(conn)["current"]
    assert current["battery_inverter_reported_soc_percent"] == 100
    assert current["battery_soc_percent"] is None
    assert current["battery_energy_available_kwh_above_minimum"] is None
    assert current["battery_soc_estimate"]["reason"] == "NO_BATTERY_VOLTAGE_HISTORY"


def test_live_half_minute_sample_overrides_current_without_changing_history():
    conn = database()
    inverter = energy_registry.upsert_equipment(conn, {"category": "inversores", "name": "Deye"}, "deye-inverter-test")
    battery = energy_registry.upsert_equipment(conn, {"category": "baterias", "name": "Battery"}, "deye-battery-test")
    old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="microseconds")
    insert_reading(conn, inverter["id"], "pv_total_power", 1000, "W", old)
    insert_reading(conn, battery["id"], "battery_soc", 70, "%", old)
    fresh = datetime.now(timezone.utc).isoformat(timespec="microseconds")

    result = energy_engine.build_summary(conn, latest_sample={
        "sampled_at": fresh,
        "metrics": [
            {"category": "inversores", "field": "pv_total_power", "value": 1800, "unit": "W", "register": 40673},
            {"category": "baterias", "field": "battery_soc", "value": 82, "unit": "%", "register": 40589},
        ],
    })

    assert result["current"]["pv_power_w"] == 1800
    assert result["current"]["battery_soc_percent"] is None
    assert result["latest_readings"]["pv_total_power"]["observed_at"] == fresh
    assert result["latest_readings"]["pv_total_power"]["trust"] == "LIVE_UNVERIFIED"
    assert [point["value"] for point in result["history"]["pv_total_power"]] == [1000]


def test_history_exposes_each_mppt_and_curtailed_hour_does_not_train_panels_down():
    conn = database()
    inverter = energy_registry.upsert_equipment(conn, {"category": "inversores", "name": "Deye"}, "deye-inverter-test")
    battery = energy_registry.upsert_equipment(conn, {"category": "baterias", "name": "Battery"}, "deye-battery-test")
    stamp = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    weather = {"hourly": [{"observed_at": stamp.isoformat(), "shortwave_radiation_w_m2": 700}]}
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?)", ("energy_engine_solar_performance", json.dumps({
        "performance_ratio": 1.0, "sample_count": 3,
        "mppt_voltage_profiles": {"7": {"samples": 3, "mppt1_voltage_v": 390, "mppt1_current_a": 5,
                                          "mppt2_voltage_v": 385, "mppt2_current_a": 5}},
    })))
    for index in range(12):
        observed = (stamp - timedelta(minutes=55) + timedelta(minutes=index * 4)).isoformat(timespec="microseconds")
        for field, value, unit in (("pv1_input_power", 500, "W"), ("pv2_input_power", 500, "W"),
                                   ("pv1_voltage", 410, "V"), ("pv1_current", 1.3, "A"),
                                   ("pv2_voltage", 405, "V"), ("pv2_current", 1.3, "A"),
                                   ("load_total_power", 100, "W")):
            insert_reading(conn, inverter["id"], field, value, unit, observed)
        insert_reading(conn, battery["id"], "battery_soc", 100, "%", observed)
        insert_reading(conn, battery["id"], "battery_charge_power", 0, "W", observed)
        insert_reading(conn, battery["id"], "battery_voltage", 55.0, "V", observed)
        insert_reading(conn, battery["id"], "battery_output_power", 0, "W", observed)
    charge_before_anchor = (stamp-timedelta(minutes=13)).isoformat(timespec="microseconds")
    insert_reading(conn, battery["id"], "battery_voltage", 54.8, "V", charge_before_anchor)
    insert_reading(conn, battery["id"], "battery_output_power", -1000, "W", charge_before_anchor)
    for minute in range(12, 0, -1):
        if minute == 11:  # already added by the four-minute telemetry sample above
            continue
        stable_at = (stamp-timedelta(minutes=minute)).isoformat(timespec="microseconds")
        insert_reading(conn, battery["id"], "battery_voltage", 55.0, "V", stable_at)
        insert_reading(conn, battery["id"], "battery_output_power", 0, "W", stable_at)
    model = energy_engine._learn_solar_performance(conn, weather, inverter, battery, 8.0, 0.85, 100.0, 30.0)
    assert model["possible_curtailment_hours"] == 1
    assert model["new_curtailment_candidates"] == 1
    assert model["sample_count"] == 3
    assert model["last_curtailment_candidate"]["mppt_voltage_support"] is True
    assert model["last_curtailment_candidate"]["state"] == "POSSIBLE_CURTAILMENT_VOLTAGE_SUPPORTED"
    assert model["mppt_empirical_curtailment_voltage_v"]["mppt1"] == 410

    result = energy_engine.build_summary(conn)
    assert len(result["history"]["pv1_voltage"]) == 12
    assert len(result["history"]["pv1_current"]) == 12
    assert len(result["history"]["pv2_voltage"]) == 12
    assert len(result["history"]["pv2_current"]) == 12


def test_stale_in_memory_sample_blocks_dispatch_even_if_owner_enabled_it():
    conn = database()
    inverter = energy_registry.upsert_equipment(conn, {"category": "inversores", "name": "Deye"}, "deye-inverter-test")
    battery = energy_registry.upsert_equipment(conn, {"category": "baterias", "name": "Battery"}, "deye-battery-test")
    config = energy_engine.save_config(conn, {
        "battery_capacity_kwh": 10,
        "loads": [{"id": "water-heater-1", "name": "AQS 1", "kind": "water_heater",
                   "control_type": "manual", "rated_power_w": 1500, "automatic": True}],
        "automation": {"enabled": True, "commissioned": True, "deye_map_verified": True,
                       "surplus_margin_w": 100, "decision_interval_seconds": 300},
    })
    assert config["automation"]["enabled"] is True
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat(timespec="microseconds")
    result = energy_engine.build_summary(conn, latest_sample={"sampled_at": stale_at, "metrics": [
        {"category": "inversores", "field": "pv_total_power", "value": 5000, "unit": "W"},
        {"category": "inversores", "field": "load_total_power", "value": 1000, "unit": "W"},
        {"category": "baterias", "field": "battery_soc", "value": 100, "unit": "%"},
        {"category": "baterias", "field": "battery_output_power", "value": 0, "unit": "W"},
    ]})
    assert result["dispatch"]["state"] == "BLOCKED_STALE_TELEMETRY"
    assert result["limits"]["controls_enabled"] is False


def test_flexible_load_schema_supports_multiple_heaters_and_radiant_heating():
    conn = database()
    config = energy_engine.save_config(conn, {"loads": [
        {"id": "aqs-1", "name": "AQS 1", "kind": "water_heater", "control_type": "tuya_breaker",
         "rated_power_w": 1500, "tuya_device_id": "switch1", "tuya_switch_code": "switch_1"},
        {"id": "aqs-2", "name": "AQS 2", "kind": "water_heater", "control_type": "tuya_smart",
         "rated_power_w": 1200, "tuya_device_id": "switch2", "tuya_switch_code": "switch_1"},
        {"id": "radiant", "name": "Toalheiro radiante", "kind": "underfloor_heating", "control_type": "tuya_breaker",
         "rated_power_w": 700, "tuya_device_id": "switch3", "tuya_switch_code": "switch_1"},
    ]})
    assert [item["id"] for item in config["loads"]] == ["aqs-1", "aqs-2", "radiant"]


def test_energy_config_stores_pv_string_and_aqs_owner_metadata():
    conn = database()
    config = energy_engine.save_config(conn, {
        "pv_strings": [{"id": "pv-mppt1-a", "name": "MPPT 1 · Sul", "mppt": 1,
                        "manufacturer": "Exemplo Solar", "panel_count": 12, "panel_power_w": 400,
                        "nominal_power_kw": 1, "active": True}],
        "loads": [{"id": "aqs-kitchen", "name": "Termoacumulador", "kind": "water_heater",
                   "control_type": "manual", "manufacturer": "MOES", "volume_l": 200,
                   "rated_power_w": 2000}],
    })
    assert config["pv_strings"] == [{"id": "pv-mppt1-a", "name": "MPPT 1 · Sul", "mppt": 1,
                                     "nominal_power_kw": 4.8, "active": True,
                                     "manufacturer": "Exemplo Solar", "panel_count": 12,
                                     "panel_power_w": 400.0}]
    assert config["loads"][0]["manufacturer"] == "MOES"
    assert config["loads"][0]["volume_l"] == 200


def test_pv_string_rejects_invalid_panel_metadata():
    conn = database()
    with pytest.raises(ValueError, match="invalid_pv_string_panel_count"):
        energy_engine.save_config(conn, {"pv_strings": [{
            "id": "pv-invalid", "name": "String inválida", "manufacturer": "Fabricante",
            "panel_count": 0, "panel_power_w": 400, "mppt": 1, "active": True,
        }]})


def test_automatic_miner_requires_a_preceding_tuya_relay():
    conn = database()
    with pytest.raises(ValueError, match="automatic_antminer_requires_tuya_relay_load"):
        energy_engine.save_config(conn, {"loads": [{
            "id": "miner", "name": "S19K Pro", "kind": "miner", "control_type": "antminer_braiins",
            "rated_power_w": 2500, "minimum_power_w": 800, "maximum_power_w": 2500,
            "automatic": True,
        }]})


def test_dispatch_plan_starts_relay_before_miner_and_allocates_heaters_after_max():
    config = {
        "automation": {"enabled": True, "commissioned": True, "deye_map_verified": True,
                       "surplus_margin_w": 100, "decision_interval_seconds": 300},
        "loads": [
            {"id": "miner-relay", "name": "Relé mineradora", "control_type": "tuya_breaker",
             "rated_power_w": 1, "priority": 1, "enabled": True, "automatic": True},
            {"id": "miner", "name": "Mineradora", "control_type": "antminer_braiins",
             "rated_power_w": 2500, "minimum_power_w": 800, "maximum_power_w": 2500,
             "priority": 2, "enabled": True, "automatic": True, "requires_load_id": "miner-relay"},
            {"id": "aqs", "name": "AQS", "control_type": "tuya_smart", "rated_power_w": 1500,
             "priority": 3, "enabled": True, "automatic": True},
        ],
    }
    current = {"pv_power_w": 5000, "load_power_w": 1000, "battery_soc_percent": 100,
               "battery_charge_headroom_kwh_to_maximum": 0, "battery_charge_power_w": 0, "battery_power_w": 0}
    result = energy_engine.build_dispatch_plan(current, config, sample_state="LIVE", telemetry_trust="OWNER_COMMISSIONED")
    assert [item["state"] for item in result["actions"]] == ["ON", "TARGET", "WAITING_FOR_SURPLUS"]
    assert result["actions"][1]["target_power_w"] == 2500


def test_dispatch_sheds_automatic_loads_when_battery_needs_charge():
    config = {"automation": {"enabled": True, "commissioned": True, "deye_map_verified": True,
                             "surplus_margin_w": 100, "decision_interval_seconds": 300},
              "loads": [{"id": "aqs", "name": "AQS", "control_type": "tuya_breaker",
                         "rated_power_w": 1500, "enabled": True, "automatic": True}]}
    current = {"pv_power_w": 4000, "load_power_w": 1000, "battery_soc_percent": 90,
               "battery_charge_headroom_kwh_to_maximum": 1, "battery_charge_power_w": 500,
               "battery_power_w": -500}
    result = energy_engine.build_dispatch_plan(current, config, sample_state="LIVE", telemetry_trust="OWNER_COMMISSIONED")
    assert result["state"] == "WAITING_FOR_BATTERY"
    assert result["actions"] == [{"load_id": "aqs", "name": "AQS", "state": "OFF_FOR_BATTERY",
                                  "target_power_w": 0, "control_type": "tuya_breaker", "requires_load_id": None}]
    discharging = {**current, "battery_charge_headroom_kwh_to_maximum": 0,
                   "battery_charge_power_w": 0, "battery_discharge_power_w": 250,
                   "battery_power_w": 250}
    result = energy_engine.build_dispatch_plan(discharging, config, sample_state="LIVE", telemetry_trust="OWNER_COMMISSIONED")
    assert result["state"] == "WAITING_FOR_BATTERY"


def test_energy_sampler_interval_defaults_to_30_seconds_and_never_goes_below_30(monkeypatch):
    from solarminer_gateway import app as gateway

    monkeypatch.delenv("SOLARMINER_ENERGY_SAMPLE_SECONDS", raising=False)
    assert gateway._energy_sample_interval_seconds() == 30
    monkeypatch.setenv("SOLARMINER_ENERGY_SAMPLE_SECONDS", "10")
    assert gateway._energy_sample_interval_seconds() == 30
    monkeypatch.setenv("SOLARMINER_ENERGY_SAMPLE_SECONDS", "45")
    assert gateway._energy_sample_interval_seconds() == 45


def test_background_sampler_persists_snapshot_without_pwa_request(tmp_path, monkeypatch):
    from solarminer_gateway import app as gateway

    monkeypatch.setattr(gateway, "DB_PATH", tmp_path / "gateway.db")
    monkeypatch.setattr(gateway.hardware_integrations, "load_config", lambda: {"deye": {"host": "192.168.8.10", "port": 502, "unit_id": 1, "enabled": True}})
    monkeypatch.setattr(gateway.hardware_integrations, "read_deye", lambda _config: {
        "host": "192.168.8.10", "unit_id": 1, "connection_state": "mapped_registers_response",
        "model": "SUN-15K-SG05LP3-EU-SM2", "register_map": {"source": "test-map"},
        "metrics": [
            {"field": "pv_total_power", "value": 1234, "unit": "W", "category": "inversores", "label": "PV total", "register": 40673},
            {"field": "battery_soc", "value": 76, "unit": "%", "category": "baterias", "label": "SOC", "register": 40589},
        ],
    })

    async def stop_after_one_sample(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(gateway.asyncio, "sleep", stop_after_one_sample)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(gateway._energy_sampling_loop())
    with gateway.db() as conn:
        rows = conn.execute("SELECT field,value_json,trust FROM energy_readings ORDER BY field").fetchall()
    assert [(row[0], row[2]) for row in rows] == [("battery_soc", "LIVE_UNVERIFIED"), ("pv_total_power", "LIVE_UNVERIFIED")]

