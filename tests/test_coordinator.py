"""Tests for BGG Data Update Coordinator."""
import logging
import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from custom_components.bgg_sync.coordinator import BggDataUpdateCoordinator
from aiohttp import ClientError
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from custom_components.bgg_sync.const import IMAGE_CACHE_DIR


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


async def test_coordinator_full_collection_flags(hass, mock_bgg_session):
    """Test coordinator correctly increments all collection flags."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])
    # Re-mock client methods directly
    coordinator.client.fetch_plays = AsyncMock(
        return_value={"status": 200, "total": 10, "last_play": None}
    )
    coordinator.client.fetch_game_plays = AsyncMock(return_value=5)
    coordinator.client.fetch_thing_details = AsyncMock(return_value=[])

    # Mock collection with all flags
    item_all_flags = {
        "objectid": 100,
        "subtype": "boardgame",
        "name": "Game 1",
        "own": True,
        "wishlist": True,
        "wanttoplay": True,
        "wanttobuy": True,
        "fortrade": True,
        "preordered": True,
        "numplays": 5,
        "image": "img.jpg",
        "thumbnail": "thumb.jpg",
        "yearpublished": "2020",
        "minplayers": "1",
        "maxplayers": "4",
        "playingtime": "60",
        "minplaytime": "60",
        "maxplaytime": "60",
        "rank": "1",
        "rating": "8.0",
        "bayes_rating": "7.5",
        "weight": "2.5",
        "users_rated": "1000",
        "stddev": "1.0",
        "median": "8.0",
        "numowned": "5000",
        "collid": "12345",
    }
    # We return the mocked item only for the first call (boardgame), empty for second
    coordinator.client.fetch_collection = AsyncMock(
        side_effect=[
            {"status": 200, "items": [item_all_flags]},
            {"status": 200, "items": []},
        ]
    )

    data = await coordinator._async_update_data()

    assert data["counts"]["wishlist"] == 1
    assert data["counts"]["want_to_play"] == 1
    assert data["counts"]["want_to_buy"] == 1
    assert data["counts"]["for_trade"] == 1
    assert data["counts"]["preordered"] == 1


async def test_coordinator_plays_processing(hass, mock_bgg_session):
    """Test coordinator handles 202 status for plays."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])

    coordinator.client.fetch_plays = AsyncMock(
        return_value={"status": 202, "total": 0, "last_play": None}
    )
    coordinator.client.fetch_collection = AsyncMock(
        return_value={"status": 200, "items": []}
    )
    coordinator.client.fetch_game_plays = AsyncMock(return_value=0)
    coordinator.client.fetch_thing_details = AsyncMock(return_value=[])

    data = await coordinator._async_update_data()
    # Should complete without error, but logging "BGG is generating play data"
    assert data is not None


async def test_coordinator_generic_error(hass, mock_bgg_session):
    """Test coordinator handles generic exceptions during update."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])

    # We must mock the method on the client instance attached to the coordinator
    coordinator.client.fetch_plays = AsyncMock(side_effect=Exception("Unexpected boom"))

    with pytest.raises(UpdateFailed) as excinfo:
        await coordinator._async_update_data()

    assert "Error communicating with BGG API" in str(excinfo.value)


@pytest.fixture
async def mock_coordinator(hass, mock_bgg_session):
    """Create a mock coordinator."""
    return BggDataUpdateCoordinator(hass, "test_user", "password", None, [123], {})


async def async_return(result):
    return result


async def test_download_image_empty_url(mock_coordinator):
    """Test downloading with empty URL returns None."""
    result = await mock_coordinator._download_image("", 123)
    assert result is None


async def test_download_image_webp(hass, mock_coordinator):
    """Test downloading a webp image."""
    with patch("os.makedirs"), patch("os.path.exists", return_value=False), patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession"
    ) as mock_session, patch(
        "custom_components.bgg_sync.coordinator.Image.open"
    ) as mock_img_open, patch("builtins.open", mock_open()):
        # Mock Session
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.side_effect = lambda: async_return(b"image_data")
        mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

        # Mock Image
        mock_img = MagicMock()
        mock_img_open.return_value.__enter__.return_value = mock_img

        result = await mock_coordinator._download_image(
            "http://example.com/image.webp", 123
        )

        assert result == f"/local/{IMAGE_CACHE_DIR}/123.webp"
        mock_img.save.assert_called()


async def test_download_image_cache_hit(hass, mock_coordinator):
    """Test existing cache prevents re-download."""
    url = "http://example.com/image.jpg"

    # Mocking os.path.exists to return True for both file and meta
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=url)
    ), patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession"
    ) as mock_session:
        result = await mock_coordinator._download_image(url, 123)

        assert result == f"/local/{IMAGE_CACHE_DIR}/123.jpg"
        # Verify NO download occurred
        mock_session.assert_not_called()


async def test_download_image_resize_failure_fallback(hass, mock_coordinator):
    """Test fallback to saving original if resize fails."""

    with patch("os.makedirs"), patch("os.path.exists", return_value=False), patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession"
    ) as mock_session, patch(
        "custom_components.bgg_sync.coordinator.Image.open",
        side_effect=Exception("Resize Error"),
    ), patch("builtins.open", mock_open()) as mock_file:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.side_effect = lambda: async_return(b"raw_data")
        mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

        result = await mock_coordinator._download_image(
            "http://example.com/image.jpg", 123
        )

        assert result == f"/local/{IMAGE_CACHE_DIR}/123.jpg"

        # Verify we wrote the raw data (fallback)
        writes = [arg[0][0] for arg in mock_file().write.call_args_list]
        assert b"raw_data" in writes


async def test_download_image_general_exception(hass, mock_coordinator):
    """Test general exception handling returns None."""

    # Force os.makedirs to raise exception
    with patch("os.path.exists", return_value=False), patch(
        "os.makedirs", side_effect=OSError("Disk Full")
    ):
        result = await mock_coordinator._download_image("http://url", 123)
        assert result is None


async def test_read_meta_exception(hass, mock_coordinator):
    """Test exception when reading metadata file proceeds to download."""
    url = "http://example.com/image.jpg"

    # Mock exists=True to try reading meta
    with patch("os.path.exists", return_value=True), patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession"
    ) as mock_session, patch(
        "custom_components.bgg_sync.coordinator.Image.open"
    ) as mock_img_open, patch("builtins.open", mock_open(read_data="should_fail")):
        # Mock download success for when we inevitably proceed
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.side_effect = lambda: async_return(b"data")
        mock_session.return_value.get.return_value.__aenter__.return_value = mock_resp

        # Mock Image open for the save part
        mock_img = MagicMock()
        mock_img_open.return_value.__enter__.return_value = mock_img

        # We intercept executor job.
        # If the job function name is 'read_meta', we raise.
        # If 'write_file', we let it pass.

        async def side_effect(target, *args):
            if target.__name__ == "read_meta":
                raise Exception("Meta Read Fail")
            # For write_file, just run it immediately?
            # Or just return None (success representation here).
            # The original code awaits it.
            if target.__name__ == "write_file":
                target()  # Execute it to trigger the open() calls inside
                return None
            return None

        with patch.object(hass, "async_add_executor_job", side_effect=side_effect):
            result = await mock_coordinator._download_image(url, 123)

            # It should have returned the local path
            assert result == f"/local/{IMAGE_CACHE_DIR}/123.jpg"

            # And we confirm download WAS called (because metadata read failed)
            assert mock_session.return_value.get.called


async def test_coordinator_init_game_data_normalization(hass, mock_bgg_session):
    """Test that game_data keys are normalized to int, and invalid ones skipped."""
    raw_data = {
        "123": {"prop": "val"},
        "invalid": {"prop": "bad"},
        456: {"prop": "val2"},
    }

    coord = BggDataUpdateCoordinator(hass, "user", None, None, [], raw_data)

    assert 123 in coord.game_data
    assert 456 in coord.game_data
    assert "invalid" not in coord.game_data
    assert coord.game_data[123] == {"prop": "val"}

async def test_cache_images(hass, mock_coordinator):
    """Test caching logic correctly overrides image dict entries."""
    test_data = {
        "game_details": {
            123: {"image": "http://img.com/123.jpg"}
        }
    }
    
    from unittest.mock import patch
    with patch.object(mock_coordinator, "_download_image", return_value="/local/bgg_sync/123.jpg"):
        await mock_coordinator._cache_images(test_data)
        
    assert test_data["game_details"][123]["original_image"] == "http://img.com/123.jpg"
    assert test_data["game_details"][123]["image"] == "/local/bgg_sync/123.jpg"
    assert test_data["game_details"][123]["thumbnail"] == "/local/bgg_sync/123.jpg"
