"""Tier-2 tests for the EMS-auto-mode switch platform.

The switch is only meaningful on installs that expose the GridX-scoped
`get_ems_settings()` endpoint. On 1K5-backend installs (`emp_type=1K5`)
the endpoint returns 30401 permanently, so the switch is skipped
at setup time to avoid a permanent-unavailable entity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
        mock_systems_cls.return_value.get_system = AsyncMock(return_value=system)
        mock_systems_cls.return_value.get_systems = AsyncMock(return_value=[system])
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


async def test_gridx_switch_toggles_call_sdk(hass: HomeAssistant, mock_system_factory) -> None:
    """`async_turn_on/off` calls ``system.set_ems_mode(True/False)`` and refreshes."""
    system = mock_system_factory(system_id="sys-1")
    entry = await _setup(hass, system)
    entity_id = _switch_entity_id(hass)
    assert entity_id is not None

    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    system.set_ems_mode.assert_awaited_with(True)

    system.set_ems_mode.reset_mock()
    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    system.set_ems_mode.assert_awaited_with(False)
    # The switch is coordinator-driven; a request-refresh follows every write.
    assert entry.runtime_data.live_coordinator.last_update_success is True


async def test_switch_state_is_none_when_ems_settings_missing(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """When the live payload carries no ``ems_settings`` the switch reads as ``None``."""
    system = mock_system_factory(system_id="sys-1")
    entry = await _setup(hass, system)
    entity_id = _switch_entity_id(hass)
    assert entity_id is not None

    # Force a coordinator refresh that returns without EMS settings — mirrors
    # the runtime path where ``get_ems_settings()`` failed.
    entry.runtime_data.live_coordinator.data.ems_settings = None
    entry.runtime_data.live_coordinator.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unavailable"


async def test_1k5_install_removes_stale_gridx_switch(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """1K5 backend: a pre-existing GRIDX-era switch entity is cleaned up."""
    # Pre-seed the registry with a stale entry that would remain unavailable
    # forever if the setup path just returns without cleanup.
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "switch", DOMAIN, "sys-1_ems_auto_mode", suggested_object_id="test_home_ems_auto_mode"
    )
    assert _switch_entity_id(hass) is not None  # stale entry exists

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

    assert _switch_entity_id(hass) is None  # cleaned up
