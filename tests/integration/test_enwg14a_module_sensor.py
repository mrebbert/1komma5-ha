"""Tier-2 tests for the authoritative §14a-EnWG enrolment ENUM sensor.

Reads ``SiteSystemInfo.enwg14a_module`` from the ``get_system_info()`` endpoint
(SDK v1.1.8+). The sensor always registers; state is one of ``none`` /
``module_1`` / ``module_3`` / ``unknown`` and lives on the meter sub-device.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _system_info(
    *,
    enwg14a_value: str | None = None,
    valid_from: str | None = None,
    availability: str = "READY",
) -> MagicMock:
    if enwg14a_value is None:
        module = None
    else:
        module = MagicMock(value=enwg14a_value, valid_from_date=valid_from)
    return MagicMock(availability=availability, enwg14a_module=module)


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


def _resolve(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_enwg14a_module"
    )
    assert entity_id is not None
    return entity_id


async def test_state_none_when_not_enrolled(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(system_id="sys-1", system_info=_system_info())
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "none"
    assert state.attributes["device_class"] == SensorDeviceClass.ENUM
    assert state.attributes["valid_from_date"] is None


async def test_state_module_1_when_enrolled(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        system_info=_system_info(enwg14a_value="module-1", valid_from="2024-07-01"),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "module_1"
    assert state.attributes["valid_from_date"] == "2024-07-01"


async def test_state_module_3_when_enrolled(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        system_info=_system_info(enwg14a_value="module-3", valid_from="2026-10-01"),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "module_3"
    assert state.attributes["valid_from_date"] == "2026-10-01"


async def test_state_unknown_when_sdk_returns_unmapped_slug(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        system_info=_system_info(enwg14a_value="module-99", valid_from="2026-10-01"),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "unknown"


async def test_state_unknown_when_fetch_fails(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(system_id="sys-1")
    # Replace get_system_info with a stub that raises so the coordinator sees
    # a soft failure (coordinator captures the exception and keeps system_info
    # as None in the SystemStatusData record).
    system.get_system_info = AsyncMock(side_effect=RuntimeError("boom"))
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "unknown"


async def test_entity_category_is_diagnostic(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(system_id="sys-1", system_info=_system_info())
    await _setup(hass, system)

    entry = er.async_get(hass).async_get(_resolve(hass))
    assert entry.entity_category == EntityCategory.DIAGNOSTIC


async def test_module1_sensor_exposes_authoritative_valid_from(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """The Modul-1 savings sensor surfaces the authoritative enrolment date."""
    system = mock_system_factory(
        system_id="sys-1",
        heartbeat_prices=MagicMock(
            day=None,
            week=None,
            month=None,
            half_year=None,
            year=MagicMock(
                module1_provisioning_date="2025-09-19",
                module1_active_days=365,
                module1_savings_per_year_eur=121.0,
                module1_total_savings_eur=121.0,
                module3_total_savings_eur=None,
                comparison_grid_fee_eur_per_kwh=None,
                comparison_grid_fees_total_eur=None,
                variable_grid_fee_eur_per_kwh=None,
                variable_grid_fees_total_eur=None,
                enwg14a_total_savings_eur=None,
            ),
        ),
        system_info=_system_info(enwg14a_value="module-1", valid_from="2024-07-01"),
    )
    await _setup(hass, system)

    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_module1_grid_fee_reduction_annual"
    )
    assert entity_id is not None
    attrs = hass.states.get(entity_id).attributes
    assert attrs["enwg14a_module_valid_from"] == "2024-07-01"
