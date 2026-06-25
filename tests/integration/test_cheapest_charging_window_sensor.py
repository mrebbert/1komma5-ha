"""Tier-2 tests for the cheapest-charging-window sensor.

The sensor surfaces today's cheapest 60-min slot as a timestamp + the
window details on attributes. It must respect the "today, local time"
boundary so users can wire it as an automation trigger without
accidentally firing at midnight on yesterday's window.
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


def _market_prices(slot_prices: dict[datetime.datetime, float]) -> MagicMock:
    """Build a MarketPrices mock from slot-END datetime → price."""
    iso = {
        ts.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z"): price
        for ts, price in slot_prices.items()
    }
    return MagicMock(
        prices_with_grid_costs_and_vat=iso,
        prices_with_grid_costs=iso,
        average_price_all_in=(sum(slot_prices.values()) / len(slot_prices))
        if slot_prices
        else None,
        lowest_price_all_in=min(slot_prices.values()) if slot_prices else None,
        highest_price_all_in=max(slot_prices.values()) if slot_prices else None,
    )


def _cheapest_window_state(hass: HomeAssistant):
    for state in hass.states.async_all("sensor"):
        if state.entity_id.endswith("_cheapest_charging_window_today"):
            return state
    raise AssertionError("cheapest charging window sensor not registered")


async def test_cheapest_window_picks_lowest_four_consecutive_slots(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """With a clear price minimum in one 60-min block, state == start of that block."""
    # 12:00 UTC — well into the day so end-of-today gives plenty of headroom.
    freezer.move_to("2026-06-15T12:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    # End-time → price. Slots 8-11 form the cheapest 60-min run.
    prices: dict[datetime.datetime, float] = {}
    for i in range(16):
        end = base + slot * (i + 1)
        prices[end] = 0.50 if i not in (8, 9, 10, 11) else 0.10

    system = mock_system_factory(prices=_market_prices(prices))
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

    state = _cheapest_window_state(hass)
    # Slot 8 is the first cheap slot — its start is base + 8*15min (end of slot 7).
    expected_start = base + slot * 8
    expected_start_iso = expected_start.isoformat()
    assert state.state == expected_start_iso
    assert state.attributes["average_price"] == 0.10
    assert state.attributes["duration_minutes"] == 60
    assert state.attributes["slot_count"] == 4
    assert state.attributes["end"] == (expected_start + slot * 4).isoformat()


async def test_cheapest_window_returns_unknown_when_no_forecast_today(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """Empty forecast → state is unknown (None), attributes are absent."""
    freezer.move_to("2026-06-15T12:00:00+00:00")
    system = mock_system_factory(prices=_market_prices({}))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-2",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-2"},
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

    state = _cheapest_window_state(hass)
    assert state.state in ("unknown", "unavailable")
    assert "average_price" not in state.attributes


async def test_cheapest_window_clips_at_end_of_today_local(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """Slots whose window-end falls past today midnight (local) must NOT be eligible.

    HA test default timezone is UTC, so ``end-of-today-local`` == ``2026-06-15
    23:59:59 UTC``. Only windows whose end ≤ that boundary may be chosen.
    """
    # Sensor's "today" boundary is in HA-local time. Pin HA timezone to UTC so
    # this test stays deterministic regardless of host timezone.
    await hass.config.async_set_time_zone("UTC")
    # now = 22:30 UTC → today has 5 quarter-hour slots left (ending 22:45..23:45).
    freezer.move_to("2026-06-15T22:30:00+00:00")
    slot = datetime.timedelta(minutes=15)
    base = datetime.datetime(2026, 6, 15, 22, 30, tzinfo=datetime.UTC)

    prices: dict[datetime.datetime, float] = {}
    # Today-eligible slots — five slots ending 22:45..23:45 at €0.30
    for i in range(5):
        prices[base + slot * (i + 1)] = 0.30
    # Tomorrow slots at €0.05 — must be ignored because no 60-min window
    # spanning them can end by 23:59:59 UTC today.
    for i in range(5, 9):
        prices[base + slot * (i + 1)] = 0.05

    system = mock_system_factory(prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-3",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-3"},
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

    state = _cheapest_window_state(hass)
    # All windows that fit today consist of 0.30 slots — sensor must pick one.
    assert state.attributes["average_price"] == 0.30
    end_dt = datetime.datetime.fromisoformat(state.attributes["end"])
    assert end_dt <= datetime.datetime(2026, 6, 15, 23, 59, 59, 999999, tzinfo=datetime.UTC)
