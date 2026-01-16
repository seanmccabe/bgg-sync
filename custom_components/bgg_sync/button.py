"""Button platform for BGG Sync."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, BGG_URL
from .coordinator import BggDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BGG Sync buttons."""
    coordinator: BggDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BggForceSyncButton(coordinator)])


class BggForceSyncButton(CoordinatorEntity[BggDataUpdateCoordinator], ButtonEntity):
    """Button to force a BGG sync."""

    _attr_has_entity_name = True
    _attr_attribution = "Data provided by BoardGameGeek"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BggDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.username}_force_sync"
        self._attr_name = "Force Sync"
        self._attr_icon = "mdi:refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.username)},
            name=coordinator.username,
            manufacturer="BoardGameGeek",
            configuration_url=f"{BGG_URL}/user/{coordinator.username}",
        )

    async def async_press(self) -> None:
        """Press the button."""
        await self.coordinator.async_request_refresh()
