import logging
import xml.etree.ElementTree as ET
from datetime import timedelta

import requests
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BASE_URL

_LOGGER = logging.getLogger(__name__)

class BggDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching BGG data."""

    def __init__(self, hass: HomeAssistant, username: str, password: str | None, api_token: str | None, game_ids: list[int]) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"BGG Data - {username}",
            update_interval=timedelta(minutes=30),
        )
        self.username = username
        self.password = password
        self.api_token = api_token
        self.game_ids = game_ids
        self.session = requests.Session()
        self.logged_in = False
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        }
        
        if self.api_token:
            self.headers["Authorization"] = f"Bearer {self.api_token}"

    def _login(self):
        """Login to BGG if password is provided and we don't have an API token."""
        # If we have an API token, we don't likely need website session login for FETCHING data.
        # But we might need it for recording plays if we implement that via website scraping.
        # For now, let's keep login separate.
        if not self.password or self.logged_in:
            return

        login_url = "https://boardgamegeek.com/login"
        login_data = {"username": self.username, "password": self.password}
        
        try:
            resp = self.session.post(login_url, data=login_data, timeout=10)
            _LOGGER.debug("Login attempt for %s: %s | Body: %s", self.username, resp.status_code, resp.text[:200])
            self.logged_in = True
        except Exception as err:
            _LOGGER.error("Login failed for %s: %s", self.username, err)

    async def _async_update_data(self):
        """Fetch data from BGG."""
        # We only need website login if we lack an API token OR if we simply want to try it as backup.
        # The docs say token is REQUIRED. So relying on password alone is deprecated/broken.
        # But we'll leave the logic in case it helps for some users or endpoints.
        if self.password and not self.logged_in and not self.api_token:
            await self.hass.async_add_executor_job(self._login)

        try:
            data = {
                "total_plays": 0,
                "last_play": {},
                "total_collection": 0,
                "game_plays": {},
            }

            # 1. Fetch Plays (Total and Last Play)
            plays_url = f"{BASE_URL}/plays?username={self.username}"
            resp = await self.hass.async_add_executor_job(
                lambda: self.session.get(plays_url, headers=self.headers, timeout=10)
            )
            # Log simplified response status
            _LOGGER.debug("Plays API response for %s: %s", self.username, resp.status_code)
            
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                data["total_plays"] = int(root.get("total", 0))
                
                # Get last play details
                play_nodes = root.findall("play")
                if play_nodes:
                    last_play = play_nodes[0]
                    item = last_play.find("item")
                    data["last_play"] = {
                        "game": item.get("name") if item is not None else "Unknown",
                        "game_id": item.get("objectid") if item is not None else None,
                        "date": last_play.get("date"),
                        "comment": last_play.findtext("comments", ""),
                    }
            elif resp.status_code == 202:
                _LOGGER.info("BGG is generating play data for %s, will try again next poll", self.username)
            elif resp.status_code == 401:
                _LOGGER.error("BGG API 401 Unauthorized for %s. Ensure you have a valid API Token configured.", self.username)
            else:
                _LOGGER.warning("Plays API returned status %s for %s", resp.status_code, self.username)

            # 2. Fetch Collection (Owned Games)
            coll_url = f"{BASE_URL}/collection?username={self.username}&own=1"
            resp = await self.hass.async_add_executor_job(
                lambda: self.session.get(coll_url, headers=self.headers, timeout=10)
            )
            _LOGGER.debug("Collection API response for %s: %s", self.username, resp.status_code)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                if root.tag == "message":
                    _LOGGER.info("BGG is still processing collection for %s, will try again next poll", self.username)
                else:
                    data["total_collection"] = len(root.findall("item"))
            elif resp.status_code == 202:
                _LOGGER.info("BGG is generating collection data for %s, will try again next poll", self.username)
            elif resp.status_code == 401:
                _LOGGER.error("BGG API 401 Unauthorized for %s. Ensure you have a valid API Token configured.", self.username)
            else:
                _LOGGER.warning("Collection API returned status %s for %s", resp.status_code, self.username)

            # 3. Fetch Specific Game Plays
            for game_id in self.game_ids:
                game_url = f"{BASE_URL}/plays?username={self.username}&id={game_id}&type=thing"
                resp = await self.hass.async_add_executor_job(
                    lambda: self.session.get(game_url, headers=self.headers, timeout=10)
                )
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    data["game_plays"][game_id] = int(root.get("total", 0))

            return data

        except Exception as err:
            _LOGGER.error("Error communicating with BGG API for %s: %s", self.username, err)
            raise UpdateFailed(f"Error communicating with BGG API: {err}")
