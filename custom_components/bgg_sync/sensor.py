"""Sensor platform for BGG Sync integration."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    BGG_URL,
    ATTR_GAME_RANK,
    ATTR_GAME_YEAR,
    ATTR_GAME_WEIGHT,
    ATTR_GAME_PLAYING_TIME,
    CONF_NFC_TAG,
    CONF_MUSIC,
    CONF_CUSTOM_IMAGE,
    CONF_IMPORT_COLLECTION,
)
from .coordinator import BggDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


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
        BggCollectionCountSensor(
            coordinator, "owned_boardgames", "Games Owned", "mdi:checkerboard"
        ),
        BggCollectionCountSensor(
            coordinator, "owned_expansions", "Expansions Owned", "mdi:puzzle"
        ),
        BggCollectionCountSensor(coordinator, "wishlist", "Wishlist", "mdi:gift"),
        BggCollectionCountSensor(
            coordinator, "want_to_play", "Want to Play", "mdi:chess-pawn"
        ),
        BggCollectionCountSensor(coordinator, "want_to_buy", "Want to Buy", "mdi:cart"),
        BggCollectionCountSensor(
            coordinator, "for_trade", "For Trade", "mdi:swap-horizontal"
        ),
        BggCollectionCountSensor(
            coordinator, "preordered", "Preordered", "mdi:clock-outline"
        ),
        BggLastSyncSensor(coordinator),
        BggShelfLastSyncSensor(coordinator),
        BggSyncOkSensor(coordinator),
    ]

    added_game_ids: set[int] = set()

    # Create sensors for explicitly tracked games
    # We use coordinator.game_ids which contains the merged list from config data and options
    for g_id in coordinator.game_ids:
        # Get metadata for this game if available (e.g. custom image, nfc)
        metadata = coordinator.game_data.get(g_id, {})
        entities.append(BggGameSensor(coordinator, g_id, metadata))
        added_game_ids.add(g_id)

    # Add entire collection if enabled
    if entry.options.get(CONF_IMPORT_COLLECTION, False):
        collection = coordinator.data.get("collection", {})
        for g_id in collection:
            if g_id not in added_game_ids:
                entities.append(BggGameSensor(coordinator, g_id, {}))
                added_game_ids.add(g_id)

        @callback
        def _async_add_collection_entities() -> None:
            """Add sensors for any newly discovered collection games."""
            new_entities = [
                BggGameSensor(coordinator, g_id, {})
                for g_id in coordinator.data.get("collection", {})
                if g_id not in added_game_ids
            ]
            for sensor in new_entities:
                added_game_ids.add(sensor.game_id)
            if new_entities:
                async_add_entities(new_entities)

        entry.async_on_unload(
            coordinator.async_add_listener(_async_add_collection_entities)
        )

    async_add_entities(entities)


class BggBaseSensor(CoordinatorEntity[BggDataUpdateCoordinator], SensorEntity):
    """Base sensor for BGG."""

    _attr_has_entity_name = True
    _attr_attribution = "Data provided by BoardGameGeek"

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.username)},
            name=coordinator.username,
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
        return self.coordinator.data.get("total_plays", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last_play = self.coordinator.data.get("last_play") or {}
        # Try to find image for the game if we have it in cache
        game_id = last_play.get("game_id")
        image = None
        if game_id:
            try:
                g_id = int(game_id)
                details = self.coordinator.data.get("game_details", {}).get(g_id, {})
                image = details.get("image")
            except (ValueError, TypeError):
                pass

        return {
            "game": last_play.get("game"),
            "bgg_id": last_play.get("game_id"),
            "date": last_play.get("date"),
            "comment": last_play.get("comment"),
            "expansions": last_play.get("expansions"),
            "winners": last_play.get("winners"),
            "players": last_play.get("players"),
            "image": image,
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
        # Use the explicit 'owned' count if available, else standard total
        return self.coordinator.data.get("counts", {}).get(
            "owned", self.coordinator.data.get("total_collection")
        )


class BggCollectionCountSensor(BggBaseSensor):
    """Sensor for other BGG collection counts (Wishlist, Want to Play, etc)."""

    def __init__(
        self, coordinator: BggDataUpdateCoordinator, key: str, name: str, icon: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.username}_{key}"
        self._attr_name = name
        self._attr_icon = icon

    @property
    def native_value(self) -> int:
        return self.coordinator.data.get("counts", {}).get(self.key, 0)


class BggLastSyncSensor(BggBaseSensor):
    """Diagnostic sensor for last successful BGG sync."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.username}_last_sync"
        self._attr_name = "Last Sync"

    @property
    def native_value(self):
        return self.coordinator.data.get("last_sync")


class BggShelfLastSyncSensor(BggLastSyncSensor):
    """Diagnostic sensor for last successful BGG sync (Shelf Device)."""

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.username}_shelf_last_sync"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.username}_shelf")},
            name=f"{coordinator.username}'s Shelf",
            manufacturer="BoardGameGeek",
            model="Board Game Collection",
            configuration_url=f"{BGG_URL}/collection/user/{coordinator.username}",
            via_device=(DOMAIN, coordinator.username),
        )


class BggSyncOkSensor(BggBaseSensor):
    """Diagnostic sensor indicating whether the last BGG sync succeeded."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.username}_sync_ok"
        self._attr_name = "Sync OK"

    @property
    def available(self) -> bool:
        """Always available so sync failures can be monitored."""
        return True

    @property
    def native_value(self) -> bool:
        """Return True if the last sync succeeded without errors."""
        if not self.coordinator.last_update_success or not self.coordinator.data:
            return False
        return bool(self.coordinator.data.get("sync_ok", False))

    @property
    def icon(self) -> str:
        """Return icon based on sync status."""
        if self.native_value:
            return "mdi:check-circle-outline"
        return "mdi:alert-circle-outline"


class BggGameSensor(CoordinatorEntity[BggDataUpdateCoordinator], SensorEntity):
    """Sensor for a specific game with rich metadata."""

    _attr_icon = "mdi:dice-multiple"
    _attr_attribution = "Data provided by BoardGameGeek"

    def __init__(
        self, coordinator: BggDataUpdateCoordinator, game_id: int, user_data: dict
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.game_id = game_id
        self.user_data = user_data
        self._attr_unique_id = f"{coordinator.username}_game_{game_id}"

        name = coordinator.data.get("game_details", {}).get(game_id, {}).get("name")
        if not name and isinstance(getattr(coordinator, "hass", None), HomeAssistant):
            ent_reg = er.async_get(coordinator.hass)
            entity_id = ent_reg.async_get_entity_id(
                "sensor", DOMAIN, self._attr_unique_id
            )
            reg_entry = ent_reg.async_get(entity_id) if entity_id else None
            if (
                reg_entry
                and reg_entry.original_name
                and not reg_entry.original_name.startswith("BGG Game ")
            ):
                name = reg_entry.original_name

        self._attr_name = name or f"BGG Game {game_id}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.username}_shelf")},
            name=f"{coordinator.username}'s Shelf",
            manufacturer="BoardGameGeek",
            model="Board Game Collection",
            configuration_url=f"{BGG_URL}/collection/user/{coordinator.username}",
            via_device=(DOMAIN, coordinator.username),
        )

    def _sync_registry_name(self) -> None:
        """Heal entity registry original_name if stuck on fallback BGG Game ID."""
        details = self.coordinator.data.get("game_details", {}).get(self.game_id, {})
        if not (fetched_name := details.get("name")):
            return
        self._attr_name = fetched_name
        if (
            not isinstance(getattr(self, "hass", None), HomeAssistant)
            or not self.entity_id
        ):
            return
        ent_reg = er.async_get(self.hass)
        reg_entry = ent_reg.async_get(self.entity_id)
        if reg_entry and (
            not reg_entry.original_name
            or reg_entry.original_name.startswith("BGG Game ")
        ):
            ent_reg.async_update_entity(self.entity_id, original_name=fetched_name)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._sync_registry_name()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._sync_registry_name()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and bool(self.coordinator.data.get("sync_ok", True))
            and self.game_id in self.coordinator.data.get("game_details", {})
            and self.game_id in self.coordinator.data.get("game_plays", {})
        )

    @property
    def name(self) -> str:
        # Allow dynamic name updates if it wasn't available at init
        details = self.coordinator.data.get("game_details", {}).get(self.game_id, {})
        if fetched_name := details.get("name"):
            self._attr_name = fetched_name
        return self._attr_name

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("game_plays", {}).get(self.game_id)

    @property
    def icon(self) -> str | None:
        if self.entity_picture:
            return None
        return "mdi:dice-multiple"

    @property
    def entity_picture(self) -> str | None:
        # 1. User override
        if cust := self.user_data.get(CONF_CUSTOM_IMAGE):
            return cust

        # 2. BGG Image
        details = self.coordinator.data.get("game_details", {}).get(self.game_id, {})
        return details.get("image") or details.get("thumbnail")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        details = self.coordinator.data.get("game_details", {}).get(self.game_id, {})

        attrs = {
            "bgg_id": str(self.game_id),
            "bgg_url": f"{BGG_URL}/boardgame/{self.game_id}",
            "image_url": details.get("image"),  # Explicitly expose URL for debugging
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
            "sub_type": details.get("sub_type"),
            "stddev": details.get("stddev"),
            "median": details.get("median"),
        }

        # Only add coll_id if it exists (it won't for non-collection tracked games)
        if cid := details.get("coll_id"):
            attrs["coll_id"] = cid

        # User added data
        if tag := self.user_data.get(CONF_NFC_TAG):
            attrs[CONF_NFC_TAG] = tag
        if music := self.user_data.get(CONF_MUSIC):
            attrs[CONF_MUSIC] = music

        return attrs
