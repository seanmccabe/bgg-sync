"""Global fixtures for BGG Sync integration tests."""
import pytest
from unittest.mock import patch

@pytest.fixture(autouse=True)
async def auto_enable_custom_integrations(enable_custom_integrations):
    """Automatically enable custom integrations for all tests."""
    yield

@pytest.fixture
def mock_setup_entry():
    """Mock setting up a config entry."""
    with patch(
        "custom_components.bgg_sync.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup
