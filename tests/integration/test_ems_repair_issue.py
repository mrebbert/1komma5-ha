"""Tier-2 tests for the EMS-unavailable Repair issue.

When the LiveCoordinator's ``get_ems_settings()`` returns None for
N consecutive refreshes (threshold = 5), an HA Repair Issue is
registered to surface the cause to the user without log-diving. The
issue is removed as soon as EMS data comes back.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
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


def _issue(hass: HomeAssistant):
    return ir.async_get(hass).async_get_issue(DOMAIN, "ems_settings_unavailable")


async def test_issue_fires_after_threshold_consecutive_failures(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """5 consecutive None ems_settings → Repair issue registered."""
    system = mock_system_factory(system_id="sys-1")
    # Make get_ems_settings raise so the coordinator sets ems_settings=None
    system.get_ems_settings.side_effect = RuntimeError("no DeviceGateway")
    entry = await _setup(hass, system)

    # First refresh during setup already counted as 1 failure. Push 4 more
    # via async_refresh to cross the threshold.
    for _ in range(4):
        await entry.runtime_data.live_coordinator.async_refresh()
        await hass.async_block_till_done()

    issue = _issue(hass)
    assert issue is not None
    assert issue.translation_key == "ems_settings_unavailable"
    assert issue.severity == ir.IssueSeverity.WARNING


async def test_issue_does_not_fire_before_threshold(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Three failures shouldn't be enough — covers transient API blips."""
    system = mock_system_factory(system_id="sys-1")
    system.get_ems_settings.side_effect = RuntimeError("temporary blip")
    entry = await _setup(hass, system)

    # 1 failure on setup + 2 more = 3, below the threshold of 5
    for _ in range(2):
        await entry.runtime_data.live_coordinator.async_refresh()
        await hass.async_block_till_done()

    assert _issue(hass) is None


async def test_issue_auto_resolves_when_ems_recovers(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Once ems_settings is back, the repair issue must auto-delete."""
    system = mock_system_factory(system_id="sys-1")
    system.get_ems_settings.side_effect = RuntimeError("no DeviceGateway")
    entry = await _setup(hass, system)

    # Force the issue to fire
    for _ in range(4):
        await entry.runtime_data.live_coordinator.async_refresh()
        await hass.async_block_till_done()
    assert _issue(hass) is not None

    # Now recover — EMS comes back with a valid object
    system.get_ems_settings.side_effect = None
    system.get_ems_settings.return_value = MagicMock(auto_mode=True)
    await entry.runtime_data.live_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _issue(hass) is None


async def test_healthy_install_never_fires_issue(hass: HomeAssistant, mock_system_factory) -> None:
    """The happy-path install (EMS always present) never triggers the issue."""
    system = mock_system_factory(system_id="sys-1")
    entry = await _setup(hass, system)

    for _ in range(10):
        await entry.runtime_data.live_coordinator.async_refresh()
        await hass.async_block_till_done()

    assert _issue(hass) is None


async def test_1k5_backend_never_fires_issue(hass: HomeAssistant, mock_system_factory) -> None:
    """emp_type=1K5 has no GridX EMS endpoint — skip the repair-issue path entirely."""
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(
            emp_type="1K5",
            customer_id="cust-uuid-1",
            device_gateways=[],
            address_country="DE",
        ),
    )
    system.get_ems_settings.side_effect = RuntimeError('error_code:30401 "DeviceGateway not found"')
    entry = await _setup(hass, system)

    for _ in range(10):
        await entry.runtime_data.live_coordinator.async_refresh()
        await hass.async_block_till_done()

    assert _issue(hass) is None
