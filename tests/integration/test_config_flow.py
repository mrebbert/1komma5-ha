"""Tier-2 tests for the config flow.

These tests stand up a real Home Assistant instance, mock the
``onekommafive`` library and walk through the integration's config flow
end-to-end.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.onekommafive.const import DOMAIN

# ----------------------------------------------------------------------------
# user flow — error paths (no entry is ever created, no setup_entry runs)
# ----------------------------------------------------------------------------


async def test_user_flow_invalid_credentials_shows_error(
    hass: HomeAssistant,
) -> None:
    """An ``AuthenticationError`` from the library surfaces as ``invalid_auth``."""
    from onekommafive.errors import AuthenticationError

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.side_effect = AuthenticationError("bad creds")

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "u@x.de", "password": "wrong"},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect_shows_error(
    hass: HomeAssistant,
) -> None:
    """A ``RequestError`` surfaces as ``cannot_connect``."""
    from onekommafive.errors import RequestError

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.side_effect = RequestError("network")

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "u@x.de", "password": "pw"},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


# ----------------------------------------------------------------------------
# user flow — success paths
#
# These need the patches active throughout the test, including HA's
# follow-up `async_setup_entry` after the entry is created. Otherwise the
# coordinator's first_refresh runs against a real (un-patched) Systems/
# Client and crashes the test teardown.
# ----------------------------------------------------------------------------


async def test_user_flow_single_system_creates_entry(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """A single-system account skips the picker and creates the entry directly."""
    system = mock_system_factory(system_id="sys-1", name="Home")

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.return_value = [system]
        mock_systems_cls.return_value.get_system.return_value = system

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "u@x.de", "password": "pw"},
        )
        await hass.async_block_till_done()

        assert result["type"] == "create_entry"
        assert result["data"]["system_id"] == "sys-1"
        assert result["data"]["username"] == "u@x.de"
        assert result["title"] == "Home"


async def test_user_flow_multiple_systems_shows_picker(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Accounts with several systems get a picker step before the entry is created."""
    system_a = mock_system_factory(system_id="sys-a", name="Home A")
    system_b = mock_system_factory(system_id="sys-b", name="Home B")

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.return_value = [system_a, system_b]
        mock_systems_cls.return_value.get_system.return_value = system_b

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "u@x.de", "password": "pw"},
        )
        assert result["type"] == "form"
        assert result["step_id"] == "system"

        # Pick the second system
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"system_id": "sys-b"},
        )
        await hass.async_block_till_done()

        assert result["type"] == "create_entry"
        assert result["data"]["system_id"] == "sys-b"
        assert result["title"] == "Home B"
