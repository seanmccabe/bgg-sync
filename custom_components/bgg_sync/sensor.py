"""Sensor platform for BGG Sync integration."""
from __future__ import annotations
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, 
    ATTR_LAST_PLAY, 
    ATTR_GAME_RANK,
    ATTR_GAME_YEAR,
    ATTR_GAME_WEIGHT,
    ATTR_GAME_PLAYING_TIME,
    CONF_NFC_TAG,
    CONF_MUSIC,
    CONF_CUSTOM_IMAGE,
    CONF_GAME_DATA
)
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

    # Parse game data from options
    # Support legacy CONF_GAMES list and new CONF_GAME_DATA dict
    game_data = entry.options.get(CONF_GAME_DATA, {})
    
    # Backwards compatibility for CSV list
    legacy_games = entry.options.get("games", "") # literal string "games" from const
    if legacy_games:
        for gid_str in legacy_games.split(","):
            if gid_str.strip().isdigit():
                gid = int(gid_str.strip())
                if gid not in game_data:
                    game_data[gid] = {}

    for game_id, metadata in game_data.items():
        # Ensure ID is int
        try:
            g_id = int(game_id)
            entities.append(BggGameSensor(coordinator, g_id, metadata))
        except ValueError:
            pass

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

class BggGameSensor(CoordinatorEntity[BggDataUpdateCoordinator], SensorEntity):
    """Sensor for a specific game with rich metadata."""

    _attr_icon = "mdi:dice-multiple"

    def __init__(self, coordinator: BggDataUpdateCoordinator, game_id: int, user_data: dict) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.game_id = game_id
        self.user_data = user_data
        self._attr_unique_id = f"{coordinator.username}_game_{game_id}"
        # Name it "BGG Game: Name" if possible, or fall back to ID
        # We can't know the name at init time easily without cache, 
        # so we'll start with ID and let update populate it? 
        # Actually HA prefers static names if possible, but dynamic is okay.
        self._attr_name = f"BGG Game {game_id}"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (play count)."""
        return self.coordinator.data.get("game_plays", {}).get(self.game_id, 0)

    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture."""
        # 1. User override
        if cust := self.user_data.get(CONF_CUSTOM_IMAGE):
            # Check if it's a local file path starting with /local/
            # or a full URL.
            return cust
        
        # 2. BGG Image
        return self.coordinator.data.get("game_details", {}).get(self.game_id, {}).get("image")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the rich attributes."""
        details = self.coordinator.data.get("game_details", {}).get(self.game_id, {})
        
        attrs = {
            "bgg_id": self.game_id,
            ATTR_GAME_RANK: details.get("rank"),
            ATTR_GAME_YEAR: details.get("year"),
            ATTR_GAME_WEIGHT: details.get("weight"),
            ATTR_GAME_PLAYING_TIME: details.get("playing_time"),
            "rating": details.get("rating"),
            "min_players": details.get("min_players"),
            "max_players": details.get("max_players"),
        }

        # User added data
        if tag := self.user_data.get(CONF_NFC_TAG):
            attrs[CONF_NFC_TAG] = tag
        if music := self.user_data.get(CONF_MUSIC):
            attrs[CONF_MUSIC] = music

        return attrs
