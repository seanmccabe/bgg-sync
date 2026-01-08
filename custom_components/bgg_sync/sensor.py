"""Sensor platform for BGG Sync integration."""
from __future__ import annotations
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, 
    BGG_URL,
    ATTR_LAST_PLAY, 
    ATTR_GAME_RANK,
    ATTR_GAME_YEAR,
    ATTR_GAME_WEIGHT,
    ATTR_GAME_PLAYING_TIME,
    CONF_NFC_TAG,
    CONF_MUSIC,
    CONF_CUSTOM_IMAGE,
    CONF_GAME_DATA,
    CONF_IMPORT_COLLECTION
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
        BggCollectionCountSensor(coordinator, "owned_boardgames", "Games Owned", "mdi:checkerboard"),
        BggCollectionCountSensor(coordinator, "owned_expansions", "Expansions Owned", "mdi:puzzle"),
        BggCollectionCountSensor(coordinator, "wishlist", "Wishlist", "mdi:gift"),
        BggCollectionCountSensor(coordinator, "want_to_play", "Want to Play", "mdi:chess-pawn"),
        BggCollectionCountSensor(coordinator, "want_to_buy", "Want to Buy", "mdi:cart"),
        BggCollectionCountSensor(coordinator, "for_trade", "For Trade", "mdi:swap-horizontal"),
        BggCollectionCountSensor(coordinator, "preordered", "Preordered", "mdi:clock-outline"),
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

    # Create sensors for explicitly tracked games
    for game_id, metadata in game_data.items():
        try:
            g_id = int(game_id)
            entities.append(BggGameSensor(coordinator, g_id, metadata))
        except ValueError:
            pass

    # If enabled, also add sensors for the ENTIRE collection
    # We do this by checking the coordinator data, which holds the full collection.
    # Note: async_setup_entry runs before the first refresh is FINISHED usually,
    # so coordinator.data might be empty. 
    # However, if we want to add entities dynamically, we really should assume
    # the user enabled it and we will add them once data arrives? 
    # Or simpler: we rely on config_entry options. 
    # But we don't know the IDs yet if data is empty!
    # Ideally, we should add them after the first refresh. 
    # But HA encourages adding entities in setup. 
    # Let's check if coordinator has data (it might if first refresh is awaited in logic above setup).
    # Wait, in __init__.py we call `await coordinator.async_config_entry_first_refresh()` BEFORE forwarding.
    # So coordinator.data IS available here!
    
    if entry.options.get(CONF_IMPORT_COLLECTION, False):
        collection = coordinator.data.get("collection", {})
        for g_id in collection:
            # Avoid duplicates if already tracked above
            if str(g_id) not in game_data:
                entities.append(BggGameSensor(coordinator, g_id, {}))

    async_add_entities(entities)

class BggBaseSensor(CoordinatorEntity[BggDataUpdateCoordinator], SensorEntity):
    """Base sensor for BGG."""
    
    _attr_has_entity_name = True

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.username)},
            name=f"BGG Sync {coordinator.username}",
            manufacturer="BoardGameGeek",
            configuration_url=f"{BGG_URL}/user/{coordinator.username}",
        )

class BggPlaysSensor(BggBaseSensor):
    """Sensor for BGG total plays."""

    _attr_icon = "mdi:dice-multiple"

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.username}_plays"
        self._attr_name = "Plays"

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

class BggCollectionSensor(BggBaseSensor):
    """Sensor for BGG collection total."""

    _attr_icon = "mdi:library-shelves"

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.username}_collection"
        self._attr_name = "Collection"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        # Use the explicit 'owned' count if available, else standard total
        return self.coordinator.data.get("counts", {}).get("owned", self.coordinator.data.get("total_collection"))

class BggCollectionCountSensor(BggBaseSensor):
    """Sensor for other BGG collection counts (Wishlist, Want to Play, etc)."""

    def __init__(self, coordinator: BggDataUpdateCoordinator, key: str, name: str, icon: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.username}_{key}"
        self._attr_name = name
        self._attr_icon = icon

    @property
    def native_value(self) -> int:
        """Return the count."""
        return self.coordinator.data.get("counts", {}).get(self.key, 0)

class BggGameSensor(CoordinatorEntity[BggDataUpdateCoordinator], SensorEntity):
    """Sensor for a specific game with rich metadata."""

    _attr_icon = "mdi:dice-multiple"

    def __init__(self, coordinator: BggDataUpdateCoordinator, game_id: int, user_data: dict) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.game_id = game_id
        self.user_data = user_data
        self._attr_unique_id = f"{coordinator.username}_game_{game_id}"
        # Try to find name in coordinator data immediately
        name = coordinator.data.get("game_details", {}).get(game_id, {}).get("name")
        if name:
             self._attr_name = name
        else:
             self._attr_name = f"BGG Game {game_id}"
             
    @property
    def name(self) -> str:
        """Return the name of the entity."""
        # Allow dynamic name updates if it wasn't available at init
        details = self.coordinator.data.get("game_details", {}).get(self.game_id, {})
        return details.get("name") or self._attr_name

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
            "bgg_url": f"{BGG_URL}/boardgame/{self.game_id}",
            ATTR_GAME_RANK: details.get("rank"),
            ATTR_GAME_YEAR: details.get("year"),
            ATTR_GAME_WEIGHT: details.get("weight"),
            ATTR_GAME_PLAYING_TIME: details.get("playing_time"),
            "min_playtime": details.get("min_playtime"),
            "max_playtime": details.get("max_playtime"),
            "rating": details.get("rating"),
            "bayes_rating": details.get("bayes_rating"),
            "weight": details.get("weight"),
            "rank": details.get("rank"),
            "min_players": details.get("min_players"),
            "max_players": details.get("max_players"),
            "users_rated": details.get("users_rated"),
            "owned_by": details.get("owned_by"),
            "sub_type": details.get("subtype"),
            "stddev": details.get("stddev"),
            "median": details.get("median"),
            "coll_id": details.get("coll_id"),
        }

        # User added data
        if tag := self.user_data.get(CONF_NFC_TAG):
            attrs[CONF_NFC_TAG] = tag
        if music := self.user_data.get(CONF_MUSIC):
            attrs[CONF_MUSIC] = music

        return attrs
