"""Tests for the BGG Sensor platform."""
from unittest.mock import MagicMock
import pytest
from custom_components.bgg_sync.const import (
    DOMAIN,
    CONF_GAME_DATA,
    CONF_IMPORT_COLLECTION,
)
from custom_components.bgg_sync.coordinator import BggDataUpdateCoordinator
from custom_components.bgg_sync.sensor import (
    async_setup_entry,
    BggPlaysSensor,
    BggCollectionSensor,
    BggCollectionCountSensor,
    BggGameSensor,
)


@pytest.fixture
def mock_coordinator(hass):
    """Mock the BGG Coordinator."""
    coordinator = MagicMock(spec=BggDataUpdateCoordinator)
    coordinator.hass = hass
    coordinator.username = "test_user"
    coordinator.data = {
        "total_plays": 150,
        "last_play": {"game": "Carcassonne", "date": "2025-01-01", "comment": "Fun"},
        "counts": {
            "owned": 50,
            "owned_boardgames": 40,
            "owned_expansions": 10,
            "wishlist": 5,
        },
        "game_plays": {
            822: 25,
        },
        "game_details": {
            822: {
                "name": "Carcassonne",
                "image": "http://img.com/carc.jpg",
                "year": "2000",
                "rank": "100",
                "weight": "2.0",
                "rating": "7.5",
                "min_players": "2",
                "max_players": "5",
                "sub_type": "boardgame",
            }
        },
        "collection": {
            822: {}  # Just presence check
        },
        "total_collection": 50,
    }
    return coordinator


async def test_sensor_creation(hass, mock_coordinator):
    """Test standard sensors are created."""
    entry = MagicMock()
    entry.entry_id = "123"
    entry.options = {}

    hass.data[DOMAIN] = {entry.entry_id: mock_coordinator}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    assert async_add_entities.called
    args = async_add_entities.call_args[0][0]

    # We expect 9 standard sensors (Plays, Collection, 7 Counts)
    assert len(args) == 9

    # Verify specific types in list
    assert any(isinstance(e, BggPlaysSensor) for e in args)
    assert any(isinstance(e, BggCollectionSensor) for e in args)
    assert any(
        isinstance(e, BggCollectionCountSensor) and e.key == "owned_boardgames"
        for e in args
    )


async def test_plays_sensor(hass, mock_coordinator):
    """Test BggPlaysSensor state and attributes."""
    sensor = BggPlaysSensor(mock_coordinator)

    assert sensor.native_value == 150
    assert sensor.extra_state_attributes["last_play"]["game"] == "Carcassonne"
    assert sensor.icon == "mdi:dice-multiple"


async def test_collection_sensor(hass, mock_coordinator):
    """Test BggCollectionSensor state."""
    sensor = BggCollectionSensor(mock_coordinator)

    assert sensor.native_value == 50
    assert sensor.icon == "mdi:library-shelves"


async def test_count_sensor(hass, mock_coordinator):
    """Test BggCollectionCountSensor state."""
    sensor = BggCollectionCountSensor(
        mock_coordinator, "owned_boardgames", "Games", "mdi:icon"
    )

    assert sensor.native_value == 40
    assert sensor.name == "Games"
    assert sensor.icon == "mdi:icon"


async def test_game_sensor(hass, mock_coordinator):
    """Test BggGameSensor state and attributes."""
    # User data (explicitly tracked)
    user_data = {"some_option": "value"}

    sensor = BggGameSensor(mock_coordinator, 822, user_data)

    assert sensor.name == "Carcassonne"
    assert sensor.native_value == 25  # play count
    assert sensor.entity_picture == "http://img.com/carc.jpg"
    assert sensor.icon is None  # Because picture is present

    attrs = sensor.extra_state_attributes
    assert attrs["bgg_id"] == "822"
    assert attrs["year"] == "2000"
    assert attrs["min_players"] == "2"
    assert attrs["max_players"] == "5"


async def test_setup_with_options(hass, mock_coordinator):
    """Test setup with updated options (explicit games and import collection)."""
    entry = MagicMock()
    entry.entry_id = "123"
    entry.options = {
        CONF_GAME_DATA: {
            "999": {
                "custom_image": "test.jpg"
            }  # Game not in coordinator dict, checking resilience
        },
        CONF_IMPORT_COLLECTION: True,
    }

    hass.data[DOMAIN] = {entry.entry_id: mock_coordinator}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    args = async_add_entities.call_args[0][0]

    # 9 Standard + 1 Explicit (999) + 1 Importer (822 is in collection mock)
    # Total 11
    assert len(args) == 11

    # Verify the explicit game sensor
    explicit_sensor = next(
        e for e in args if isinstance(e, BggGameSensor) and e.game_id == 999
    )
    assert explicit_sensor.user_data["custom_image"] == "test.jpg"
    assert (
        explicit_sensor.name == "BGG Game 999"
    )  # Default fallback as mock data doesn't have 999
