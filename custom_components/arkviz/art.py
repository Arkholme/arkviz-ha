"""Art for art mode, kept here so every screen can show it. Each screen chooses its own image, how long it waits and
whether there's a mat; this only keeps the images. They're files in the configuration folder, so backups include them."""

from __future__ import annotations

import asyncio
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from aiohttp import web

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import ART_FOLDER, ART_STORAGE_KEY, ART_STORAGE_VERSION, ART_URL, DATA_ART
from .images import ID, MAX_IMAGES, TYPES, Refused, read_image

# How long an image's signed address works. A screen asks for new ones each time it shows the art.
SIGNED_FOR = timedelta(days=1)


class ArtStore:
    """The list of images in .storage, and their files beside the configuration."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, ART_STORAGE_VERSION, ART_STORAGE_KEY)
        self._data: dict[str, Any] | None = None
        self._folder = Path(hass.config.path(ART_FOLDER))
        # Adding counts the images first, so two at once can't both take the last place
        self._lock = asyncio.Lock()

    async def async_images(self) -> list[dict[str, Any]]:
        if self._data is None:
            self._data = await self._store.async_load() or {"images": []}
        return self._data["images"]

    async def async_find(self, image_id: str) -> dict[str, Any] | None:
        return next((i for i in await self.async_images() if i["id"] == image_id), None)

    def file(self, image: dict[str, Any]) -> Path:
        return self._folder / f"{image['id']}.{TYPES[image['type']]}"

    async def async_add(self, name: str, kind: str, encoded: str, width: int, height: int) -> dict[str, Any]:
        data = read_image(kind, encoded)
        async with self._lock:
            images = await self.async_images()
            if len(images) >= MAX_IMAGES:
                raise Refused("full", f"Home Assistant keeps up to {MAX_IMAGES} images for art mode.")
            image = {"id": secrets.token_hex(16), "name": name, "type": kind, "width": width, "height": height, "added": dt_util.utcnow().isoformat()}
            await self._hass.async_add_executor_job(_write, self.file(image), data)
            images.append(image)
            await self._store.async_save(self._data)
        return image

    async def async_remove(self, image_id: str) -> bool:
        async with self._lock:
            image = await self.async_find(image_id)
            if image is None:
                return False
            images = await self.async_images()
            images.remove(image)
            await self._store.async_save(self._data)
            await self._hass.async_add_executor_job(_delete, self.file(image))
        return True


def _write(file: Path, data: bytes) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(data)


def _delete(file: Path) -> None:
    file.unlink(missing_ok=True)


class ArtView(HomeAssistantView):
    """One image's file. It takes a signed address, as an image on a page can't send a token."""

    url = f"{ART_URL}/{{image_id}}"
    name = "api:arkviz:art"

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request, image_id: str) -> web.StreamResponse:
        image = await _art(self._hass).async_find(image_id) if ID.match(image_id) else None
        if image is None:
            raise web.HTTPNotFound
        file = _art(self._hass).file(image)
        if not await self._hass.async_add_executor_job(file.is_file):
            raise web.HTTPNotFound
        # An image never changes under its id
        return web.FileResponse(file, headers={"Content-Type": image["type"], "Cache-Control": "private, max-age=31536000, immutable"})


def _art(hass: HomeAssistant) -> ArtStore:
    return hass.data[DATA_ART]


def _shown(hass: HomeAssistant, connection: websocket_api.ActiveConnection, image: dict[str, Any]) -> dict[str, Any]:
    """An image as the app reads it: its words and size, and an address to show it from that works for a day."""
    src = async_sign_path(hass, f"{ART_URL}/{image['id']}", SIGNED_FOR, refresh_token_id=connection.refresh_token_id)
    return {"id": image["id"], "name": image["name"], "width": image["width"], "height": image["height"], "src": src}


@websocket_api.websocket_command({vol.Required("type"): "arkviz/art"})
@websocket_api.async_response
async def ws_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Every image, newest first: `{ images }`."""
    images = await _art(hass).async_images()
    connection.send_result(msg["id"], {"images": [_shown(hass, connection, i) for i in reversed(images)]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "arkviz/art/add",
        vol.Required("name"): vol.All(str, vol.Length(max=200)),
        vol.Required("mime"): str,
        # Base64, checked against the limit before it's decoded
        vol.Required("data"): str,
        vol.Required("width"): vol.All(int, vol.Range(min=1, max=20000)),
        vol.Required("height"): vol.All(int, vol.Range(min=1, max=20000)),
    }
)
@websocket_api.async_response
async def ws_add(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Keeps a new image, and answers with it as `arkviz/art` lists it."""
    try:
        image = await _art(hass).async_add(msg["name"], msg["mime"], msg["data"], msg["width"], msg["height"])
    except Refused as err:
        connection.send_error(msg["id"], err.code, err.message)
        return
    connection.send_result(msg["id"], _shown(hass, connection, image))


# `id` is the message's own, so the image goes as `image`
@websocket_api.websocket_command({vol.Required("type"): "arkviz/art/remove", vol.Required("image"): str})
@websocket_api.async_response
async def ws_remove(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Removes an image, its file included, for every screen."""
    if not await _art(hass).async_remove(msg["image"]):
        connection.send_error(msg["id"], "not_found", "That image isn't kept here.")
        return
    connection.send_result(msg["id"])


WEBSOCKET_COMMANDS = (ws_list, ws_add, ws_remove)
