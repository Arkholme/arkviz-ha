"""Error reports and usage metrics, both off until an admin turns them on. The browser only ever talks to Home Assistant: this
checks the home's settings and the account's opt-out, then sends to Sentry and PostHog itself. There's no queue, so what can't
be sent is dropped. Python errors aren't reported, as Sentry's own SDK here would hook all of Home Assistant."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import aiohttp
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry, device_registry, entity_registry, floor_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from . import keys
from .const import DATA_TELEMETRY, DOMAIN, TELEMETRY_STORAGE_KEY, TELEMETRY_STORAGE_VERSION
from .consent import ERRORS, SETTINGS, USAGE, Consent
from .limits import ErrorLimit
from .scrub import envelope_url, fingerprint, read_envelope_event, scrub_event, write_envelope
from .usage import ACCOUNT_ACTIVE, HOME_SNAPSHOT, build_event, plan_counts, plan_names

_LOGGER = logging.getLogger(__name__)

# An error report is small, so anything much bigger isn't one
MAX_ENVELOPE = 256 * 1024
# Reports being read and sent at once. Any more are dropped.
MAX_SENDING = 3

SEND_TIMEOUT = aiohttp.ClientTimeout(total=10)

# How soon after starting the day's snapshot is looked at, and how often after that. It's marked sent only once it has
# been, so a home that was offline tries again.
SNAPSHOT_FIRST_CHECK = timedelta(minutes=1)
SNAPSHOT_CHECK = timedelta(hours=1)


def _sentry_dsn() -> str | None:
    return keys.SENTRY_DSN if keys.SENTRY_DSN and envelope_url(keys.SENTRY_DSN) else None


def _posthog_url() -> str | None:
    if not keys.POSTHOG_KEY or not keys.POSTHOG_HOST:
        return None
    return f"{keys.POSTHOG_HOST.rstrip('/')}/i/v0/e/"


def _available() -> dict[str, bool]:
    return {ERRORS: _sentry_dsn() is not None, USAGE: _posthog_url() is not None}


def _now() -> datetime:
    return datetime.now(UTC)


def _today() -> str:
    return _now().date().isoformat()


class Telemetry:
    """The home's settings as saved in .storage/arkviz.telemetry, and sending what they allow."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, TELEMETRY_STORAGE_VERSION, TELEMETRY_STORAGE_KEY)
        self._consent: Consent | None = None
        self._limit = ErrorLimit()
        self._sending = 0

    async def consent(self) -> Consent:
        if self._consent is None:
            consent = Consent(await self._store.async_load())
            # A second caller may have read it too while this one waited, and only one of them can be kept
            if self._consent is None:
                self._consent = consent
                await self._store.async_save(consent.data)
        return self._consent

    async def save(self) -> None:
        await self._store.async_save((await self.consent()).data)

    async def status(self, user_id: str, is_admin: bool) -> dict[str, Any]:
        """What Settings and the first-run question show this account."""
        consent = await self.consent()
        available = _available()

        async def setting(name: str) -> dict[str, Any]:
            record = consent.record(name) or {}
            on = consent.is_on(name)
            user = await self._hass.auth.async_get_user(record["by"]) if on and record.get("by") else None
            return {
                "available": available[name],
                "on": on,
                "setBy": user.name if user else None,
                "setAt": record.get("at") if on else None,
            }

        return {
            "textVersion": consent.text_version,
            "isAdmin": is_admin,
            "needsAnswer": is_admin and consent.needs_answer(available),
            ERRORS: await setting(ERRORS),
            USAGE: await setting(USAGE),
            "optedOut": {name: consent.opted_out(user_id, name) for name in SETTINGS},
        }

    async def set_home(self, user_id: str, answers: dict[str, bool]) -> None:
        consent = await self.consent()
        available = _available()
        at = _now().isoformat()
        for name, on in answers.items():
            # A setting this build can't send has no question to answer yet
            if available[name]:
                consent.set_home(name, on, user_id, at)
        await self.save()
        # Just turned on, so today's counts needn't wait for the next hourly look
        if answers.get(USAGE):
            self._hass.async_create_background_task(self.send_snapshot(), "arkviz usage snapshot")

    async def set_opt_out(self, user_id: str, setting: str, out: bool) -> None:
        (await self.consent()).set_opt_out(user_id, setting, out)
        await self.save()

    async def opened(self, user_id: str) -> None:
        """An account opened ArkViz, which counts once a day while it may."""
        consent = await self.consent()
        account_id = consent.active_today(user_id, _today())
        if account_id is None:
            return
        await self.save()
        await self._send_event(ACCOUNT_ACTIVE, account_id, {})

    async def send_snapshot(self) -> None:
        """The day's counts for the whole home, if they're due."""
        consent = await self.consent()
        day = _today()
        home_id = consent.snapshot_due(day)
        if home_id is None:
            return
        stored = await self._hass.data[DOMAIN].async_get()
        plan = stored.get("plan") or {}
        integration = await async_get_integration(self._hass, DOMAIN)
        properties = {"arkviz_version": str(integration.version), "ha_version": HA_VERSION, **plan_counts(plan.get("text"))}
        if await self._send_event(HOME_SNAPSHOT, home_id, properties):
            consent.snapshot_sent(day)
            await self.save()

    async def _send_event(self, name: str, distinct_id: str, properties: dict[str, Any]) -> bool:
        url = _posthog_url()
        if url is None:
            return False
        event = build_event(keys.POSTHOG_KEY, name, distinct_id, _now().isoformat(), properties)
        return await self._post(url, json=event)

    @callback
    def report_error(self, user_id: str, envelope: str) -> None:
        """A report from the browser, if this account's reports are wanted. The answer to the browser doesn't wait for it."""
        if self._sending >= MAX_SENDING or self._limit.spent(time.time()):
            return
        self._sending += 1
        self._hass.async_create_background_task(self._send_error(user_id, envelope), "arkviz error report")

    async def _send_error(self, user_id: str, envelope: str) -> None:
        try:
            consent = await self.consent()
            dsn = _sentry_dsn()
            if dsn is None or not consent.allowed(user_id, ERRORS):
                return
            event = read_envelope_event(envelope)
            if event is None:
                return
            names = await self._home_names()
            scrubbed = await self._hass.async_add_executor_job(scrub_event, event, names, consent.home_id(ERRORS))
            if not self._limit.take(fingerprint(scrubbed), time.time()):
                return
            # Reading the names took a moment, and the setting may have gone off meanwhile
            if consent.allowed(user_id, ERRORS):
                url = envelope_url(dsn)
                body = write_envelope(scrubbed, dsn, _now().isoformat())
                await self._post(url, data=body, headers={"Content-Type": "application/x-sentry-envelope"})
        finally:
            self._sending -= 1

    async def _post(self, url: str, **kwargs: Any) -> bool:
        try:
            response = await async_get_clientsession(self._hass).post(url, timeout=SEND_TIMEOUT, **kwargs)
            async with response:
                return response.ok
        except (aiohttp.ClientError, TimeoutError) as e:
            # Only what kind of failure: the address and the report aren't for the log
            _LOGGER.debug("Couldn't send a report: %s", type(e).__name__)
            return False

    async def _home_names(self) -> set[str]:
        """Everything in this home with a name someone gave it, and the addresses it's known by."""
        hass = self._hass
        stored = await hass.data[DOMAIN].async_get()
        names = plan_names((stored.get("plan") or {}).get("text")) | plan_names(stored.get("draft"))
        names.update(area.name for area in area_registry.async_get(hass).async_list_areas())
        names.update(floor.name for floor in floor_registry.async_get(hass).async_list_floors())
        for device in device_registry.async_get(hass).devices.values():
            names.update(n for n in (device.name, device.name_by_user) if n)
        for entity in entity_registry.async_get(hass).entities.values():
            names.update(n for n in (entity.entity_id, entity.name, entity.original_name) if n)
        for state in hass.states.async_all():
            names.add(state.entity_id)
            friendly = state.attributes.get("friendly_name")
            if isinstance(friendly, str):
                names.add(friendly)
        names.update(user.name for user in await hass.auth.async_get_users() if user.name)
        names.add(hass.config.location_name)
        for url in (hass.config.internal_url, hass.config.external_url):
            host = urlsplit(url).hostname if url else None
            if host:
                names.add(host)
        return names


def setup_snapshots(hass: HomeAssistant) -> list[Any]:
    """Looks for the day's snapshot soon after starting and each hour after. Returns what stops it."""

    async def check(_now: datetime) -> None:
        await hass.data[DATA_TELEMETRY].send_snapshot()

    return [async_call_later(hass, SNAPSHOT_FIRST_CHECK, check), async_track_time_interval(hass, check, SNAPSHOT_CHECK)]


def _telemetry(hass: HomeAssistant) -> Telemetry:
    return hass.data[DATA_TELEMETRY]


@websocket_api.websocket_command({vol.Required("type"): "arkviz/telemetry"})
@websocket_api.async_response
async def ws_status(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """The home's two settings and this account's opt-outs. Anyone signed in can read them."""
    connection.send_result(msg["id"], await _telemetry(hass).status(connection.user.id, connection.user.is_admin))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "arkviz/telemetry/home",
        # The text the answer was given to: a page from before it changed can't answer for the new one
        vol.Required("textVersion"): int,
        vol.Optional(ERRORS): bool,
        vol.Optional(USAGE): bool,
    }
)
@websocket_api.async_response
async def ws_set_home(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """An admin's answer for the whole home."""
    telemetry = _telemetry(hass)
    consent = await telemetry.consent()
    if msg["textVersion"] != consent.text_version:
        connection.send_error(msg["id"], "text_changed", "This page shows an older version of what's sent. Reload it and answer again.")
        return
    await telemetry.set_home(connection.user.id, {name: msg[name] for name in SETTINGS if name in msg})
    connection.send_result(msg["id"], await telemetry.status(connection.user.id, connection.user.is_admin))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "arkviz/telemetry/opt_out",
        vol.Required("setting"): vol.In(SETTINGS),
        vol.Required("out"): bool,
    }
)
@websocket_api.async_response
async def ws_opt_out(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """One account leaving or rejoining a setting, for itself alone."""
    telemetry = _telemetry(hass)
    await telemetry.set_opt_out(connection.user.id, msg["setting"], msg["out"])
    connection.send_result(msg["id"], await telemetry.status(connection.user.id, connection.user.is_admin))


@websocket_api.websocket_command({vol.Required("type"): "arkviz/telemetry/opened"})
@websocket_api.async_response
async def ws_opened(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """This account opened ArkViz. It says nothing else, so nothing else can be sent."""
    await _telemetry(hass).opened(connection.user.id)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "arkviz/telemetry/error",
        vol.Required("envelope"): vol.All(str, vol.Length(max=MAX_ENVELOPE)),
    }
)
@callback
def ws_error(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """An error report from the browser, forwarded if it's wanted."""
    _telemetry(hass).report_error(connection.user.id, msg["envelope"])
    connection.send_result(msg["id"])


WEBSOCKET_COMMANDS = (ws_status, ws_set_home, ws_opt_out, ws_opened, ws_error)
