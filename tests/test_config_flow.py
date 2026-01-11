"""Test BGG Sync config flow."""
import logging
from unittest.mock import patch
from homeassistant import config_entries, setup
from custom_components.bgg_sync.config_flow import validate_input
from custom_components.bgg_sync.const import (
    DOMAIN,
    CONF_API_TOKEN,
    CONF_BGG_USERNAME,
    CONF_BGG_PASSWORD,
    CONF_ENABLE_LOGGING,
)
from aiohttp import ClientError


async def test_config_flow(hass):
    """Test the config flow."""
    await setup.async_setup_component(hass, "persistent_notification", {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch(
        "custom_components.bgg_sync.config_flow.validate_input",
        return_value={},
    ), patch(
        "custom_components.bgg_sync.async_setup_entry",
        return_value=True,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "bgg_username": "test_user",
                "bgg_api_token": "test_token",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "test_user"
    assert result2["data"] == {
        "bgg_username": "test_user",
        "bgg_api_token": "test_token",
        "enable_logging": False,
    }


async def test_flow_validation_invalid_auth(hass):
    """Test invalid auth error (mocked validation)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.bgg_sync.config_flow.validate_input",
        return_value={CONF_API_TOKEN: "invalid_auth"},
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "bgg_username": "test_user",
                "bgg_api_token": "bad_token",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {CONF_API_TOKEN: "invalid_auth"}


async def test_flow_validation_cannot_connect(hass):
    """Test connection error (mocked validation)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.bgg_sync.config_flow.validate_input",
        return_value={"base": "cannot_connect"},
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "bgg_username": "test_user",
                "bgg_api_token": "token",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_flow_validation_password_required_logging(hass):
    """Test password is required if logging is enabled (logic inside validate_input)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.bgg_sync.config_flow.validate_input",
        return_value={CONF_BGG_PASSWORD: "password_required_for_logging"},
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "bgg_username": "test_user",
                "bgg_api_token": "token",
                "enable_logging": True,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {CONF_BGG_PASSWORD: "password_required_for_logging"}


async def test_options_flow(hass):
    """Test options flow."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    # 1. Setup Entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test_user",
        data={CONF_BGG_USERNAME: "test_user", CONF_API_TOKEN: "token"},
        unique_id="test_user",
    )
    entry.add_to_hass(hass)

    # Initialize Options Flow
    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == "form"
    assert result["step_id"] == "init"

    # Submit Options
    with patch(
        "custom_components.bgg_sync.config_flow.validate_input", return_value={}
    ):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_API_TOKEN: "new_token"}
        )

    assert result2["type"] == "create_entry"
    assert result2["data"][CONF_API_TOKEN] == "new_token"


# --- Unit Tests for validate_input ---


async def test_validate_input_logic_success(hass, mock_bgg_session, mock_response):
    """Test validate_input logic: Success (200)."""
    data = {
        CONF_BGG_USERNAME: "user",
        CONF_API_TOKEN: "token",
        CONF_ENABLE_LOGGING: False,
    }

    mock_bgg_session.get.return_value = mock_response(status=200)

    errors = await validate_input(hass, data)

    await hass.async_block_till_done()
    assert errors == {}


async def test_validate_input_logic_invalid_auth(hass, mock_bgg_session, mock_response):
    """Test validate_input logic: Invalid Auth (401)."""
    data = {
        CONF_BGG_USERNAME: "user",
        CONF_API_TOKEN: "bad_token",
        CONF_ENABLE_LOGGING: False,
    }

    mock_bgg_session.get.return_value = mock_response(status=401)

    errors = await validate_input(hass, data)

    await hass.async_block_till_done()
    assert errors == {CONF_API_TOKEN: "invalid_auth"}


async def test_validate_input_logic_connection_error(
    hass, mock_bgg_session, mock_response
):
    """Test validate_input logic: Connection Error."""
    data = {
        CONF_BGG_USERNAME: "user",
        CONF_API_TOKEN: "token",
        CONF_ENABLE_LOGGING: False,
    }

    mock_bgg_session.get.return_value = mock_response(exc=ClientError("fail"))

    errors = await validate_input(hass, data)

    await hass.async_block_till_done()
    assert errors == {"base": "cannot_connect"}


async def test_validate_input_logic_server_error(hass, mock_bgg_session, mock_response):
    """Test validate_input logic: Server Error (500)."""
    data = {
        CONF_BGG_USERNAME: "user",
        CONF_API_TOKEN: "token",
        CONF_ENABLE_LOGGING: False,
    }

    mock_bgg_session.get.return_value = mock_response(status=500)

    errors = await validate_input(hass, data)

    await hass.async_block_till_done()
    assert errors == {"base": "cannot_connect"}


async def test_validate_input_logic_202_warning(
    hass, caplog, mock_bgg_session, mock_response
):
    """Test validate_input logic: 202 Accepted warning."""
    data = {
        CONF_BGG_USERNAME: "user",
        CONF_API_TOKEN: "token",
        CONF_ENABLE_LOGGING: False,
    }

    mock_bgg_session.get.return_value = mock_response(status=202)

    with caplog.at_level(logging.WARNING):
        errors = await validate_input(hass, data)

    await hass.async_block_till_done()
    assert errors == {}
    assert "BGG returned 202 Accepted" in caplog.text


async def test_validate_input_password_check(hass, mock_bgg_session):
    """Test validate_input logic: Password required check."""
    data = {
        CONF_BGG_USERNAME: "user",
        CONF_API_TOKEN: "token",
        CONF_ENABLE_LOGGING: True,
        # Missing password
    }

    # we don't need to patch async_get_clientsession again as mock_bgg_session handles it
    # But actually, the logic fails before creating session.
    # The fixture mock_bgg_session is already providing the mock.

    errors = await validate_input(hass, data)

    await hass.async_block_till_done()
    assert errors.get(CONF_BGG_PASSWORD) == "password_required_for_logging"
