import sqlite3

import pytest

from solarminer_gateway import site_profile


def database():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE system_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    return conn


def test_site_profile_starts_without_preloaded_photo():
    profile = site_profile.get_profile(database())
    assert profile == {"name": "Solar Energy", "photo_data_url": None, "photo_opacity": 0.38, "photo_position_x": 50, "photo_position_y": 50, "photo_zoom": 1.0, "photo_vignette": 0.35, "floors": []}


def test_old_saved_profile_receives_the_default_photo_opacity():
    conn = database()
    conn.execute("INSERT INTO system_state(key,value) VALUES(?,?)", (
        site_profile.PROFILE_KEY, '{"name":"Casa antiga","photo_data_url":null,"floors":[]}'))
    assert site_profile.get_profile(conn)["photo_opacity"] == 0.38
    assert site_profile.get_profile(conn)["photo_zoom"] == 1.0


def test_site_profile_round_trips_shared_house_and_structure():
    conn = database()
    payload = {"name": "Casa Solar", "photo_data_url": None, "photo_opacity": 0.72, "photo_position_x": 42, "photo_position_y": 61, "photo_zoom": 1.6, "photo_vignette": 0.64, "floors": [
        {"id": "floor-ground", "name": "Rés do chão", "rooms": [
            {"id": "room-living", "name": "Sala"}, {"id": "room-kitchen", "name": "Cozinha"}]}
    ]}
    assert site_profile.save_profile(conn, payload) == payload
    assert site_profile.get_profile(conn) == payload


@pytest.mark.parametrize("opacity", [-0.01, 1.01, True, "0.5"])
def test_site_profile_rejects_invalid_photo_opacity(opacity):
    with pytest.raises(ValueError, match="invalid_site_photo_opacity"):
        site_profile.normalize_profile({"photo_opacity": opacity})


@pytest.mark.parametrize("payload", [
    {"photo_position_x": -1}, {"photo_position_y": 101},
    {"photo_zoom": .99}, {"photo_zoom": 3.01},
    {"photo_vignette": -.01}, {"photo_vignette": 1.01},
    {"photo_zoom": True},
])
def test_site_profile_rejects_out_of_range_photo_adjustments(payload):
    with pytest.raises(ValueError):
        site_profile.normalize_profile(payload)


def test_site_profile_accepts_full_strength_vignette():
    assert site_profile.normalize_profile({"photo_vignette": 1.0})["photo_vignette"] == 1.0


@pytest.mark.parametrize("payload", [
    {"unexpected": True},
    {"name": ""},
    {"floors": [{"id": "../bad", "name": "Piso", "rooms": []}]},
    {"floors": [{"id": "floor-a", "name": "Piso", "rooms": [
        {"id": "room-a", "name": "Sala"}, {"id": "room-a", "name": "Cozinha"}]}]},
    {"photo_data_url": "data:image/png;base64,AAAA"},
    {"photo_data_url": "data:image/jpeg;base64,AAAA"},
])
def test_site_profile_rejects_invalid_payloads(payload):
    with pytest.raises(ValueError):
        site_profile.normalize_profile(payload)


def test_site_profile_accepts_a_bounded_real_jpeg():
    import base64

    jpeg = b"\xff\xd8\xff" + b"solarminer-test" + b"\xff\xd9"
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    normalized = site_profile.normalize_profile({"photo_data_url": data_url})
    assert normalized["photo_data_url"] == data_url
    assert normalized["photo_opacity"] == 0.38


def test_site_profile_round_trips_floor_plan_and_room_photographs():
    import base64

    jpeg = b"\xff\xd8\xff" + b"casa-test" + b"\xff\xd9"
    image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    payload = {"floors": [{"id": "floor-ground", "name": "Rés do chão", "photo_data_url": image,
        "plan_data_url": image, "plan_zoom": 1.4,
        "rooms": [{"id": "room-living", "name": "Sala", "photo_data_url": image}]}]}
    normalized = site_profile.normalize_profile(payload)
    floor = normalized["floors"][0]
    assert floor["photo_data_url"] == image
    assert floor["plan_data_url"] == image
    assert floor["plan_zoom"] == 1.4
    assert floor["rooms"][0]["photo_data_url"] == image


@pytest.mark.parametrize("zoom", [0.99, 2.51, True, "1.5"])
def test_site_profile_rejects_invalid_floor_plan_zoom(zoom):
    with pytest.raises(ValueError, match="invalid_site_plan_zoom"):
        site_profile.normalize_profile({"floors": [{"id": "floor-ground", "name": "Piso", "plan_zoom": zoom}]})
