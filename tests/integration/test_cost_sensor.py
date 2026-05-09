"""Tier-2 tests for the trapezoidal cost sensor.

Verify the wiring between the live coordinator, the stable price sensor
and the cost sensor — including the negative-price scenario that we
previously regressed on.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _live_overview(grid_consumption_power: float) -> MagicMock:
    return MagicMock(
        pv_power=0.0,
        battery_power=0.0,
        battery_soc=0,
        grid_power=grid_consumption_power,
        grid_consumption_power=grid_consumption_power,
        grid_feed_in_power=0.0,
        consumption_power=grid_consumption_power,
        household_power=grid_consumption_power,
        ev_chargers_power=0.0,
        heat_pumps_power=0.0,
        acs_power=0.0,
        self_sufficiency=0.0,
    )


def _market_prices(price_eur_per_kwh: float | None) -> MagicMock:
    """Build a MarketPrices stub whose only future slot has the given price."""
    if price_eur_per_kwh is None:
        return MagicMock(
            prices_with_grid_costs_and_vat={},
            prices_with_grid_costs={},
            average_price_all_in=None,
            lowest_price_all_in=None,
            highest_price_all_in=None,
        )
    # Slot ending well in the future so get_current_price picks it up.
    far_future = (
        (datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    slots = {far_future: price_eur_per_kwh}
    return MagicMock(
        prices_with_grid_costs_and_vat=slots,
        prices_with_grid_costs=slots,
        average_price_all_in=price_eur_per_kwh,
        lowest_price_all_in=price_eur_per_kwh,
        highest_price_all_in=price_eur_per_kwh,
    )


async def _setup_with_price(
    hass: HomeAssistant,
    mock_system_factory,
    *,
    price: float | None,
    initial_power: float = 1000.0,
) -> tuple[MockConfigEntry, MagicMock]:
    """Set up the integration. Returns (entry, system) — caller controls power afterwards."""
    system = mock_system_factory(
        system_id="sys-1",
        live_overview=_live_overview(initial_power),
        prices=_market_prices(price),
    )
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
    return entry, system


def _cost_sensor(hass: HomeAssistant) -> tuple[str, float]:
    """Return the (entity_id, accumulated_cost) of the electricity_cost sensor."""
    for state in hass.states.async_all("sensor"):
        if state.entity_id.endswith("_electricity_cost"):
            return state.entity_id, float(state.state)
    raise AssertionError("electricity_cost sensor not registered")


async def test_cost_sensor_accumulates_for_positive_price(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """Two refreshes 60 s apart at 2 kW with 0.30 €/kWh produce > 0 € of cost."""
    freezer.move_to("2026-05-08T12:00:00+00:00")
    entry, system = await _setup_with_price(
        hass, mock_system_factory, price=0.30, initial_power=2000.0
    )

    # First refresh after setup — the sensors only subscribed *after* the
    # bootstrap refresh, so this is their first observed sample. It seeds
    # _last_power / _last_time without accumulating.
    await entry.runtime_data.live_coordinator.async_refresh()
    await hass.async_block_till_done()

    # Advance 60 s and refresh again — now the sensor has two samples and
    # accumulates the trapezoidal delta.
    freezer.move_to("2026-05-08T12:01:00+00:00")
    system.get_live_overview.return_value = _live_overview(2000.0)
    await entry.runtime_data.live_coordinator.async_refresh()
    await hass.async_block_till_done()

    _, cost = _cost_sensor(hass)
    # 2000 W * (60/3600) h / 1000 = 0.0333 kWh * 0.30 €/kWh = 0.01 €
    assert cost > 0
    assert cost < 0.05  # sanity bound


async def test_cost_sensor_decreases_for_negative_price(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """Negative price means consuming reduces accumulated cost (you get paid)."""
    freezer.move_to("2026-05-08T12:00:00+00:00")
    entry, system = await _setup_with_price(
        hass, mock_system_factory, price=-0.05, initial_power=2000.0
    )

    # Seed _last_power / _last_time on the sensor (it didn't subscribe in time
    # for the bootstrap refresh).
    await entry.runtime_data.live_coordinator.async_refresh()
    await hass.async_block_till_done()

    freezer.move_to("2026-05-08T12:01:00+00:00")
    system.get_live_overview.return_value = _live_overview(2000.0)
    await entry.runtime_data.live_coordinator.async_refresh()
    await hass.async_block_till_done()

    _, cost = _cost_sensor(hass)
    assert cost < 0


async def test_cost_sensor_skips_when_price_unavailable(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """When the stable price is None (no API data ever) the cost stays at 0."""
    freezer.move_to("2026-05-08T12:00:00+00:00")
    entry, system = await _setup_with_price(
        hass, mock_system_factory, price=None, initial_power=2000.0
    )

    freezer.move_to("2026-05-08T12:01:00+00:00")
    system.get_live_overview.return_value = _live_overview(2000.0)
    await entry.runtime_data.live_coordinator.async_refresh()
    await hass.async_block_till_done()

    _, cost = _cost_sensor(hass)
    assert cost == 0.0
