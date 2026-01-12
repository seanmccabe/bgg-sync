"""Tests for BGG Data Update Coordinator."""
import logging
import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from custom_components.bgg_sync.coordinator import BggDataUpdateCoordinator
from aiohttp import ClientError


async def test_coordinator_data_update(
    hass, sample_loader, mock_response, mock_bgg_session
):
    """Test the coordinator successfully fetches and parses data using real samples."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", "test_pass", "test_token", [822]
    )

    xml_plays = sample_loader("plays.xml")
    xml_collection = sample_loader("collection.xml")
    xml_thing = sample_loader("thing_822.xml")

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(xml_plays)
        if "collection" in url:
            return mock_response(xml_collection)
        if "thing" in url:
            return mock_response(xml_thing)
        return mock_response(status=404)

    mock_bgg_session.get.side_effect = side_effect
    # Login mock
    mock_bgg_session.post.return_value = mock_response(status=200)

    coordinator.data = await coordinator._async_update_data()

    assert coordinator.data["counts"]["owned_boardgames"] > 0
    assert coordinator.data["total_plays"] > 0
    game = coordinator.data["game_details"][822]
    assert game["name"] == "Carcassonne"
    assert str(game["rank"]).isdigit() or game["rank"] == "Not Ranked"

    await hass.async_block_till_done()


async def test_coordinator_parsing_corner_cases(
    hass, caplog, mock_response, mock_bgg_session
):
    """Test XML parsing edge cases for coverage."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [4])

    xml_thing = b"""
    <items>
        <!-- Item 1: Valid Rank -->
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

    mock_bgg_session.get.side_effect = side_effect

    # We expect other parts to be successful
    coordinator.data = await coordinator._async_update_data()

    g4 = coordinator.data["game_details"][4]
    assert g4["rank"] == "100"

    await hass.async_block_till_done()


async def test_coordinator_202_response(hass, caplog, mock_response, mock_bgg_session):
    """Test handling of 202 accepted response (processing)."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(b'<plays total="0"></plays>')
        if "collection" in url:
            return mock_response(status=202)
        if "thing" in url:
            return mock_response(b"<items></items>")
        return mock_response(status=200)

    mock_bgg_session.get.side_effect = side_effect

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    await hass.async_block_till_done()


async def test_coordinator_401_response(hass, caplog, mock_response, mock_bgg_session):
    """Test handling of 401 unauthorized response."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(status=401)
        return mock_response(b"<items></items>")

    mock_bgg_session.get.side_effect = side_effect

    with caplog.at_level(logging.ERROR):
        await coordinator._async_update_data()

    assert "BGG API 401 Unauthorised" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_unknown_status_code(
    hass, caplog, mock_response, mock_bgg_session
):
    """Test handling of unexpected status codes."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(status=500)
        if "collection" in url:
            return mock_response(status=403)
        return mock_response(b"<items></items>")

    mock_bgg_session.get.side_effect = side_effect

    with caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()

    assert "Plays API returned status 500" in caplog.text
    assert "Collection API returned status 403" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_thing_batch_failure(
    hass, caplog, mock_response, mock_bgg_session
):
    """Test failure in one batch of thing requests."""
    coordinator = BggDataUpdateCoordinator(
        hass, "test_user", None, None, list(range(1, 25))
    )

    ids_1 = ",".join(str(i) for i in range(1, 21))

    def side_effect(url, **kwargs):
        if ids_1 in url:
            return mock_response(status=500)
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        if "collection" in url:
            return mock_response(b"<items></items>")
        return mock_response(b"<items></items>")

    mock_bgg_session.get.side_effect = side_effect

    with caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()

    assert "Thing API failed for batch" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_login_logic(hass, caplog, mock_response, mock_bgg_session):
    """Test login logic."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])

    # 1. No password, login skipped
    await coordinator.client.login()
    assert coordinator.client.logged_in is False

    # 2. Login fail
    coordinator = BggDataUpdateCoordinator(hass, "test_user", "wrong_pass", None, [])
    mock_bgg_session.post.return_value = mock_response(exc=ClientError())

    with caplog.at_level(logging.ERROR):
        await coordinator.client.login()

    assert "Login failed for test_user" in caplog.text

    # 3. Login success
    mock_bgg_session.post.return_value = mock_response(status=200)

    await coordinator.client.login()

    assert coordinator.client.logged_in is True

    await hass.async_block_till_done()


async def test_coordinator_login_path_in_update(hass, mock_response, mock_bgg_session):
    """Test that login is called during update if conditions met."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", "password", None, [])

    mock_bgg_session.post.return_value = mock_response(status=200)

    # Needs to handle both post (login) and get (data)
    def get_side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        return mock_response(b"<items></items>")

    mock_bgg_session.get.side_effect = get_side_effect

    await coordinator._async_update_data()

    assert coordinator.client.logged_in is True

    await hass.async_block_till_done()


async def test_coordinator_expansion_counting(hass, mock_response, mock_bgg_session):
    """Test that expansions are counted correctly."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    collection_boardgame = b"""
    <items totalitems="1">
        <item objectid="101" subtype="boardgame">
            <status own="1" />
            <name>BG</name>
        </item>
    </items>
    """

    collection_expansion = b"""
    <items totalitems="1">
        <item objectid="102" subtype="boardgameexpansion">
            <status own="1" />
            <name>Exp</name>
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

    mock_bgg_session.get.side_effect = side_effect

    coordinator.data = await coordinator._async_update_data()

    assert coordinator.data["counts"]["owned_expansions"] == 1
    assert coordinator.data["counts"]["owned_boardgames"] == 1
    assert coordinator.data["counts"]["owned"] == 2

    await hass.async_block_till_done()


async def test_coordinator_thing_malformed_xml(
    hass, caplog, mock_response, mock_bgg_session
):
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

    mock_bgg_session.get.side_effect = side_effect

    # The new implementation catches XML errors and logs them, possibly not raising UpdateFailed
    # if it's just one batch failing, OR if the XML parse fails entirely it might log "Failed to parse..."
    # api.py: _LOGGER.error("Failed to parse BGG XML response: %s", e)

    with caplog.at_level(logging.ERROR):
        await coordinator._async_update_data()

    assert "Failed to parse BGG XML" in caplog.text

    await hass.async_block_till_done()
