"""Test BGG Sync config flow."""
from unittest.mock import patch
import pytest
from homeassistant import config_entries, setup
from custom_components.bgg_sync.const import DOMAIN

async def test_config_flow(hass):
    """Test the config flow."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch(
        "custom_components.bgg_sync.config_flow.validate_input",
        return_value={},
    ), patch(
        "custom_components.bgg_sync.async_setup_entry",
        return_value=True,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "bgg_username": "test_user",
                "bgg_api_token": "test_token",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "test_user"
    assert result2["data"] == {
        "bgg_username": "test_user",
        "bgg_api_token": "test_token",
        "enable_logging": False,
    }
