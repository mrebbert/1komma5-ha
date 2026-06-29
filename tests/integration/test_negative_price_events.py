"""Tier-2 tests for the negative-price bus events."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from homeassistant.core import Event, HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
    EVENT_NEGATIVE_PRICE_ENDED,
    EVENT_NEGATIVE_PRICE_STARTED,
)


def _market_prices(slot_prices: dict[datetime.datetime, float]) -> MagicMock:
    """Build a MarketPrices mock from slot-END datetime → price."""
    iso = {
        ts.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z"): price
        for ts, price in slot_prices.items()
    }
    return MagicMock(
        prices_with_grid_costs_and_vat=iso,
        prices_with_grid_costs=iso,
        average_price_all_in=sum(slot_prices.values()) / max(len(slot_prices), 1),
        lowest_price_all_in=min(slot_prices.values()) if slot_prices else None,
        highest_price_all_in=max(slot_prices.values()) if slot_prices else None,
    )


def _capture_events(hass: HomeAssistant, event_type: str) -> list[Event]:
    captured: list[Event] = []
    hass.bus.async_listen(event_type, lambda e: captured.append(e))
    return captured


async def _setup_with_prices(
    hass: HomeAssistant,
    mock_system_factory,
    *,
    prices: dict[datetime.datetime, float],
    system_id: str,
) -> MockConfigEntry:
    system = mock_system_factory(system_id=system_id, prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=system_id,
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: system_id},
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


async def test_first_refresh_does_not_fire_events(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-15T12:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    prices = {base + slot * i: 0.20 for i in range(16)}

    started = _capture_events(hass, EVENT_NEGATIVE_PRICE_STARTED)
    ended = _capture_events(hass, EVENT_NEGATIVE_PRICE_ENDED)

    await _setup_with_prices(hass, mock_system_factory, prices=prices, system_id="sys-prime")
    assert started == []
    assert ended == []


async def test_positive_to_negative_fires_started(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-15T12:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    prices = {base + slot * i: 0.20 for i in range(16)}

    entry = await _setup_with_prices(
        hass, mock_system_factory, prices=prices, system_id="sys-edge-down"
    )
    started = _capture_events(hass, EVENT_NEGATIVE_PRICE_STARTED)
    ended = _capture_events(hass, EVENT_NEGATIVE_PRICE_ENDED)

    freezer.move_to("2026-06-15T13:00:00+00:00")
    new_base = datetime.datetime(2026, 6, 15, 13, 15, tzinfo=datetime.UTC)
    negative_prices = {new_base + slot * i: -0.05 for i in range(16)}
    entry.runtime_data.system.get_prices.return_value = _market_prices(negative_prices)

    await entry.runtime_data.price_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(started) == 1
    assert ended == []
    assert started[0].data["price"] == -0.05
    assert started[0].data["system_id"] == "sys-edge-down"


async def test_negative_to_positive_fires_ended(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-15T12:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    negative_prices = {base + slot * i: -0.05 for i in range(16)}

    entry = await _setup_with_prices(
        hass, mock_system_factory, prices=negative_prices, system_id="sys-edge-up"
    )
    started = _capture_events(hass, EVENT_NEGATIVE_PRICE_STARTED)
    ended = _capture_events(hass, EVENT_NEGATIVE_PRICE_ENDED)

    freezer.move_to("2026-06-15T13:00:00+00:00")
    new_base = datetime.datetime(2026, 6, 15, 13, 15, tzinfo=datetime.UTC)
    positive_prices = {new_base + slot * i: 0.15 for i in range(16)}
    entry.runtime_data.system.get_prices.return_value = _market_prices(positive_prices)

    await entry.runtime_data.price_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(ended) == 1
    assert started == []
    assert ended[0].data["price"] == 0.15


async def test_no_transition_no_event(hass: HomeAssistant, mock_system_factory, freezer) -> None:
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-15T12:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    prices = {base + slot * i: 0.20 for i in range(16)}

    entry = await _setup_with_prices(
        hass, mock_system_factory, prices=prices, system_id="sys-no-edge"
    )
    started = _capture_events(hass, EVENT_NEGATIVE_PRICE_STARTED)
    ended = _capture_events(hass, EVENT_NEGATIVE_PRICE_ENDED)

    freezer.move_to("2026-06-15T13:00:00+00:00")
    new_base = datetime.datetime(2026, 6, 15, 13, 15, tzinfo=datetime.UTC)
    same_sign_prices = {new_base + slot * i: 0.18 for i in range(16)}
    entry.runtime_data.system.get_prices.return_value = _market_prices(same_sign_prices)

    await entry.runtime_data.price_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert started == []
    assert ended == []
