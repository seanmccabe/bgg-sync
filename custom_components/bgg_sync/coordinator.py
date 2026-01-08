import logging
import xml.etree.ElementTree as ET
from datetime import timedelta

import requests
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BASE_URL, BGG_URL

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
        if not self.password:
            return

        login_url = f"{BGG_URL}/login"
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
                _LOGGER.error("BGG API 401 Unauthorised for %s. Ensure you have a valid API Token configured.", self.username)
            else:
                _LOGGER.warning("Plays API returned status %s for %s", resp.status_code, self.username)

            # 2. Fetch Collection (Games AND Expansions)
            # BGG API defaults to only returning boardgames if no subtype is specified.
            # We must fetch boardgames and expansions explicitly to get both.
            
            all_items = []
            
            for subtype in ["boardgame", "boardgameexpansion"]:
                coll_url = f"{BASE_URL}/collection?username={self.username}&subtype={subtype}&stats=1"
                resp = await self.hass.async_add_executor_job(
                    lambda: self.session.get(coll_url, headers=self.headers, timeout=60)
                )
                
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    if root.tag != "message":
                        items = root.findall("item")
                        all_items.extend(items)
                    else:
                         _LOGGER.info("BGG is (202) processing collection for %s (%s), will try again next poll", self.username, subtype)
                elif resp.status_code == 202:
                     _LOGGER.info("BGG is (202) generating collection data for %s (%s)", self.username, subtype)
                else:
                    _LOGGER.warning("Collection API returned status %s for %s (%s)", resp.status_code, self.username, subtype)

            data["collection"] = {}
            data["game_details"] = {}
            # Initialize counts
            data["counts"] = {
                "owned": 0,
                "owned_boardgames": 0,
                "owned_expansions": 0,
                "wishlist": 0,
                "want_to_play": 0,
                "want_to_buy": 0,
                "for_trade": 0,
                "preordered": 0,
            }

            # Process Merged Items
            if all_items:
                # Deduplication might be needed if an item appears in both lists (unlikely but possible with weird BGG data)
                # But our dict storage handles overwrite by ID naturally.
                for item in all_items:
                    try:
                        # Parse Status
                        subtype = item.get("subtype")
                        status = item.find("status")
                        is_owned = status.get("own") == "1"
                        is_wishlist = status.get("wishlist") == "1"
                        is_want_to_play = status.get("wanttoplay") == "1"
                        is_want_to_buy = status.get("wanttobuy") == "1"
                        is_for_trade = status.get("fortrade") == "1"
                        is_preordered = status.get("preordered") == "1"

                        # Increment Counts
                        if is_owned: 
                            data["counts"]["owned"] += 1
                            if subtype == "boardgame":
                                data["counts"]["owned_boardgames"] += 1
                            elif subtype == "boardgameexpansion":
                                data["counts"]["owned_expansions"] += 1
                            
                        if is_wishlist: data["counts"]["wishlist"] += 1
                        if is_want_to_play: data["counts"]["want_to_play"] += 1
                        if is_want_to_buy: data["counts"]["want_to_buy"] += 1
                        if is_for_trade: data["counts"]["for_trade"] += 1
                        if is_preordered: data["counts"]["preordered"] += 1

                        g_id = int(item.get("objectid"))
                        
                        # Parse Stats
                        stats = item.find("stats")
                        rating = stats.find("rating") if stats is not None else None
                        ranks = rating.find("ranks") if rating is not None else None
                        
                        rank_val = "Not Ranked"
                        if ranks:
                            for rank in ranks.findall("rank"):
                                if rank.get("name") == "boardgame":
                                    rank_val = rank.get("value")
                                    break

                        # Build Game Object
                        game_obj = {
                            "bgg_id": g_id,
                            "name": item.findtext("name"),
                            "image": item.findtext("image"),
                            "thumbnail": item.findtext("thumbnail"),
                            "year": item.findtext("yearpublished"),
                            "numplays": item.findtext("numplays", "0"),
                            "subtype": item.get("subtype"),
                            "min_players": stats.get("minplayers") if stats is not None else None,
                            "max_players": stats.get("maxplayers") if stats is not None else None,
                            "playing_time": stats.get("playingtime") if stats is not None else None,
                            "min_playtime": stats.get("minplaytime") if stats is not None else None,
                            "max_playtime": stats.get("maxplaytime") if stats is not None else None,
                            "rank": rank_val,
                            "rating": rating.find("average").get("value") if rating is not None and rating.find("average") is not None else None,
                            "bayes_rating": rating.find("bayesaverage").get("value") if rating is not None and rating.find("bayesaverage") is not None else None,
                            "weight": rating.find("averageweight").get("value") if rating is not None and rating.find("averageweight") is not None else None,
                            "users_rated": rating.find("usersrated").get("value") if rating is not None and rating.find("usersrated") is not None else None,
                            "stddev": rating.find("stddev").get("value") if rating is not None and rating.find("stddev") is not None else None,
                            "median": rating.find("median").get("value") if rating is not None and rating.find("median") is not None else None,
                            "owned_by": stats.get("numowned") if stats is not None else None,
                            "coll_id": item.get("collid"),
                        }
                        
                        # Store in game_details for generic access (used by sensors)
                        data["game_details"][g_id] = game_obj

                        # ONLY add to 'collection' dict if owned (for Shelf/Sensors)
                        if is_owned:
                            data["collection"][g_id] = game_obj
                        
                        # Always populate game_details so we have data for plays/tracking even if not owned (e.g. wishlist game tracked)
                        if "game_details" not in data:
                            data["game_details"] = {}
                        data["game_details"][g_id] = game_obj
                        
                        # Also populate play count even if not owned (you can record plays for friends' games)
                        data["game_plays"][g_id] = int(game_obj["numplays"])
                        
                    except Exception as e:
                        _LOGGER.warning("Error parsing collection item %s: %s", item.get("objectid"), e)
            
            # Update total_collection to match owned count for backward compatibility
            data["total_collection"] = data["counts"]["owned"]

            # 3. Fetch Specific Game Plays
            for game_id in self.game_ids:
                game_url = f"{BASE_URL}/plays?username={self.username}&id={game_id}&type=thing"
                resp = await self.hass.async_add_executor_job(
                    lambda: self.session.get(game_url, headers=self.headers, timeout=10)
                )
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    data["game_plays"][game_id] = int(root.get("total", 0))

            # 4. Fetch Rich Game Details (One Batch Request)
            if self.game_ids:
                ids_str = ",".join(map(str, self.game_ids))
                thing_url = f"{BASE_URL}/thing?id={ids_str}&stats=1"
                resp = await self.hass.async_add_executor_job(
                    lambda: self.session.get(thing_url, headers=self.headers, timeout=10)
                )
                _LOGGER.debug("Thing API response: %s", resp.status_code)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    # Merge into existing details
                    for item in root.findall("item"):
                        try:
                            g_id = int(item.get("id"))
                            # Safe retrieval of values
                            rank_val = "Not Ranked"
                            ranks = item.find("statistics/ratings/ranks")
                            if ranks:
                                for rank in ranks.findall("rank"):
                                    if rank.get("name") == "boardgame":
                                        rank_val = rank.get("value")
                                        break
                                        
                            
                            existing = data["game_details"].get(g_id, {})
                            # Parse Name (Thing API uses name element with value attribute)
                            name = existing.get("name")
                            for n in item.findall("name"):
                                if n.get("type") == "primary":
                                    name = n.get("value")
                                    break
                                    
                            existing.update({
                                "name": name,
                                "image": item.findtext("image"),
                                "year": item.findtext("yearpublished"),
                                "min_players": item.findtext("minplayers"),
                                "max_players": item.findtext("maxplayers"),
                                "playing_time": item.findtext("playingtime"),
                                "min_playtime": item.findtext("minplaytime"),
                                "max_playtime": item.findtext("maxplaytime"),
                                "rank": rank_val,
                                "weight": item.find("statistics/ratings/averageweight").get("value"),
                                "rating": item.find("statistics/ratings/average").get("value"),
                                "bayes_rating": item.find("statistics/ratings/bayesaverage").get("value"),
                                "users_rated": item.find("statistics/ratings/usersrated").get("value"),
                                "stddev": item.find("statistics/ratings/stddev").get("value"),
                                "median": item.find("statistics/ratings/median").get("value"),
                                "owned_by": item.find("statistics/ratings/owned").get("value"),
                                "sub_type": item.get("type"),
                            })
                            data["game_details"][g_id] = existing
                        except Exception as e:
                            _LOGGER.warning("Error parsing game details for ID %s: %s", item.get("id"), e)

            return data

        except Exception as err:
            _LOGGER.error("Error communicating with BGG API for %s: %s", self.username, err)
            raise UpdateFailed(f"Error communicating with BGG API: {err}")
