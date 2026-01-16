"""Tests for the BGG To-do list platform."""
from unittest.mock import MagicMock
import pytest
from homeassistant.components.todo import TodoItem
from custom_components.bgg_sync.const import DOMAIN, CONF_ENABLE_SHELF_TODO
from custom_components.bgg_sync.todo import (
    async_setup_entry,
    BggCollectionTodoList,
)


@pytest.fixture
def populated_coordinator(hass, mock_coordinator):
    """Mock the BGG Coordinator with specific data for todo tests."""
    mock_coordinator.hass = hass
    mock_coordinator.username = "test_user"
    mock_coordinator.data = {
        "collection": {
            822: {
                "bgg_id": 822,
                "name": "Carcassonne",
                "rank": "100",
                "rating": "7.5",
                "min_players": "2",
                "max_players": "5",
                "year": "2000",
            },
            123: {
                "bgg_id": 123,
                "name": "Another Game",
                "rank": "N/A",
                "rating": "N/A",
                "min_players": "1",
                "max_players": "4",
                "year": "2020",
            },
        }
    }
    return mock_coordinator


async def test_todo_creation(hass, mock_coordinator):
    """Test standard to-do list creation."""
    mock_coordinator.username = "test_user"  # required for unique_id

    entry = MagicMock()
    entry.entry_id = "123"
    entry.options = {CONF_ENABLE_SHELF_TODO: True}

    hass.data[DOMAIN] = {entry.entry_id: mock_coordinator}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    assert async_add_entities.called
    args = async_add_entities.call_args[0][0]

    assert len(args) == 1
    assert isinstance(args[0], BggCollectionTodoList)
    assert args[0].name == "Shelf"
    assert args[0].unique_id == "test_user_shelf"
    assert args[0].attribution == "Data provided by BoardGameGeek"
    assert args[0].device_info["name"] == "test_user"


async def test_todo_creation_disabled(hass, mock_coordinator):
    """Test to-do list creation when disabled."""
    entry = MagicMock()
    entry.entry_id = "123"
    entry.options = {CONF_ENABLE_SHELF_TODO: False}

    hass.data[DOMAIN] = {entry.entry_id: mock_coordinator}

    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)

    assert not async_add_entities.called


async def test_todo_items_content(hass, populated_coordinator):
    """Test to-do list items are populated correctly."""
    todo_list = BggCollectionTodoList(populated_coordinator)

    items = todo_list.todo_items

    assert len(items) == 2

    # Sort order is by name: "Another Game" then "Carcassonne"
    first = items[0]
    assert first.summary == "Another Game"
    assert first.uid == "123"
    assert "Rank: N/A" in first.description
    assert "Rating: N/A" in first.description

    second = items[1]
    assert second.summary == "Carcassonne"
    assert second.uid == "822"
    assert "Rank: 100" in second.description
    assert "Rating: 7.5" in second.description
    assert "Players: 2-5" in second.description


async def test_todo_empty_data(hass, mock_coordinator):
    """Test to-do list handles empty data."""
    mock_coordinator.data = {}
    todo_list = BggCollectionTodoList(mock_coordinator)
    assert todo_list.todo_items == []


async def test_todo_unsupported_operations(hass, mock_coordinator):
    """Test that write operations raise NotImplementedError."""
    todo_list = BggCollectionTodoList(mock_coordinator)

    # Add
    with pytest.raises(NotImplementedError):
        await todo_list.async_create_todo_item(TodoItem(summary="Test"))

    # Update
    with pytest.raises(NotImplementedError):
        await todo_list.async_update_todo_item(TodoItem(summary="Test", uid="1"))

    # Delete
    with pytest.raises(NotImplementedError):
        await todo_list.async_delete_todo_items(["1"])
