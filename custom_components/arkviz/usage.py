"""The fixed list of usage events, and what they count from a saved plan. There's no way to send anything not listed here."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

# src/sketch/types.ts' DeviceKind, which a test holds these to
DEVICE_KINDS = (
    "downlight",
    "pendant",
    "sconce",
    "lamp",
    "switch",
    "outlet",
    "thermostat",
    "temperature",
    "motion",
    "contact",
    "lock",
    "shade",
    "speaker",
    "smoke",
    "camera",
    "leak",
)

HOME_SNAPSHOT = "home_snapshot"
ACCOUNT_ACTIVE = "account_active"

# Each event's properties and their types, all of them required and no others allowed
EVENTS: dict[str, dict[str, type]] = {
    HOME_SNAPSHOT: {
        "arkviz_version": str,
        "ha_version": str,
        "floors": int,
        "rooms": int,
        "devices": int,
        **{f"devices_{kind}": int for kind in DEVICE_KINDS},
        "devices_other": int,
    },
    ACCOUNT_ACTIVE: {},
}

# On every event: which app it's from, as the PostHog project is shared with Arkholme's other apps, then no person profile
# and no looking up where the request came from
_FIXED_PROPERTIES = {"app": "arkviz", "$process_person_profile": False, "$geoip_disable": True}


def build_event(api_key: str, name: str, distinct_id: str, at: str, properties: dict[str, Any]) -> dict[str, Any]:
    """One event for PostHog's capture API. Anything off the list raises ValueError instead of being sent."""
    expected = EVENTS.get(name)
    if expected is None:
        raise ValueError("Unknown event")
    if set(properties) != set(expected):
        raise ValueError("Wrong properties")
    for key, value in properties.items():
        # bool is an int to Python, but it's no count
        if not isinstance(value, expected[key]) or isinstance(value, bool):
            raise ValueError("Wrong property type")
    return {
        "api_key": api_key,
        "event": name,
        "distinct_id": distinct_id,
        "timestamp": at,
        "properties": {**properties, **_FIXED_PROPERTIES},
    }


def _read(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        house = json.loads(text)
    except ValueError:
        return {}
    return house if isinstance(house, dict) else {}


def _floors(house: dict[str, Any]) -> list[dict[str, Any]]:
    floors = house.get("floors")
    return [f for f in floors if isinstance(f, dict)] if isinstance(floors, list) else []


def _items(floor: dict[str, Any], key: str) -> list[dict[str, Any]]:
    doc = floor.get("doc")
    items = doc.get(key) if isinstance(doc, dict) else None
    return [i for i in items.values() if isinstance(i, dict)] if isinstance(items, dict) else []


def plan_counts(text: str | None) -> dict[str, int]:
    """How many floors, rooms and devices of each kind a saved plan has. A plan that can't be read has none."""
    floors = _floors(_read(text))
    counts = {"floors": len(floors), "rooms": 0, "devices": 0, "devices_other": 0}
    counts.update({f"devices_{kind}": 0 for kind in DEVICE_KINDS})
    for floor in floors:
        counts["rooms"] += len(_items(floor, "rooms"))
        for device in _items(floor, "devices"):
            counts["devices"] += 1
            kind = device.get("kind")
            counts[f"devices_{kind}" if kind in DEVICE_KINDS else "devices_other"] += 1
    return counts


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value


def plan_names(text: str | None) -> set[str]:
    """Everything named in a saved plan, for taking out of error reports."""
    house = _read(text)
    names: set[str] = set()
    for parameter in house.get("parameters") or []:
        if isinstance(parameter, dict):
            names.update(_strings(parameter.get("name")))
    for floor in _floors(house):
        names.update(_strings(floor.get("name")))
        for room in _items(floor, "rooms"):
            names.update(_strings(room.get("name")))
        for device in _items(floor, "devices"):
            names.update(_strings(device.get("name")))
            names.update(_strings(device.get("entity")))
    return names
