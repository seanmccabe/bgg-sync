"""BGG API Client."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp

from .const import BGG_URL, BASE_URL

_LOGGER = logging.getLogger(__name__)


class BggClient:
    """Client for BoardGameGeek API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str | None = None,
        api_token: str | None = None,
    ) -> None:
        """Initialize the client."""
        self.username = username
        self.password = password
        self.api_token = api_token
        self._session = session
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
            lines = text.split("\n")
            in_expansions = False
            for line in lines:
                if "Played with expansions" in line:
                    in_expansions = True
                    continue
                if in_expansions:
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
                val = player.get("username") or player.get("name")
                if val:
                    player_list.append(val)
        return player_list

    async def login(self) -> bool:
        """Login to BGG if password is provided."""
        if not self.password:
            return False

        login_url = f"{BGG_URL}/login"
        login_data = {"username": self.username, "password": self.password}

        try:
            async with self._session.post(
                login_url, data=login_data, timeout=10
            ) as resp:
                _LOGGER.debug(
                    "Login attempt for %s: %s | Body: %s",
                    self.username,
                    resp.status,
                    (await resp.text())[:200],
                )
                self.logged_in = True
                return True
        except Exception as err:
            _LOGGER.error("Login failed for %s: %s", self.username, err)
            return False

    async def fetch_plays(self) -> dict[str, Any]:
        """Fetch plays for the user."""
        url = f"{BASE_URL}/plays?username={self.username}"
        async with self._session.get(url, headers=self.headers, timeout=10) as resp:
            if resp.status != 200:
                return {"status": resp.status, "total": 0, "last_play": None}

            text = await resp.text()
            try:
                root = ET.fromstring(text)
            except Exception as e:
                _LOGGER.error("Failed to parse plays XML: %s", e)
                return {"status": resp.status, "total": 0, "last_play": None}

            total = int(root.get("total", 0))
            last_play = None
            play_nodes = root.findall("play")
            if play_nodes:
                lp_node = play_nodes[0]
                item = lp_node.find("item")
                comment = lp_node.findtext("comments", "")
                last_play = {
                    "game": item.get("name") if item is not None else "Unknown",
                    "game_id": int(item.get("objectid"))
                    if item is not None and item.get("objectid")
                    else None,
                    "date": lp_node.get("date"),
                    "comment": self._clean_bgg_text(comment),
                    "expansions": self._extract_expansions(comment),
                    "winners": self._extract_winners(lp_node),
                    "players": self._extract_players(lp_node),
                }

            return {"status": 200, "total": total, "last_play": last_play}

    async def fetch_game_plays(self, game_id: int) -> int:
        """Fetch play count for a specific game."""
        url = f"{BASE_URL}/plays?username={self.username}&id={game_id}&type=thing"
        async with self._session.get(url, headers=self.headers, timeout=10) as resp:
            if resp.status != 200:
                _LOGGER.warning(
                    "Plays API for game %s returned status %s", game_id, resp.status
                )
                return 0

            text = await resp.text()
            try:
                root = ET.fromstring(text)
                return int(root.get("total", 0))
            except Exception as e:
                _LOGGER.error("Failed to parse game plays XML for %s: %s", game_id, e)
                return 0

    def _get_xml_val(
        self, element: ET.Element | None, tag: str, attr: str | None = "value"
    ) -> str | None:
        """Helper to safely get value from XML element."""
        if element is None:
            return None
        child = element.find(tag)
        if child is None:
            return None
        if attr:
            return child.get(attr)
        return child.text

    async def fetch_collection(self, subtype: str = "boardgame") -> dict[str, Any]:
        """Fetch collection for the user."""
        url = (
            f"{BASE_URL}/collection?username={self.username}&subtype={subtype}&stats=1"
        )
        async with self._session.get(url, headers=self.headers, timeout=60) as resp:
            if resp.status != 200:
                return {"status": resp.status, "items": []}

            text = await resp.text()
            try:
                root = ET.fromstring(text)
            except Exception as e:
                _LOGGER.error("Failed to parse collection XML for %s: %s", subtype, e)
                return {"status": resp.status, "items": []}

            if root.tag == "message":
                return {"status": 202, "items": []}

            items = []
            for item in root.findall("item"):
                try:
                    g_id = int(item.get("objectid"))
                    subtype_val = item.get("subtype")
                    status = item.find("status")
                    stats = item.find("stats")
                    rating = stats.find("rating") if stats is not None else None

                    # Rank
                    rank_val = "Not Ranked"
                    if (
                        rating is not None
                        and (ranks := rating.find("ranks")) is not None
                    ):
                        for rank in ranks.findall("rank"):
                            if rank.get("name") == "boardgame":
                                rank_val = rank.get("value")
                                break

                    items.append(
                        {
                            "objectid": g_id,
                            "subtype": subtype_val,
                            "name": item.findtext("name"),
                            "image": item.findtext("image"),
                            "thumbnail": item.findtext("thumbnail"),
                            "yearpublished": item.findtext("yearpublished"),
                            "numplays": int(item.findtext("numplays", "0")),
                            "own": status.get("own") == "1",
                            "wishlist": status.get("wishlist") == "1",
                            "wanttoplay": status.get("wanttoplay") == "1",
                            "wanttobuy": status.get("wanttobuy") == "1",
                            "fortrade": status.get("fortrade") == "1",
                            "preordered": status.get("preordered") == "1",
                            "minplayers": stats.get("minplayers")
                            if stats is not None
                            else None,
                            "maxplayers": stats.get("maxplayers")
                            if stats is not None
                            else None,
                            "playingtime": stats.get("playingtime")
                            if stats is not None
                            else None,
                            "minplaytime": stats.get("minplaytime")
                            if stats is not None
                            else None,
                            "maxplaytime": stats.get("maxplaytime")
                            if stats is not None
                            else None,
                            "rank": rank_val,
                            "rating": self._get_xml_val(rating, "average"),
                            "bayes_rating": self._get_xml_val(rating, "bayesaverage"),
                            "weight": self._get_xml_val(rating, "averageweight"),
                            "users_rated": self._get_xml_val(rating, "usersrated"),
                            "stddev": self._get_xml_val(rating, "stddev"),
                            "median": self._get_xml_val(rating, "median"),
                            "numowned": stats.get("numowned")
                            if stats is not None
                            else None,
                            "collid": item.get("collid"),
                        }
                    )
                except (TypeError, ValueError) as e:
                    _LOGGER.warning("Error parsing collection item: %s", e)
                    continue

            return {"status": 200, "items": items}

    async def validate_auth(self) -> int:
        """Validate that the API token/auth works. Returns status code."""
        # We use a simple collection fetch to validate auth
        url = f"{BASE_URL}/collection?username={self.username}&brief=1"
        async with self._session.get(url, headers=self.headers, timeout=10) as resp:
            return resp.status

    async def fetch_thing_details(self, game_ids: list[int]) -> list[dict[str, Any]]:
        """Fetch rich game details."""
        if not game_ids:
            return []

        ids_str = ",".join(map(str, game_ids))
        url = f"{BASE_URL}/thing?id={ids_str}&stats=1"
        async with self._session.get(url, headers=self.headers, timeout=30) as resp:
            if resp.status != 200:
                _LOGGER.error("Thing API failed for batch with status %s", resp.status)
                return []
            text = await resp.text()
            try:
                root = ET.fromstring(text)
            except Exception as e:
                _LOGGER.error("Failed to parse BGG XML: %s", e)
                return []

            parsed_items = []
            for item in root.findall("item"):
                try:
                    g_id = int(item.get("id"))

                    # Rank
                    rank_val = "Not Ranked"
                    ranks = item.find("statistics/ratings/ranks")
                    if ranks is not None:
                        for rank in ranks.findall("rank"):
                            if rank.get("name") == "boardgame":
                                rank_val = rank.get("value")
                                break

                    # Name
                    name = None
                    for n in item.findall("name"):
                        if n.get("type") == "primary":
                            name = n.get("value")
                            break

                    ratings = item.find("statistics/ratings")

                    parsed_items.append(
                        {
                            "id": g_id,
                            "name": name,
                            "image": item.findtext("image"),
                            "thumbnail": item.findtext("thumbnail"),
                            "yearpublished": self._get_xml_val(item, "yearpublished"),
                            "minplayers": self._get_xml_val(item, "minplayers"),
                            "maxplayers": self._get_xml_val(item, "maxplayers"),
                            "playingtime": self._get_xml_val(item, "playingtime"),
                            "minplaytime": self._get_xml_val(item, "minplaytime"),
                            "maxplaytime": self._get_xml_val(item, "maxplaytime"),
                            "rank": rank_val,
                            "weight": self._get_xml_val(ratings, "averageweight"),
                            "rating": self._get_xml_val(ratings, "average"),
                            "bayes_rating": self._get_xml_val(ratings, "bayesaverage"),
                            "users_rated": self._get_xml_val(ratings, "usersrated"),
                            "stddev": self._get_xml_val(ratings, "stddev"),
                            "median": self._get_xml_val(ratings, "median"),
                            "owned": self._get_xml_val(ratings, "owned"),
                            "type": item.get("type"),
                        }
                    )
                except (TypeError, ValueError) as e:
                    _LOGGER.warning(
                        "Error parsing thing details for ID %s: %s", item.get("id"), e
                    )
                    continue

            return parsed_items

    async def record_play(
        self,
        game_id: int,
        date: str | None = None,
        length: str | None = None,
        comments: str | None = None,
        players: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Record a play on BGG."""
        # Note: Recording plays via geekplay.php often requires a specific cookie session.
        # This implementation uses the login/api/v1 to get a session.

        login_url = f"{BGG_URL}/login/api/v1"
        login_payload = {
            "credentials": {"username": self.username, "password": self.password}
        }

        try:
            async with self._session.post(
                login_url, json=login_payload, timeout=10
            ) as response:
                if response.status not in [200, 204]:
                    _LOGGER.error(
                        "BGG Login failed for %s. Status: %s, Body: %s",
                        self.username,
                        response.status,
                        await response.text(),
                    )
                    return False

                play_url = f"{BGG_URL}/geekplay.php"
                data = {
                    "action": "save",
                    "objectid": str(game_id),
                    "objecttype": "thing",
                    "playdate": date or "",
                    "length": length or "",
                    "comments": comments or "",
                    "ajax": "1",
                }

                # Update Referer for the play post
                headers = self.headers.copy()
                headers["Referer"] = f"{BGG_URL}/boardgame/{game_id}"

                async with self._session.post(
                    play_url, data=data, timeout=10, headers=headers
                ) as resp:
                    resp_text = await resp.text()
                    _LOGGER.debug(
                        "Record Play Response Code: %s | Body: %s",
                        resp.status,
                        resp_text[:1000],
                    )

                    if resp.status == 200 and "error" not in resp_text.lower():
                        _LOGGER.info(
                            "Successfully recorded play for %s on BGG", self.username
                        )
                        return True

                    _LOGGER.error("Failed to record play on BGG: %s", resp_text)
                    return False

        except Exception as err:
            _LOGGER.error("Error recording play on BGG: %s", err)
            return False
