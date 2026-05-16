"""Tier-2 tests for the diagnostics platform.

The diagnostics download is what bug reporters attach to issues, so the
contract here is:
1. credentials and the system_id must NOT appear in the output
2. all four coordinators are summarised
3. the dict is JSON-serialisable
"""

from __future__ import annotations

import json
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.onekommafive.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def _setup(hass: HomeAssistant, system) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-secret-42",
        data={
            CONF_USERNAME: "secret@example.com",
            CONF_PASSWORD: "topsecret",
            CONF_SYSTEM_ID: "sys-secret-42",
        },
    )
    entry.add_to_hass(hass)
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_diagnostics_redacts_credentials_and_system_id(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Credentials and system_id must not leak into the diagnostics dump."""
    system = mock_system_factory(system_id="sys-secret-42")
    entry = await _setup(hass, system)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    serialised = json.dumps(diag)
    assert "secret@example.com" not in serialised
    assert "topsecret" not in serialised
    assert "sys-secret-42" not in serialised


async def test_diagnostics_includes_all_four_coordinators(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """The four coordinator summaries are present with shape we expect."""
    system = mock_system_factory(system_id="sys-1")
    entry = await _setup(hass, system)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert set(diag["coordinators"]) == {"live", "price", "optimization", "weather"}
    for snap in diag["coordinators"].values():
        assert "last_update_success" in snap
        assert "update_interval_seconds" in snap
        assert "summary" in snap


async def test_diagnostics_is_json_serialisable(hass: HomeAssistant, mock_system_factory) -> None:
    """HA serialises diagnostics to JSON when the user downloads them."""
    system = mock_system_factory(system_id="sys-1")
    entry = await _setup(hass, system)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    # Must not raise.
    json.dumps(diag)
    assert diag["sdk_version"]  # version() returns a string for the installed SDK
