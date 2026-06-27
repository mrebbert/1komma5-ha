"""Tier-2 tests for the system-status coordinator.

The coordinator combines ``get_status_and_assets()`` (site connectivity +
asset inventory) with ``get_active_features()`` (customer-bound feature
flags) in one refresh. The active-features call needs a ``customer_id``
sourced from ``get_details()``; both are degraded gracefully when their
upstream calls fail.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _asset(asset_type: str, *, connection_status: str = "CONNECTED") -> MagicMock:
    # manufacturer/model/firmware default to None so the asset_device_info
    # helper (consumed by the sensor platform setup at the end of the test)
    # doesn't end up putting MagicMock objects into DeviceInfo and breaking
    # device-registry JSON serialisation during teardown.
    return MagicMock(
        type=asset_type,
        connection_status=connection_status,
        manufacturer=None,
        model=None,
        firmware=None,
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


async def test_happy_path_populates_all_three_fields(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("HYBRID"), _asset("EV_CHARGER")],
        active_features=["DYNAMIC_TARIFF", "SMART_CHARGING"],
    )
    entry = await _setup(hass, system)

    data = entry.runtime_data.system_status_coordinator.data
    assert data is not None
    assert data.site_status == "CONNECTED"
    assert [a.type for a in data.assets] == ["HYBRID", "EV_CHARGER"]
    assert data.active_features == ["DYNAMIC_TARIFF", "SMART_CHARGING"]


async def test_details_failure_skips_features_but_keeps_status(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """When get_details() fails, customer_id is None → no features call,
    but the coordinator still refreshes status + assets successfully."""
    system = mock_system_factory(
        system_id="sys-1", assets=[_asset("HYBRID")], active_features=["DYNAMIC_TARIFF"]
    )
    system.get_details.side_effect = RuntimeError("upstream 503")
    entry = await _setup(hass, system)

    data = entry.runtime_data.system_status_coordinator.data
    assert data is not None
    assert data.site_status == "CONNECTED"
    assert [a.type for a in data.assets] == ["HYBRID"]
    assert data.active_features == []
    # We never asked for features because we had no customer_id.
    system.get_active_features.assert_not_called()
    assert entry.runtime_data.details is None
    assert entry.runtime_data.customer_id is None


async def test_features_failure_does_not_break_coordinator(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """A failure on the second SDK call must not flip the whole coordinator
    to last_update_success=False — we silently fall back to features=[]."""
    system = mock_system_factory(system_id="sys-1", assets=[_asset("METER")])
    system.get_active_features.side_effect = RuntimeError("nope")
    entry = await _setup(hass, system)

    coord = entry.runtime_data.system_status_coordinator
    assert coord.last_update_success is True
    assert coord.data.active_features == []
    assert [a.type for a in coord.data.assets] == ["METER"]


async def test_status_and_assets_failure_marks_coordinator_failed(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """When the primary endpoint fails, the coordinator reports an
    unsuccessful refresh — entities will go unavailable."""
    from onekommafive.errors import ApiError

    system = mock_system_factory(system_id="sys-1")
    system.get_status_and_assets.side_effect = ApiError("rate limit")
    entry = await _setup(hass, system)

    coord = entry.runtime_data.system_status_coordinator
    assert coord.last_update_success is False
