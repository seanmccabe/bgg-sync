"""Sensor platform for BGG Sync integration."""
from __future__ import annotations
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ATTR_LAST_PLAY
from .coordinator import BggDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BGG Sync sensors."""
    coordinator: BggDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        BggPlaysSensor(coordinator),
        BggCollectionSensor(coordinator),
    ]

    for game_id in coordinator.game_ids:
        entities.append(BggGamePlaysSensor(coordinator, game_id))

    async_add_entities(entities)

class BggPlaysSensor(CoordinatorEntity[BggDataUpdateCoordinator], SensorEntity):
    """Sensor for BGG total plays."""

    _attr_icon = "mdi:dice-multiple"

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.username}_plays"
        # Names starting with "BGG Sync" will result in sensor.bgg_sync_...
        self._attr_name = f"BGG Sync {coordinator.username} Plays"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        return self.coordinator.data.get("total_plays", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            ATTR_LAST_PLAY: self.coordinator.data.get("last_play")
        }

class BggCollectionSensor(CoordinatorEntity[BggDataUpdateCoordinator], SensorEntity):
    """Sensor for BGG collection total."""

    _attr_icon = "mdi:library-shelves"

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.username}_collection"
        self._attr_name = f"BGG Sync {coordinator.username} Collection"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("total_collection")

class BggGamePlaysSensor(CoordinatorEntity[BggDataUpdateCoordinator], SensorEntity):
    """Sensor for BGG plays of a specific game."""

    _attr_icon = "mdi:dice-multiple"

    def __init__(self, coordinator: BggDataUpdateCoordinator, game_id: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.game_id = game_id
        self._attr_unique_id = f"{coordinator.username}_plays_{game_id}"
        self._attr_name = f"BGG Sync {coordinator.username} Plays {game_id}"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("game_plays", {}).get(self.game_id)
