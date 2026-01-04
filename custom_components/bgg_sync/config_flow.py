"""Config flow for BGG Sync integration."""
from __future__ import annotations

import logging
from typing import Any

import requests
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_BGG_USERNAME, CONF_BGG_PASSWORD, CONF_API_TOKEN, CONF_GAMES, BASE_URL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BGG_USERNAME): str,
        vol.Optional(CONF_BGG_PASSWORD): str,
        vol.Optional(CONF_API_TOKEN): str,
        vol.Optional(CONF_GAMES): str,
    }
)

class BggSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BGG Sync."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_BGG_USERNAME]
            # No validation here, we trust the input.
            return self.async_create_entry(title=username, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> BggOptionsFlowHandler:
        """Get the options flow for this handler."""
        return BggOptionsFlowHandler(config_entry)

class BggOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for BGG Sync."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_BGG_PASSWORD,
                        default=self.config_entry.data.get(CONF_BGG_PASSWORD, ""),
                    ): str,
                    vol.Optional(
                        CONF_API_TOKEN,
                        default=self.config_entry.data.get(CONF_API_TOKEN, ""),
                    ): str,
                    vol.Optional(
                        CONF_GAMES,
                        default=self.config_entry.data.get(CONF_GAMES, ""),
                    ): str,
                }
            ),
            errors=errors
        )
