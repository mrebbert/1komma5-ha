"""Tier-2 tests for the grid-cost breakdown attributes on the current-price sensor.

Live reconciliation (2026-07-12): all_in = (spot + Σ net grid components) × (1 + vat).
The itemised components are NET (ex-VAT); the SDK scalar grid_costs_total is GROSS
and is intentionally NOT surfaced. The sensor exposes the net adder so
`spot_price + grid_costs` reconciles to the pre-VAT price.
"""

from __future__ import annotations

import datetime
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

SPOT = 0.126
ENERGY_TAX = 0.13756
VAT = 0.19
ALL_IN = round((SPOT + ENERGY_TAX) * (1 + VAT), 7)  # 0.3136364


def _market_prices(*, uses_fallback: bool = False) -> MagicMock:
    slot = (
        (datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    return MagicMock(
        prices={slot: SPOT},
        prices_with_grid_costs={slot: round(SPOT + ENERGY_TAX, 7)},
        prices_with_grid_costs_and_vat={slot: ALL_IN},
        average_price_all_in=ALL_IN,
        lowest_price_all_in=ALL_IN,
        highest_price_all_in=ALL_IN,
        grid_cost_energy_tax=ENERGY_TAX,
        grid_cost_purchasing=0.0,
        grid_cost_fixed_tariff=0.0,
        grid_cost_dynamic_markup=0.0,
        grid_cost_feed_in_remuneration_adj=0.0,
        vat=VAT,
        uses_fallback_grid_costs=uses_fallback,
    )


async def _setup(hass: HomeAssistant, prices: MagicMock, mock_system_factory) -> None:
    system = mock_system_factory(system_id="sys-1", prices=prices)
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


def _current_price_state(hass: HomeAssistant):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_current_electricity_price"
    )
    assert entity_id is not None
    return hass.states.get(entity_id)


async def test_breakdown_attributes_reconcile(hass: HomeAssistant, mock_system_factory) -> None:
    await _setup(hass, _market_prices(), mock_system_factory)
    attrs = _current_price_state(hass).attributes

    assert attrs["spot_price"] == SPOT
    assert attrs["grid_costs"] == ENERGY_TAX
    assert attrs["vat_rate"] == VAT
    assert attrs["uses_fallback_grid_costs"] is False
    assert attrs["grid_cost_components"]["energy_tax"] == ENERGY_TAX
    # zero components are surfaced (present, not None), not dropped
    assert attrs["grid_cost_components"]["dynamic_markup"] == 0.0

    # The exposed net figures must reconcile to the all-in state.
    reconstructed = round((attrs["spot_price"] + attrs["grid_costs"]) * (1 + attrs["vat_rate"]), 7)
    assert reconstructed == ALL_IN


async def test_fallback_flag_surfaces_true(hass: HomeAssistant, mock_system_factory) -> None:
    await _setup(hass, _market_prices(uses_fallback=True), mock_system_factory)
    attrs = _current_price_state(hass).attributes
    assert attrs["uses_fallback_grid_costs"] is True
