"""Tests for BGG Sync sensors."""
from unittest.mock import MagicMock
from custom_components.bgg_sync.sensor import (
    BggPlaysSensor,
    BggCollectionSensor,
    BggGameSensor,
    BggCollectionCountSensor,
)
from custom_components.bgg_sync.const import (
    CONF_NFC_TAG,
    CONF_MUSIC,
    CONF_CUSTOM_IMAGE,
    ATTR_LAST_PLAY,
    CONF_IMPORT_COLLECTION,
)


async def test_sensor_setup(hass):
    """Test setting up the sensors."""
    # Mock coordinator data
    coordinator = MagicMock()
    coordinator.data = {
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
    plays_sensor = BggPlaysSensor(coordinator)
    assert plays_sensor.state == 100
    assert plays_sensor.extra_state_attributes[ATTR_LAST_PLAY]["game"] == "Catan"
    assert plays_sensor.icon == "mdi:dice-multiple"

    # 2. BggCollectionSensor
    coll_sensor = BggCollectionSensor(coordinator)
    assert coll_sensor.state == 50

    # 3. BggCollectionCountSensor (Counts)
    count_sensor = BggCollectionCountSensor(
        coordinator, "owned_boardgames", "Games Owned", "mdi:checkerboard"
    )
    assert count_sensor.state == 40
    assert count_sensor.name == "Games Owned"

    # 4. BggGameSensor
    # Create one with custom metadata
    game_sensor = BggGameSensor(
        coordinator,
        13,
        {
            CONF_NFC_TAG: "abc",
            CONF_MUSIC: "uri",
            CONF_CUSTOM_IMAGE: "http://custom.com",
        },
    )
    assert game_sensor.state == 5
    assert game_sensor.extra_state_attributes["bgg_id"] == "13"
    assert game_sensor.extra_state_attributes[CONF_NFC_TAG] == "abc"
    assert game_sensor.extra_state_attributes[CONF_MUSIC] == "uri"
    assert game_sensor.extra_state_attributes["coll_id"] == "999"
    assert game_sensor.entity_picture == "http://custom.com"
    # When picture is present, icon should be None
    assert game_sensor.icon is None

    # Test BggGameSensor fallback image
    game_sensor_no_custom = BggGameSensor(coordinator, 13, {})
    assert game_sensor_no_custom.entity_picture == "http://image.com"

    # Test BggGameSensor no image at all -> use icon
    coordinator.data["game_details"][13]["image"] = None
    game_sensor_no_img = BggGameSensor(coordinator, 13, {})
    assert game_sensor_no_img.entity_picture is None
    assert game_sensor_no_img.icon == "mdi:dice-multiple"


async def test_sensor_game_not_in_collection_exclusion(hass):
    """Test proper handling of game not in collection (coll_id exclusion)."""
    coordinator = MagicMock()
    coordinator.data = {
        "game_details": {99: {"name": "Test Game", "image": "img", "coll_id": None}},
        "game_plays": {99: 0},
    }

    sensor = BggGameSensor(coordinator, 99, {})
    attrs = sensor.extra_state_attributes

    assert "coll_id" not in attrs


async def test_sensor_legacy_csv_format(hass):
    """Test we can handle legacy CSV format if passed into setup."""
    from custom_components.bgg_sync.sensor import async_setup_entry
    from custom_components.bgg_sync.const import CONF_GAMES, DOMAIN

    entry = MagicMock()
    entry.options = {CONF_GAMES: "123, 456"}
    entry.entry_id = "test"

    coordinator = MagicMock()
    coordinator.data = {
        "game_details": {
            123: {"name": "Game 1", "image": "i"},
            456: {"name": "Game 2", "image": "i"},
        },
        "game_plays": {123: 1, 456: 0},
    }
    hass.data = {DOMAIN: {"test": coordinator}}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    added_list = async_add_entities.call_args[0][0]
    game_sensors = [e for e in added_list if isinstance(e, BggGameSensor)]
    assert len(game_sensors) == 2
    ids = [s.game_id for s in game_sensors]
    assert 123 in ids
    assert 456 in ids


async def test_sensor_game_creation_error(hass, caplog):
    """Test generic exception during sensor creation logic."""
    from custom_components.bgg_sync.sensor import async_setup_entry
    from custom_components.bgg_sync.const import CONF_GAME_DATA, DOMAIN
    import logging

    entry = MagicMock()
    entry.options = {CONF_GAME_DATA: {"invalid": {}}}
    entry.entry_id = "test"

    coordinator = MagicMock()
    hass.data = {DOMAIN: {"test": coordinator}}
    async_add_entities = MagicMock()

    with caplog.at_level(logging.WARNING):
        await async_setup_entry(hass, entry, async_add_entities)

    assert "Error creating sensor for game ID invalid" in caplog.text


async def test_sensor_import_collection_option(hass):
    """Test importing entire collection via option."""
    from custom_components.bgg_sync.sensor import async_setup_entry
    from custom_components.bgg_sync.const import CONF_GAME_DATA, DOMAIN

    entry = MagicMock()
    # Enable import option, and have explicit config for game 100
    entry.options = {CONF_IMPORT_COLLECTION: True, CONF_GAME_DATA: {"100": {}}}
    entry.entry_id = "test"

    coordinator = MagicMock()
    coordinator.data = {
        # Collection has 100 (explicit) and 200 (implicit)
        "collection": {100: {}, 200: {}},
        "game_details": {100: {"name": "Game 100"}, 200: {"name": "Game 200"}},
        "game_plays": {},
    }
    hass.data = {DOMAIN: {"test": coordinator}}

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


async def test_sensor_game_name_fallback(hass):
    """Test BggGameSensor uses fallback name if details missing on init."""
    coordinator = MagicMock()
    coordinator.data = {
        "game_details": {},  # NO details yet
        "game_plays": {},
    }

    sensor = BggGameSensor(coordinator, 999, {})
    assert sensor.name == "BGG Game 999"

    # Later details update
    coordinator.data["game_details"] = {999: {"name": "Late Game"}}
    assert sensor.name == "Late Game"
