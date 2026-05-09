"""Tier-2 tests for the reauth and reconfigure flows."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _make_entry(hass: HomeAssistant, system_id: str = "sys-1") -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=system_id,
        data={
            CONF_USERNAME: "old@x.de",
            CONF_PASSWORD: "old_pw",
            CONF_SYSTEM_ID: system_id,
        },
    )
    entry.add_to_hass(hass)
    return entry


# ----------------------------------------------------------------------------
# reauth
# ----------------------------------------------------------------------------


async def test_reauth_updates_credentials(hass: HomeAssistant, mock_system_factory) -> None:
    """A successful reauth replaces username/password but keeps system_id."""
    system = mock_system_factory(system_id="sys-1")
    entry = _make_entry(hass)

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.return_value = [system]
        mock_systems_cls.return_value.get_system.return_value = system

        result = await entry.start_reauth_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new@x.de", CONF_PASSWORD: "new_pw"},
        )
        await hass.async_block_till_done()

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_USERNAME] == "new@x.de"
    assert entry.data[CONF_PASSWORD] == "new_pw"
    assert entry.data[CONF_SYSTEM_ID] == "sys-1"


async def test_reauth_invalid_credentials_shows_error(hass: HomeAssistant) -> None:
    """Wrong credentials during reauth keep the form open with invalid_auth."""
    from onekommafive.errors import AuthenticationError

    entry = _make_entry(hass)

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.side_effect = AuthenticationError("still bad")

        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "u@x.de", CONF_PASSWORD: "wrong"},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}
    # Entry data was NOT updated
    assert entry.data[CONF_PASSWORD] == "old_pw"


async def test_reauth_system_no_longer_present_errors(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """If the existing system_id is missing from the new account → system_not_found."""
    different_system = mock_system_factory(system_id="sys-OTHER")
    entry = _make_entry(hass, system_id="sys-1")

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.return_value = [different_system]

        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new@x.de", CONF_PASSWORD: "new_pw"},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "system_not_found"}
    assert entry.data[CONF_PASSWORD] == "old_pw"


# ----------------------------------------------------------------------------
# reconfigure
# ----------------------------------------------------------------------------


async def test_reconfigure_updates_credentials(hass: HomeAssistant, mock_system_factory) -> None:
    """A successful reconfigure replaces username/password and keeps system_id."""
    system = mock_system_factory(system_id="sys-1")
    entry = _make_entry(hass)

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.return_value = [system]
        mock_systems_cls.return_value.get_system.return_value = system

        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "renamed@x.de", CONF_PASSWORD: "rotated_pw"},
        )
        await hass.async_block_till_done()

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_USERNAME] == "renamed@x.de"
    assert entry.data[CONF_PASSWORD] == "rotated_pw"
    assert entry.data[CONF_SYSTEM_ID] == "sys-1"


async def test_reconfigure_cannot_connect_shows_error(hass: HomeAssistant) -> None:
    """Network errors during reconfigure surface as cannot_connect."""
    from onekommafive.errors import RequestError

    entry = _make_entry(hass)

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.side_effect = RequestError("down")

        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw"},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}
