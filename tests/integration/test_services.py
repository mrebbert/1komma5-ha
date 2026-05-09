"""Tier-2 tests for the integration's services.

Validate end-to-end that ``onekommafive.get_cheapest_window`` and
``onekommafive.get_most_expensive_window`` walk through the resolver,
talk to the price coordinator and shape the response correctly.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _make_market_prices(prices_15min: dict[str, float]) -> MagicMock:
    """Build a MarketPrices mock that the price coordinator can digest."""
    return MagicMock(
        prices_with_grid_costs_and_vat=prices_15min,
        prices_with_grid_costs=prices_15min,
        average_price_all_in=sum(prices_15min.values()) / max(len(prices_15min), 1),
        lowest_price_all_in=min(prices_15min.values()) if prices_15min else None,
        highest_price_all_in=max(prices_15min.values()) if prices_15min else None,
    )


@pytest.fixture
async def integration_with_prices(hass: HomeAssistant, mock_system_factory):
    """Set up the integration with a known price forecast and return the entry."""
    # Build a 4-slot forecast in the future.
    now = datetime.datetime.now(tz=datetime.UTC).replace(second=0, microsecond=0)
    # Round up to the next 15-min boundary to keep slot ends > now.
    future = now + datetime.timedelta(minutes=15 - (now.minute % 15))
    slots = {
        (future + datetime.timedelta(minutes=15 * i)).isoformat().replace("+00:00", "Z"): price
        for i, price in enumerate([0.30, 0.10, 0.05, 0.40])
    }
    prices = _make_market_prices(slots)

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

    return entry


async def test_get_cheapest_window_returns_minimum_average_slot(
    hass: HomeAssistant, integration_with_prices
) -> None:
    """A 30-min window over (0.10 + 0.05) / 2 = 0.075 must be the winner."""
    response = await hass.services.async_call(
        DOMAIN,
        "get_cheapest_window",
        {"duration_minutes": 30},
        blocking=True,
        return_response=True,
    )
    assert response["found"] is True
    assert response["slot_count"] == 2
    assert response["average_price"] == pytest.approx(0.075)


async def test_get_most_expensive_window_returns_maximum_average_slot(
    hass: HomeAssistant, integration_with_prices
) -> None:
    """The mirror service finds the maximum-average window instead."""
    response = await hass.services.async_call(
        DOMAIN,
        "get_most_expensive_window",
        {"duration_minutes": 30},
        blocking=True,
        return_response=True,
    )
    assert response["found"] is True
    assert response["slot_count"] == 2
    # Highest pair: (0.05 + 0.40) / 2 = 0.225
    assert response["average_price"] == pytest.approx(0.225)


async def test_get_cheapest_window_without_entry_raises(
    hass: HomeAssistant,
) -> None:
    """Calling the service with no integration configured raises a clear error."""
    # Need to register the service even without an entry — invoke setup
    from custom_components.onekommafive.services import async_setup_services

    async_setup_services(hass)

    with pytest.raises(HomeAssistantError, match="No 1KOMMA5° integration configured"):
        await hass.services.async_call(
            DOMAIN,
            "get_cheapest_window",
            {"duration_minutes": 30},
            blocking=True,
            return_response=True,
        )


async def test_get_cheapest_window_validation_rejects_short_duration(
    hass: HomeAssistant, integration_with_prices
) -> None:
    """duration_minutes below the 15-min floor is rejected by voluptuous."""
    import voluptuous as vol

    with pytest.raises((vol.Invalid, vol.MultipleInvalid)):
        await hass.services.async_call(
            DOMAIN,
            "get_cheapest_window",
            {"duration_minutes": 5},
            blocking=True,
            return_response=True,
        )
