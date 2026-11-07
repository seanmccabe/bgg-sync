"""Tests for BGG Sync sensors."""
from unittest.mock import MagicMock
from custom_components.bgg_sync.sensor import (
    BggPlaysSensor,
    BggCollectionSensor,
    BggGameSensor,
    BggCollectionCountSensor,
    BggLastSyncSensor,
    BggShelfLastSyncSensor,
    BggSyncOkSensor,
)
from custom_components.bgg_sync.const import (
    CONF_NFC_TAG,
    CONF_MUSIC,
    CONF_CUSTOM_IMAGE,
    CONF_IMPORT_COLLECTION,
)
import pytest


@pytest.fixture
def mock_coordinator_with_username(mock_coordinator):
    """Mock coordinator with a set username."""
    mock_coordinator.username = "test_user"
    return mock_coordinator


async def test_sensor_setup(hass, mock_coordinator_with_username):
    """Test setting up the sensors."""
    # Mock coordinator data
    mock_coordinator_with_username.data = {
        "total_plays": 100,
        "last_play": {"game": "Catan", "date": "2023-01-01", "game_id": 13},
        "total_collection": 50,
        "counts": {
            "owned": 50,
            "owned_boardgames": 40,
            "owned_expansions": 10,
        },
        # Important: game_details must be present for BggGameSensor
        "game_details": {
            13: {"name": "Catan", "image": "http://image.com", "coll_id": "999"}
        },
        "game_plays": {13: 5},
    }

    # 1. BggPlaysSensor
    plays_sensor = BggPlaysSensor(mock_coordinator_with_username)
    assert plays_sensor.state == 100
    assert plays_sensor.extra_state_attributes["game"] == "Catan"
    assert plays_sensor.extra_state_attributes["bgg_id"] == 13
    assert plays_sensor.icon == "mdi:dice-multiple"
    assert plays_sensor.attribution == "Data provided by BoardGameGeek"
    assert plays_sensor.device_info["name"] == "test_user"

    # 1.5 BggLastSyncSensor
    last_sync_sensor = BggLastSyncSensor(mock_coordinator_with_username)
    assert last_sync_sensor.native_value is None  # Initially None if not set
    assert last_sync_sensor.icon == "mdi:clock-check-outline"
    assert last_sync_sensor.device_class == "timestamp"
    # entity_category is "diagnostic" but that's an entity property, not easily mockable unless we check class attr
    from homeassistant.helpers.entity import EntityCategory

    assert last_sync_sensor.entity_category == EntityCategory.DIAGNOSTIC

    # Simulate sync update
    from datetime import datetime

    now = datetime.now()
    mock_coordinator_with_username.data["last_sync"] = now
    assert last_sync_sensor.native_value == now

    # 1.6 BggShelfLastSyncSensor
    shelf_last_sync = BggShelfLastSyncSensor(mock_coordinator_with_username)
    assert shelf_last_sync.unique_id == "test_user_shelf_last_sync"
    assert shelf_last_sync.device_info["name"] == "test_user's Shelf"
    assert shelf_last_sync.native_value == now

    # 1.7 BggSyncOkSensor
    sync_ok_sensor = BggSyncOkSensor(mock_coordinator_with_username)
    assert sync_ok_sensor.unique_id == "test_user_sync_ok"
    assert sync_ok_sensor.name == "Sync OK"
    assert sync_ok_sensor.available is True
    assert sync_ok_sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sync_ok_sensor.native_value is False
    assert sync_ok_sensor.icon == "mdi:alert-circle-outline"

    mock_coordinator_with_username.last_update_success = True
    mock_coordinator_with_username.data["sync_ok"] = True
    assert sync_ok_sensor.native_value is True
    assert sync_ok_sensor.icon == "mdi:check-circle-outline"

    mock_coordinator_with_username.last_update_success = False
    assert sync_ok_sensor.native_value is False
    mock_coordinator_with_username.last_update_success = True

    # 2. BggCollectionSensor
    coll_sensor = BggCollectionSensor(mock_coordinator_with_username)
    assert coll_sensor.state == 50
    assert coll_sensor.device_info["name"] == "test_user"

    # 3. BggCollectionCountSensor (Counts)
    count_sensor = BggCollectionCountSensor(
        mock_coordinator_with_username,
        "owned_boardgames",
        "Games Owned",
        "mdi:checkerboard",
    )
    assert count_sensor.state == 40
    assert count_sensor.name == "Games Owned"
    assert count_sensor.device_info["name"] == "test_user"

    # 4. BggGameSensor
    # Create one with custom metadata
    game_sensor = BggGameSensor(
        mock_coordinator_with_username,
        13,
        {
            CONF_NFC_TAG: "abc",
            CONF_MUSIC: "uri",
            CONF_CUSTOM_IMAGE: "http://custom.com",
        },
    )
    assert game_sensor.state == 5
    assert game_sensor.available is True
    assert game_sensor.device_info["name"] == "test_user's Shelf"
    assert game_sensor.extra_state_attributes["bgg_id"] == "13"
    assert game_sensor.extra_state_attributes[CONF_NFC_TAG] == "abc"
    assert game_sensor.extra_state_attributes[CONF_MUSIC] == "uri"
    assert game_sensor.extra_state_attributes["coll_id"] == "999"
    assert game_sensor.entity_picture == "http://custom.com"
    # When picture is present, icon should be None
    assert game_sensor.icon is None

    # Test BggGameSensor fallback image
    game_sensor_no_custom = BggGameSensor(mock_coordinator_with_username, 13, {})
    assert game_sensor_no_custom.entity_picture == "http://image.com"

    # Test BggGameSensor no image at all -> use icon
    mock_coordinator_with_username.data["game_details"][13]["image"] = None
    game_sensor_no_img = BggGameSensor(mock_coordinator_with_username, 13, {})
    assert game_sensor_no_img.entity_picture is None
    assert game_sensor_no_img.icon == "mdi:dice-multiple"


async def test_sensor_game_not_in_collection_exclusion(hass, mock_coordinator):
    """Test proper handling of game not in collection (coll_id exclusion)."""
    mock_coordinator.data = {
        "game_details": {99: {"name": "Test Game", "image": "img", "coll_id": None}},
        "game_plays": {99: 0},
    }

    sensor = BggGameSensor(mock_coordinator, 99, {})
    attrs = sensor.extra_state_attributes

    assert "coll_id" not in attrs


async def test_sensor_legacy_csv_format(hass, mock_coordinator):
    """Test we can handle legacy CSV format if passed into setup."""
    from custom_components.bgg_sync.sensor import async_setup_entry
    from custom_components.bgg_sync.const import CONF_GAMES, DOMAIN

    entry = MagicMock()
    game_ids = [123, 456]
    entry.options = {CONF_GAMES: ", ".join(map(str, game_ids))}
    entry.entry_id = "test"

    # Coordinator must now have these IDs mocked (as if init parsed them)
    mock_coordinator.game_ids = game_ids
    mock_coordinator.game_data = {}

    mock_coordinator.data = {
        "game_details": {
            123: {"name": "Game 1", "image": "i"},
            456: {"name": "Game 2", "image": "i"},
        },
        "game_plays": {123: 1, 456: 0},
    }
    hass.data = {DOMAIN: {"test": mock_coordinator}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    added_list = async_add_entities.call_args[0][0]
    game_sensors = [e for e in added_list if isinstance(e, BggGameSensor)]
    assert len(game_sensors) == 2
    ids = [s.game_id for s in game_sensors]
    assert 123 in ids
    assert 456 in ids


async def test_sensor_import_collection_option(hass, mock_coordinator):
    """Test importing entire collection via option."""
    from custom_components.bgg_sync.sensor import async_setup_entry
    from custom_components.bgg_sync.const import CONF_GAME_DATA, DOMAIN

    entry = MagicMock()
    # Enable import option, and have explicit config for game 100
    entry.options = {CONF_IMPORT_COLLECTION: True, CONF_GAME_DATA: {"100": {}}}
    entry.entry_id = "test"

    mock_coordinator.data = {
        # Collection has 100 (explicit) and 200 (implicit)
        "collection": {100: {}, 200: {}},
        "game_details": {100: {"name": "Game 100"}, 200: {"name": "Game 200"}},
        "game_plays": {},
    }
    hass.data = {DOMAIN: {"test": mock_coordinator}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    added_list = async_add_entities.call_args[0][0]
    game_sensors = [e for e in added_list if isinstance(e, BggGameSensor)]

    # 100 is added via explicit loop (first pass)
    # 200 is added via import collection loop (second pass)
    # 100 should NOT be added twice

    ids = [s.game_id for s in game_sensors]
    assert 100 in ids
    assert 200 in ids
    assert len(ids) == 2


async def test_sensor_game_name_fallback(hass, mock_coordinator):
    """Test BggGameSensor uses fallback name if details missing on init."""
    mock_coordinator.data = {
        "game_details": {},  # NO details yet
        "game_plays": {},
    }

    sensor = BggGameSensor(mock_coordinator, 999, {})
    assert sensor.name == "BGG Game 999"

    # Later details update
    mock_coordinator.data["game_details"] = {999: {"name": "Late Game"}}
    assert sensor.name == "Late Game"


async def test_sensor_plays_flattened_attributes(hass, mock_coordinator):
    """Test that Play Sensor has flattened attributes."""
    # Mock data for last play
    last_play_data = {
        "game": "Carcassonne",
        "game_id": "822",
        "date": "2024-01-01",
        "comment": "Nice game",
        "expansions": ["Inns & Cathedrals"],
        "winners": ["Alice"],
        "players": ["Alice", "Bob"],
    }
    # Mock game details for image lookup
    mock_coordinator.data = {
        "total_plays": 10,
        "last_play": last_play_data,
        "counts": {},
        "game_details": {822: {"image": "http://image.url"}},
        "collection": {},
    }

    from custom_components.bgg_sync.sensor import BggPlaysSensor

    sensor = BggPlaysSensor(mock_coordinator)

    attrs = sensor.extra_state_attributes

    # Check flattened attributes
    assert attrs["game"] == "Carcassonne"
    assert attrs["bgg_id"] == "822"
    assert attrs["date"] == "2024-01-01"
    assert attrs["comment"] == "Nice game"
    assert attrs["expansions"] == ["Inns & Cathedrals"]
    assert attrs["winners"] == ["Alice"]
    assert attrs["players"] == ["Alice", "Bob"]
    assert attrs["image"] == "http://image.url"


async def test_sensor_plays_invalid_game_id(hass, mock_coordinator):
    """Test Play Sensor handles invalid game_id gracefully (coverage)."""
    mock_coordinator.data = {
        "total_plays": 5,
        "last_play": {
            "game": "Unknown",
            "game_id": "not_an_int",  # invalid ID
            "date": "2024-01-01",
        },
        "game_details": {},
        "collection": {},
    }
    from custom_components.bgg_sync.sensor import BggPlaysSensor

    sensor = BggPlaysSensor(mock_coordinator)
    attrs = sensor.extra_state_attributes

    assert attrs["bgg_id"] == "not_an_int"
    assert attrs["image"] is None


async def test_sensor_fallback_to_coordinator_games(hass, mock_coordinator):
    """Test sensor creation falls back to coordinator.game_ids if options empty."""
    from custom_components.bgg_sync.sensor import async_setup_entry
    from custom_components.bgg_sync.const import DOMAIN

    entry = MagicMock()
    entry.options = {}  # Empty options, mimicking the bug scenario
    entry.entry_id = "test"

    # Coordinator knows about the game from init merge
    mock_coordinator.game_ids = [777]
    mock_coordinator.game_data = {
        777: {
            "custom_image": "http://custom",
            "nfc_tag": "test_nfc",
            "music": "spotify:track:123",
        }
    }

    # Mock data fetch result
    mock_coordinator.data = {
        "game_details": {777: {"name": "Fetched Name"}},
        "game_plays": {777: 10},
    }

    hass.data = {DOMAIN: {"test": mock_coordinator}}
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    added_list = async_add_entities.call_args[0][0]
    game_sensors = [e for e in added_list if isinstance(e, BggGameSensor)]

    # Assert sensor was created despite empty options
    assert len(game_sensors) == 1
    sensor = game_sensors[0]
    assert sensor.game_id == 777
    # Verify metadata was correctly passed from coordinator.game_data
    assert sensor.user_data["custom_image"] == "http://custom"
    assert sensor.user_data["nfc_tag"] == "test_nfc"
    assert sensor.user_data["music"] == "spotify:track:123"


async def test_sensor_registry_recovery_and_name_healing(
    hass, mock_coordinator_with_username
):
    """Test tracked sensors recover names, show unavailable on sync failure, and heal names."""
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.bgg_sync.sensor import async_setup_entry
    from custom_components.bgg_sync.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"bgg_username": "test_user"},
        options={CONF_IMPORT_COLLECTION: True},
        entry_id="test_entry",
    )
    entry.add_to_hass(hass)

    ent_reg = er.async_get(hass)
    # 1. Pre-existing tracked sensor with known real name in Entity Registry
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "test_user_game_822",
        config_entry=entry,
        original_name="Carcassonne",
    )
    # 2. Pre-existing tracked sensor stuck on "BGG Game 13" in Entity Registry
    reg_catan = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "test_user_game_13",
        config_entry=entry,
        original_name="BGG Game 13",
    )

    mock_coordinator_with_username.hass = hass
    mock_coordinator_with_username.last_update_success = True
    mock_coordinator_with_username.game_ids = [13, 822]
    mock_coordinator_with_username.game_data = {}
    # Simulate startup during 403 outage: sync_ok is False, details & plays are empty
    mock_coordinator_with_username.data = {
        "sync_ok": False,
        "collection": {},
        "game_details": {},
        "game_plays": {},
    }

    listeners = []

    def capture_listener(cb):
        listeners.append(cb)
        return lambda: None

    mock_coordinator_with_username.async_add_listener.side_effect = capture_listener
    hass.data = {DOMAIN: {entry.entry_id: mock_coordinator_with_username}}
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    added_list = async_add_entities.call_args[0][0]
    game_sensors = {e.game_id: e for e in added_list if isinstance(e, BggGameSensor)}

    # Both tracked games exist and are marked unavailable during sync failure
    assert 13 in game_sensors
    assert 822 in game_sensors
    assert game_sensors[13].available is False
    assert game_sensors[822].available is False
    assert game_sensors[13].native_value is None
    # Game 822 recovered its real name from the Entity Registry instead of "BGG Game 822"
    assert game_sensors[822].name == "Carcassonne"
    # Game 13 was stuck on "BGG Game 13" and details are still empty
    assert game_sensors[13].name == "BGG Game 13"

    catan_sensor = game_sensors[13]
    catan_sensor.hass = hass
    catan_sensor.entity_id = reg_catan.entity_id

    # Calling _sync_registry_name while details are empty is a no-op
    catan_sensor._sync_registry_name()
    assert ent_reg.async_get(reg_catan.entity_id).original_name == "BGG Game 13"

    # Coordinator succeeds on next poll: fetches real game details, plays, and collection
    mock_coordinator_with_username.data["sync_ok"] = True
    mock_coordinator_with_username.data["game_details"] = {
        13: {"name": "CATAN"},
        822: {"name": "Carcassonne"},
        400000: {"name": "New Collection Game"},
    }
    mock_coordinator_with_username.data["game_plays"] = {
        13: 5,
        822: 0,
        400000: 2,
    }
    mock_coordinator_with_username.data["collection"] = {
        400000: {"name": "New Collection Game"},
    }

    assert catan_sensor.available is True
    assert catan_sensor.native_value == 5
    assert game_sensors[822].available is True
    assert game_sensors[822].native_value == 0

    # Test _sync_registry_name when entity_id is not set yet (early return branch)
    catan_sensor.entity_id = None
    catan_sensor._sync_registry_name()
    assert catan_sensor.name == "CATAN"

    # Restore entity_id and test async_added_to_hass + _handle_coordinator_update
    catan_sensor.entity_id = reg_catan.entity_id
    catan_sensor.async_write_ha_state = MagicMock()
    await catan_sensor.async_added_to_hass()
    catan_sensor._handle_coordinator_update()

    # Verify Entity Registry original_name was healed from "BGG Game 13" to "CATAN"!
    assert ent_reg.async_get(reg_catan.entity_id).original_name == "CATAN"

    # Trigger dynamic collection listener to add game 400000
    async_add_entities.reset_mock()
    assert len(listeners) == 1
    listeners[0]()
    new_added = async_add_entities.call_args[0][0]
    assert len(new_added) == 1
    assert new_added[0].game_id == 400000
    assert new_added[0].name == "New Collection Game"
