"""__init__ for BGG Sync integration."""
from __future__ import annotations

import logging
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

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
    BGG_URL,
)
from .coordinator import BggDataUpdateCoordinator


_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.TODO, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BGG Sync from a config entry."""
    conf = {**entry.data, **entry.options}

    username = conf[CONF_BGG_USERNAME]
    enable_logging = conf.get(CONF_ENABLE_LOGGING, False)
    raw_password = conf.get(CONF_BGG_PASSWORD)
    password = raw_password if enable_logging else None

    api_token = conf.get(CONF_API_TOKEN)

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

    if not hass.services.has_service(DOMAIN, SERVICE_RECORD_PLAY):

        async def async_record_play(call):
            """Record a play on BGG."""
            username = call.data["username"]
            game_id = call.data["game_id"]

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

            await async_record_play_on_bgg(
                hass,
                username,
                password,
                game_id,
                call.data.get("date"),
                call.data.get("length"),
                call.data.get("comments"),
                call.data.get("players"),
            )

        hass.services.async_register(DOMAIN, SERVICE_RECORD_PLAY, async_record_play)

    if not hass.services.has_service(DOMAIN, SERVICE_TRACK_GAME):

        async def async_track_game(call):
            """Add a game to be tracked."""
            bgg_id = call.data["bgg_id"]
            nfc = call.data.get("nfc_tag")
            music = call.data.get("music")
            custom_image = call.data.get("custom_image")

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

            new_options = dict(entry.options)
            current_data = new_options.get(CONF_GAME_DATA, {}).copy()

            metadata = current_data.get(str(bgg_id), {})
            if nfc:
                metadata[CONF_NFC_TAG] = nfc
            if music:
                metadata[CONF_MUSIC] = music
            if custom_image:
                metadata[CONF_CUSTOM_IMAGE] = custom_image

            current_data[str(bgg_id)] = metadata
            new_options[CONF_GAME_DATA] = current_data

            hass.config_entries.async_update_entry(entry, options=new_options)

        hass.services.async_register(DOMAIN, SERVICE_TRACK_GAME, async_track_game)


async def async_record_play_on_bgg(
    hass: HomeAssistant, username, password, game_id, date, length, comments, players
):
    """BGG play recording logic using aiohttp with session persistence."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"{BGG_URL}/login",
            }

            login_url = f"{BGG_URL}/login/api/v1"
            login_payload = {
                "credentials": {"username": username, "password": password}
            }

            # 1. Login to get session cookies
            async with session.post(
                login_url, json=login_payload, headers=headers, timeout=10
            ) as response:
                if response.status not in [200, 204]:
                    _LOGGER.error(
                        "BGG Login failed for %s. Status: %s, Body: %s",
                        username,
                        response.status,
                        await response.text(),
                    )
                    return

            # 2. Record Play
            play_url = f"{BGG_URL}/geekplay.php"
            if not date:
                date = dt_util.now().strftime("%Y-%m-%d")

            data = {
                "action": "save",
                "objectid": game_id,
                "objecttype": "thing",
                "playdate": date,
                "length": str(length) if length else "",
                "comments": comments or "",
                "ajax": "1",
            }

            # Add players if provided
            if players and isinstance(players, list):
                for i, p in enumerate(players):
                    data[f"playername[{i}]"] = p.get("name", "")
                    data[f"playerwin[{i}]"] = "1" if p.get("winner") else "0"

            headers["Referer"] = f"{BGG_URL}/boardgame/{game_id}"

            async with session.post(
                play_url, data=data, headers=headers, timeout=10
            ) as resp:
                text = await resp.text()
                _LOGGER.debug(
                    "Record Play Response Code: %s | Body: %s",
                    resp.status,
                    text[:1000],
                )

                if resp.status == 200 and "error" not in text.lower():
                    _LOGGER.info("Successfully recorded play for %s on BGG", username)
                else:
                    _LOGGER.error("Failed to record play on BGG: %s", text)

    except Exception as err:
        _LOGGER.error("Error recording play on BGG: %s", err)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
