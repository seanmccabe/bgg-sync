"""Tests for BGG Sync button."""
from unittest.mock import AsyncMock, MagicMock
import pytest
from custom_components.bgg_sync.button import BggForceSyncButton, async_setup_entry
from custom_components.bgg_sync.const import DOMAIN


@pytest.fixture
def mock_coordinator():
    """Fixture for mocking the coordinator."""
    coordinator = MagicMock()
    coordinator.username = "test_user"
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


async def test_button_setup(hass, mock_coordinator):
    """Test button setup."""
    entry = MagicMock()
    entry.entry_id = "test"
    hass.data = {DOMAIN: {"test": mock_coordinator}}

    async_add = MagicMock()

    await async_setup_entry(hass, entry, async_add)

    assert async_add.called
    args = async_add.call_args[0][0]
    assert len(args) == 1
    assert isinstance(args[0], BggForceSyncButton)
    assert args[0].unique_id == "test_user_force_sync"
    assert args[0].attribution == "Data provided by BoardGameGeek"


async def test_button_press(hass, mock_coordinator):
    """Test button press triggers refresh."""
    button = BggForceSyncButton(mock_coordinator)

    assert button.name == "Force Sync"
    assert button.icon == "mdi:refresh"
    assert button.attribution == "Data provided by BoardGameGeek"
    assert button.device_info["name"] == "test_user"

    await button.async_press()
    mock_coordinator.async_request_refresh.assert_called_once()
