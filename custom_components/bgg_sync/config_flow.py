"""Config flow for BGG Sync integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_BGG_USERNAME,
    CONF_BGG_PASSWORD,
    CONF_API_TOKEN,
    CONF_GAMES,
    BASE_URL,
    CONF_ENABLE_LOGGING,
    CONF_IMPORT_COLLECTION,
    CONF_ENABLE_SHELF_TODO,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    errors = {}

    # Check if password is provided when logging is enabled
    if data.get(CONF_ENABLE_LOGGING) and not data.get(CONF_BGG_PASSWORD):
        errors[CONF_BGG_PASSWORD] = "password_required_for_logging"

    # Validate API Token by making a simple request
    # Use the username to fetch collection, which is a standard authenticated read
    username = data[CONF_BGG_USERNAME]
    token = data[CONF_API_TOKEN].strip()

    # We use a known endpoint that requires auth or we just test general connectivity
    # /collection requires auth if we want private info, but we can just test if the token is accepted
    # Actually, getting the collection for the username is a good test.
    url = f"{BASE_URL}/collection?username={username}&brief=1"

    # If the token is invalid, BGG might return 200 OK but with an error message in XML,
    # or just work. However, BGG often just works publicly.
    # A better test for the TOKEN specifically is strict.
    # But let's assume if we get a 200, we are "connected".
    # To strictly test the token, let's trust the user or check if 401 is returned.

    try:
        # We must ignore self-signed certs or verify? requests verifies by default.
        # Adding timeout is good practice.
        session = async_get_clientsession(hass)
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(url, headers=headers, timeout=10) as response:
            # BGG returns 200 even for errors sometimes, but 401/403 for bad auth if enforced.
            if response.status == 401:
                errors[CONF_API_TOKEN] = "invalid_auth"
            elif response.status not in (200, 202):
                errors["base"] = "cannot_connect"
            elif response.status == 202:
                _LOGGER.warning(
                    "BGG returned 202 Accepted. Your collection is being processed and may take some time to appear."
                )
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
            # Validate!
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
            # We need the username for validation, which is immutable in data
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
