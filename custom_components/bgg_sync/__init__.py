"""__init__ for BGG Sync integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_BGG_USERNAME, CONF_BGG_PASSWORD, SERVICE_RECORD_PLAY, CONF_GAMES, CONF_API_TOKEN
from .coordinator import BggDataUpdateCoordinator
import requests


_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BGG Sync from a config entry."""
    # Merge data and options
    conf = {**entry.data, **entry.options}
    
    username = conf[CONF_BGG_USERNAME]
    password = conf.get(CONF_BGG_PASSWORD)
    api_token = conf.get(CONF_API_TOKEN)
    game_ids_raw = conf.get(CONF_GAMES, "")
    game_ids = [int(x.strip()) for x in game_ids_raw.split(",") if x.strip().isdigit()]
    
    coordinator = BggDataUpdateCoordinator(hass, username, password, api_token, game_ids)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await async_setup_services(hass)

    return True

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for BGG Sync."""
    if hass.services.has_service(DOMAIN, SERVICE_RECORD_PLAY):
        return

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
            _LOGGER.error("No password configured for %s, cannot log play", username)
            return

        # Perform the actual POST. This should be in an executor job.
        await hass.async_add_executor_job(
            record_play_on_bgg,
            username,
            password,
            game_id,
            call.data.get("date"),
            call.data.get("length"),
            call.data.get("comments"),
            call.data.get("players"),
        )

    hass.services.async_register(DOMAIN, SERVICE_RECORD_PLAY, async_record_play)

def record_play_on_bgg(username, password, game_id, date, length, comments, players):
    """BGG play recording logic using requests."""
    # BGG uses a login process then a post to geekplay.php
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://boardgamegeek.com/login"
    })
    
    login_url = "https://boardgamegeek.com/login/api/v1"
    login_payload = {"credentials": {"username": username, "password": password}}
    
    try:
        # We must use json=login_payload so requests sets Content-Type: application/json
        response = session.post(login_url, json=login_payload, timeout=10)
        
        # API v1 usually returns 200 or 204 on success.
        # If it fails, it might return 400/401.
        if response.status_code not in [200, 204]:
             _LOGGER.error("BGG Login failed for %s. Status: %s, Body: %s", username, response.status_code, response.text)
             return

        play_url = "https://boardgamegeek.com/geekplay.php"
        # BGG Play data format is complex, often involves XML or specific form fields.
        # This is a simplified version; in a real library it would be more robust.
        # Most BGG play loggers use the PHP endpoint.
        if not date:
            from datetime import datetime
            date = datetime.now().strftime("%Y-%m-%d")

        data = {
            "action": "save",
            "objectid": game_id,
            "objecttype": "thing",
            "playdate": date,
            "length": length or "",
            "comments": comments or "",
            "ajax": 1
        }
        # Add players if provided
        # This part is highly dependent on BGG's internal form structure.
        
        # Update Referer for the play post
        session.headers.update({"Referer": f"https://boardgamegeek.com/boardgame/{game_id}"})
        
        resp = session.post(play_url, data=data, timeout=10)
        _LOGGER.debug("Record Play Response Code: %s | Body: %s", resp.status_code, resp.text[:1000])
        
        if resp.status_code == 200 and "error" not in resp.text.lower():
            _LOGGER.info("Successfully recorded play for %s on BGG", username)
        else:
            _LOGGER.error("Failed to record play on BGG: %s", resp.text)
            
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
