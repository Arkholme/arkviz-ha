"""What a report keeps on its way to Sentry. Each report is rebuilt from a short list of what helps fix a bug, so anything else
is left behind, and its text has this home's names and anything that looks private taken out. The browser does the same with
src/telemetry/scrub.ts, which doesn't know the names. tests/scrub-cases.json holds both to the same results."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

REDACTED = "[redacted]"

# Names shorter than this would match inside ordinary words
_MIN_NAME_LENGTH = 3
_MAX_NAMES = 20_000

# The longest any one piece of text is kept
_MAX_TEXT = 2000

_MAX_FRAMES = 60
_MAX_EXCEPTIONS = 5

# Home Assistant's domains, written as src/telemetry/scrub.ts has them
_ENTITY_DOMAINS = (
    "air_quality|alarm_control_panel|automation|binary_sensor|button|calendar|camera|climate|conversation|counter|cover|"
    "date|datetime|device_tracker|event|fan|geo_location|group|humidifier|image|input_boolean|input_button|input_datetime|"
    "input_number|input_select|input_text|lawn_mower|light|lock|media_player|notify|number|person|remote|scene|script|"
    "select|sensor|siren|stt|sun|switch|text|time|timer|todo|tts|update|vacuum|valve|wake_word|water_heater|weather|zone"
)

_ENTITY_ID = re.compile(rf"\b(?:{_ENTITY_DOMAINS})\.[a-z0-9_]+\b(?![.(])", re.ASCII)
# Registry IDs: 32 hex characters, or a ULID
_REGISTRY_ID = re.compile(r"\b(?:[0-9a-f]{32}|[0-9A-HJKMNP-TV-Z]{26})\b", re.ASCII)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.ASCII)
_JWT = re.compile(r"\beyJ[\w-]{6,}\.[\w-]{6,}\.[\w-]*", re.ASCII)
_BEARER = re.compile(r"\bBearer\s+[\w.~+/=-]+", re.ASCII | re.IGNORECASE)
_TOKEN_FIELD = re.compile(
    r"\b(access_token|refresh_token|auth_code|client_secret|api_key|apikey|password|token)"
    r"([\"']?\s*[:=]\s*[\"']?)[^\s\"'&,;}]+",
    re.ASCII | re.IGNORECASE,
)

# A URL's query string or fragment, which can carry anything
_URL_QUERY = re.compile(r"(\b[a-z][a-z\d+.-]*://[^\s?#\"'<>]*|(?<![\w/])/[\w\-./~%]*)([?#][^\s\"'<>)]*)", re.ASCII | re.IGNORECASE)
_URL_HOST = re.compile(r"\b([a-z][a-z\d+.-]*://)[^/\s\"'<>)]+", re.ASCII | re.IGNORECASE)
_HOSTNAME = re.compile(
    r"\b[\w-]+(?:\.[\w-]+)*\.(?:local|localdomain|lan|home\.arpa|home|internal|intranet|duckdns\.org|ui\.nabu\.casa)\b",
    re.ASCII | re.IGNORECASE,
)

_IPV4 = re.compile(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b", re.ASCII)
# IPv6 with a `::`, eight full groups, or a link-local or unique-local prefix. Clock times (12:30:45) don't match.
_IPV6 = re.compile(
    r"(?<![\w:])(?:(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}|(?:[0-9a-f]{1,4}:){1,7}:(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*)?"
    r"|::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*)?|f[cde][0-9a-f]{2}:(?::?[0-9a-f]{1,4}){1,7})(?:%[\w.-]+)?(?![\w:])",
    re.ASCII | re.IGNORECASE,
)

_JSON_ATTRIBUTES = re.compile(r'("attributes"\s*:\s*)\{[^{}]*\}', re.ASCII | re.IGNORECASE)
_JSON_NAME_FIELD = re.compile(
    r'("(?:name|friendly_name|original_name|name_by_user|email|label|title|displayName|username|location_name|area|area_id|'
    r'floor|floor_id|room|device|device_id|entity|entity_id|text|draft|plan|url|external_url|internal_url)"\s*:\s*)'
    r'"(?:[^"\\]|\\.)*"',
    re.ASCII | re.IGNORECASE,
)
_JSON_VALUE_FIELD = re.compile(
    r'("(?:state|value|brightness|temperature|current_temperature|target_temp_low|target_temp_high|humidity|position)"'
    r'\s*:\s*)(?:-?\d+(?:\.\d+)?(?:e[+-]?\d+)?|"(?:[^"\\]|\\.)*")',
    re.ASCII | re.IGNORECASE,
)

# A quoted value after a word that names something in a home: `Room "Mason's office" has no floor`. A single quote only
# closes before a non-word character, so `Mason's` stays inside the value. Not after a quote: a JSON key is the fields' above.
_ENTITY_QUOTED = re.compile(
    r"(?<![\"'])\b(room|floor|area|device|light|fixture|fan|sensor|switch|lock|thermostat|shade|speaker|camera|entity|scene|"
    r"user|account|person|home|house|plan|parameter|name|label|title|network|ssid)"
    r"(s?\b(?:\s+(?:named|called|with\s+name))?\s*[:=]?\s*)"
    r"('(?:[^'\n]|'(?=\w))+'(?!\w)|\"[^\"\n]*\"|`[^`\n]*`|“[^”\n]*”|‘[^’\n]*’)",
    re.ASCII | re.IGNORECASE,
)


def _requote(quoted: str) -> str:
    return f"{quoted[0]}{REDACTED}{quoted[-1]}"


def _names_pattern(names: Iterable[str] | None) -> re.Pattern[str] | None:
    if not names:
        return None
    unique = {name.strip() for name in names if isinstance(name, str) and len(name.strip()) >= _MIN_NAME_LENGTH}
    if not unique:
        return None
    alternatives = []
    # Longest first, so "Upper floor 2" wins over "Upper floor"
    for name in sorted(unique, key=len, reverse=True)[:_MAX_NAMES]:
        # Word boundaries only where the name itself starts or ends with a word character, so "Den" doesn't match "Dented"
        start = r"\b" if re.match(r"\w", name[0]) else ""
        end = r"\b" if re.match(r"\w", name[-1]) else ""
        alternatives.append(f"{start}{re.escape(name)}{end}")
    return re.compile("|".join(alternatives), re.IGNORECASE)


def text_scrubber(names: Iterable[str] | None = None):
    """The string scrubber, with this home's names if given."""
    pattern = _names_pattern(names)

    def scrub(text: str) -> str:
        out = text[:_MAX_TEXT]
        if pattern:
            out = pattern.sub(REDACTED, out)
        out = _EMAIL.sub("[email]", out)
        out = _JWT.sub("[token]", out)
        out = _BEARER.sub("Bearer [token]", out)
        out = _TOKEN_FIELD.sub(lambda m: f"{m[1]}{m[2]}[token]", out)
        out = _URL_QUERY.sub(lambda m: f"{m[1]}?{REDACTED}", out)
        out = _URL_HOST.sub(lambda m: f"{m[1]}[host]", out)
        out = _HOSTNAME.sub("[host]", out)
        out = _IPV4.sub("[ip]", out)
        out = _IPV6.sub("[ip]", out)
        out = _ENTITY_ID.sub("[entity]", out)
        out = _REGISTRY_ID.sub("[id]", out)
        out = _JSON_ATTRIBUTES.sub(lambda m: f'{m[1]}"{REDACTED}"', out)
        out = _JSON_NAME_FIELD.sub(lambda m: f'{m[1]}"{REDACTED}"', out)
        out = _JSON_VALUE_FIELD.sub(lambda m: f'{m[1]}"{REDACTED}"', out)
        return _ENTITY_QUOTED.sub(lambda m: f"{m[1]}{m[2]}{_requote(m[3])}", out)

    return scrub


_ORIGIN = re.compile(r"^[a-z][a-z\d+.-]*://[^/?#]*", re.ASCII | re.IGNORECASE)


def _code_path(url: Any) -> str | None:
    """A code file's path: no host, query string or fragment. `app://` stands in for the host, so a page's address is never sent."""
    if not isinstance(url, str):
        return None
    without_query = re.sub(r"[?#].*$", "", url, flags=re.DOTALL)
    return _ORIGIN.sub("app://", without_query)[:_MAX_TEXT]


def _frame(frame: Any) -> dict[str, Any] | None:
    if not isinstance(frame, dict):
        return None
    out: dict[str, Any] = {}
    # Function names and paths are the code's own. Local variables and source lines stay behind.
    for key in ("filename", "abs_path"):
        path = _code_path(frame.get(key))
        if path:
            out[key] = path
    if isinstance(frame.get("function"), str):
        out["function"] = frame["function"][:200]
    for key in ("lineno", "colno"):
        if isinstance(frame.get(key), int):
            out[key] = frame[key]
    if isinstance(frame.get("in_app"), bool):
        out["in_app"] = frame["in_app"]
    return out


def _exception(value: Any, text) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, Any] = {}
    if isinstance(value.get("type"), str):
        out["type"] = text(value["type"])
    if isinstance(value.get("value"), str):
        out["value"] = text(value["value"])
    mechanism = value.get("mechanism")
    if isinstance(mechanism, dict):
        kept = {k: mechanism[k] for k in ("type", "handled", "synthetic") if isinstance(mechanism.get(k), (str, bool))}
        if isinstance(kept.get("type"), str):
            kept["type"] = text(kept["type"])
        out["mechanism"] = kept
    stacktrace = value.get("stacktrace")
    frames = stacktrace.get("frames") if isinstance(stacktrace, dict) else None
    if isinstance(frames, list):
        out["stacktrace"] = {"frames": [f for f in map(_frame, frames[-_MAX_FRAMES:]) if f is not None]}
    return out


def _debug_images(debug_meta: Any) -> list[dict[str, str]]:
    images = debug_meta.get("images") if isinstance(debug_meta, dict) else None
    out = []
    for image in images if isinstance(images, list) else []:
        if not isinstance(image, dict) or not isinstance(image.get("debug_id"), str):
            continue
        code_file = _code_path(image.get("code_file"))
        # Sentry finds a frame's source map by this path, so it's the frames' own
        if code_file and image.get("type") == "sourcemap":
            out.append({"type": "sourcemap", "code_file": code_file, "debug_id": image["debug_id"][:64]})
    return out


# The pages of the app, the only values the `route` tag can have
_ROUTES = {"/", "/editor", "/settings", "/components", "other"}

_RELEASE = re.compile(r"^[\w.+-]{1,64}$", re.ASCII)
_LEVELS = {"fatal", "error", "warning", "info", "debug"}


def scrub_event(event: dict[str, Any], names: Iterable[str] | None = None, home_id: str | None = None) -> dict[str, Any]:
    """A new event holding only what's listed here. `home_id` is the setting's random ID, and the only user Sentry hears of."""
    text = text_scrubber(names)
    out: dict[str, Any] = {
        # No IP address, and Sentry must not take one from the connection: a home's public address locates it. Sentry looks
        # up a city from the connection even so, unless the event already has a location, so this one has an empty one.
        "user": {"ip_address": None, "geo": {}, **({"id": home_id} if home_id else {})},
        "sdk": {"settings": {"infer_ip": "never"}},
    }
    if isinstance(event.get("event_id"), str) and re.fullmatch(r"[0-9a-f]{32}", event["event_id"]):
        out["event_id"] = event["event_id"]
    if isinstance(event.get("timestamp"), (int, float)):
        out["timestamp"] = event["timestamp"]
    if event.get("platform") == "javascript":
        out["platform"] = "javascript"
    if event.get("level") in _LEVELS:
        out["level"] = event["level"]
    for key in ("release", "environment"):
        if isinstance(event.get(key), str) and _RELEASE.match(event[key]):
            out[key] = event[key]
    sdk = event.get("sdk")
    if isinstance(sdk, dict):
        for key in ("name", "version"):
            if isinstance(sdk.get(key), str) and _RELEASE.match(sdk[key].replace("/", ".")):
                out["sdk"][key] = sdk[key]
    if isinstance(event.get("message"), str):
        out["message"] = text(event["message"])
    exception = event.get("exception")
    values = exception.get("values") if isinstance(exception, dict) else None
    if isinstance(values, list):
        out["exception"] = {"values": [e for e in (_exception(v, text) for v in values[-_MAX_EXCEPTIONS:]) if e is not None]}
    images = _debug_images(event.get("debug_meta"))
    if images:
        out["debug_meta"] = {"images": images}
    tags = event.get("tags")
    if isinstance(tags, dict) and tags.get("route") in _ROUTES:
        out["tags"] = {"route": tags["route"]}
    request = event.get("request")
    headers = request.get("headers") if isinstance(request, dict) else None
    # Which browser, which Sentry reads into its browser and operating system contexts
    if isinstance(headers, dict) and isinstance(headers.get("User-Agent"), str):
        out["request"] = {"headers": {"User-Agent": text_scrubber()(headers["User-Agent"])[:400]}}
    return out


def fingerprint(event: dict[str, Any]) -> str:
    """The same error from the same place, however many times it's thrown. Reads a scrubbed event."""
    parts: list[str] = [str(event.get("message", ""))]
    for value in (event.get("exception") or {}).get("values", []):
        parts += [str(value.get("type", "")), str(value.get("value", ""))]
        frames = (value.get("stacktrace") or {}).get("frames", [])
        if frames:
            top = frames[-1]
            parts += [str(top.get("filename", "")), str(top.get("function", "")), str(top.get("lineno", ""))]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def read_envelope_event(envelope: str) -> dict[str, Any] | None:
    """The first event in a Sentry envelope. Everything else in it, such as sessions or attachments, stays behind."""
    data = envelope.encode()
    # The envelope's own header comes first
    position = data.find(b"\n")
    while 0 <= position < len(data):
        position += 1
        end = data.find(b"\n", position)
        if end < 0:
            return None
        try:
            header = json.loads(data[position:end])
            length = header.get("length")
            if isinstance(length, int):
                payload = data[end + 1 : end + 1 + length]
                position = end + 1 + length
            else:
                stop = data.find(b"\n", end + 1)
                stop = stop if stop >= 0 else len(data)
                payload = data[end + 1 : stop]
                position = stop
            if header.get("type") == "event":
                event = json.loads(payload)
                return event if isinstance(event, dict) else None
        except (ValueError, AttributeError):
            return None
    return None


def write_envelope(event: dict[str, Any], dsn: str, sent_at: str) -> str:
    """An envelope holding one event, for this build's Sentry project whatever the browser's said."""
    header = {"sent_at": sent_at, "dsn": dsn, **({"event_id": event["event_id"]} if "event_id" in event else {})}
    payload = json.dumps(event, separators=(",", ":"))
    return "\n".join((json.dumps(header), json.dumps({"type": "event", "content_type": "application/json"}), payload)) + "\n"


def envelope_url(dsn: str) -> str | None:
    """Where a DSN's envelopes go, or None if it isn't one."""
    parts = urlsplit(dsn)
    project = parts.path.rsplit("/", 1)[-1]
    if not parts.scheme or not parts.hostname or not parts.username or not project.isdigit():
        return None
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}/api/{project}/envelope/?sentry_key={parts.username}&sentry_version=7"
