"""Test BGG Sync setup."""
import logging
from unittest.mock import patch, MagicMock
from custom_components.bgg_sync.const import (
    DOMAIN,
    SERVICE_TRACK_GAME,
    SERVICE_RECORD_PLAY,
    CONF_BGG_USERNAME,
    CONF_GAMES,
    CONF_GAME_DATA,
    CONF_NFC_TAG,
    CONF_MUSIC,
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


async def test_setup_entry_legacy_csv(hass):
    """Test setting up the entry with legacy CSV game list."""
    entry = MagicMock()
    entry.data = {
        "bgg_username": "test_user",
        "bgg_api_token": "test_token",
        CONF_GAMES: "123, 456, 789",
    }
    entry.options = {}
    entry.entry_id = "test_entry"

    with patch(
        "custom_components.bgg_sync.BggDataUpdateCoordinator.async_config_entry_first_refresh",
        return_value=None,
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        return_value=None,
    ):
        await async_setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["test_entry"]
        # Coordinator should have merged list of game IDs
        assert 123 in coordinator.game_ids
        assert 456 in coordinator.game_ids
        assert 789 in coordinator.game_ids


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


async def test_service_track_game_targeting(hass, caplog):
    """Test track_game service targeting specific user."""
    entry1 = MagicMock()
    entry1.data = {CONF_BGG_USERNAME: "user1"}
    entry1.options = {CONF_GAME_DATA: {}}
    entry1.entry_id = "entry1"

    entry2 = MagicMock()
    entry2.data = {CONF_BGG_USERNAME: "user2"}
    entry2.options = {CONF_GAME_DATA: {}}
    entry2.entry_id = "entry2"

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_entries",
        return_value=[entry1, entry2],
    ), patch(
        "custom_components.bgg_sync.BggDataUpdateCoordinator.async_config_entry_first_refresh"
    ), patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"):
        await async_setup_entry(hass, entry1)  # Register services

        # 1. Target correct user
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_update_entry"
        ) as mock_update:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_TRACK_GAME,
                service_data={
                    "bgg_id": 123,
                    "username": "user2",
                    "nfc_tag": "abc",
                    "music": "spotify:track",
                },
                blocking=True,
            )
            assert mock_update.called
            # Verify update was called on entry2
            assert mock_update.call_args[0][0] == entry2
            assert (
                mock_update.call_args[1]["options"][CONF_GAME_DATA]["123"][CONF_NFC_TAG]
                == "abc"
            )
            assert (
                mock_update.call_args[1]["options"][CONF_GAME_DATA]["123"][CONF_MUSIC]
                == "spotify:track"
            )

        # 2. Target non-existent user
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_update_entry"
        ) as mock_update:
            with caplog.at_level(logging.ERROR):
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_TRACK_GAME,
                    service_data={"bgg_id": 123, "username": "nobodys_home"},
                    blocking=True,
                )
            assert "No BGG Sync configuration found" in caplog.text
            assert not mock_update.called


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


async def test_service_record_play_errors(hass, caplog):
    """Test failures in record_play service."""
    entry = MagicMock()
    entry.data = {"bgg_username": "test_user"}  # NO PASSWORD
    entry.options = {}
    entry.entry_id = "test"

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_entries", return_value=[entry]
    ), patch(
        "custom_components.bgg_sync.BggDataUpdateCoordinator.async_config_entry_first_refresh"
    ), patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"):
        await async_setup_entry(hass, entry)

        # 1. No password configured
        with caplog.at_level(logging.ERROR):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_RECORD_PLAY,
                service_data={"username": "test_user", "game_id": 123},
                blocking=True,
            )
        assert "No password configured for test_user" in caplog.text

        # Reset logs
        caplog.clear()

        # 2. Logic failure - Mock requests failure inside the helper function
        entry.data["bgg_password"] = "saved_pass"

        # We Mock requests.Session to propagate an error
        with patch("requests.Session") as mock_session_cls:
            mock_session = mock_session_cls.return_value
            # Make POST raise exception
            mock_session.post.side_effect = Exception("API Error")

            with caplog.at_level(logging.ERROR):
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_RECORD_PLAY,
                    service_data={"username": "test_user", "game_id": 123},
                    blocking=True,
                )

        # Assert the exception handler in record_play_on_bgg caught it
        assert "Error recording play on BGG" in caplog.text

        # 3. Test Unknown User
        caplog.clear()
        with caplog.at_level(logging.ERROR):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_RECORD_PLAY,
                service_data={"username": "unknown_user", "game_id": 123},
                blocking=True,
            )
        assert "No BGG account configured for unknown_user" in caplog.text


def test_record_play_logic():
    """Test the synchronous logic for recording play."""
    # Test record_play_on_bgg logic with mocked requests
    with patch("requests.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        # Mock Login Post
        mock_session.post.return_value.status_code = 200

        from custom_components.bgg_sync import record_play_on_bgg

        # Run with explicit date
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


def test_record_play_logic_default_date():
    """Test that default date is used if not provided."""
    with patch("requests.Session") as mock_session_cls, patch(
        "custom_components.bgg_sync.dt_util.now"
    ) as mock_now:
        mock_session = mock_session_cls.return_value
        mock_session.post.return_value.status_code = 200

        # Mock time
        from datetime import datetime

        fixed_now = datetime(2023, 5, 20, 12, 0, 0)
        mock_now.return_value = fixed_now

        from custom_components.bgg_sync import record_play_on_bgg

        # Run without date
        record_play_on_bgg("u", "p", 123, None, None, None, [])

        play_call = mock_session.post.call_args_list[1]
        data = play_call[1]["data"]
        # Expect fixed date
        assert data["playdate"] == "2023-05-20"


def test_record_play_logic_login_fail(caplog):
    """Test synchronous record logic: Login Failure (401)."""
    with patch("requests.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        mock_session.post.return_value.status_code = 401

        from custom_components.bgg_sync import record_play_on_bgg
        import logging

        with caplog.at_level(logging.ERROR):
            record_play_on_bgg("u", "p", 1, "2022-01-01", 30, "", [])

        assert "BGG Login failed" in caplog.text


def test_record_play_logic_post_fail(caplog):
    """Test synchronous record logic: Post Failure (500)."""
    with patch("requests.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value

        from custom_components.bgg_sync import record_play_on_bgg
        import logging

        # 1. Login = 200, Play = 500
        mock_session.post.side_effect = [
            MagicMock(status_code=200),
            MagicMock(status_code=500, text="Internal Server Error"),
        ]

        with caplog.at_level(logging.ERROR):
            record_play_on_bgg("u", "p", 1, "2022-01-01", 30, "", [])

        assert "Failed to record play on BGG: Internal Server Error" in caplog.text


async def test_reload_entry(hass):
    """Test config entry reload."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    from custom_components.bgg_sync import async_reload_entry

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload", return_value=True
    ) as mock_reload:
        await async_reload_entry(hass, entry)
        assert mock_reload.called
