"""Shared property identity and floor/room structure stored by the Gateway."""
from __future__ import annotations

import base64
import binascii
import json
import re
import sqlite3
from typing import Any

PROFILE_KEY = "site_profile"
DEFAULT_PROFILE: dict[str, Any] = {
    "name": "Solar Energy", "photo_data_url": None, "photo_opacity": 0.38,
    "photo_position_x": 50, "photo_position_y": 50, "photo_zoom": 1.0,
    "photo_vignette": 0.35, "floors": [],
}
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
_JPEG = re.compile(r"^data:image/jpeg;base64,([A-Za-z0-9+/]+={0,2})$")
MAX_PHOTO_BYTES = 1_800_000


def get_profile(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM system_state WHERE key=?", (PROFILE_KEY,)).fetchone()
    if not row:
        return json.loads(json.dumps(DEFAULT_PROFILE))
    try:
        saved = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return json.loads(json.dumps(DEFAULT_PROFILE))
    if not isinstance(saved, dict):
        return json.loads(json.dumps(DEFAULT_PROFILE))
    return {**DEFAULT_PROFILE, **saved}


def _photo(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_site_photo")
    if len(value) > (MAX_PHOTO_BYTES * 4 // 3 + 64):
        raise ValueError("invalid_site_photo_size_or_format")
    match = _JPEG.fullmatch(value)
    if not match:
        raise ValueError("site_photo_must_be_jpeg_data_url")
    try:
        raw = base64.b64decode(match.group(1), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid_site_photo_base64") from exc
    if len(raw) < 5 or len(raw) > MAX_PHOTO_BYTES or not raw.startswith(b"\xff\xd8\xff") or not raw.endswith(b"\xff\xd9"):
        raise ValueError("invalid_site_photo_size_or_format")
    return value


def _text(value: Any, field: str, maximum: int, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_" + field)
    normalized = value.strip()
    if not normalized and optional:
        return None
    if not normalized or len(normalized) > maximum:
        raise ValueError("invalid_" + field)
    return normalized


def normalize_profile(payload: dict[str, Any]) -> dict[str, Any]:
    fields = {"name", "photo_data_url", "photo_opacity", "photo_position_x", "photo_position_y", "photo_zoom", "photo_vignette", "floors"}
    if not isinstance(payload, dict) or set(payload) - fields:
        raise ValueError("invalid_site_profile_fields")
    name = _text(payload.get("name", DEFAULT_PROFILE["name"]), "site_name", 100)
    photo = _photo(payload.get("photo_data_url"))
    opacity = payload.get("photo_opacity", DEFAULT_PROFILE["photo_opacity"])
    if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0 <= opacity <= 1:
        raise ValueError("invalid_site_photo_opacity")
    position_x = payload.get("photo_position_x", DEFAULT_PROFILE["photo_position_x"])
    position_y = payload.get("photo_position_y", DEFAULT_PROFILE["photo_position_y"])
    zoom = payload.get("photo_zoom", DEFAULT_PROFILE["photo_zoom"])
    vignette = payload.get("photo_vignette", DEFAULT_PROFILE["photo_vignette"])
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (position_x, position_y, zoom, vignette)):
        raise ValueError("invalid_site_photo_adjustment")
    if not 0 <= position_x <= 100 or not 0 <= position_y <= 100:
        raise ValueError("invalid_site_photo_position")
    if not 1 <= zoom <= 3:
        raise ValueError("invalid_site_photo_zoom")
    if not 0 <= vignette <= 0.85:
        raise ValueError("invalid_site_photo_vignette")
    floors = payload.get("floors", [])
    if not isinstance(floors, list) or len(floors) > 32:
        raise ValueError("invalid_site_floors")
    normalized_floors = []
    floor_ids: set[str] = set()
    room_ids: set[str] = set()
    room_count = 0
    for floor in floors:
        if not isinstance(floor, dict) or set(floor) - {"id", "name", "photo_data_url", "plan_data_url", "plan_zoom", "rooms"}:
            raise ValueError("invalid_site_floor")
        floor_id = floor.get("id")
        if not isinstance(floor_id, str) or not _ID.fullmatch(floor_id) or floor_id in floor_ids:
            raise ValueError("invalid_or_duplicate_site_floor_id")
        floor_name = _text(floor.get("name"), "site_floor_name", 100)
        rooms = floor.get("rooms", [])
        if not isinstance(rooms, list):
            raise ValueError("invalid_site_rooms")
        normalized_rooms = []
        for room in rooms:
            room_count += 1
            if room_count > 200 or not isinstance(room, dict) or set(room) - {"id", "name", "photo_data_url"}:
                raise ValueError("invalid_site_room")
            room_id = room.get("id")
            if not isinstance(room_id, str) or not _ID.fullmatch(room_id) or room_id in room_ids:
                raise ValueError("invalid_or_duplicate_site_room_id")
            room_name = _text(room.get("name"), "site_room_name", 100)
            room_ids.add(room_id)
            normalized_room = {"id": room_id, "name": room_name}
            if "photo_data_url" in room:
                normalized_room["photo_data_url"] = _photo(room.get("photo_data_url"))
            normalized_rooms.append(normalized_room)
        floor_ids.add(floor_id)
        floor_photo = _photo(floor.get("photo_data_url"))
        normalized_floor = {"id": floor_id, "name": floor_name, "rooms": normalized_rooms}
        if "photo_data_url" in floor:
            normalized_floor["photo_data_url"] = floor_photo
        if "plan_data_url" in floor:
            normalized_floor["plan_data_url"] = _photo(floor.get("plan_data_url"))
        plan_zoom = floor.get("plan_zoom", 1.0)
        if isinstance(plan_zoom, bool) or not isinstance(plan_zoom, (int, float)) or not 1 <= plan_zoom <= 2.5:
            raise ValueError("invalid_site_plan_zoom")
        if "plan_zoom" in floor:
            normalized_floor["plan_zoom"] = float(plan_zoom)
        normalized_floors.append(normalized_floor)
    return {
        "name": name, "photo_data_url": photo, "photo_opacity": float(opacity),
        "photo_position_x": float(position_x), "photo_position_y": float(position_y),
        "photo_zoom": float(zoom), "photo_vignette": float(vignette), "floors": normalized_floors,
    }


def save_profile(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    result = normalize_profile(payload)
    conn.execute(
        "INSERT INTO system_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (PROFILE_KEY, json.dumps(result, ensure_ascii=False, separators=(",", ":"))),
    )
    return result
