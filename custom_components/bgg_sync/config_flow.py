"""Config flow for BGG Sync integration."""
from __future__ import annotations

import logging
from typing import Any

import requests
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_BGG_USERNAME, CONF_BGG_PASSWORD, CONF_API_TOKEN, CONF_GAMES, BASE_URL, CONF_ENABLE_LOGGING

_LOGGER = logging.getLogger(__name__)

def validate_input(data: dict[str, Any]) -> dict[str, str]:
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
    token = data[CONF_API_TOKEN]
    
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
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers, timeout=10)
        # BGG returns 200 even for errors sometimes, but 401/403 for bad auth if enforced.
        if response.status_code == 401:
            errors[CONF_API_TOKEN] = "invalid_auth"
        elif response.status_code != 200:
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
            # Validate!
            errors = await self.hass.async_add_executor_job(
                validate_input, user_input
            )

            if not errors:
                return self.async_create_entry(title=user_input[CONF_BGG_USERNAME], data=user_input)

        return self.async_show_form(
            step_id="user", 
            data_schema=vol.Schema({
                vol.Required(CONF_BGG_USERNAME): str,
                vol.Required(CONF_API_TOKEN): str,
                vol.Optional(CONF_ENABLE_LOGGING, default=False): bool,
                vol.Optional(CONF_BGG_PASSWORD): str,
                vol.Optional(CONF_GAMES): str,
            }), 
            errors=errors
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
            errors = await self.hass.async_add_executor_job(
                validate_input, full_input
            )

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_TOKEN,
                        default=self.config_entry.options.get(
                            CONF_API_TOKEN, self.config_entry.data.get(CONF_API_TOKEN, "")
                        ),
                    ): str,
                    vol.Optional(
                        CONF_ENABLE_LOGGING,
                        default=self.config_entry.options.get(
                            CONF_ENABLE_LOGGING, self.config_entry.data.get(CONF_ENABLE_LOGGING, False)
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_BGG_PASSWORD,
                        default=self.config_entry.options.get(
                            CONF_BGG_PASSWORD, self.config_entry.data.get(CONF_BGG_PASSWORD, "")
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
            errors=errors
        )
