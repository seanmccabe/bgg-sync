"""Regression tests for the authenticated API client identity (issue #11)."""

from custom_components.bgg_sync.config_flow import validate_input
from custom_components.bgg_sync.const import API_HEADERS
from custom_components.bgg_sync.coordinator import BggDataUpdateCoordinator


async def test_api_client_identity_is_used_by_coordinator_and_config_flow(
    hass, mock_response, mock_bgg_session
):
    coordinator = BggDataUpdateCoordinator(hass, "test_user", None, "test_token", [])
    mock_bgg_session.get.return_value = mock_response(b"<items/>")

    errors = await validate_input(
        hass, {"bgg_username": "test_user", "bgg_api_token": "test_token"}
    )

    assert not errors
    assert coordinator.headers == mock_bgg_session.get.call_args.kwargs["headers"]
    assert coordinator.headers["Accept"] == "application/xml"
    assert coordinator.headers["User-Agent"].startswith("BGGSync/")
    assert "Mozilla" not in coordinator.headers["User-Agent"]
    assert coordinator.headers["Authorization"] == "Bearer test_token"


async def test_api_headers_do_not_share_credentials_between_entries(hass):
    first = BggDataUpdateCoordinator(hass, "first", None, "first_token", [])
    second = BggDataUpdateCoordinator(hass, "second", None, "second_token", [])
    assert first.headers["Authorization"] == "Bearer first_token"
    assert second.headers["Authorization"] == "Bearer second_token"
    assert "Authorization" not in API_HEADERS
