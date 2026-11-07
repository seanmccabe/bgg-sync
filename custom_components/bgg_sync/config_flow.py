"""Config flow for BGG Sync integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from bgg_pi import BggClient
from .const import (
    DOMAIN,
    CONF_BGG_USERNAME,
    CONF_BGG_PASSWORD,
    CONF_API_TOKEN,
    CONF_GAMES,
    CONF_ENABLE_LOGGING,
    CONF_IMPORT_COLLECTION,
    CONF_ENABLE_SHELF_TODO,
    USER_AGENT,
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
        client = BggClient(session, username, password, token, user_agent=USER_AGENT)
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

        data_schema = vol.Schema(
            {
                vol.Required(CONF_BGG_USERNAME): str,
                vol.Required(CONF_API_TOKEN): str,
                vol.Optional(CONF_ENABLE_LOGGING, default=False): bool,
                vol.Optional(CONF_BGG_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return BggOptionsFlowHandler(config_entry)


class BggOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle BGG Sync options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

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

        # Merge data and options to show current values
        current_config = {**self.config_entry.data, **self.config_entry.options}

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_TOKEN, default=current_config.get(CONF_API_TOKEN, "")
                ): str,
                vol.Optional(
                    CONF_ENABLE_LOGGING,
                    default=current_config.get(CONF_ENABLE_LOGGING, False),
                ): bool,
                vol.Optional(
                    CONF_BGG_PASSWORD,
                    description={
                        "suggested_value": current_config.get(CONF_BGG_PASSWORD, "")
                    },
                ): str,
                vol.Optional(
                    CONF_IMPORT_COLLECTION,
                    default=current_config.get(CONF_IMPORT_COLLECTION, False),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_SHELF_TODO,
                    default=current_config.get(CONF_ENABLE_SHELF_TODO, False),
                ): bool,
                vol.Optional(
                    CONF_GAMES,
                    default=current_config.get(CONF_GAMES, ""),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
