"""Tests for BGG API Client."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from custom_components.bgg_sync.api import BggClient
import xml.etree.ElementTree as ET


@pytest.fixture
def mock_session():
    """Mock aiohttp session."""
    return MagicMock()


@pytest.fixture
def client(mock_session):
    """BggClient instance."""
    return BggClient(mock_session, "test_user", "password")


async def test_clean_bgg_text(client):
    """Test the BBCode cleaning helper."""
    # Test simple text
    assert client._clean_bgg_text("Simple text") == "Simple text"

    # Test with thing tag
    assert (
        client._clean_bgg_text("Played [thing=123]Game Name[/thing]")
        == "Played Game Name"
    )

    # Test with multiple tags
    assert (
        client._clean_bgg_text("[thing=1]A[/thing] vs [thing=2]B[/thing]") == "A vs B"
    )

    # Test with simple tags
    assert client._clean_bgg_text("Bold [b]text[/b]") == "Bold text"

    # Test None
    assert client._clean_bgg_text(None) == ""

    # Test the user reported case
    raw_comment = """Won with most parks (12)

Played with expansions:
-[thing=298729]PARKS: Nightfall[/thing]
-[thing=358854]PARKS: Wildlife[/thing]"""

    expected = """Won with most parks (12)

Played with expansions:
-PARKS: Nightfall
-PARKS: Wildlife"""

    assert client._clean_bgg_text(raw_comment) == expected


def test_extract_expansions(client):
    """Test extraction of expansions."""
    assert client._extract_expansions(None) == []
    assert client._extract_expansions("") == []

    text = "Played with expansions\n[thing=123]Exp 1[/thing]"
    assert client._extract_expansions(text) == ["Exp 1"]


def test_extract_players(client):
    """Test extraction of players."""
    xml = """
    <play>
        <players>
            <player username="" name="Bob" />
            <player username="Alice" name="Alice Real" />
        </players>
    </play>
    """
    node = ET.fromstring(xml)
    players = client._extract_players(node)
    assert "Alice" in players
    assert "Bob" in players
    assert len(players) == 2


async def test_fetch_thing_details_parsing(client, mock_session):
    """Test parsing logic in thing details."""
    xml_thing = """
    <items>
        <!-- Item 1: Valid Rank -->
        <item id="4" type="boardgame">
            <name type="primary" value="Ranked Game" />
            <statistics>
                <ratings>
                    <ranks>
                        <rank type="subtype" id="1" name="boardgame" friendlyname="Board Game Rank" value="100" />
                    </ranks>
                    <average value="8.5" />
                </ratings>
            </statistics>
        </item>
    </items>
    """

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = xml_thing
    mock_resp.__aenter__.return_value = mock_resp
    mock_session.get.return_value = mock_resp

    result = await client.fetch_thing_details([4])

    assert len(result) == 1
    assert result[0]["id"] == 4
    assert result[0]["name"] == "Ranked Game"
    assert result[0]["rank"] == "100"
    assert result[0]["rating"] == "8.5"


async def test_fetch_thing_details_error_handling(client, mock_session):
    """Test error handling in parsing for thing details."""
    xml_thing = """
    <items>
        <!-- Item 1: Invalid ID to trigger ValueError in int conversion if strict -->
        <item id="invalid" type="boardgame"></item>
    </items>
    """
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = xml_thing
    mock_resp.__aenter__.return_value = mock_resp
    mock_session.get.return_value = mock_resp

    # helper logs warning but continues
    result = await client.fetch_thing_details([1])
    # Should be empty or filtered
    assert len(result) == 0


async def test_login(client, mock_session):
    """Test login logic."""
    # Success
    # Success
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__.return_value = mock_resp
    mock_session.post.return_value = mock_resp

    assert await client.login() is True
    assert client.logged_in is True

    # Failure
    mock_session.post.side_effect = Exception("Conn Error")
    assert await client.login() is False


async def test_validate_auth(client, mock_session):
    """Test auth validation."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__.return_value = mock_resp
    mock_session.get.return_value = mock_resp

    assert await client.validate_auth() == 200


async def test_record_play(client, mock_session):
    """Test recording a play."""
    # Mock login (called inside record_play)
    mock_login_resp = AsyncMock()
    mock_login_resp.status = 200
    mock_login_resp.text.return_value = "{}"
    mock_login_resp.__aenter__.return_value = mock_login_resp

    # Mock play post
    mock_play_resp = AsyncMock()
    mock_play_resp.status = 200
    mock_play_resp.text.return_value = "<html>Success</html>"
    mock_play_resp.__aenter__.return_value = mock_play_resp

    # side_effect for multiple calls
    # Call 1: Login, Call 2: Play
    mock_session.post.side_effect = [mock_login_resp, mock_play_resp]

    players = [{"name": "P1", "username": "P1", "win": True}]
    success = await client.record_play(
        game_id=123, date="2023-01-01", length="60", comments="Fun", players=players
    )

    assert success is True
    assert mock_session.post.call_count == 2

    # Verify play args
    call_args = mock_session.post.call_args_list[1]
    url = call_args[0][0]
    kwargs = call_args[1]
    assert "geekplay.php" in url
    assert kwargs["data"]["objectid"] == "123"
    assert kwargs["data"]["action"] == "save"
    assert kwargs["data"]["comments"] == "Fun"


async def test_record_play_login_fail(client, mock_session):
    """Test recording play when login fails."""
    mock_login_resp = AsyncMock()
    mock_login_resp.status = 401
    mock_login_resp.text.return_value = "Unauthorized"
    mock_login_resp.__aenter__.return_value = mock_login_resp

    mock_session.post.return_value = mock_login_resp

    success = await client.record_play(123)
    assert success is False
    assert mock_session.post.call_count == 1


async def test_record_play_error(client, mock_session):
    """Test recording play when API returns error."""
    mock_login_resp = AsyncMock()
    mock_login_resp.status = 200
    mock_login_resp.__aenter__.return_value = mock_login_resp

    mock_play_resp = AsyncMock()
    mock_play_resp.status = 200
    mock_play_resp.text.return_value = "<html>Error: Something went wrong</html>"
    mock_play_resp.__aenter__.return_value = mock_play_resp

    mock_session.post.side_effect = [mock_login_resp, mock_play_resp]

    success = await client.record_play(123)
    assert success is False
