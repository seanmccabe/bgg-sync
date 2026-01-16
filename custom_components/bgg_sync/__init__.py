"""__init__ for BGG Sync integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_BGG_USERNAME,
    CONF_BGG_PASSWORD,
    SERVICE_RECORD_PLAY,
    SERVICE_TRACK_GAME,
    CONF_GAMES,
    CONF_API_TOKEN,
    CONF_GAME_DATA,
    CONF_NFC_TAG,
    CONF_MUSIC,
    CONF_CUSTOM_IMAGE,
    CONF_ENABLE_LOGGING,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from bgg_pi import BggClient
from .coordinator import BggDataUpdateCoordinator


_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.TODO, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BGG Sync from a config entry."""
    # Merge data and options
    conf = {**entry.data, **entry.options}

    username = conf[CONF_BGG_USERNAME]
    # If logging is disabled, don't pass the password to coordinator
    enable_logging = conf.get(CONF_ENABLE_LOGGING, False)
    # Check both data and options for password as it might be in either
    raw_password = conf.get(CONF_BGG_PASSWORD)
    password = raw_password if enable_logging else None

    api_token = conf.get(CONF_API_TOKEN)

    # Parse game IDs from configuration
    game_ids_from_csv = []
    game_ids_raw = conf.get(CONF_GAMES, "")
    for x in game_ids_raw.split(","):
        if x.strip().isdigit():
            game_ids_from_csv.append(int(x.strip()))

    game_data = conf.get(CONF_GAME_DATA, {})
    all_game_ids = list(set(game_ids_from_csv + [int(k) for k in game_data.keys()]))

    coordinator = BggDataUpdateCoordinator(
        hass, username, password, api_token, all_game_ids
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await async_setup_services(hass)

    return True


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for BGG Sync."""

    # RECORD PLAY SERVICE
    if not hass.services.has_service(DOMAIN, SERVICE_RECORD_PLAY):

        async def async_record_play(call):
            """Record a play on BGG."""
            username = call.data["username"]
            game_id = call.data["game_id"]
            # Find config entry for this username to get password
            entry = None
            for config_entry in hass.config_entries.async_entries(DOMAIN):
                if config_entry.data.get(CONF_BGG_USERNAME) == username:
                    entry = config_entry
                    break

            if not entry:
                _LOGGER.error("No BGG account configured for %s", username)
                return

            password = entry.data.get(CONF_BGG_PASSWORD)
            if not password:
                _LOGGER.error(
                    "No password configured for %s, cannot log play", username
                )
                return

            session = async_get_clientsession(hass)
            client = BggClient(session, username, password)
            await client.record_play(
                game_id,
                call.data.get("date"),
                call.data.get("length"),
                call.data.get("comments"),
                call.data.get("players"),
            )

        hass.services.async_register(DOMAIN, SERVICE_RECORD_PLAY, async_record_play)

    # TRACK GAME SERVICE
    if not hass.services.has_service(DOMAIN, SERVICE_TRACK_GAME):

        async def async_track_game(call):
            """Add a game to be tracked."""
            bgg_id = call.data["bgg_id"]
            # Handle optional args
            nfc = call.data.get("nfc_tag")
            music = call.data.get("music") or call.data.get("search_spotify")
            custom_image = call.data.get("custom_image")

            _LOGGER.info(
                "Tracking request for ID %s | NFC: %s | Music: %s", bgg_id, nfc, music
            )

            # Find entry (default to first if not specified)
            # Support optional 'username' to target specific instance
            target_username = call.data.get("username")
            entry = None
            entries = hass.config_entries.async_entries(DOMAIN)

            if target_username:
                for e in entries:
                    if e.data.get(CONF_BGG_USERNAME) == target_username:
                        entry = e
                        break
            elif entries:
                entry = entries[0]

            if not entry:
                _LOGGER.error("No BGG Sync configuration found to track game.")
                return

            # Update Options
            new_options = dict(entry.options)
            current_data = new_options.get(CONF_GAME_DATA, {}).copy()

            # Update the game entry
            metadata = current_data.get(str(bgg_id), {})
            # If it was an empty dict from previous legacy import, it might be there

            if nfc:
                metadata[CONF_NFC_TAG] = nfc
            if music:
                metadata[CONF_MUSIC] = music
            if custom_image:
                metadata[CONF_CUSTOM_IMAGE] = custom_image

            current_data[str(bgg_id)] = metadata
            new_options[CONF_GAME_DATA] = current_data

            _LOGGER.info("Updating entry options with new metadata for %s", bgg_id)
            hass.config_entries.async_update_entry(entry, options=new_options)

        hass.services.async_register(DOMAIN, SERVICE_TRACK_GAME, async_track_game)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
