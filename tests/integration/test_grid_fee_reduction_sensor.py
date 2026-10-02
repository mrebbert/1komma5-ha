"""Tier-2 tests for the §14a Modul 1 grid-fee reduction sensor.

Surfaces ``HeartbeatPriceWindow.module1_savings_per_year_eur`` from the
``year`` window of ``System.get_heartbeat_prices``. Entity is unavailable
until the account has a provisioning date; attributes expose the derived
gross estimate (× 1.19), provisioning date, active days and the basis string.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
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


def _window(
    *,
    provisioning_date: str | None = "2025-09-19",
    active_days: int | None = 365,
    savings_per_year_eur: float | None = 121.0,
    total_savings_eur: float | None = 121.0,
) -> MagicMock:
    return MagicMock(
        module1_provisioning_date=provisioning_date,
        module1_active_days=active_days,
        module1_savings_per_year_eur=savings_per_year_eur,
        module1_total_savings_eur=total_savings_eur,
    )


def _heartbeat_prices(year: MagicMock | None = None) -> MagicMock:
    if year is None:
        year = _window()
    return MagicMock(day=None, week=None, month=None, half_year=None, year=year)


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
        "sensor", "onekommafive", "sys-1_module1_grid_fee_reduction_annual"
    )
    assert entity_id is not None
    return entity_id


async def test_state_reflects_savings_per_year(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        heartbeat_prices=_heartbeat_prices(_window(savings_per_year_eur=121.0)),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "121.0"
    assert state.attributes["device_class"] == SensorDeviceClass.MONETARY
    assert state.attributes["state_class"] == SensorStateClass.TOTAL


async def test_entity_category_is_diagnostic(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1", heartbeat_prices=_heartbeat_prices()
    )
    await _setup(hass, system)

    entry = er.async_get(hass).async_get(_resolve(hass))
    assert entry.entity_category == EntityCategory.DIAGNOSTIC


async def test_attributes_expose_provisioning_and_gross_estimate(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        heartbeat_prices=_heartbeat_prices(
            _window(
                provisioning_date="2025-09-19",
                active_days=365,
                savings_per_year_eur=121.0,
            )
        ),
    )
    await _setup(hass, system)

    attrs = hass.states.get(_resolve(hass)).attributes
    assert attrs["provisioning_date"] == "2025-09-19"
    # 121 × 1.19 = 143.99 → rounded 143.99
    assert attrs["gross_estimate_eur_assumption"] == 143.99
    assert "§14a EnWG Modul 1" in attrs["basis"]
    # `active_days` was removed in the refactor — it mirrored the window length.
    assert "active_days" not in attrs


async def test_unavailable_without_provisioning_date(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        heartbeat_prices=_heartbeat_prices(
            _window(
                provisioning_date=None,
                active_days=None,
                savings_per_year_eur=None,
                total_savings_eur=None,
            )
        ),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "unavailable"
