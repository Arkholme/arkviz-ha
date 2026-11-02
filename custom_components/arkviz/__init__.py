"""ArkViz in Home Assistant: your home drawn in a sidebar panel and on a page of its own, and one plan kept here for every screen."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from aiohttp import web

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import APP_URL, CONF_SIDEBAR, DATA_TELEMETRY, DEFAULT_SIDEBAR, DOMAIN, FILES_URL, PANEL_ELEMENT, PANEL_URL, STORAGE_KEY, STORAGE_VERSION
from .telemetry import WEBSOCKET_COMMANDS, Telemetry, setup_snapshots

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# How long draft writes wait to be gathered into one, as the editor keeps its draft on every change
DRAFT_DELAY = 2


class PlanStore:
    """The saved plan and the changes made since, as the app's PlanStorage reads and writes them."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] | None = None

    async def async_get(self) -> dict[str, Any]:
        if self._data is None:
            self._data = await self._store.async_load() or {"plan": None, "draft": None}
        return self._data

    async def async_save_plan(self, text: str, revision: dict[str, Any]) -> None:
        data = await self.async_get()
        data["plan"] = {"text": text, "revision": revision}
        await self._store.async_save(data)

    async def async_save_draft(self, text: str | None) -> None:
        data = await self.async_get()
        data["draft"] = text
        self._store.async_delay_save(lambda: data, DRAFT_DELAY)


class FilesView(HomeAssistantView):
    """The panel and the app's files. The app's assets are named by their contents, so browsers keep them; the rest are
    checked on every load, so a new build shows at once instead of a page that asks for assets it no longer has."""

    url = f"{FILES_URL}/{{path:.+}}"
    name = "arkviz:files"
    # Loaded by the browser as a page and its scripts, which carry no token, like Home Assistant's own frontend files
    requires_auth = False

    def __init__(self, hass: HomeAssistant, root: Path) -> None:
        self._hass = hass
        self._root = root.resolve()

    async def get(self, request: web.Request, path: str) -> web.StreamResponse:
        file = (self._root / path).resolve()
        if not file.is_relative_to(self._root) or not await self._hass.async_add_executor_job(file.is_file):
            raise web.HTTPNotFound
        keep = file.parent.name == "assets"
        return web.FileResponse(file, headers={"Cache-Control": "public, max-age=31536000, immutable" if keep else "no-cache"})


class AppView(FilesView):
    """ArkViz as a page of its own. It signs in for itself, as Home Assistant's own pages do."""

    url = f"{APP_URL}/{{path:.*}}"
    extra_urls = [APP_URL]
    name = "arkviz:app"

    async def get(self, request: web.Request, path: str = "") -> web.StreamResponse:
        # The page finds its files relative to its address, so that has to end in a slash
        if request.path == APP_URL:
            raise web.HTTPFound(f"{APP_URL}/")
        return await super().get(request, path or "index.html")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the app's files and answer its commands. Neither can be taken back, so they're set up once."""
    hass.data[DOMAIN] = PlanStore(hass)
    hass.data[DATA_TELEMETRY] = Telemetry(hass)
    www = Path(__file__).parent / "www"
    hass.http.register_view(FilesView(hass, www))
    hass.http.register_view(AppView(hass, www / "app"))
    websocket_api.async_register_command(hass, ws_get_plan)
    websocket_api.async_register_command(hass, ws_save_plan)
    websocket_api.async_register_command(hass, ws_save_draft)
    for command in WEBSOCKET_COMMANDS:
        websocket_api.async_register_command(hass, command)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Put ArkViz in the sidebar, unless it's been asked not to be there. Changing that sets it up again."""
    entry.async_on_unload(entry.add_update_listener(_async_options_changed))
    for stop in setup_snapshots(hass):
        entry.async_on_unload(stop)
    if not entry.options.get(CONF_SIDEBAR, DEFAULT_SIDEBAR):
        return True
    integration = await async_get_integration(hass, DOMAIN)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="ArkViz",
        sidebar_icon="mdi:floor-plan",
        # The version makes browsers fetch the panel afresh after an update
        module_url=f"{FILES_URL}/panel.js?v={integration.version}",
        require_admin=False,
        config={},
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Take ArkViz out of the sidebar. The plan stays, for when it's added again."""
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
    return True


async def _async_options_changed(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _plans(hass: HomeAssistant) -> PlanStore:
    return hass.data[DOMAIN]


@websocket_api.websocket_command({vol.Required("type"): "arkviz/plan"})
@websocket_api.async_response
async def ws_get_plan(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """The last saved revision and the changes made since: `{ plan, draft }`."""
    connection.send_result(msg["id"], await _plans(hass).async_get())


@websocket_api.websocket_command(
    {
        vol.Required("type"): "arkviz/plan/save",
        vol.Required("text"): str,
        vol.Required("revision"): {
            vol.Required("number"): int,
            vol.Required("savedAt"): vol.Any(str, None),
        },
    }
)
@websocket_api.async_response
async def ws_save_plan(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Keeps a new revision."""
    await _plans(hass).async_save_plan(msg["text"], msg["revision"])
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "arkviz/draft/save",
        vol.Required("text"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_save_draft(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Keeps the changes made since the last save, or clears them with null."""
    await _plans(hass).async_save_draft(msg["text"])
    connection.send_result(msg["id"])
