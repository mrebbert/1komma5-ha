"""Tier-2 tests for wallbox lifecycle behaviour (stale + dynamic).

Two Gold-tier quality-scale properties:

- ``stale-devices``: sub-devices for wallboxes that no longer exist are
  purged from the device registry on reload.
- ``dynamic-devices``: a change in the wallbox inventory triggers a
  config-entry reload so new hardware appears without manual action.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _asset(name: str) -> MagicMock:
    asset = MagicMock(
        type="EV_CHARGER",
        connection_status="CONNECTED",
        manufacturer="go-e",
        model="HOMEfix",
        firmware="60.5",
    )
    asset.name = name
    return asset


def _wallbox(*, id_: str, name: str) -> MagicMock:
    wb = MagicMock(id=id_, assigned_ev_id=None)
    wb.name = name
    return wb


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


async def test_stale_wallbox_sub_device_is_removed_on_reload(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """A wallbox that vanishes between reloads is cleared from the device registry."""
    wb_a = _wallbox(id_="wb-a", name="Garage")
    wb_b = _wallbox(id_="wb-b", name="Carport")
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("Garage"), _asset("Carport")],
        wallboxes=[wb_a, wb_b],
    )
    entry = await _setup(hass, system)

    registry = dr.async_get(hass)
    assert registry.async_get_device({(DOMAIN, "sys-1_wallbox_wb-b")}) is not None

    # Second setup: wb-b is gone. The reload rebuilds the entry so patches must
    # cover it too, otherwise the SDK tries a real socket.
    system.get_wallboxes.return_value = [wb_a]
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    # After reload the count drops to 1, so the identifier collapses to the
    # single-wallbox form ``sys-1_wallbox``. Both per-wb identifiers must be gone.
    assert registry.async_get_device({(DOMAIN, "sys-1_wallbox_wb-a")}) is None
    assert registry.async_get_device({(DOMAIN, "sys-1_wallbox_wb-b")}) is None
    assert registry.async_get_device({(DOMAIN, "sys-1_wallbox")}) is not None


async def test_wallbox_added_between_refreshes_triggers_reload(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """A new wallbox appearing in a live refresh reloads the entry so it surfaces."""
    wb_a = _wallbox(id_="wb-a", name="Garage")
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("Garage")],
        wallboxes=[wb_a],
    )
    entry = await _setup(hass, system)

    # The live coordinator sees a second wallbox on the next refresh. Keep the
    # SDK patched: the reload the coordinator schedules will otherwise trip
    # pytest-socket while rebuilding the entry.
    wb_b = _wallbox(id_="wb-b", name="Carport")
    system.get_wallboxes.return_value = [wb_a, wb_b]

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
        patch.object(
            hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
        ) as reload_spy,
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]
        await entry.runtime_data.live_coordinator.async_refresh()
        await hass.async_block_till_done()

    reload_spy.assert_called_with(entry.entry_id)
