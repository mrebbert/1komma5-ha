"""Tier-2 tests for the §14a Modul 3 variable-grid-fee savings sensor.

Surfaces ``HeartbeatPriceWindow.module3_total_savings_eur`` from the
``year`` window of ``System.get_heartbeat_prices``. Entity is unavailable
until the account has opted into Modul 3 (HT/NT variable Netzentgelte per
BK6-22-300); attributes expose the comparison tariff, the fee totals under
both scenarios, the combined Modul-1-plus-Modul-3 savings and the derived
gross estimate (× 1.19).
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
    module3_total_savings_eur: float | None = 42.5,
    comparison_grid_fee_eur_per_kwh: float | None = 0.12,
    comparison_grid_fees_total_eur: float | None = 180.0,
    variable_grid_fees_total_eur: float | None = 137.5,
    enwg14a_total_savings_eur: float | None = 163.5,
) -> MagicMock:
    return MagicMock(
        # Modul-1 defaults — present so the Modul-1 sensor coexists cleanly.
        module1_provisioning_date="2025-09-19",
        module1_active_days=365,
        module1_savings_per_year_eur=121.0,
        module1_total_savings_eur=121.0,
        # Modul-3 fields under test.
        module3_total_savings_eur=module3_total_savings_eur,
        comparison_grid_fee_eur_per_kwh=comparison_grid_fee_eur_per_kwh,
        comparison_grid_fees_total_eur=comparison_grid_fees_total_eur,
        variable_grid_fees_total_eur=variable_grid_fees_total_eur,
        enwg14a_total_savings_eur=enwg14a_total_savings_eur,
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
        "sensor", "onekommafive", "sys-1_module3_grid_fee_savings_annual"
    )
    assert entity_id is not None
    return entity_id


async def test_state_reflects_module3_savings(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        heartbeat_prices=_heartbeat_prices(_window(module3_total_savings_eur=42.5)),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "42.5"
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


async def test_attributes_expose_comparison_and_combined_savings(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        heartbeat_prices=_heartbeat_prices(
            _window(
                module3_total_savings_eur=42.5,
                comparison_grid_fee_eur_per_kwh=0.12,
                comparison_grid_fees_total_eur=180.0,
                variable_grid_fees_total_eur=137.5,
                enwg14a_total_savings_eur=163.5,
            )
        ),
    )
    await _setup(hass, system)

    attrs = hass.states.get(_resolve(hass)).attributes
    assert attrs["comparison_grid_fee_eur_per_kwh"] == 0.12
    assert attrs["comparison_grid_fees_total_eur"] == 180.0
    assert attrs["variable_grid_fees_total_eur"] == 137.5
    assert attrs["enwg14a_total_savings_eur"] == 163.5
    # 42.5 × 1.19 = 50.5749999… → rounded 50.57 (float precision, not banker's).
    assert attrs["gross_estimate_eur_assumption"] == 50.57
    assert "§14a EnWG Modul 3" in attrs["basis"]


async def test_unavailable_without_module3_opt_in(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        heartbeat_prices=_heartbeat_prices(
            _window(
                module3_total_savings_eur=None,
                comparison_grid_fee_eur_per_kwh=None,
                comparison_grid_fees_total_eur=None,
                variable_grid_fees_total_eur=None,
                enwg14a_total_savings_eur=None,
            )
        ),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "unavailable"
