"""Tier-2 tests for asset-driven entity auto-hide.

When an asset type is missing from the cloud's status_and_assets
response, the matching entities still register (so user history /
unique_ids stay), but with ``entity_registry_enabled_default=False``.
The user can re-enable them manually from the entity registry; HA
preserves that choice across reloads.
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


def _asset(asset_type: str) -> MagicMock:
    return MagicMock(
        type=asset_type,
        connection_status="CONNECTED",
        manufacturer=None,
        model=None,
        firmware=None,
        serial_number=None,
        network_address=None,
        heat_pump_meter_type=None,
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


def _record_by_unique_id(hass: HomeAssistant, unique_id: str):
    entity_reg = er.async_get(hass)
    for record in entity_reg.entities.values():
        if record.unique_id == unique_id:
            return record
    return None


async def test_missing_heat_pump_disables_heat_pump_entities(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """An install without a HEAT_PUMP asset registers heat-pump entities as
    disabled-by-default so they don't clutter the device list."""
    # Only HYBRID + METER + EV_CHARGER present — no heat pump
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("HYBRID"), _asset("METER"), _asset("EV_CHARGER")],
    )
    await _setup(hass, system)

    record = _record_by_unique_id(hass, "sys-1_heat_pumps_power")
    assert record is not None, "entity must still exist for history continuity"
    assert record.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # Sister entity (heat-pump energy) shares the fate
    energy = _record_by_unique_id(hass, "sys-1_heat_pumps_power_energy")
    assert energy is not None
    assert energy.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_present_asset_keeps_entities_enabled(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """When the asset is present, the matching entities stay enabled."""
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("HYBRID"), _asset("HEAT_PUMP"), _asset("METER"), _asset("EV_CHARGER")],
    )
    await _setup(hass, system)

    record = _record_by_unique_id(hass, "sys-1_heat_pumps_power")
    assert record is not None
    assert record.disabled_by is None


async def test_parent_only_entities_always_enabled(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """System-parent entities (no device_key) are never auto-hidden, even
    when the entire asset list is empty."""
    system = mock_system_factory(system_id="sys-1", assets=[])
    await _setup(hass, system)

    for parent_unique_id in (
        "sys-1_current_electricity_price",
        "sys-1_self_sufficiency",
        "sys-1_active_features",
    ):
        record = _record_by_unique_id(hass, parent_unique_id)
        assert record is not None
        assert record.disabled_by is None, f"{parent_unique_id} disabled but should not be"
