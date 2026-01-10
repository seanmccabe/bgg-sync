"""Tests for BGG Data Update Coordinator."""
import os
import logging
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

    # Assertions
    assert coordinator.data["counts"]["owned_boardgames"] > 0
    assert coordinator.data["total_plays"] > 0
    game = coordinator.data["game_details"][822]
    assert game["name"] == "Carcassonne"
    assert str(game["rank"]).isdigit() or game["rank"] == "Not Ranked"


async def test_coordinator_parsing_corner_cases(hass, requests_mock, caplog):
    """Test XML parsing edge cases for 100% coverage."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [1, 2, 3, 4])

    # 1. Plays and Collection (empty)
    requests_mock.get(f"{BASE_URL}/plays", content=b"<plays></plays>")
    requests_mock.get(f"{BASE_URL}/collection", content=b"<items></items>")

    # 2. Thing response with various edge case items
    # Item 1: Invalid ID (should log warning but continue)
    # Item 2: Missing 'statistics' (test get_r_val None branch)
    # Item 3: 'statistics' but missing children (test get_r_val None node branch)
    # Item 4: Valid Rank (test rank parsing loop)
    # Item 5: Valid Item but triggers parsing exception inside details update? (e.g. malformed int in other fields if we parsed them as ints, but we parse most as strings or only ID which is checked)

    xml = b"""
    <items>
        <!-- Item 1: Invalid ID -->
        <item id="invalid_id" type="boardgame">
            <name type="primary" value="Invalid Game" />
        </item>

        <!-- Item 2: No statistics -->
        <item id="2" type="boardgame">
            <name type="primary" value="No Stats Game" />
        </item>

        <!-- Item 3: Empty Ranks (Ratings existing but empty) -->
        <item id="3" type="boardgame">
            <name type="primary" value="Empty Stats Game" />
            <statistics>
                <ratings>
                     <!-- convert some to None -->
                </ratings>
            </statistics>
        </item>

        <!-- Item 4: Valid Rank -->
        <item id="4" type="boardgame">
            <name type="primary" value="Ranked Game" />
            <statistics>
                <ratings>
                    <ranks>
                        <rank type="subtype" id="1" name="boardgame" friendlyname="Board Game Rank" value="100" />
                        <rank type="family" id="5497" name="strategygames" friendlyname="Strategy Game Rank" value="50" />
                    </ranks>
                </ratings>
            </statistics>
        </item>
    </items>
    """

    requests_mock.get(f"{BASE_URL}/thing", content=xml)

    with caplog.at_level(logging.WARNING):
        coordinator.data = await coordinator._async_update_data()

    # Verify Item 1 caused warning (line 447)
    assert "Error parsing game details" in caplog.text

    # Verify Item 2 handled (missing stats)
    g2 = coordinator.data["game_details"][2]
    assert g2["rating"] is None

    # Verify Item 3 handled (empty stats)
    g3 = coordinator.data["game_details"][3]
    assert g3["rating"] is None

    # Verify Item 4 Rank
    g4 = coordinator.data["game_details"][4]
    assert g4["rank"] == "100"


async def test_coordinator_202_response(hass, requests_mock, caplog):
    """Test handling of 202 accepted response (processing)."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

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
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    requests_mock.get(f"{BASE_URL}/plays", status_code=401)
    requests_mock.get(
        f"{BASE_URL}/collection", status_code=200, content=b"<items></items>"
    )
    requests_mock.get(f"{BASE_URL}/thing", status_code=200, content=b"<items></items>")

    with caplog.at_level(logging.ERROR):
        await coordinator._async_update_data()

    assert "BGG API 401 Unauthorised" in caplog.text


async def test_coordinator_unknown_status_code(hass, requests_mock, caplog):
    """Test handling of unexpected status codes."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    requests_mock.get(f"{BASE_URL}/plays", status_code=500)
    requests_mock.get(f"{BASE_URL}/collection", status_code=403)
    requests_mock.get(f"{BASE_URL}/thing", status_code=200, content=b"<items></items>")

    with caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()

    assert "Plays API returned status 500" in caplog.text
    assert "Collection API returned status 403" in caplog.text


async def test_coordinator_malformed_xml(hass, requests_mock, caplog):
    """Test handling of malformed XML."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [123])

    # Plays returns junk
    requests_mock.get(f"{BASE_URL}/plays", content=b"Not XML")
    requests_mock.get(f"{BASE_URL}/collection", content=b"<items></items>")
    requests_mock.get(f"{BASE_URL}/thing", content=b"<items></items>")

    with caplog.at_level(logging.ERROR):
        try:
            await coordinator._async_update_data()
        except Exception:
            pass


async def test_coordinator_thing_malformed_xml(hass, requests_mock, caplog):
    """Test malformed XML specifically in the Thing API to hit the batch loop exception handler."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [123])

    requests_mock.get(f"{BASE_URL}/plays", content=b"<plays></plays>")
    requests_mock.get(f"{BASE_URL}/collection", content=b"<items></items>")

    # Thing API returns 200 but bad XML
    requests_mock.get(f"{BASE_URL}/thing", content=b"<items> <unclosed tag")

    with caplog.at_level(logging.ERROR):
        await coordinator._async_update_data()

    assert "Failed to parse BGG XML response" in caplog.text


async def test_coordinator_xml_with_bad_items(hass, requests_mock, caplog):
    """Test XML that is well-formed but contains unexpected structures."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    # Collection with an item with missing ID
    bad_collection = (
        b'<items><item subtype="boardgame"><name>Bad Game</name></item></items>'
    )

    requests_mock.get(f"{BASE_URL}/plays", content=b"<plays total='0'></plays>")
    requests_mock.get(f"{BASE_URL}/collection", content=bad_collection)
    requests_mock.get(f"{BASE_URL}/thing", content=b"<items></items>")

    with caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()

    assert "Error parsing collection item" in caplog.text


async def test_coordinator_expansion_counting(hass, requests_mock):
    """Test that expansions are counted correctly."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    collection_boardgame = b"""
    <items totalitems="1">
        <item objectid="101" subtype="boardgame">
            <status own="1" />
        </item>
    </items>
    """

    collection_expansion = b"""
    <items totalitems="1">
        <item objectid="102" subtype="boardgameexpansion">
            <status own="1" />
        </item>
    </items>
    """

    requests_mock.get(f"{BASE_URL}/plays", content=b"<plays total='0'></plays>")

    requests_mock.get(
        f"{BASE_URL}/collection?username=test_user&subtype=boardgame&stats=1",
        content=collection_boardgame,
    )
    requests_mock.get(
        f"{BASE_URL}/collection?username=test_user&subtype=boardgameexpansion&stats=1",
        content=collection_expansion,
    )

    requests_mock.get(f"{BASE_URL}/thing", content=b"<items></items>")

    coordinator.data = await coordinator._async_update_data()

    assert coordinator.data["counts"]["owned_expansions"] == 1
    assert coordinator.data["counts"]["owned_boardgames"] == 1
    assert coordinator.data["counts"]["owned"] == 2


async def test_coordinator_login_logic(hass, requests_mock, caplog):
    """Test login logic."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])
    coordinator._login()
    assert coordinator.logged_in is False

    coordinator = BggDataUpdateCoordinator(hass, "test_user", "wrong_pass", None, [])
    requests_mock.post(f"{BGG_URL}/login", exc=Exception("Connection Error"))

    with caplog.at_level(logging.ERROR):
        coordinator._login()
    assert "Login failed for test_user" in caplog.text

    requests_mock.post(f"{BGG_URL}/login", status_code=200)
    coordinator._login()
    assert coordinator.logged_in is True


async def test_coordinator_login_path_in_update(hass, requests_mock):
    """Test that _login is called during update if conditions met."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", "password", None, [])

    requests_mock.post(f"{BGG_URL}/login", status_code=200)
    requests_mock.get(f"{BASE_URL}/plays", content=b"<plays></plays>")
    requests_mock.get(f"{BASE_URL}/collection", content=b"<items></items>")
    requests_mock.get(f"{BASE_URL}/thing", content=b"<items></items>")

    await coordinator._async_update_data()
    assert coordinator.logged_in is True


async def test_coordinator_api_failure(hass, requests_mock):
    """Test total API failure raises UpdateFailed."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    requests_mock.get(f"{BASE_URL}/plays", exc=Exception("Connection Refused"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_collection_message_202(hass, requests_mock, caplog):
    """Test collection returning message tag (202 processing)."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])
    requests_mock.get(f"{BASE_URL}/plays", content=b"<plays></plays>")

    requests_mock.get(
        f"{BASE_URL}/collection",
        content=b"<message>Your request for this collection has been accepted</message>",
    )
    requests_mock.get(f"{BASE_URL}/thing", content=b"<items></items>")

    with caplog.at_level(logging.INFO):
        await coordinator._async_update_data()

    assert "BGG is (202) processing collection" in caplog.text


async def test_coordinator_thing_batch_failure(hass, requests_mock, caplog):
    """Test failure in one batch of thing requests."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", None, None, list(range(1, 25))
    )

    requests_mock.get(f"{BASE_URL}/plays", content=b"<plays></plays>")
    requests_mock.get(f"{BASE_URL}/collection", content=b"<items></items>")

    import re

    matcher = re.compile(f"{BASE_URL}/thing")

    # Use response_list for sequential responses
    requests_mock.get(
        matcher,
        response_list=[
            {"status_code": 500},
            {"status_code": 200, "content": b"<items></items>"},
        ],
    )

    with caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()

    assert "Thing API failed for batch" in caplog.text


async def test_coordinator_full_counts(hass, requests_mock):
    """Test all count types."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])

    xml = b"""
    <items>
        <item objectid="1" subtype="boardgame">
            <status own="0" wishlist="1" wanttoplay="1" wanttobuy="1" fortrade="1" preordered="1" />
        </item>
    </items>
    """

    requests_mock.get(f"{BASE_URL}/plays", content=b"<plays></plays>")
    requests_mock.get(
        f"{BASE_URL}/collection?username=test_user&subtype=boardgame&stats=1",
        content=xml,
    )
    requests_mock.get(
        f"{BASE_URL}/collection?username=test_user&subtype=boardgameexpansion&stats=1",
        content=b"<items></items>",
    )
    requests_mock.get(f"{BASE_URL}/thing", content=b"<items></items>")

    coordinator.data = await coordinator._async_update_data()

    c = coordinator.data["counts"]
    assert c["wishlist"] == 1
    assert c["want_to_play"] == 1
    assert c["want_to_buy"] == 1
    assert c["for_trade"] == 1
    assert c["preordered"] == 1
