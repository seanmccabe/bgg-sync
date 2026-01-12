"""Coordinator for BGG Sync integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import BggClient

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
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"BGG Data - {username}",
            update_interval=timedelta(minutes=30),
        )
        self.username = username
        self.game_ids = game_ids
        session = async_get_clientsession(hass)
        self.client = BggClient(session, username, password, api_token)

    async def _async_update_data(self):
        """Fetch data from BGG."""
        if (
            self.client.password
            and not self.client.logged_in
            and not self.client.api_token
        ):
            await self.client.login()

        try:
            data = {
                "total_plays": 0,
                "last_play": {},
                "total_collection": 0,
                "game_plays": {},
                "collection": {},
                "game_details": {},
                "counts": {
                    "owned": 0,
                    "owned_boardgames": 0,
                    "owned_expansions": 0,
                    "wishlist": 0,
                    "want_to_play": 0,
                    "want_to_buy": 0,
                    "for_trade": 0,
                    "preordered": 0,
                },
            }

            # 1. Fetch Plays
            plays_resp = await self.client.fetch_plays()
            if plays_resp["status"] == 200:
                data["total_plays"] = plays_resp["total"]
                if plays_resp["last_play"]:
                    data["last_play"] = plays_resp["last_play"]
            elif plays_resp["status"] == 202:
                _LOGGER.info(
                    "BGG is generating play data for %s, will try again next poll",
                    self.username,
                )
            elif plays_resp["status"] == 401:
                _LOGGER.error(
                    "BGG API 401 Unauthorised for %s. Ensure you have a valid API Token configured.",
                    self.username,
                )
            else:
                _LOGGER.warning(
                    "Plays API returned status %s for %s",
                    plays_resp["status"],
                    self.username,
                )

            # 2. Fetch Collection
            all_items = []
            for subtype in ["boardgame", "boardgameexpansion"]:
                coll_resp = await self.client.fetch_collection(subtype)
                if coll_resp["status"] == 200:
                    all_items.extend(coll_resp["items"])
                elif coll_resp["status"] == 202:
                    _LOGGER.info(
                        "BGG is (202) generating collection data for %s (%s)",
                        self.username,
                        subtype,
                    )
                    raise UpdateFailed("BGG is processing collection, retrying later")
                else:
                    _LOGGER.warning(
                        "Collection API returned status %s for %s (%s)",
                        coll_resp["status"],
                        self.username,
                        subtype,
                    )

            for item in all_items:
                g_id = item["objectid"]
                subtype = item["subtype"]

                if item["own"]:
                    data["counts"]["owned"] += 1
                    if subtype == "boardgame":
                        data["counts"]["owned_boardgames"] += 1
                    elif subtype == "boardgameexpansion":
                        data["counts"]["owned_expansions"] += 1

                if item["wishlist"]:
                    data["counts"]["wishlist"] += 1
                if item["wanttoplay"]:
                    data["counts"]["want_to_play"] += 1
                if item["wanttobuy"]:
                    data["counts"]["want_to_buy"] += 1
                if item["fortrade"]:
                    data["counts"]["for_trade"] += 1
                if item["preordered"]:
                    data["counts"]["preordered"] += 1

                game_obj = {
                    "bgg_id": g_id,
                    "name": item["name"],
                    "image": item["image"],
                    "thumbnail": item["thumbnail"],
                    "year": item["yearpublished"],
                    "numplays": str(item["numplays"]),
                    "subtype": subtype,
                    "min_players": item["minplayers"],
                    "max_players": item["maxplayers"],
                    "playing_time": item["playingtime"],
                    "min_playtime": item["minplaytime"],
                    "max_playtime": item["maxplaytime"],
                    "rank": item["rank"],
                    "rating": item["rating"],
                    "bayes_rating": item["bayes_rating"],
                    "weight": item["weight"],
                    "users_rated": item["users_rated"],
                    "stddev": item["stddev"],
                    "median": item["median"],
                    "owned_by": item["numowned"],
                    "coll_id": item["collid"],
                }

                data["game_details"][g_id] = game_obj
                if item["own"]:
                    data["collection"][g_id] = game_obj
                data["game_plays"][g_id] = int(game_obj["numplays"])

            data["total_collection"] = data["counts"]["owned"]

            # 3. Fetch Specific Game Plays
            for game_id in self.game_ids:
                if game_id not in data["game_plays"]:
                    count = await self.client.fetch_game_plays(game_id)
                    data["game_plays"][game_id] = count

            # 4. Fetch Rich Game Details
            all_ids = set(self.game_ids)
            all_ids.update(data["collection"].keys())
            all_ids_list = list(all_ids)

            BATCH_SIZE = 20
            for i in range(0, len(all_ids_list), BATCH_SIZE):
                batch_ids = all_ids_list[i : i + BATCH_SIZE]
                details = await self.client.fetch_thing_details(batch_ids)

                for item in details:
                    g_id = item["id"]
                    existing = data["game_details"].get(g_id, {})
                    existing.update(
                        {
                            "name": item["name"] or existing.get("name"),
                            "image": item["image"] or existing.get("image"),
                            "year": item["yearpublished"],
                            "min_players": item["minplayers"],
                            "max_players": item["maxplayers"],
                            "playing_time": item["playingtime"],
                            "min_playtime": item["minplaytime"],
                            "max_playtime": item["maxplaytime"],
                            "rank": item["rank"],
                            "weight": item["weight"],
                            "rating": item["rating"],
                            "bayes_rating": item["bayes_rating"],
                            "users_rated": item["users_rated"],
                            "stddev": item["stddev"],
                            "median": item["median"],
                            "owned_by": item["owned"],
                            "sub_type": item["type"],
                        }
                    )
                    data["game_details"][g_id] = existing

            data["last_sync"] = dt_util.now()
            return data

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error(
                "Error communicating with BGG API for %s: %s", self.username, err
            )
            raise UpdateFailed(f"Error communicating with BGG API: {err}")
