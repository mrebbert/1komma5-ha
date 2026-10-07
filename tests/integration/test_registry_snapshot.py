"""Device- and Entity-registry snapshot tests across setup scenarios.

Pins the structural shape of what the integration creates: parent + per-asset
sub-devices, their identifiers/manufacturer/model, the entity → device
mapping, and each entity's platform / entity_category / translation_key.
Catches historical live-only bugs:

- `via_device_id` self-reference (v0.1.63)
- Empty sub-device creation when an asset is missing
- Identifier shift during single-wallbox → multi-wallbox transition

Snapshots live in ``tests/integration/__snapshots__/`` and are regenerated
with ``pytest tests/integration/test_registry_snapshot.py --snapshot-update``.
UUIDs and timestamps are normalised so the files are deterministic.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

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


def _snapshot_registries(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, Any]:
    """Serialise device + entity registries to a deterministic dict.

    Normalises unstable fields (device.id, timestamps, config_entry refs) so
    the resulting dict is stable across runs. The structure that matters —
    identifiers, via-device chains, entity → device assignment, categories,
    translation keys — is preserved verbatim.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    devices = sorted(
        dr.async_entries_for_config_entry(dev_reg, entry.entry_id),
        key=lambda d: tuple(sorted(tuple(i) for i in d.identifiers)),
    )

    # Build id → placeholder map so via_device_id is referenceable.
    device_slug: dict[str, str] = {}
    for device in devices:
        slug = "/".join(
            f"{domain}:{ident}" for domain, ident in sorted(device.identifiers)
        )
        device_slug[device.id] = slug

    devices_out: list[dict[str, Any]] = []
    for device in devices:
        via_slug = device_slug.get(device.via_device_id or "")
        devices_out.append(
            {
                "identifiers": sorted(tuple(i) for i in device.identifiers),
                "manufacturer": device.manufacturer,
                "model": device.model,
                "sw_version": device.sw_version,
                "name": device.name,
                "name_by_user": device.name_by_user,
                "via_device_slug": via_slug,
                "entry_type": device.entry_type.value if device.entry_type else None,
                "disabled_by": (
                    device.disabled_by.value if device.disabled_by else None
                ),
            }
        )

    entities = sorted(
        er.async_entries_for_config_entry(ent_reg, entry.entry_id),
        key=lambda e: (e.platform, e.unique_id or ""),
    )
    entities_out: list[dict[str, Any]] = []
    for entity in entities:
        entities_out.append(
            {
                "unique_id": entity.unique_id,
                "platform": entity.platform,
                "entity_category": (
                    entity.entity_category.value if entity.entity_category else None
                ),
                "translation_key": entity.translation_key,
                "device_slug": device_slug.get(entity.device_id or ""),
                "disabled_by": (
                    entity.disabled_by.value if entity.disabled_by else None
                ),
                "hidden_by": entity.hidden_by.value if entity.hidden_by else None,
            }
        )

    return {"devices": devices_out, "entities": entities_out}


def _asset(asset_type: str, manufacturer: str = "ACME", model: str = "X1") -> MagicMock:
    return MagicMock(
        type=asset_type,
        connection_status="CONNECTED",
        manufacturer=manufacturer,
        model=model,
        firmware="1.0.0",
        serial_number=f"serial-{asset_type.lower()}",
        name=f"{asset_type}-{manufacturer}",
        heat_pump_meter_type=None,
        id=f"asset-{asset_type.lower()}",
        emp_type="GRIDX",
        network_address=None,
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "gridx_single_wallbox",
        "onek5_single_wallbox",
        "no_heatpump",
        "no_wallbox",
    ],
)
async def test_registry_snapshot(
    hass: HomeAssistant,
    mock_system_factory,
    snapshot: SnapshotAssertion,
    scenario: str,
) -> None:
    """Pin device + entity registry shape per setup scenario."""
    emp_type = "1K5" if scenario == "onek5_single_wallbox" else "GRIDX"
    details = MagicMock(
        customer_id="cust-1",
        emp_type=emp_type,
        status="ACTIVE",
        dynamic_pulse_compatible=True,
        energy_trader_active=True,
        electricity_contract_active=True,
        has_third_party_smart_meter=None,
        earliest_measurement="2024-01-15",
        created_at=None,
        updated_at=None,
        device_gateways=[],
        address_country="DE",
    )
    assets: list[MagicMock] = [
        _asset("HYBRID", "Sungrow", "SH6.0RT"),
        _asset("METER", "Chint", "DTSU666"),
    ]
    if scenario != "no_heatpump":
        assets.append(_asset("HEAT_PUMP", "Stiebel Eltron", "WPMsystem"))
    if scenario != "no_wallbox":
        assets.append(_asset("EV_CHARGER", "go-e", "HOMEfix 11kW"))

    system = mock_system_factory(
        system_id="sys-1", details=details, assets=assets, active_features=[]
    )

    entry = await _setup(hass, system)
    assert _snapshot_registries(hass, entry) == snapshot
