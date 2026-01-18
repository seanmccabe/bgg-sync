import logging
import re
import xml.etree.ElementTree as ET
from datetime import timedelta

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BASE_URL, BGG_URL, IMAGE_CACHE_DIR, CONF_CUSTOM_IMAGE
import os
from PIL import Image
import io

_LOGGER = logging.getLogger(__name__)


class BggDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching BGG data."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str | None,
        api_token: str | None,
        game_ids: list[int],
        game_data: dict | None = None,
    ) -> None:
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
        # Normalize game_data keys to ints
        self.game_data = {}
        if game_data:
            for k, v in game_data.items():
                try:
                    self.game_data[int(k)] = v
                except ValueError:
                    continue
        self.logged_in = False
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        }

        if self.api_token:
            self.headers["Authorization"] = f"Bearer {self.api_token}"

    def _clean_bgg_text(self, text: str | None) -> str:
        """Clean BGG BBCode from text."""
        if not text:
            return ""
        # Remove tags with properties like [thing=123]Name[/thing] -> Name
        text = re.sub(r"\[\w+=[^\]]*\](.*?)\[\/\w+\]", r"\1", text)
        # Remove simple tags like [b]Bold[/b] -> Bold
        text = re.sub(r"\[/?\w+\]", "", text)
        return text.strip()

    def _extract_expansions(self, text: str | None) -> list[str]:
        """Extract expansion names from BBCode in comments."""
        if not text:
            return []

        expansions = []
        if "Played with expansions" in text:
            # Split by lines to only capture things in the relevant block if desired
            lines = text.split("\n")
            in_expansions = False
            for line in lines:
                if "Played with expansions" in line:
                    in_expansions = True
                    continue
                if in_expansions:
                    # simplistic extraction of content between tags
                    matches = re.findall(r"\[thing=\d+\](.*?)\[/thing\]", line)
                    expansions.extend(matches)

        return expansions

    def _extract_winners(self, play_node: ET.Element) -> list[str]:
        """Extract lists of winners from the play."""
        winners = []
        players = play_node.find("players")
        if players is not None:
            for player in players.findall("player"):
                if player.get("win") == "1":
                    name = player.get("name") or player.get("username")
                    if name:
                        winners.append(name)
        return winners

    def _extract_players(self, play_node: ET.Element) -> list[str]:
        """Extract list of players (username or name)."""
        player_list = []
        players = play_node.find("players")
        if players is not None:
            for player in players.findall("player"):
                # Use username if available, otherwise name
                val = player.get("username")
                if not val:
                    val = player.get("name")

                if val:
                    player_list.append(val)
        return player_list

    async def _login(self):
        """Login to BGG if password is provided."""
        if not self.password:
            return

        login_url = f"{BGG_URL}/login"
        login_data = {"username": self.username, "password": self.password}

        try:
            session = async_get_clientsession(self.hass)
            async with session.post(login_url, data=login_data, timeout=10) as resp:
                _LOGGER.debug(
                    "Login attempt for %s: %s | Body: %s",
                    self.username,
                    resp.status,
                    (await resp.text())[:200],
                )
                self.logged_in = True
        except Exception as err:
            _LOGGER.error("Login failed for %s: %s", self.username, err)

    async def _download_image(self, url: str, game_id: int) -> str | None:
        """Download image and save locally, returning local path."""
        if not url:
            return None

        # Determine file path
        try:
            # Create www/bgg_images dir if not exists
            # Note: We must ensure we are writing to a path that HA can serve
            # In HA, hass.config.path("www") maps to /local/
            www_dir = self.hass.config.path("www")
            cache_dir = os.path.join(www_dir, IMAGE_CACHE_DIR)

            # Ensure directory exists (sync op, but fast/rare)
            if not os.path.exists(cache_dir):
                await self.hass.async_add_executor_job(os.makedirs, cache_dir)

            # Parse extension
            ext = "jpg"
            if ".png" in url.lower():
                ext = "png"
            elif ".webp" in url.lower():
                ext = "webp"

            filename = f"{game_id}.{ext}"
            file_path = os.path.join(cache_dir, filename)
            meta_path = f"{file_path}.url"

            # Check if we have a valid cache
            cached_url = None
            if os.path.exists(meta_path) and os.path.exists(file_path):

                def read_meta():
                    with open(meta_path) as f:
                        return f.read().strip()

                try:
                    cached_url = await self.hass.async_add_executor_job(read_meta)
                except Exception:
                    pass

            # If file exists and URL matches, return local path
            if cached_url == url:
                return f"/local/{IMAGE_CACHE_DIR}/{filename}"

            # Download
            session = async_get_clientsession(self.hass)
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.read()

                    # Write file and metadata in executor
                    def write_file():
                        # Optimize image size
                        try:
                            with Image.open(io.BytesIO(data)) as img:
                                # Convert to RGB if necessary (e.g. PNG with transparency to JPG)
                                # But we want to keep transparency if PNG.
                                # Just resize.
                                img.thumbnail((500, 500))
                                img.save(file_path, optimize=True, quality=85)
                        except Exception as e:
                            _LOGGER.warning(
                                f"Error resizing image {game_id}, saving original: {e}"
                            )
                            with open(file_path, "wb") as f:
                                f.write(data)

                        with open(meta_path, "w") as f:
                            f.write(url)

                    await self.hass.async_add_executor_job(write_file)
                    _LOGGER.debug("Downloaded image for game %s", game_id)
                    return f"/local/{IMAGE_CACHE_DIR}/{filename}"
                else:
                    _LOGGER.warning(
                        "Failed to download image for %s: %s", game_id, resp.status
                    )
                    return None

        except Exception as e:
            _LOGGER.warning(f"Error caching image for {game_id}: {e}")
            return None

    async def _cache_images(self, data: dict):
        """Download images for all games in details."""
        details = data.get("game_details", {})

        # We limit concurrency to avoid blocking too much
        # But for now, let's just do it sequentially or simple gather if list isn't huge?
        # A simple sequential check is safer for start

        for g_id, info in details.items():
            # Determine source URL: Custom overrides BGG
            # game_data keys are normalized to int in init
            custom_img = self.game_data.get(g_id, {}).get(CONF_CUSTOM_IMAGE)

            img_url = custom_img or info.get("image")

            if img_url and not img_url.startswith("/local/"):
                # Check if we already have it in a previous run?
                # We re-check file existence in _download_image so it's idempotent
                local_path = await self._download_image(img_url, g_id)
                if local_path:
                    # Update the data dict to point to local
                    data["game_details"][g_id]["original_image"] = img_url
                    data["game_details"][g_id]["image"] = local_path
                    # Also update thumbnail fallback?
                    data["game_details"][g_id]["thumbnail"] = local_path

        return
        return

    async def _async_update_data(self):
        """Fetch data from BGG."""
        if self.password and not self.logged_in and not self.api_token:
            await self._login()

        session = async_get_clientsession(self.hass)

        try:
            data = {
                "total_plays": 0,
                "last_play": {},
                "total_collection": 0,
                "game_plays": {},
            }

            # 1. Fetch Plays (Total and Last Play)
            plays_url = f"{BASE_URL}/plays?username={self.username}"

            async with session.get(plays_url, headers=self.headers, timeout=10) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    root = await self.hass.async_add_executor_job(ET.fromstring, text)
                    data["total_plays"] = int(root.get("total", 0))

                    # Get last play details
                    play_nodes = root.findall("play")
                    if play_nodes:
                        last_play = play_nodes[0]
                        item = last_play.find("item")
                        logger_comment = last_play.findtext("comments", "")

                        data["last_play"] = {
                            "game": item.get("name") if item is not None else "Unknown",
                            "game_id": item.get("objectid")
                            if item is not None
                            else None,
                            "date": last_play.get("date"),
                            "comment": self._clean_bgg_text(logger_comment),
                            "expansions": self._extract_expansions(logger_comment),
                            "winners": self._extract_winners(last_play),
                            "players": self._extract_players(last_play),
                        }
                elif resp.status == 202:
                    _LOGGER.info(
                        "BGG is generating play data for %s, will try again next poll",
                        self.username,
                    )
                elif resp.status == 401:
                    _LOGGER.error(
                        "BGG API 401 Unauthorised for %s. Ensure you have a valid API Token configured.",
                        self.username,
                    )
                else:
                    _LOGGER.warning(
                        "Plays API returned status %s for %s",
                        resp.status,
                        self.username,
                    )

            # 2. Fetch Collection (Games AND Expansions)
            all_items = []

            for subtype in ["boardgame", "boardgameexpansion"]:
                coll_url = f"{BASE_URL}/collection?username={self.username}&subtype={subtype}&stats=1"

                async with session.get(
                    coll_url, headers=self.headers, timeout=60
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        root = await self.hass.async_add_executor_job(
                            ET.fromstring, text
                        )
                        if root.tag != "message":
                            items = root.findall("item")
                            all_items.extend(items)
                        else:
                            _LOGGER.info(
                                "BGG is (202) processing collection for %s (%s), retrying",
                                self.username,
                                subtype,
                            )
                            raise UpdateFailed(
                                "BGG is processing collection, retrying later"
                            )
                    elif resp.status == 202:
                        _LOGGER.info(
                            "BGG is (202) generating collection for %s (%s), retrying",
                            self.username,
                            subtype,
                        )
                        raise UpdateFailed(
                            "BGG is processing collection, retrying later"
                        )
                    else:
                        _LOGGER.warning(
                            "Collection API returned status %s for %s (%s)",
                            resp.status,
                            self.username,
                            subtype,
                        )

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

            # Process collection items
            if all_items:
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

                        if is_wishlist:
                            data["counts"]["wishlist"] += 1
                        if is_want_to_play:
                            data["counts"]["want_to_play"] += 1
                        if is_want_to_buy:
                            data["counts"]["want_to_buy"] += 1
                        if is_for_trade:
                            data["counts"]["for_trade"] += 1
                        if is_preordered:
                            data["counts"]["preordered"] += 1

                        g_id = int(item.get("objectid"))

                        # Parse Stats
                        stats = item.find("stats")
                        rating = stats.find("rating") if stats is not None else None
                        ranks = rating.find("ranks") if rating is not None else None

                        rank_val = "Not Ranked"
                        if ranks is not None:
                            for rank in ranks.findall("rank"):
                                if rank.get("name") == "boardgame":
                                    rank_val = rank.get("value")
                                    break

                        # Build Game Object
                        game_obj = {
                            "bgg_id": g_id,
                            "name": item.findtext("name"),
                            "image": (item.findtext("image") or "").strip() or None,
                            "thumbnail": (item.findtext("thumbnail") or "").strip()
                            or None,
                            "year": item.findtext("yearpublished"),
                            "numplays": item.findtext("numplays", "0"),
                            "subtype": item.get("subtype"),
                            "min_players": stats.get("minplayers")
                            if stats is not None
                            else None,
                            "max_players": stats.get("maxplayers")
                            if stats is not None
                            else None,
                            "playing_time": stats.get("playingtime")
                            if stats is not None
                            else None,
                            "min_playtime": stats.get("minplaytime")
                            if stats is not None
                            else None,
                            "max_playtime": stats.get("maxplaytime")
                            if stats is not None
                            else None,
                            "rank": rank_val,
                            "rating": rating.find("average").get("value")
                            if rating is not None and rating.find("average") is not None
                            else None,
                            "bayes_rating": rating.find("bayesaverage").get("value")
                            if rating is not None
                            and rating.find("bayesaverage") is not None
                            else None,
                            "weight": rating.find("averageweight").get("value")
                            if rating is not None
                            and rating.find("averageweight") is not None
                            else None,
                            "users_rated": rating.find("usersrated").get("value")
                            if rating is not None
                            and rating.find("usersrated") is not None
                            else None,
                            "stddev": rating.find("stddev").get("value")
                            if rating is not None and rating.find("stddev") is not None
                            else None,
                            "median": rating.find("median").get("value")
                            if rating is not None and rating.find("median") is not None
                            else None,
                            "owned_by": stats.get("numowned")
                            if stats is not None
                            else None,
                            "coll_id": item.get("collid"),
                        }

                        # Store in game_details for generic access (used by sensors)
                        data["game_details"][g_id] = game_obj

                        # ONLY add to 'collection' dict if owned (for Shelf/Sensors)
                        if is_owned:
                            data["collection"][g_id] = game_obj

                        data["game_details"][g_id] = game_obj

                        # Also populate play count even if not owned (you can record plays for friends' games)
                        data["game_plays"][g_id] = int(game_obj["numplays"])

                    except Exception as e:
                        _LOGGER.warning(
                            "Error parsing collection item %s: %s",
                            item.get("objectid"),
                            e,
                        )

            # Update total_collection to match owned count for backward compatibility
            data["total_collection"] = data["counts"]["owned"]

            # 3. Fetch Specific Game Plays
            for game_id in self.game_ids:
                game_url = (
                    f"{BASE_URL}/plays?username={self.username}&id={game_id}&type=thing"
                )
                async with session.get(
                    game_url, headers=self.headers, timeout=10
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        root = await self.hass.async_add_executor_job(
                            ET.fromstring, text
                        )
                        data["game_plays"][game_id] = int(root.get("total", 0))

            # 4. Fetch Rich Game Details for ALL games (Collection + Tracked)
            all_ids = set(self.game_ids)
            if "collection" in data:
                all_ids.update(data["collection"].keys())

            all_ids_list = list(all_ids)
            _LOGGER.info(
                "BGG Sync: Processing rich details for %d games...", len(all_ids_list)
            )

            # Batch requests to avoid URL length limits
            BATCH_SIZE = 20

            for i in range(0, len(all_ids_list), BATCH_SIZE):
                batch_ids = all_ids_list[i : i + BATCH_SIZE]

                ids_str = ",".join(map(str, batch_ids))
                thing_url = f"{BASE_URL}/thing?id={ids_str}&stats=1"
                _LOGGER.debug("Requesting batch %d: %s", i, thing_url)

                async with session.get(
                    thing_url, headers=self.headers, timeout=30
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.warning(
                            "Thing API failed for batch starting at index %s. Status: %s",
                            i,
                            resp.status,
                        )
                        continue

                    # If status is 200, parse content
                    text = await resp.text()
                    try:
                        root = await self.hass.async_add_executor_job(
                            ET.fromstring, text
                        )
                        for item in root.findall("item"):
                            try:
                                g_id = int(item.get("id"))

                                # Re-parse Rank for consistency
                                rank_val = "Not Ranked"
                                ranks = item.find("statistics/ratings/ranks")
                                if ranks is not None:
                                    for rank in ranks.findall("rank"):
                                        if rank.get("name") == "boardgame":
                                            rank_val = rank.get("value")
                                            break

                                existing = data["game_details"].get(g_id, {})
                                # Parse primary name from Thing API
                                name = existing.get("name")
                                for n in item.findall("name"):
                                    if n.get("type") == "primary":
                                        name = n.get("value")
                                        break

                                # Safe Parsing Helper for Ratings
                                ratings = item.find("statistics/ratings")

                                def get_r_val(tag):
                                    if ratings is None:
                                        return None
                                    node = ratings.find(tag)
                                    return (
                                        node.get("value") if node is not None else None
                                    )

                                weight_val = get_r_val("averageweight")
                                rating_val = get_r_val("average")

                                # Store metadata
                                existing.update(
                                    {
                                        "name": name,
                                        "image": (item.findtext("image") or "").strip()
                                        or None,
                                        "year": item.find("yearpublished").get("value")
                                        if item.find("yearpublished") is not None
                                        else None,
                                        "min_players": item.find("minplayers").get(
                                            "value"
                                        )
                                        if item.find("minplayers") is not None
                                        else None,
                                        "max_players": item.find("maxplayers").get(
                                            "value"
                                        )
                                        if item.find("maxplayers") is not None
                                        else None,
                                        "playing_time": item.find("playingtime").get(
                                            "value"
                                        )
                                        if item.find("playingtime") is not None
                                        else None,
                                        "min_playtime": item.find("minplaytime").get(
                                            "value"
                                        )
                                        if item.find("minplaytime") is not None
                                        else None,
                                        "max_playtime": item.find("maxplaytime").get(
                                            "value"
                                        )
                                        if item.find("maxplaytime") is not None
                                        else None,
                                        "rank": rank_val,
                                        "weight": weight_val,
                                        "rating": rating_val,
                                        "bayes_rating": get_r_val("bayesaverage"),
                                        "users_rated": get_r_val("usersrated"),
                                        "stddev": get_r_val("stddev"),
                                        "median": get_r_val("median"),
                                        "owned_by": get_r_val("owned"),
                                        "sub_type": item.get("type"),
                                    }
                                )
                                data["game_details"][g_id] = existing
                            except Exception as e:
                                _LOGGER.warning(
                                    "Error parsing game details for ID %s: %s",
                                    item.get("id"),
                                    e,
                                )
                    except Exception as e:
                        _LOGGER.error("Failed to parse BGG XML response: %s", e)

            # 5. Cache Images Locally
            await self._cache_images(data)

            data["last_sync"] = dt_util.now()
            return data

        except Exception as err:
            _LOGGER.error(
                "Error communicating with BGG API for %s: %s", self.username, err
            )
            raise UpdateFailed(f"Error communicating with BGG API: {err}")
