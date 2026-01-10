"""Test BGG Sync config flow."""
from unittest.mock import patch, MagicMock
from homeassistant import config_entries, data_entry_flow, setup
from custom_components.bgg_sync.const import DOMAIN, CONF_API_TOKEN, CONF_BGG_USERNAME
from custom_components.bgg_sync.config_flow import validate_input

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


async def test_flow_validation_invalid_auth(hass):
    """Test invalid auth error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    # Mock requests inside validate_input
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 401
        
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "bgg_username": "test_user",
                "bgg_api_token": "bad_token",
            },
        )
    
    assert result2["type"] == "form"
    assert result2["errors"] == {CONF_API_TOKEN: "invalid_auth"}


async def test_flow_validation_cannot_connect(hass):
    """Test connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    with patch("requests.get", side_effect=Exception("Connection error")):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "bgg_username": "test_user",
                "bgg_api_token": "token",
            },
        )
        
    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_options_flow(hass):
    """Test options flow."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    
    # 1. Setup Entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test_user",
        data={CONF_BGG_USERNAME: "test_user", CONF_API_TOKEN: "token"},
        unique_id="test_user"
    )
    entry.add_to_hass(hass)
    
    # Initialize Options Flow
    result = await hass.config_entries.options.async_init(entry.entry_id)
    
    assert result["type"] == "form"
    assert result["step_id"] == "init"
    
    # Submit Options
    with patch("custom_components.bgg_sync.config_flow.validate_input", return_value={}):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_API_TOKEN: "new_token"}
        )
        
    assert result2["type"] == "create_entry"
    assert result2["data"][CONF_API_TOKEN] == "new_token"
