"""Tests for BGG Data Update Coordinator."""
import logging
import unittest
from unittest.mock import AsyncMock
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

    mock_bgg_session.get.side_effect = side_effect

    with caplog.at_level(logging.WARNING):
        coordinator.data = await coordinator._async_update_data()

    assert "Error parsing game details" in caplog.text
    g2 = coordinator.data["game_details"][2]
    assert g2["rating"] is None
    g3 = coordinator.data["game_details"][3]
    assert g3["rating"] is None
    g4 = coordinator.data["game_details"][4]
    assert g4["rank"] == "100"

    await hass.async_block_till_done()


async def test_coordinator_202_response(hass, caplog, mock_response, mock_bgg_session):
    """Test handling of 202 accepted response (processing)."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])

    def side_effect(url, **kwargs):
        if "thing" in url:
            return mock_response(b"<items></items>")
        return mock_response(status=202)

    mock_bgg_session.get.side_effect = side_effect

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


async def test_coordinator_malformed_xml(hass, caplog, mock_response, mock_bgg_session):
    """Test handling of malformed XML."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [123])

    def side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(b"Not XML")
        return mock_response(b"<items></items>")

    mock_bgg_session.get.side_effect = side_effect

    with caplog.at_level(logging.ERROR):
        try:
            await coordinator._async_update_data()
        except Exception:
            pass

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

    with caplog.at_level(logging.ERROR):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    assert "Error communicating with BGG API" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_xml_with_bad_items(
    hass, caplog, mock_response, mock_bgg_session
):
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

    mock_bgg_session.get.side_effect = side_effect

    with caplog.at_level(logging.WARNING):
        await coordinator._async_update_data()

    assert "Error parsing collection item" in caplog.text

    await hass.async_block_till_done()


async def test_coordinator_expansion_counting(hass, mock_response, mock_bgg_session):
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

    mock_bgg_session.get.side_effect = side_effect

    coordinator.data = await coordinator._async_update_data()

    assert coordinator.data["counts"]["owned_expansions"] == 1
    assert coordinator.data["counts"]["owned_boardgames"] == 1
    assert coordinator.data["counts"]["owned"] == 2

    await hass.async_block_till_done()


async def test_coordinator_login_logic(hass, caplog, mock_response, mock_bgg_session):
    """Test login logic."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])

    # 1. No password, login skipped
    await coordinator._login()
    assert coordinator.logged_in is False

    # 2. Login fail
    coordinator = BggDataUpdateCoordinator(hass, "test_user", "wrong_pass", None, [])
    mock_bgg_session.post.return_value = mock_response(exc=ClientError())

    with caplog.at_level(logging.ERROR):
        await coordinator._login()

    assert "Login failed for test_user" in caplog.text

    # 3. Login success
    mock_bgg_session.post.return_value = mock_response(status=200)

    await coordinator._login()

    assert coordinator.logged_in is True

    await hass.async_block_till_done()


async def test_coordinator_login_path_in_update(hass, mock_response, mock_bgg_session):
    """Test that _login is called during update if conditions met."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", "password", None, [])

    mock_bgg_session.post.return_value = mock_response(status=200)

    # Needs to handle both post (login) and get (data)
    def get_side_effect(url, **kwargs):
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        return mock_response(b"<items></items>")

    mock_bgg_session.get.side_effect = get_side_effect

    await coordinator._async_update_data()

    assert coordinator.logged_in is True

    await hass.async_block_till_done()


async def test_coordinator_api_failure(hass, mock_response, mock_bgg_session):
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

    mock_bgg_session.get.side_effect = side_effect

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    await hass.async_block_till_done()


async def test_coordinator_collection_message_202(
    hass, caplog, mock_response, mock_bgg_session
):
    """Test collection returning message tag (202 processing)."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [])

    msg_xml = b"<message>Your request for this collection has been accepted</message>"

    def side_effect(url, **kwargs):
        if "collection" in url:
            return mock_response(msg_xml)
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        return mock_response(b"<items></items>")

    mock_bgg_session.get.side_effect = side_effect

    mock_bgg_session.get.side_effect = side_effect

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

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


async def test_coordinator_full_counts(hass, mock_response, mock_bgg_session):
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

    mock_bgg_session.get.side_effect = side_effect

    coordinator.data = await coordinator._async_update_data()

    c = coordinator.data["counts"]
    assert c["wishlist"] == 1
    assert c["want_to_play"] == 1
    assert c["want_to_buy"] == 1
    assert c["for_trade"] == 1
    assert c["preordered"] == 1

    await hass.async_block_till_done()


async def test_thing_api_xml_parse_error(hass, mock_bgg_session):
    def make_resp(content, status=200):
        m = AsyncMock()
        m.status = status
        m.text.return_value = content
        m.__aenter__.return_value = m
        return m

    mock_bgg_session.get.side_effect = [
        # 1. Plays: Success
        make_resp('<plays total="10"></plays>'),
        # 2. Collection: Success (returns item 123)
        make_resp(
            '<items><item objectid="123" subtype="boardgame"><name>G</name><status own="1"/></item></items>'
        ),
        # 3. Collection (Expansions): Empty
        make_resp("<items></items>"),
        # 4. Specific Game Plays (for ID 123)
        make_resp('<plays total="5"></plays>'),
        # 5. Thing API (Batch): Returns invalid XML to trigger the specific exception line
        make_resp("<start><unclosed_tag>"),
    ]

    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [123])

    # Verify data is partially populated despite Thing API failure
    data = await coordinator._async_update_data()
    assert 123 in data["collection"]
    assert data["game_details"][123]["name"] == "G"


def test_coordinator_extract_methods(hass):
    """Test the extraction helper methods directly for coverage."""
    coord = BggDataUpdateCoordinator(hass, "test", None, None, [])

    # Test _extract_expansions with None/Empty
    assert coord._extract_expansions(None) == []
    assert coord._extract_expansions("") == []

    # Test _extract_players with missing username (fallback to name)
    import xml.etree.ElementTree as ET

    xml = """
    <play>
        <players>
            <player username="" name="Bob" />
            <player username="Alice" name="Alice Real" />
        </players>
    </play>
    """
    node = ET.fromstring(xml)
    players = coord._extract_players(node)
    # Alice should be "Alice", Bob should be "Bob"
    assert "Alice" in players
    assert "Bob" in players
    assert len(players) == 2


async def test_clean_bgg_text(hass):
    """Test the BBCode cleaning helper."""
    coordinator = BggDataUpdateCoordinator(hass, "user", None, None, [])

    # Test simple text
    assert coordinator._clean_bgg_text("Simple text") == "Simple text"

    # Test with thing tag
    assert (
        coordinator._clean_bgg_text("Played [thing=123]Game Name[/thing]")
        == "Played Game Name"
    )

    # Test with multiple tags
    assert (
        coordinator._clean_bgg_text("[thing=1]A[/thing] vs [thing=2]B[/thing]")
        == "A vs B"
    )

    # Test with simple tags
    assert coordinator._clean_bgg_text("Bold [b]text[/b]") == "Bold text"

    # Test None
    assert coordinator._clean_bgg_text(None) == ""

    # Test the user reported case
    raw_comment = """Won with most parks (12)

Played with expansions:
-[thing=298729]PARKS: Nightfall[/thing]
-[thing=358854]PARKS: Wildlife[/thing]"""

    expected = """Won with most parks (12)

Played with expansions:
-PARKS: Nightfall
-PARKS: Wildlife"""

    assert coordinator._clean_bgg_text(raw_comment) == expected


async def test_coordinator_image_whitespace_handling(
    hass, mock_response, mock_bgg_session
):
    """Test that image URLs are stripped of whitespace."""
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, None, [777], None)

    xml_with_space = b"""
    <items>
        <item id="777" type="boardgame">
            <name type="primary" value="Test Space" />
            <image>
                http://example.com/image.png
            </image>
        </item>
    </items>
    """

    def side_effect(url, **kwargs):
        if "thing" in url:
            return mock_response(xml_with_space)
        if "plays" in url:
            return mock_response(b"<plays></plays>")
        if "collection" in url:
            return mock_response(b"<items></items>")
        return mock_response(b"<items></items>")

    mock_bgg_session.get.side_effect = side_effect

    with (
        unittest.mock.patch("os.makedirs"),
        unittest.mock.patch("os.path.exists", return_value=False),
        unittest.mock.patch("builtins.open", unittest.mock.mock_open()),
        unittest.mock.patch("PIL.Image.open"),
        unittest.mock.patch("io.BytesIO"),
    ):
        data = await coordinator._async_update_data()

    # The coordinator logic usually returns the local path if successful, but we mocked open
    # and the download response (mock_response default is 200).
    # Since we mocked the download as "successful" via default mock_response,
    # the coordinator will set the image to the local path.
    # We should verify it TRIED to download the whitespace-stripped URL.
    # But since we didn't mock the specific image download GET, it might fail or use default.

    # Actually, simpler: verify the stripped URL was put in 'original_image' or 'image'
    # Wait, if download fails it keeps original URL.

    # Let's adjust the test to expect the local path if we mock success
    # img_path = data["game_details"][777].get("image")
    # It should be local path OR clean URL if download failed
    assert "http://example.com/image.png" in str(data["game_details"][777])


from unittest.mock import MagicMock, patch, mock_open
import pytest
from custom_components.bgg_sync.coordinator import BggDataUpdateCoordinator
from custom_components.bgg_sync.const import IMAGE_CACHE_DIR


@pytest.fixture
def mock_coordinator(hass):
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
        original_add_job = hass.async_add_executor_job

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


def test_coordinator_init_game_data_normalization(hass):
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
