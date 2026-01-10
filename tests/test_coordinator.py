"""Tests for BGG Data Update Coordinator."""
import os
from custom_components.bgg_sync.coordinator import BggDataUpdateCoordinator


def load_sample(filename):
    """Load sample XML from the samples directory."""
    path = os.path.join(os.path.dirname(__file__), "samples", filename)
    with open(path, "rb") as f:
        return f.read()


async def test_coordinator_data_update(hass, requests_mock):
    """Test the coordinator successfully fetches and parses data using real samples."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", "test_pass", "test_token", [822]
    )

    # Load real XML samples
    xml_plays = load_sample("plays.xml")
    xml_collection = load_sample("collection.xml")
    xml_thing = load_sample("thing_822.xml")

    # Matchers
    # 1. Plays
    requests_mock.get("https://boardgamegeek.com/xmlapi2/plays", content=xml_plays)

    # 2. Collection
    # Note: The coordinator logic calls collection twice (once for boardgame, once for boardgameexpansion)
    # We will return the same collection XML for 'boardgame' subtype
    # and an empty XML for 'boardgameexpansion'
    # requests_mock evaluates matchers in order, but checking query params is safer

    requests_mock.get(
        "https://boardgamegeek.com/xmlapi2/collection",
        content=xml_collection,  # Default match
    )

    # 3. Thing
    requests_mock.get("https://boardgamegeek.com/xmlapi2/thing", content=xml_thing)

    coordinator.data = await coordinator._async_update_data()

    # --- ASSERTIONS BASED ON REAL DATA (Carcassonne id 822) ---

    # Verify Counts
    assert coordinator.data["counts"]["owned_boardgames"] > 0
    assert coordinator.data["total_plays"] > 0

    # Verify Last Play
    assert "game" in coordinator.data["last_play"]
    assert "date" in coordinator.data["last_play"]

    # Verify Game Details for Carcassonne (822)
    game = coordinator.data["game_details"][822]
    assert game["name"] == "Carcassonne"

    # Assert values that correspond to real BGG data
    assert game["year"] == "2000"
    assert "min_players" in game
    assert "max_players" in game
    assert "playing_time" in game

    # Rank should be a number (string format) or "Not Ranked"
    assert str(game["rank"]).isdigit() or game["rank"] == "Not Ranked"

    # Check extra attributes
    assert "weight" in game
    assert "rating" in game
    assert "image" in game
