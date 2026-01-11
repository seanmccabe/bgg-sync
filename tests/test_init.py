"""Tests for BGG Sync init."""
import logging
from unittest.mock import MagicMock, patch


from custom_components.bgg_sync import (
    async_setup_entry,
    async_unload_entry,
)
from custom_components.bgg_sync.const import (
    DOMAIN,
    CONF_BGG_USERNAME,
    CONF_BGG_PASSWORD,
    SERVICE_RECORD_PLAY,
    SERVICE_TRACK_GAME,
)


async def test_setup_unload_entry(hass):
    """Test setting up and unloading a config entry."""
    entry = MagicMock()
    entry.data = {CONF_BGG_USERNAME: "test_user", "games": "123, 456"}
    entry.options = {}
    entry.entry_id = "test"

    with patch(
        "custom_components.bgg_sync.BggDataUpdateCoordinator.async_config_entry_first_refresh"
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        return_value=True,
    ) as mock_forward:
        # Setup
        assert await async_setup_entry(hass, entry) is True
        assert mock_forward.called
        assert DOMAIN in hass.data
        assert entry.entry_id in hass.data[DOMAIN]

        # Unload
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            return_value=True,
        ) as mock_unload:
            assert await async_unload_entry(hass, entry) is True
            assert mock_unload.called
            assert entry.entry_id not in hass.data[DOMAIN]


async def test_service_record_play(hass):
    """Test the record_play service."""
    entry = MagicMock()
    entry.data = {CONF_BGG_USERNAME: "test_user", CONF_BGG_PASSWORD: "password"}
    entry.options = {}
    entry.entry_id = "test"

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
            service_data={"username": "test_user", "game_id": 123},
            blocking=True,
        )

        assert mock_record.called
        assert mock_record.call_args[0][0] == "test_user"


async def test_service_record_play_errors(hass, caplog):
    """Test failures in record_play service."""
    entry = MagicMock()
    entry.data = {CONF_BGG_USERNAME: "test_user"}  # NO PASSWORD
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

        caplog.clear()
        # 2. Test Unknown User
        with caplog.at_level(logging.ERROR):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_RECORD_PLAY,
                service_data={"username": "unknown_user", "game_id": 123},
                blocking=True,
            )
        assert "No BGG account configured for unknown_user" in caplog.text


def test_record_play_logic_requests():
    """Test the record_play_on_bgg logic using requests."""
    from custom_components.bgg_sync import record_play_on_bgg

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"success":1}'
    mock_session.post.return_value = mock_resp

    with patch("requests.Session", return_value=mock_session):
        players = [{"name": "Sean", "winner": True}]
        record_play_on_bgg("u", "p", 123, "2022-01-01", 30, "Fun", players)

        assert mock_session.post.call_count == 2
        calls = mock_session.post.call_args_list
        assert "/login/api/v1" in calls[0][0][0]
        assert "/geekplay.php" in calls[1][0][0]
        data = calls[1][1]["data"]
        assert data["playername[0]"] == "Sean"
        assert data["playerwin[0]"] == "1"


def test_record_play_logic_fail_requests(caplog):
    """Test failure in recording play."""
    from custom_components.bgg_sync import record_play_on_bgg

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_session.post.return_value = mock_resp

    with patch("requests.Session", return_value=mock_session):
        with caplog.at_level(logging.ERROR):
            record_play_on_bgg("u", "p", 123, None, None, None, None)
        assert "BGG Login failed for u" in caplog.text

        # Test play recording fail
        caplog.clear()
        mock_resp.status_code = 200
        mock_resp.text = '{"error":"Failed"}'
        with caplog.at_level(logging.ERROR):
            record_play_on_bgg("u", "p", 123, None, None, None, None)
        assert "Failed to record play on BGG" in caplog.text


def test_record_play_logic_exception(caplog):
    """Test exception during record play."""
    from custom_components.bgg_sync import record_play_on_bgg

    with patch("requests.Session") as mock_session_class:
        mock_session_class.side_effect = Exception("Connection Error")
        with caplog.at_level(logging.ERROR):
            record_play_on_bgg("u", "p", 123, None, None, None, None)
        assert "Error recording play on BGG: Connection Error" in caplog.text


async def test_service_track_game(hass):
    """Test the track_game service."""
    entry = MagicMock()
    entry.data = {CONF_BGG_USERNAME: "test_user"}
    entry.options = {}
    entry.entry_id = "test"

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_entries", return_value=[entry]
    ), patch(
        "custom_components.bgg_sync.BggDataUpdateCoordinator.async_config_entry_first_refresh"
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_update_entry"
    ) as mock_update:
        await async_setup_entry(hass, entry)

        # 1. Basic tracking
        await hass.services.async_call(
            DOMAIN,
            SERVICE_TRACK_GAME,
            service_data={"bgg_id": 123, "nfc_tag": "tag123"},
            blocking=True,
        )
        assert mock_update.called

        # 2. Tracking with music and image and specific username
        mock_update.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            SERVICE_TRACK_GAME,
            service_data={
                "bgg_id": 456,
                "music": "spotify:track",
                "custom_image": "http://img",
                "username": "test_user",
            },
            blocking=True,
        )
        assert mock_update.called
        options_passed = mock_update.call_args[1]["options"]
        assert "456" in options_passed["game_data"]

        # 3. Target username NOT found
        with patch("custom_components.bgg_sync._LOGGER.error") as mock_log:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_TRACK_GAME,
                service_data={"bgg_id": 123, "username": "wrong_user"},
                blocking=True,
            )
            assert mock_log.called


async def test_async_reload_entry(hass):
    """Test reloading entry."""
    from custom_components.bgg_sync import async_reload_entry

    entry = MagicMock()
    entry.entry_id = "test"
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload"
    ) as mock_reload:
        await async_reload_entry(hass, entry)
        assert mock_reload.called
