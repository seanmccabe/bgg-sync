import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture(autouse=True)
async def auto_enable_custom_integrations(enable_custom_integrations):
    """Automatically enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_response():
    """Return a factory for creating mock responses."""

    def _make_response(content=b"", status=200, exc=None):
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

    return _make_response


@pytest.fixture
def mock_bgg_session():
    """Mock the BGG client session."""
    with patch(
        "custom_components.bgg_sync.coordinator.async_get_clientsession"
    ) as mock_get_session, patch(
        "custom_components.bgg_sync.config_flow.async_get_clientsession"
    ) as mock_get_session_flow, patch(
        "custom_components.bgg_sync.async_get_clientsession"
    ) as mock_get_session_init:
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_get_session_flow.return_value = mock_session
        mock_get_session_init.return_value = mock_session
        yield mock_session


@pytest.fixture
def sample_loader():
    """Load sample XML from the samples directory."""

    def _load(filename):
        path = os.path.join(os.path.dirname(__file__), "samples", filename)
        with open(path, "rb") as f:
            return f.read()

    return _load


@pytest.fixture
def mock_coordinator():
    """Mock the BGG coordinator."""
    coordinator = MagicMock()
    coordinator.data = {
        "game_details": {},
        "game_plays": {},
        "collection": {},
        "counts": {},
        "total_plays": 0,
    }
    return coordinator
