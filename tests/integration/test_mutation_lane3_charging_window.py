"""Adversarial assertions targeting mutmut survivors in the charging-window pair.

Lane-3 of the mutation-score push: targets the two
`OneKomma5CheapestChargingWindow[Tomorrow]Sensor` methods on commit
`d24d030` — `_refresh_window` on both sensors plus `_restore_window_from_state`
on the today sensor (19 survivors total). Each test is annotated with the
specific mutmut mutation number(s) it kills.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

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


def _empty_market_prices() -> MagicMock:
    """MarketPrices mock whose slot dict is empty — forecast evaluates to []."""
    return MagicMock(
        prices_with_grid_costs_and_vat={},
        prices_with_grid_costs={},
        average_price_all_in=None,
        lowest_price_all_in=None,
        highest_price_all_in=None,
    )


async def _setup(
    hass: HomeAssistant,
    system: MagicMock,
    *,
    unique_id: str = "sys-1",
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data={
            CONF_USERNAME: "u@x.de",
            CONF_PASSWORD: "pw",
            CONF_SYSTEM_ID: unique_id,
        },
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


def _today_state(hass: HomeAssistant):
    for s in hass.states.async_all("sensor"):
        if s.entity_id.endswith("_cheapest_charging_window_today"):
            return s
    raise AssertionError("today sensor not registered")


def _tomorrow_state(hass: HomeAssistant):
    for s in hass.states.async_all("sensor"):
        if s.entity_id.endswith("_cheapest_charging_window_tomorrow"):
            return s
    raise AssertionError("tomorrow sensor not registered")


# ----------------------------------------------------------------------------
# _refresh_window — empty-forecast short-circuit (today mut_5, tomorrow mut_2)
# ----------------------------------------------------------------------------


class TestRefreshWindowEmptyForecast:
    """`if data is None or not forecast: return` short-circuit must survive both
    an empty slot dict AND a missing data payload (mut_5 / mut_2 flip `or` →
    `and`, which would evaluate `None.forecast` and crash)."""

    async def test_today_sensor_handles_empty_forecast(
        self, hass: HomeAssistant, mock_system_factory
    ) -> None:
        system = mock_system_factory(prices=_empty_market_prices())
        await _setup(hass, system)
        state = _today_state(hass)
        # Empty forecast → sensor stays unknown, no crash
        assert state.state == "unknown"

    async def test_tomorrow_sensor_handles_empty_forecast(
        self, hass: HomeAssistant, mock_system_factory
    ) -> None:
        system = mock_system_factory(prices=_empty_market_prices())
        await _setup(hass, system)
        state = _tomorrow_state(hass)
        assert state.state == "unknown"


# ----------------------------------------------------------------------------
# today _refresh_window — bounds (mut_25 earliest_start, mut_29 arg swap)
# ----------------------------------------------------------------------------


class TestTodayRefreshWindowBounds:
    """`earliest_start=now` is a hard floor; `latest_end=end_of_today` a hard
    ceiling. Argument-swap and None-default mutations would quietly accept
    slots outside the day."""

    async def test_today_sensor_ignores_slot_entirely_before_now(
        self, hass: HomeAssistant, mock_system_factory, freezer
    ) -> None:
        """mut_25 (`earliest_start=None`) would accept a slot in the past.
        Original: skip and leave the sensor unknown."""
        freezer.move_to("2026-06-15T20:00:00+00:00")
        base = datetime.datetime(2026, 6, 15, 10, 15, tzinfo=datetime.UTC)
        slot = datetime.timedelta(minutes=15)
        # Four cheap slots ending 10:30-11:15 UTC — all before now=20:00.
        prices = {base + slot * i: 0.10 for i in range(4)}
        system = mock_system_factory(prices=_market_prices(prices))
        await _setup(hass, system)
        state = _today_state(hass)
        assert state.state == "unknown"

    async def test_today_sensor_picks_window_in_valid_range(
        self, hass: HomeAssistant, mock_system_factory, freezer
    ) -> None:
        """mut_29 (`earliest_start=latest_end`) would make the range empty
        and lock in no window. Original: pick the obvious cheap block."""
        freezer.move_to("2026-06-15T12:00:00+00:00")
        base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
        slot = datetime.timedelta(minutes=15)
        prices = {
            base + slot * (i + 1): (0.10 if i in (8, 9, 10, 11) else 0.50)
            for i in range(16)
        }
        system = mock_system_factory(prices=_market_prices(prices))
        await _setup(hass, system)
        state = _today_state(hass)
        # mut_29 would leave state == "unknown"; original locks the 14:15 start
        assert state.state != "unknown"
        assert state.attributes["average_price"] == 0.10


# ----------------------------------------------------------------------------
# today _restore_window_from_state — slot_count fallback + attribute lookup
# ----------------------------------------------------------------------------


class TestRestoreWindowSlotCountMismatch:
    """`slot_count` attribute lookup + fallback branches (mut_11/12/14/15/16/17)."""

    async def _setup_with_restored(
        self,
        hass: HomeAssistant,
        mock_system_factory,
        freezer,
        *,
        restored_attrs: dict,
    ) -> None:
        freezer.move_to("2026-06-15T12:00:00+00:00")
        base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
        slot = datetime.timedelta(minutes=15)
        prices = {
            base + slot * (i + 1): (0.10 if i in (0, 1, 2, 3) else 0.50)
            for i in range(16)
        }
        mock_restore_cache(
            hass,
            (
                State(
                    "sensor.test_home_cheapest_charging_window_today",
                    "2026-06-15T14:15:00+00:00",
                    attributes=restored_attrs,
                ),
            ),
        )
        system = mock_system_factory(prices=_market_prices(prices))
        await _setup(hass, system, unique_id="sys-restore")

    async def test_mismatched_slot_count_discards_restored_window(
        self, hass: HomeAssistant, mock_system_factory, freezer
    ) -> None:
        """mut_11/15/16 — if the attribute lookup is broken (key renamed or
        set to None), the comparison ``slot_count != self._slot_count`` would
        always compare the fallback against itself and keep the restored
        window. Original: discard when the saved count differs."""
        await self._setup_with_restored(
            hass,
            mock_system_factory,
            freezer,
            restored_attrs={
                "start": "2026-06-15T14:15:00+00:00",
                "end": "2026-06-15T15:15:00+00:00",
                "average_price": 0.10,
                "duration_minutes": 60,
                "slot_count": 8,  # options flow is 60 min = 4 slots; mismatch
            },
        )
        state = _today_state(hass)
        # mismatch → restore discarded → the sensor re-picks the fresh
        # cheapest 4-slot window (slots 0-3, start 12:15).
        assert state.state == "2026-06-15T12:15:00+00:00"
        assert state.attributes["slot_count"] == 4

    async def test_matching_slot_count_restores_window(
        self, hass: HomeAssistant, mock_system_factory, freezer
    ) -> None:
        """Positive case: a correctly-saved slot_count must round-trip.
        mut_12/14 (default swapped to None) would turn ``int(None)`` into a
        TypeError, caught by the except, and return None."""
        await self._setup_with_restored(
            hass,
            mock_system_factory,
            freezer,
            restored_attrs={
                "start": "2026-06-15T14:15:00+00:00",
                "end": "2026-06-15T15:15:00+00:00",
                "average_price": 0.10,
                "duration_minutes": 60,
                "slot_count": 4,
            },
        )
        state = _today_state(hass)
        assert state.state == "2026-06-15T14:15:00+00:00"
        assert state.attributes["slot_count"] == 4

    async def test_missing_end_discards_restored_window(
        self, hass: HomeAssistant, mock_system_factory, freezer
    ) -> None:
        """mut_17 flips the `end` / `avg_price` guard from `or` to `and`:
        with `end_iso` missing but `avg_price` present, the mutation would
        continue instead of bailing — the restore would then try to parse
        the empty end and crash."""
        await self._setup_with_restored(
            hass,
            mock_system_factory,
            freezer,
            restored_attrs={
                "start": "2026-06-15T14:15:00+00:00",
                # end deliberately missing
                "average_price": 0.10,
                "duration_minutes": 60,
                "slot_count": 4,
            },
        )
        state = _today_state(hass)
        # Restore is discarded → sensor falls back to the fresh pick (12:15).
        assert state.state == "2026-06-15T12:15:00+00:00"


# ----------------------------------------------------------------------------
# tomorrow _refresh_window — end-of-tomorrow bound (mut_15 days=2, mut_22/26)
# ----------------------------------------------------------------------------


class TestTomorrowRefreshWindowBounds:
    """`end_of_tomorrow = start_of_tomorrow + 1 day − 1 µs` sets the ceiling.

    mut_15 would widen the ceiling to +2 days (day-after-tomorrow). mut_22 /
    mut_26 strip `latest_end` entirely, letting the search run unbounded —
    both would accept a slot in the day after tomorrow if it is the cheapest."""

    async def test_tomorrow_sensor_rejects_slot_in_day_after_tomorrow(
        self, hass: HomeAssistant, mock_system_factory, freezer
    ) -> None:
        freezer.move_to("2026-06-15T12:00:00+00:00")
        # Insert the cheapest 60-min block into day-after-tomorrow (06-17).
        base = datetime.datetime(2026, 6, 17, 2, 0, tzinfo=datetime.UTC)
        slot = datetime.timedelta(minutes=15)
        prices = {
            base + slot * i: 0.05  # very cheap
            for i in range(4)
        }
        # Add a less-cheap but valid block in tomorrow (06-16).
        tomorrow_base = datetime.datetime(2026, 6, 16, 10, 0, tzinfo=datetime.UTC)
        prices.update({tomorrow_base + slot * i: 0.20 for i in range(4)})
        system = mock_system_factory(prices=_market_prices(prices))
        await _setup(hass, system)
        state = _tomorrow_state(hass)
        attrs = state.attributes
        # The sensor must pick a tomorrow window, not the cheaper day-after one.
        assert attrs["average_price"] == 0.20
