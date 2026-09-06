"""Tier-2 tests for the EMS-auto-mode switch platform.

The switch is only meaningful on installs that expose the GridX-scoped
`get_ems_settings()` endpoint. On 1K5-backend installs (`emp_type=1K5`)
the endpoint returns 30401 permanently, so the switch is skipped
at setup time to avoid a permanent-unavailable entity.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


async def _setup(hass: HomeAssistant, system: MagicMock) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-1",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-1"},
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


def _switch_entity_id(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id("switch", DOMAIN, "sys-1_ems_auto_mode")


async def test_gridx_install_creates_switch(hass: HomeAssistant, mock_system_factory) -> None:
    """GRIDX backend: the EMS switch entity is created."""
    system = mock_system_factory(system_id="sys-1")
    await _setup(hass, system)
    assert _switch_entity_id(hass) is not None


async def test_1k5_install_skips_switch(hass: HomeAssistant, mock_system_factory) -> None:
    """1K5 backend: the EMS switch entity is NOT created."""
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(
            emp_type="1K5",
            customer_id="cust-uuid-1",
            device_gateways=[],
            address_country="DE",
        ),
    )
    await _setup(hass, system)
    assert _switch_entity_id(hass) is None
