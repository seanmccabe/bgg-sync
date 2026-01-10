"""Test BGG Sync setup."""
from unittest.mock import patch, MagicMock
from custom_components.bgg_sync.const import (
    DOMAIN,
    SERVICE_TRACK_GAME,
    SERVICE_RECORD_PLAY,
    CONF_BGG_USERNAME,
)
from custom_components.bgg_sync import async_setup_entry, async_unload_entry


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


async def test_unload_entry(hass):
    """Test unloading the entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"

    # Setup mock data
    hass.data[DOMAIN] = {"test_entry": "mock_coordinator"}

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        return_value=True,
    ):
        assert await async_unload_entry(hass, entry) is True
        assert "test_entry" not in hass.data[DOMAIN]


async def test_service_track_game(hass):
    """Test the track_game service."""
    # Setup - need a config entry in HASS
    entry = MagicMock()
    entry.data = {CONF_BGG_USERNAME: "test_user"}
    entry.options = {}
    entry.entry_id = "test_entry"

    # Mock hass.config_entries.async_entries
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_entries", return_value=[entry]
    ), patch(
        "custom_components.bgg_sync.BggDataUpdateCoordinator.async_config_entry_first_refresh",
        return_value=None,
    ), patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"):
        # Initialize Integration
        await async_setup_entry(hass, entry)

        # Verify Service Registered
        assert hass.services.has_service(DOMAIN, SERVICE_TRACK_GAME)

        # Test Service Call behavior (mocking the actual update call)
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_update_entry"
        ) as mock_update:
            # We need to manually invoke the service handler or simulate a call
            # hass.services.async_call is the integration way.

            await hass.services.async_call(
                DOMAIN,
                SERVICE_TRACK_GAME,
                service_data={"bgg_id": 123, "custom_image": "http://img.com"},
                blocking=True,
            )

            assert mock_update.called
            args = mock_update.call_args
            # Check options were updated
            assert (
                args.kwargs["options"]["game_data"]["123"]["custom_image"]
                == "http://img.com"
            )


async def test_service_record_play(hass):
    """Test the record_play service."""
    entry = MagicMock()
    entry.data = {"bgg_username": "test_user", "bgg_password": "password"}
    entry.options = {}

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_entries", return_value=[entry]
    ), patch(
        "custom_components.bgg_sync.BggDataUpdateCoordinator.async_config_entry_first_refresh"
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"
    ), patch("custom_components.bgg_sync.record_play_on_bgg") as mock_record:
        await async_setup_entry(hass, entry)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_RECORD_PLAY,
            service_data={"username": "test_user", "game_id": 123, "players": []},
            blocking=True,
        )

        assert mock_record.called
        assert mock_record.call_args[0][0] == "test_user"


def test_record_play_logic():
    """Test the synchronous logic for recording play."""
    # Test record_play_on_bgg logic with mocked requests
    with patch("requests.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        # Mock Login Post
        mock_session.post.return_value.status_code = 200

        from custom_components.bgg_sync import record_play_on_bgg

        # Run
        record_play_on_bgg("u", "p", 123, "2022-01-01", 30, "Fun", [])

        # Verify calls
        assert mock_session.post.call_count == 2  # Login + Play

        # Verify Login
        login_call = mock_session.post.call_args_list[0]
        assert "login/api/v1" in login_call[0][0]

        # Verify Play
        play_call = mock_session.post.call_args_list[1]
        assert "geekplay.php" in play_call[0][0]
        data = play_call[1]["data"]
        assert data["objectid"] == 123
        assert data["playdate"] == "2022-01-01"
