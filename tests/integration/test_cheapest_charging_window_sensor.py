"""Tier-2 tests for the cheapest-charging-window sensor.

The sensor surfaces today's cheapest 60-min slot as a timestamp + the
window details on attributes. It must respect the "today, local time"
boundary so users can wire it as an automation trigger without
accidentally firing at midnight on yesterday's window.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

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


async def test_cheapest_window_locks_in_across_time_advance(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """Once chosen, the window is held — time moving on does NOT re-pick it.

    Regression test for the v0.1.41 bug where the sensor flickered to the
    next 15-min slot at every quarter-hour boundary.
    """
    freezer.move_to("2026-06-15T12:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    # Slots 8-11 form the only cheap 60-min block; everything else is flat.
    prices = {base + slot * (i + 1): (0.10 if i in (8, 9, 10, 11) else 0.50) for i in range(16)}

    system = mock_system_factory(prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-lock",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-lock"},
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

        initial_start = _cheapest_window_state(hass).state

        # Time advances past several quarter-hour boundaries that USED to
        # cause flicker in v0.1.41.
        freezer.move_to("2026-06-15T13:30:00+00:00")
        await entry.runtime_data.price_coordinator.async_refresh()
        await hass.async_block_till_done()

    state = _cheapest_window_state(hass)
    # Locked-in window persists — same start, still 0.10 € average.
    assert state.state == initial_start
    assert state.attributes["average_price"] == 0.10


async def test_cheapest_window_restores_valid_previous_state(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """A previously-chosen window (end in the future) survives an HA restart.

    Prices changed in the meantime — but the lock-in keeps the original
    pick instead of bouncing to whatever the fresh forecast says is cheapest.
    """
    freezer.move_to("2026-06-15T12:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    # Fresh forecast: slots 0-3 are now the cheapest — but the restored
    # window points elsewhere, so the lock-in must keep the restored pick.
    prices = {base + slot * (i + 1): (0.10 if i in (0, 1, 2, 3) else 0.50) for i in range(16)}

    restored_start = "2026-06-15T14:15:00+00:00"  # slot-8 start
    restored_end = "2026-06-15T15:15:00+00:00"  # slot-12 end
    mock_restore_cache(
        hass,
        (
            State(
                "sensor.test_home_cheapest_charging_window_today",
                restored_start,
                attributes={
                    "start": restored_start,
                    "end": restored_end,
                    "average_price": 0.10,
                    "duration_minutes": 60,
                    "slot_count": 4,
                },
            ),
        ),
    )

    system = mock_system_factory(prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-restore",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-restore"},
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
    assert state.state == restored_start
    assert state.attributes["end"] == restored_end


async def test_cheapest_window_ignores_restored_state_after_expiry(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """If the restored window has already ended, the sensor picks fresh."""
    freezer.move_to("2026-06-15T18:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 18, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    # Slots 0-3 are the only cheap 60-min block in the remaining day.
    prices = {base + slot * (i + 1): (0.10 if i in (0, 1, 2, 3) else 0.50) for i in range(16)}

    # Restored window ended at 11:00 UTC — well before now (18:00 UTC).
    mock_restore_cache(
        hass,
        (
            State(
                "sensor.test_home_cheapest_charging_window_today",
                "2026-06-15T10:00:00+00:00",
                attributes={
                    "start": "2026-06-15T10:00:00+00:00",
                    "end": "2026-06-15T11:00:00+00:00",
                    "average_price": 0.05,
                    "duration_minutes": 60,
                    "slot_count": 4,
                },
            ),
        ),
    )

    system = mock_system_factory(prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-expired",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-expired"},
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
    # Fresh pick — first cheap slot starts at 18:15 (slot-0 start).
    assert state.state == base.isoformat()
    assert state.attributes["average_price"] == 0.10


async def test_cheapest_window_honours_configured_duration(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """A 30-min duration option = 2 slots; the picked window matches."""
    from custom_components.onekommafive.const import CONF_CHARGING_WINDOW_DURATION_MINUTES

    freezer.move_to("2026-06-15T12:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    # End-time → price. Slots 5 + 6 form the cheapest 30-min run.
    prices: dict[datetime.datetime, float] = {}
    for i in range(16):
        end = base + slot * (i + 1)
        prices[end] = 0.50 if i not in (5, 6) else 0.10

    system = mock_system_factory(prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-dur",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-dur"},
        options={CONF_CHARGING_WINDOW_DURATION_MINUTES: 30},
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
    expected_start = base + slot * 5
    assert state.state == expected_start.isoformat()
    assert state.attributes["duration_minutes"] == 30
    assert state.attributes["slot_count"] == 2
    assert state.attributes["end"] == (expected_start + slot * 2).isoformat()


async def test_cheapest_window_reloads_on_options_change(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """Updating the duration via options-flow reloads the entry; sensor picks up the new duration."""
    from custom_components.onekommafive.const import CONF_CHARGING_WINDOW_DURATION_MINUTES

    freezer.move_to("2026-06-15T12:00:00+00:00")
    base = datetime.datetime(2026, 6, 15, 12, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    # 16 slots all priced 0.10 — the picker locks in the earliest n-slot run.
    prices = {base + slot * (i + 1): 0.10 for i in range(16)}

    system = mock_system_factory(prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-reload",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-reload"},
        options={},  # default 60 min
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

        before = _cheapest_window_state(hass)
        assert before.attributes["duration_minutes"] == 60
        assert before.attributes["slot_count"] == 4

        # Trigger the options-update listener — should reload the entry.
        hass.config_entries.async_update_entry(
            entry, options={CONF_CHARGING_WINDOW_DURATION_MINUTES: 90}
        )
        await hass.async_block_till_done()

    after = _cheapest_window_state(hass)
    assert after.attributes["duration_minutes"] == 90
    assert after.attributes["slot_count"] == 6


def _tomorrow_window_state(hass: HomeAssistant):
    for state in hass.states.async_all("sensor"):
        if state.entity_id.endswith("_cheapest_charging_window_tomorrow"):
            return state
    raise AssertionError("cheapest charging window tomorrow sensor not registered")


async def test_tomorrow_window_picks_cheapest_tomorrow_slot(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """Tomorrow-window sensor selects the cheapest 60-min run from tomorrow's slots."""
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-15T22:00:00+00:00")  # Late evening; tomorrow's prices loaded.
    # Tomorrow starts at 2026-06-16T00:00 UTC. Build 16 tomorrow-slots with a min run.
    tomorrow_base = datetime.datetime(2026, 6, 16, 0, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    prices: dict[datetime.datetime, float] = {}
    # 4 today-slots, all expensive, so the today-window picker has data but tomorrow is the cheap one.
    today_base = datetime.datetime(2026, 6, 15, 22, 15, tzinfo=datetime.UTC)
    for i in range(4):
        prices[today_base + slot * i] = 0.90
    # 16 tomorrow-slots; slots 4-7 form the cheapest 60-min block.
    for i in range(16):
        end = tomorrow_base + slot * (i + 1)
        prices[end] = 0.50 if i not in (4, 5, 6, 7) else 0.10

    system = mock_system_factory(prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-tmrw",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-tmrw"},
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

    state = _tomorrow_window_state(hass)
    expected_start = tomorrow_base + slot * 4
    assert state.state == expected_start.isoformat()
    assert state.attributes["duration_minutes"] == 60
    assert state.attributes["slot_count"] == 4
    assert state.attributes["average_price"] == 0.10


async def test_tomorrow_window_unknown_without_tomorrow_forecast(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """Without tomorrow-slots in the forecast the tomorrow sensor stays unknown."""
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to(
        "2026-06-15T08:00:00+00:00"
    )  # Morning — tomorrow's prices typically not yet available.
    today_base = datetime.datetime(2026, 6, 15, 8, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    # Only today-slots, no tomorrow data.
    prices = {today_base + slot * i: 0.20 for i in range(16)}

    system = mock_system_factory(prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-no-tmrw",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-no-tmrw"},
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

    state = _tomorrow_window_state(hass)
    assert state.state in ("unknown", "unavailable")
    assert "average_price" not in state.attributes


async def test_tomorrow_window_honours_configured_duration(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """The tomorrow sensor uses the same options-flow duration as the today twin."""
    from custom_components.onekommafive.const import CONF_CHARGING_WINDOW_DURATION_MINUTES

    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-06-15T22:00:00+00:00")
    tomorrow_base = datetime.datetime(2026, 6, 16, 0, 15, tzinfo=datetime.UTC)
    slot = datetime.timedelta(minutes=15)
    prices: dict[datetime.datetime, float] = {}
    # 30-min option → slots 2 + 3 form the cheapest run.
    for i in range(16):
        end = tomorrow_base + slot * (i + 1)
        prices[end] = 0.50 if i not in (2, 3) else 0.10

    system = mock_system_factory(prices=_market_prices(prices))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-tmrw-30",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-tmrw-30"},
        options={CONF_CHARGING_WINDOW_DURATION_MINUTES: 30},
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

    state = _tomorrow_window_state(hass)
    expected_start = tomorrow_base + slot * 2
    assert state.state == expected_start.isoformat()
    assert state.attributes["duration_minutes"] == 30
    assert state.attributes["slot_count"] == 2
