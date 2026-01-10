"""Todo platform for BGG Sync."""
from __future__ import annotations


from homeassistant.components.todo import TodoListEntity, TodoItem
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, BGG_URL, CONF_ENABLE_SHELF_TODO
from .coordinator import BggDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BGG Sync todo list."""
    # Check if the Shelf Todo feature is enabled (default True for existing/new users if not set)
    if entry.options.get(CONF_ENABLE_SHELF_TODO, True):
        coordinator: BggDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        async_add_entities([BggCollectionTodoList(coordinator)])


class BggCollectionTodoList(
    CoordinatorEntity[BggDataUpdateCoordinator], TodoListEntity
):
    """A Todo List representation of the BGG Collection."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bookshelf"

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the todo list."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.username}_shelf"
        self._attr_name = "Shelf"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.username)},
            name=f"BGG Sync {coordinator.username}",
            manufacturer="BoardGameGeek",
            configuration_url=f"{BGG_URL}/user/{coordinator.username}",
        )

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Get the items in the todo list."""
        if not self.coordinator.data or "collection" not in self.coordinator.data:
            return []

        items = []
        collection = self.coordinator.data["collection"]

        # Sort by name for nicer display
        sorted_games = sorted(collection.values(), key=lambda x: x.get("name", ""))

        for game in sorted_games:
            # We can use the description field for stats
            rank = game.get("rank", "N/A")
            rating = game.get("rating", "N/A")
            try:
                rating_val = float(rating)
                rating_str = f"{rating_val:.1f}"
            except (ValueError, TypeError):
                rating_str = str(rating)

            desc = f"Rank: {rank} | Rating: {rating_str} | Players: {game.get('min_players')}-{game.get('max_players')}"

            # Use 'completed' status to indicate if played previously?
            # Or just leave all open. Let's leave all open so it looks like a shelf.
            status = "needs_action"

            items.append(
                TodoItem(
                    summary=game.get("name", "Unknown Game"),
                    uid=str(game.get("bgg_id")),
                    status=status,
                    description=desc,
                )
            )
        return items

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add an item to the todo list."""
        # Not supported yet - would require adding to BGG collection
        raise NotImplementedError(
            "Adding games to BGG collection via Todo list is not supported yet."
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update an item in the todo list."""
        # Not supported yet
        raise NotImplementedError("Updating BGG games via Todo list is not supported.")

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete items from the todo list."""
        # Not supported yet
        raise NotImplementedError("Deleting BGG games via Todo list is not supported.")
