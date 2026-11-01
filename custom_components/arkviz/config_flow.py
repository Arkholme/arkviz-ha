"""Adding ArkViz from Settings, Devices and services, and its one option: whether it shows in the sidebar."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import CONF_SIDEBAR, DEFAULT_SIDEBAR, DOMAIN


class ArkVizConfigFlow(ConfigFlow, domain=DOMAIN):
    """Asks once, then adds ArkViz."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ArkVizOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="ArkViz", data={})
        return self.async_show_form(step_id="user")


class ArkVizOptionsFlow(OptionsFlow):
    """Shows ArkViz in the sidebar or not. Its own address works either way."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self._entry.options.get(CONF_SIDEBAR, DEFAULT_SIDEBAR)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({vol.Required(CONF_SIDEBAR, default=current): bool}))
