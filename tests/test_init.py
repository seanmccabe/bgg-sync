"""Test BGG Sync setup."""
from unittest.mock import patch, MagicMock
from homeassistant.setup import async_setup_component
from custom_components.bgg_sync.const import DOMAIN

async def test_setup_entry(hass):
    """Test setting up the entry."""
    entry = MagicMock()
    entry.data = {
        "bgg_username": "test_user",
        "bgg_api_token": "test_token",
    }
    entry.options = {}
    entry.entry_id = "test_entry"

    with patch(
        "custom_components.bgg_sync.BggDataUpdateCoordinator.async_config_entry_first_refresh",
        return_value=None,
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        return_value=None,
    ) as mock_forward:
        # Import the component
        from custom_components.bgg_sync import async_setup_entry
        
        assert await async_setup_entry(hass, entry) is True
        assert DOMAIN in hass.data
        assert entry.entry_id in hass.data[DOMAIN]
        assert mock_forward.called
