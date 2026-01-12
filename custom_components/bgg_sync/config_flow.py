"""Config flow for BGG Sync integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .api import BggClient
from .const import (
    DOMAIN,
    CONF_BGG_USERNAME,
    CONF_BGG_PASSWORD,
    CONF_API_TOKEN,
    CONF_GAMES,
    CONF_ENABLE_LOGGING,
    CONF_IMPORT_COLLECTION,
    CONF_ENABLE_SHELF_TODO,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect."""
    errors = {}

    if data.get(CONF_ENABLE_LOGGING) and not data.get(CONF_BGG_PASSWORD):
        errors[CONF_BGG_PASSWORD] = "password_required_for_logging"

    username = data[CONF_BGG_USERNAME]
    token = data[CONF_API_TOKEN].strip()
    password = data.get(CONF_BGG_PASSWORD)

    try:
        session = async_get_clientsession(hass)
        client = BggClient(session, username, password, token)
        status = await client.validate_auth()

        if status == 401:
            errors[CONF_API_TOKEN] = "invalid_auth"
        elif status == 202:
            _LOGGER.warning(
                "BGG returned 202 Accepted. Your collection is being processed and may take some time to appear."
            )
        elif status != 200:
            errors["base"] = "cannot_connect"

    except Exception:
        errors["base"] = "cannot_connect"

    return errors


class BggSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BGG Sync."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await validate_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_BGG_USERNAME], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BGG_USERNAME): str,
                    vol.Required(CONF_API_TOKEN): str,
                    vol.Optional(CONF_ENABLE_LOGGING, default=False): bool,
                    vol.Optional(CONF_BGG_PASSWORD): str,
                    vol.Optional(CONF_GAMES): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> BggOptionsFlowHandler:
        """Get the options flow for this handler."""
        return BggOptionsFlowHandler()


class BggOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for BGG Sync."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            full_input = {**self.config_entry.data, **user_input}
            errors = await validate_input(self.hass, full_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_TOKEN,
                        default=self.config_entry.options.get(
                            CONF_API_TOKEN,
                            self.config_entry.data.get(CONF_API_TOKEN, ""),
                        ),
                    ): str,
                    vol.Optional(
                        CONF_ENABLE_LOGGING,
                        default=self.config_entry.options.get(
                            CONF_ENABLE_LOGGING,
                            self.config_entry.data.get(CONF_ENABLE_LOGGING, False),
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_IMPORT_COLLECTION,
                        default=self.config_entry.options.get(
                            CONF_IMPORT_COLLECTION, False
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_ENABLE_SHELF_TODO,
                        default=self.config_entry.options.get(
                            CONF_ENABLE_SHELF_TODO, True
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_BGG_PASSWORD,
                        default=self.config_entry.options.get(
                            CONF_BGG_PASSWORD,
                            self.config_entry.data.get(CONF_BGG_PASSWORD, ""),
                        ),
                    ): str,
                    vol.Optional(
                        CONF_GAMES,
                        default=self.config_entry.options.get(
                            CONF_GAMES, self.config_entry.data.get(CONF_GAMES, "")
                        ),
                    ): str,
                }
            ),
            errors=errors,
        )
