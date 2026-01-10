"""Tests for BGG Data Update Coordinator."""
import os
import logging
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from custom_components.bgg_sync.coordinator import BggDataUpdateCoordinator
from aiohttp import ClientError


def load_sample(filename):
    """Load sample XML from the samples directory."""
    path = os.path.join(os.path.dirname(__file__), "samples", filename)
    with open(path, "rb") as f:
        return f.read()


# Helper to create a mock response context manager
def mock_response(content=b"", status=200, exc=None):
    mock = AsyncMock()
    mock.status = status
    mock.text.return_value = (
        content.decode("utf-8") if isinstance(content, bytes) else content
    )
    if exc:
        mock.__aenter__.side_effect = exc
    else:
        mock.__aenter__.return_value = mock
    return mock


async def test_coordinator_data_update(hass):
    """Test the coordinator successfully fetches and parses data using real samples."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", "test_pass", "test_token", [822]
    )

    xml_plays = load_sample("plays.xml")
    xml_collection = load_sample("collection.xml")
    xml_thing = load_sample("thing_822.xml")

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(xml_plays)
        if "collection" in url:
            return mock_response(xml_collection)
        if "thing" in url:
            return mock_response(xml_thing)
        return mock_response(status=404)

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect
    # Login mock
    mock_session.post.return_value = mock_response(status=200)

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator.data = await coordinator._async_update_data()

    assert coordinator.data["counts"]["owned_boardgames"] > 0
    assert coordinator.data["total_plays"] > 0
    game = coordinator.data["game_details"][822]
    assert game["name"] == "Carcassonne"
    assert str(game["rank"]).isdigit() or game["rank"] == "Not Ranked"

    await hass.async_block_till_done()


async def test_coordinator_parsing_corner_cases(hass, caplog):
    """Test XML parsing edge cases for 100% coverage."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [1, 2, 3, 4])

    xml_thing = b"""
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

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        if "collection" in url:
            return mock_response(b"<items></items>")
        if "thing" in url:
            return mock_response(xml_thing)
        return mock_response(status=404)

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.WARNING):
        coordinator.data = await coordinator._async_update_data()

    assert "Error parsing game details" in caplog.text
    g2 = coordinator.data["game_details"][2]
    assert g2["rating"] is None
    g3 = coordinator.data["game_details"][3]
    assert g3["rating"] is None
    g4 = coordinator.data["game_details"][4]
    assert g4["rank"] == "100"

    await hass.async_block_till_done()


async def test_coordinator_202_response(hass, caplog):
    """Test handling of 202 accepted response (processing)."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    def side_effect(url, **kwargs):
        if "thing" in url:
            return mock_response(b"<items></items>")
        return mock_response(status=202)

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.INFO):
        await coordinator._async_update_data()

    assert "BGG is generating play data" in caplog.text
    assert "BGG is (202) generating collection data" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_401_response(hass, caplog):
    """Test handling of 401 unauthorized response."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(status=401)
        return mock_response(b"<items></items>")

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.ERROR):
        await coordinator._async_update_data()

    assert "BGG API 401 Unauthorised" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_unknown_status_code(hass, caplog):
    """Test handling of unexpected status codes."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(status=500)
        if "collection" in url:
            return mock_response(status=403)
        return mock_response(b"<items></items>")

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()

    assert "Plays API returned status 500" in caplog.text
    assert "Collection API returned status 403" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_malformed_xml(hass, caplog):
    """Test handling of malformed XML."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [123])

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(b"Not XML")
        return mock_response(b"<items></items>")

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.ERROR):
        try:
            await coordinator._async_update_data()
        except Exception:
            pass

    await hass.async_block_till_done()


async def test_coordinator_thing_malformed_xml(hass, caplog):
    """Test malformed XML specifically in the Thing API."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [123])

    def side_effect(url, **kwargs):
        if "thing" in url:
            return mock_response(b"<items> <unclosed tag")
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        if "collection" in url:
            return mock_response(b"<items></items>")
        return mock_response(status=404)

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.ERROR):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    assert "Error communicating with BGG API" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_xml_with_bad_items(hass, caplog):
    """Test XML that is well-formed but contains unexpected structures."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    bad_collection = (
        b'<items><item subtype="boardgame"><name>Bad Game</name></item></items>'
    )

    def side_effect(url, **kwargs):
        if "collection" in url:
            return mock_response(bad_collection)
        if "plays" in url:
            return mock_response(b"<plays total='0'></plays>")
        return mock_response(b"<items></items>")

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()

    assert "Error parsing collection item" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_expansion_counting(hass):
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

    def side_effect(url, **kwargs):
        if "subtype=boardgame" in url and "subtype=boardgameexpansion" not in url:
            return mock_response(collection_boardgame)
        if "subtype=boardgameexpansion" in url:
            return mock_response(collection_expansion)
        if "plays" in url:
            return mock_response(b"<plays total='0'></plays>")
        return mock_response(b"<items></items>")

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator.data = await coordinator._async_update_data()

    assert coordinator.data["counts"]["owned_expansions"] == 1
    assert coordinator.data["counts"]["owned_boardgames"] == 1
    assert coordinator.data["counts"]["owned"] == 2

    await hass.async_block_till_done()


async def test_coordinator_login_logic(hass, caplog):
    """Test login logic."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])

    # 1. No password, login skipped
    mock_session = MagicMock()
    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        await coordinator._login()
        assert coordinator.logged_in is False

    # 2. Login fail
    coordinator = BggDataUpdateCoordinator(hass, "test_user", "wrong_pass", None, [])

    mock_session = MagicMock()
    mock_session.post.return_value = mock_response(exc=ClientError())

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.ERROR):
        await coordinator._login()

    assert "Login failed for test_user" in caplog.text

    # 3. Login success
    mock_session.post.return_value = mock_response(status=200)

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        await coordinator._login()

    assert coordinator.logged_in is True

    await hass.async_block_till_done()


async def test_coordinator_login_path_in_update(hass):
    """Test that _login is called during update if conditions met."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", "password", None, [])

    mock_session = MagicMock()
    mock_session.post.return_value = mock_response(status=200)

    # Needs to handle both post (login) and get (data)

    def get_side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        return mock_response(b"<items></items>")

    mock_session.get.side_effect = get_side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        await coordinator._async_update_data()

    assert coordinator.logged_in is True

    await hass.async_block_till_done()


async def test_coordinator_api_failure(hass):
    """Test total API failure raises UpdateFailed."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    def side_effect(url, **kwargs):
        if "plays" in url:
            # Simulate cleanup/exit with raising exception
            # We must use side_effect on __aenter__ for context manager exceptions
            m = AsyncMock()
            m.__aenter__.side_effect = ClientError("Connection Refused")
            return m
        return mock_response(b"<items></items>")

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    await hass.async_block_till_done()


async def test_coordinator_collection_message_202(hass, caplog):
    """Test collection returning message tag (202 processing)."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])

    msg_xml = b"<message>Your request for this collection has been accepted</message>"

    def side_effect(url, **kwargs):
        if "collection" in url:
            return mock_response(msg_xml)
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        return mock_response(b"<items></items>")

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.INFO):
        await coordinator._async_update_data()

    assert "BGG is (202) processing collection" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_thing_batch_failure(hass, caplog):
    """Test failure in one batch of thing requests."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", None, None, list(range(1, 25))
    )

    ids_1 = ",".join(str(i) for i in range(1, 21))
    # ids_2 = ",".join(str(i) for i in range(21, 25)) # Not needed for matching if strict

    def side_effect(url, **kwargs):
        if ids_1 in url:
            return mock_response(status=500)
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        if "collection" in url:
            return mock_response(b"<items></items>")
        return mock_response(b"<items></items>")

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ), caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()

    assert "Thing API failed for batch" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_full_counts(hass):
    """Test all count types."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])

    xml = b"""
    <items>
        <item objectid="1" subtype="boardgame">
            <status own="0" wishlist="1" wanttoplay="1" wanttobuy="1" fortrade="1" preordered="1" />
        </item>
    </items>
    """

    def side_effect(url, **kwargs):
        if "username=test_user&subtype=boardgame&stats=1" in url:
            return mock_response(xml)
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        return mock_response(b"<items></items>")

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession",
        return_value=mock_session,
    ):
        coordinator.data = await coordinator._async_update_data()

    c = coordinator.data["counts"]
    assert c["wishlist"] == 1
    assert c["want_to_play"] == 1
    assert c["want_to_buy"] == 1
    assert c["for_trade"] == 1
    assert c["preordered"] == 1

    await hass.async_block_till_done()
