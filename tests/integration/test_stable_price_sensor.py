"""Tier-2 tests for the StablePriceSensor's hold-last-valid behaviour.

Why this matters: the cost sensor reads its multiplier from the stable
price sensor. If a coordinator refresh returns no usable price data the
stable sensor must keep returning the last valid price; otherwise the
cost accumulator silently stops.
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


def _market_prices_with(price: float | None) -> MagicMock:
    """Build a MarketPrices mock that has either one future slot or no slots."""
    if price is None:
        return MagicMock(
            prices_with_grid_costs_and_vat={},
            prices_with_grid_costs={},
            average_price_all_in=None,
            lowest_price_all_in=None,
            highest_price_all_in=None,
        )
    far_future = (
        (datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    slots = {far_future: price}
    return MagicMock(
        prices_with_grid_costs_and_vat=slots,
        prices_with_grid_costs=slots,
        average_price_all_in=price,
        lowest_price_all_in=price,
        highest_price_all_in=price,
    )


def _stable_price_state(hass: HomeAssistant) -> str:
    for state in hass.states.async_all("sensor"):
        if state.entity_id.endswith("_last_valid_electricity_price"):
            return state.state
    raise AssertionError("stable price sensor not registered")


async def test_stable_price_holds_last_valid_when_api_returns_empty(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """A subsequent empty MarketPrices payload must not zero the stable sensor.

    Previously the sensor's ``_dynamic_current_price`` returned ``None`` for
    an empty price dict and the sensor's update logic only assigns when the
    new value is not None — that contract is what protects the cost
    accumulator's multiplier.
    """
    system = mock_system_factory(
        system_id="sys-1",
        prices=_market_prices_with(0.30),
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

        # First refresh of the stable price sensor sees a valid price.
        assert float(_stable_price_state(hass)) == 0.30

        # Now the API drops the price (empty MarketPrices) — refresh again.
        system.get_prices.return_value = _market_prices_with(None)
        await entry.runtime_data.price_coordinator.async_refresh()
        await hass.async_block_till_done()

    # Stable sensor must still report the previously known good value.
    assert float(_stable_price_state(hass)) == 0.30
