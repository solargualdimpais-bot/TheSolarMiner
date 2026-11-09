#!/usr/bin/env python3
"""Build a compact, normalized SolarMiner catalog from Zigbee2MQTT device docs.

The input is the upstream zigbee2mqtt.io/docs/devices Markdown tree. This keeps
the import reproducible and does not copy the full prose pages into SolarMiner.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


SOURCE_REPOSITORY = "https://github.com/Koenkk/zigbee2mqtt.io"


def clean(value: str) -> str:
    value = re.sub(r"!\[[^]]*\]\([^)]*\)", "", value)
    value = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"[`*_]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def table_value(text: str, key: str) -> str:
    match = re.search(r"^\|\s*" + re.escape(key) + r"\s*\|\s*(.*?)\s*\|\s*$", text, re.M | re.I)
    return clean(match.group(1)) if match else ""


def section(text: str, heading: str) -> str:
    match = re.search(r"^##\s+" + re.escape(heading) + r"\s*$", text, re.M | re.I)
    if not match:
        return ""
    tail = text[match.end() :]
    end = re.search(r"^##\s+", tail, re.M)
    return tail[: end.start()] if end else tail


def split_commas(value: str) -> list[str]:
    parts: list[str] = []
    start = depth = 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            item = clean(value[start:index])
            if item:
                parts.append(item)
            start = index + 1
    item = clean(value[start:])
    if item:
        parts.append(item)
    return parts


def parse_options(text: str) -> list[dict[str, str]]:
    lines = section(text, "Options").splitlines()
    result: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines:
        match = re.match(r"^\s*[*-]\s+`([^`]+)`\s*:\s*(.*)$", line)
        if match:
            if current:
                result.append(current)
            current = {"name": match.group(1).strip(), "description": clean(match.group(2))}
        elif current and line.strip() and not line.lstrip().startswith(("*", "-", "#")):
            current["description"] = clean(current["description"] + " " + line.strip())
    if current:
        result.append(current)
    return result


def parse_exposes(text: str) -> list[dict[str, Any]]:
    body = section(text, "Exposes")
    lines = body.splitlines()
    blocks: list[tuple[str, str, list[str]]] = []
    current: tuple[str, str, list[str]] | None = None
    for line in lines:
        heading = re.match(r"^###\s+(.+?)(?:\s+\(([^)]+)\))?\s*$", line)
        if heading:
            if current:
                blocks.append(current)
            current = (clean(heading.group(1)), clean(heading.group(2) or "unknown"), [])
        elif current:
            current[2].append(line)
    if current:
        blocks.append(current)

    records: list[dict[str, Any]] = []
    for label, kind, content_lines in blocks:
        content = "\n".join(content_lines)
        properties: list[str] = []
        for token in re.findall(r"`([^`]+)`", content):
            token = token.strip()
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", token) and token not in {
                "FRIENDLY_NAME", "VALUE", "ON", "OFF", "TOGGLE"
            } and token not in properties:
                properties.append(token)

        set_supported: bool | None = None
        if re.search(r"\b(To control|To write|publish a message|send a message)\b|/set", content, re.I):
            set_supported = True
        elif re.search(r"not possible[^\n]{0,60}/set|Writing \(`/set`\)[^\n]{0,60}not possible", content, re.I):
            set_supported = False
        get_supported: bool | None = None
        if re.search(r"\bTo read\b|read a message publish|Reading \(`/get`\)[^\n]{0,30}possible", content, re.I):
            get_supported = True
        elif re.search(r"not possible[^\n]{0,60}/get|Reading \(`/get`\)[^\n]{0,60}not possible", content, re.I):
            get_supported = False
        reports_state = bool(re.search(r"published state|state is published|reported state", content, re.I))
        unit_match = re.search(r"(?:unit of this value|unit) is `([^`]+)`", content, re.I)
        limits: dict[str, float] = {}
        for key, pattern in (
            ("min", r"(?:minimal|minimum) value is `?(-?[\d.]+)"),
            ("max", r"(?:maximum|maximal) value is `?(-?[\d.]+)"),
            ("step", r"(?:step size|step) of `?(-?[\d.]+)"),
        ):
            match = re.search(pattern, content, re.I)
            if match:
                try:
                    limits[key] = float(match.group(1))
                except ValueError:
                    pass

        values: list[str] = []
        value_match = re.search(r"(?:one of|possible values are):\s*([^\n.]+)", content, re.I)
        if value_match:
            values = [clean(value).strip("` ") for value in re.split(r",\s*|\s+or\s+", value_match.group(1)) if clean(value)]

        examples: list[dict[str, Any]] = []
        for raw in re.findall(r"`(\{[^`]+\})`", content):
            try:
                command = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(command, dict):
                examples.append(command)

        records.append(
            {
                "label": label,
                "type": kind,
                "properties": properties,
                "get_supported": get_supported,
                "reports_state": reports_state,
                "set_supported": set_supported,
                "unit": unit_match.group(1) if unit_match else None,
                "limits": limits,
                "values": values,
                "set_examples": examples,
            }
        )
    return records


def load_device(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "model": table_value(text, "Model") or path.stem,
        "manufacturer": table_value(text, "Vendor") or "Unknown",
        "description": table_value(text, "Description") or None,
        "protocol": "zigbee2mqtt",
        "product_id": path.stem,
        "features": split_commas(table_value(text, "Exposes")),
        "capabilities": parse_exposes(text),
        "options": parse_options(text),
        "source_url": f"https://www.zigbee2mqtt.io/devices/{path.stem}.html",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docs_root", type=Path, help="Path to upstream docs/devices")
    parser.add_argument("output", type=Path)
    parser.add_argument("--commit", required=True, help="Exact upstream documentation commit SHA")
    parser.add_argument("--site-count", type=int, default=None, help="Supported count shown on the upstream website")
    args = parser.parse_args()
    paths = sorted(args.docs_root.glob("*.md"))
    profiles = [load_device(path) for path in paths]
    document = {
        "schema_version": 1,
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": args.commit,
        "source_commit_url": f"{SOURCE_REPOSITORY}/commit/{args.commit}",
        "source_license": "GPL-3.0 (upstream documentation repository)",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "supported_device_count_reported_by_site": args.site_count,
        "documentation_profiles_imported": len(profiles),
        "profiles": profiles,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(
        f"Imported {len(profiles)} profiles, "
        f"{sum(len(item['capabilities']) for item in profiles)} capability records, "
        f"{sum(len(item['options']) for item in profiles)} device options; "
        f"{args.output.stat().st_size:,} bytes"
    )


if __name__ == "__main__":
    main()
