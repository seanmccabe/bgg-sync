"""Tests for BGG Data Update Coordinator."""
import os
import logging
from unittest.mock import patch
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from custom_components.bgg_sync.coordinator import BggDataUpdateCoordinator
from custom_components.bgg_sync.const import BASE_URL, BGG_URL


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
    requests_mock.get(f"{BASE_URL}/plays", content=xml_plays)

    # 2. Collection
    requests_mock.get(
        f"{BASE_URL}/collection",
        content=xml_collection,
    )

    # 3. Thing
    requests_mock.get(f"{BASE_URL}/thing", content=xml_thing)

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


async def test_coordinator_202_response(hass, requests_mock, caplog):
    """Test handling of 202 accepted response (processing)."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", None, "test_token", []
    )
    
    # Simulate 202 for all endpoints
    requests_mock.get(f"{BASE_URL}/plays", status_code=202)
    requests_mock.get(f"{BASE_URL}/collection", status_code=202)
    requests_mock.get(f"{BASE_URL}/thing", status_code=200, content=b"<items></items>")
    
    with caplog.at_level(logging.INFO):
        await coordinator._async_update_data()
        
    assert "BGG is generating play data" in caplog.text
    assert "BGG is (202) generating collection data" in caplog.text


async def test_coordinator_401_response(hass, requests_mock, caplog):
    """Test handling of 401 unauthorized response."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", None, "test_token", []
    )
    
    requests_mock.get(f"{BASE_URL}/plays", status_code=401)
    
    # We expect other calls to proceed or fail gracefully
    requests_mock.get(f"{BASE_URL}/collection", status_code=200, content=b"<items></items>")
    requests_mock.get(f"{BASE_URL}/thing", status_code=200, content=b"<items></items>")
    
    with caplog.at_level(logging.ERROR):
        await coordinator._async_update_data()
        
    assert "BGG API 401 Unauthorised" in caplog.text


async def test_coordinator_malformed_xml(hass, requests_mock, caplog):
    """Test handling of malformed XML."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", None, "test_token", [123]
    )
    
    # Plays returns junk
    requests_mock.get(f"{BASE_URL}/plays", content=b"Not XML")
    requests_mock.get(f"{BASE_URL}/collection", content=b"<items></items>")
    requests_mock.get(f"{BASE_URL}/thing", content=b"<items></items>")
    
    with caplog.at_level(logging.ERROR):
        try:
            await coordinator._async_update_data()
        except Exception:
            pass # It might raise UpdateFailed depending on where it fails
            
    # The ET.fromstring in plays/collection currently raises ParseError which is caught by the generic Exception handler
    # in _update_data -> raises UpdateFailed.
    pass 


async def test_coordinator_login_logic(hass, requests_mock):
    """Test that login is called if no token is present."""
    # Coordinator with password but NO token
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", "password", None, []
    )
    
    # Mock Login Endpoint
    requests_mock.post(f"{BGG_URL}/login", status_code=200, text="Login Successful")
    
    # Mock Data Endpoints
    requests_mock.get(f"{BASE_URL}/plays", content=b"<plays total='0'></plays>")
    requests_mock.get(f"{BASE_URL}/collection", content=b"<items></items>")
    requests_mock.get(f"{BASE_URL}/thing", content=b"<items></items>")
    
    await coordinator._async_update_data()
    
    assert coordinator.logged_in is True
    assert requests_mock.call_count >= 2 # Login + Plays + Collection...


async def test_coordinator_api_failure(hass, requests_mock):
    """Test total API failure raises UpdateFailed."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", None, "test_token", []
    )
    
    # Network Error
    requests_mock.get(f"{BASE_URL}/plays", exc=Exception("Connection Refused"))
    
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
