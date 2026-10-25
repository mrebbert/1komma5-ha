"""Tier-2 tests for the AI-decisions calendar platform (v0.1.73).

Covers:
- the percentile / phase-reconstruction / proxy-block pure helpers;
- end-to-end entity registration and the `event` property via the
  shared `setup_integration` fixture;
- the Recorder-history → CalendarEvent mapping with a stubbed
  `get_significant_states`.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.calendar import CalendarEvent
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from custom_components.onekommafive import calendar as calendar_module
from custom_components.onekommafive.calendar import (
    PROXY_CHEAP_KEY,
    PROXY_EXPENSIVE_KEY,
    _percentile,
    _proxy_blocks,
    _quantize_and_merge,
    _reconstruct_phases,
    _snap_ceil,
    _snap_floor,
    _split_at_dst_transition,
)
from custom_components.onekommafive.const import DOMAIN

UTC = dt.UTC


def _state(entity_id: str, value: str, when: dt.datetime) -> State:
    """Build a minimal recorder-shaped State for phase reconstruction."""
    s = State(entity_id, value)
    s.last_changed = when
    return s


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_percentile_single_value_returns_it() -> None:
    assert _percentile([0.21], 0.5) == 0.21


def test_percentile_linear_interpolation() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(values, 0.0) == 1.0
    assert _percentile(values, 1.0) == 5.0
    assert _percentile(values, 0.5) == 3.0
    # 0.25 of 4 positions = 1.0 → interpolates between index 1 and 2
    assert _percentile(values, 0.25) == pytest.approx(2.0)


def test_percentile_empty_raises() -> None:
    with pytest.raises(ValueError, match="requires at least one value"):
        _percentile([], 0.5)


def test_snap_floor_aligns_to_15min() -> None:
    t = dt.datetime(2026, 10, 25, 11, 3, 19, 967531, tzinfo=UTC)
    assert _snap_floor(t) == dt.datetime(2026, 10, 25, 11, 0, 0, tzinfo=UTC)


def test_snap_ceil_already_aligned_stays_put() -> None:
    t = dt.datetime(2026, 10, 25, 11, 0, 0, tzinfo=UTC)
    assert _snap_ceil(t) == t


def test_snap_ceil_rounds_up() -> None:
    t = dt.datetime(2026, 10, 25, 11, 3, 19, 967531, tzinfo=UTC)
    assert _snap_ceil(t) == dt.datetime(2026, 10, 25, 11, 15, 0, tzinfo=UTC)


def test_quantize_merges_sub_slot_jitter() -> None:
    t0 = dt.datetime(2026, 10, 25, 10, 45, 0, 393307, tzinfo=UTC)
    t1 = dt.datetime(2026, 10, 25, 11, 0, 0, 371087, tzinfo=UTC)
    t2 = dt.datetime(2026, 10, 25, 11, 3, 19, 967531, tzinfo=UTC)
    t3 = dt.datetime(2026, 10, 25, 11, 15, 0, 370092, tzinfo=UTC)
    # Two phases of the same decision with microsecond gaps on slot borders
    # should merge into one 10:45 → 11:15 block.
    merged = _quantize_and_merge([(t0, t1), (t2, t3)])
    assert merged == [
        (
            dt.datetime(2026, 10, 25, 10, 45, tzinfo=UTC),
            dt.datetime(2026, 10, 25, 11, 15, tzinfo=UTC),
        )
    ]


def test_quantize_drops_zero_duration_slot() -> None:
    t = dt.datetime(2026, 10, 25, 11, 0, 0, tzinfo=UTC)
    assert _quantize_and_merge([(t, t)]) == []


@pytest.fixture
def _berlin_tz():
    """Temporarily switch HA's default timezone to Europe/Berlin."""
    from zoneinfo import ZoneInfo

    from homeassistant.util import dt as dt_util_mod

    original = dt_util_mod.DEFAULT_TIME_ZONE
    dt_util_mod.set_default_time_zone(ZoneInfo("Europe/Berlin"))
    try:
        yield
    finally:
        dt_util_mod.set_default_time_zone(original)


def test_split_at_dst_transition_splits_fall_back(_berlin_tz) -> None:
    # Phase that straddles the Europe/Berlin fall-back (UTC 01:00).
    start = dt.datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # CEST 02:30
    end = dt.datetime(2026, 10, 25, 1, 30, tzinfo=UTC)  # CET 02:30
    parts = _split_at_dst_transition(start, end)
    # Expect two sub-phases, each entirely in one UTC offset. The ambiguous
    # slot around the transition is dropped (HA validator cannot represent
    # mixed-offset events).
    assert len(parts) == 2
    for sub_start, sub_end in parts:
        assert sub_start.astimezone(dt.UTC).minute % 15 == 0
        assert sub_end.astimezone(dt.UTC).minute % 15 == 0
        assert sub_end > sub_start


def test_split_at_dst_transition_no_split_outside_transition(_berlin_tz) -> None:
    start = dt.datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    end = dt.datetime(2026, 10, 25, 12, 30, tzinfo=UTC)
    assert _split_at_dst_transition(start, end) == [(start, end)]


def test_reconstruct_phases_merges_consecutive_on_states() -> None:
    entity_id = "binary_sensor.x"
    t0 = dt.datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
    states = [
        _state(entity_id, "on", t0),
        _state(entity_id, "on", t0 + dt.timedelta(minutes=15)),
        _state(entity_id, "on", t0 + dt.timedelta(minutes=30)),
        _state(entity_id, "off", t0 + dt.timedelta(minutes=45)),
    ]
    phases = _reconstruct_phases(states, t0 + dt.timedelta(hours=1))
    assert phases == [(t0, t0 + dt.timedelta(minutes=45))]


def test_reconstruct_phases_two_separate_on_blocks() -> None:
    entity_id = "binary_sensor.x"
    t0 = dt.datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
    states = [
        _state(entity_id, "on", t0),
        _state(entity_id, "off", t0 + dt.timedelta(minutes=15)),
        _state(entity_id, "on", t0 + dt.timedelta(minutes=30)),
        _state(entity_id, "off", t0 + dt.timedelta(minutes=45)),
    ]
    phases = _reconstruct_phases(states, t0 + dt.timedelta(hours=1))
    assert phases == [
        (t0, t0 + dt.timedelta(minutes=15)),
        (t0 + dt.timedelta(minutes=30), t0 + dt.timedelta(minutes=45)),
    ]


def test_reconstruct_phases_trailing_on_clamps_to_window_end() -> None:
    entity_id = "binary_sensor.x"
    t0 = dt.datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
    window_end = t0 + dt.timedelta(hours=1)
    states = [_state(entity_id, "on", t0)]
    phases = _reconstruct_phases(states, window_end)
    assert phases == [(t0, window_end)]


def test_reconstruct_phases_ignores_leading_off() -> None:
    entity_id = "binary_sensor.x"
    t0 = dt.datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
    states = [
        _state(entity_id, "off", t0),
        _state(entity_id, "on", t0 + dt.timedelta(minutes=15)),
        _state(entity_id, "off", t0 + dt.timedelta(minutes=30)),
    ]
    phases = _reconstruct_phases(states, t0 + dt.timedelta(hours=1))
    assert phases == [(t0 + dt.timedelta(minutes=15), t0 + dt.timedelta(minutes=30))]


def _slot(start: dt.datetime, price: float) -> dict[str, object]:
    return {
        "start": start.isoformat(),
        "end": (start + dt.timedelta(minutes=15)).isoformat(),
        "price": price,
    }


def test_proxy_blocks_cheap_and_expensive_runs() -> None:
    t0 = dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
    # 10 slots: four cheap, two mid, four expensive — expect two blocks.
    prices = [0.10, 0.11, 0.12, 0.13, 0.20, 0.21, 0.40, 0.41, 0.42, 0.43]
    forecast = [
        _slot(t0 + dt.timedelta(minutes=15 * i), p) for i, p in enumerate(prices)
    ]
    blocks = _proxy_blocks(forecast, t0, t0 + dt.timedelta(hours=4))
    assert len(blocks) == 2
    cheap, expensive = blocks
    assert cheap[0] == PROXY_CHEAP_KEY
    assert expensive[0] == PROXY_EXPENSIVE_KEY
    # cheap block covers at least the lowest two slots
    assert cheap[1] == t0
    assert cheap[2] >= t0 + dt.timedelta(minutes=30)
    # expensive block runs to the very end of the forecast window
    assert expensive[2] == t0 + dt.timedelta(minutes=15 * 10)


def test_proxy_blocks_drops_single_slot_blocks_as_noise() -> None:
    t0 = dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
    # cheap, mid, cheap, mid, cheap — three isolated cheap slots, none ≥ 2
    prices = [0.10, 0.20, 0.11, 0.20, 0.12, 0.20, 0.20, 0.40, 0.41]
    forecast = [
        _slot(t0 + dt.timedelta(minutes=15 * i), p) for i, p in enumerate(prices)
    ]
    blocks = _proxy_blocks(forecast, t0, t0 + dt.timedelta(hours=4))
    # the single expensive run (two slots at the end) survives, each cheap
    # slot stands alone → no cheap block.
    assert all(b[0] != PROXY_CHEAP_KEY for b in blocks)
    assert any(b[0] == PROXY_EXPENSIVE_KEY for b in blocks)


def test_proxy_blocks_flat_forecast_returns_nothing() -> None:
    t0 = dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
    forecast = [_slot(t0 + dt.timedelta(minutes=15 * i), 0.25) for i in range(6)]
    assert _proxy_blocks(forecast, t0, t0 + dt.timedelta(hours=2)) == []


def test_proxy_blocks_empty_forecast() -> None:
    t0 = dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
    assert _proxy_blocks([], t0, t0 + dt.timedelta(hours=1)) == []


def test_proxy_blocks_respects_window_bounds() -> None:
    t0 = dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
    prices = [0.10, 0.11, 0.12, 0.40, 0.41, 0.42]
    forecast = [
        _slot(t0 + dt.timedelta(minutes=15 * i), p) for i, p in enumerate(prices)
    ]
    # Window only covers the last four slots (14:30 → 15:30).
    window_start = t0 + dt.timedelta(minutes=30)
    window_end = t0 + dt.timedelta(minutes=15 * 6)
    blocks = _proxy_blocks(forecast, window_start, window_end)
    # Classification uses the full forecast's percentiles, so slot[2]=0.12
    # is still "cheap" relative to the whole distribution.
    assert all(b[1] >= window_start for b in blocks)
    assert all(b[2] <= window_end for b in blocks)


# ---------------------------------------------------------------------------
# Entity-level integration
# ---------------------------------------------------------------------------


def _price_forecast(
    now: dt.datetime, slots: int, base: float
) -> list[dict[str, object]]:
    """Build a sortable price forecast with a cheap tail and expensive head."""
    out: list[dict[str, object]] = []
    for i in range(slots):
        start = now + dt.timedelta(minutes=15 * i)
        price = base + (0.5 - (i / max(slots - 1, 1))) * 0.3
        out.append(_slot(start, price))
    return out


async def test_calendar_entity_registers(
    hass: HomeAssistant, mock_system_factory, setup_integration
) -> None:
    """The calendar entity is registered on first setup."""
    system = mock_system_factory(system_id="sys-1", optimizations=MagicMock(events=[]))
    await setup_integration(system)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "calendar", DOMAIN, "sys-1_ai_decisions_calendar"
    )
    assert entity_id is not None


async def test_calendar_event_property_reflects_active_decision(
    hass: HomeAssistant, mock_system_factory, setup_integration, freezer
) -> None:
    """`event` returns the currently active decision from the coordinator."""
    freezer.move_to("2026-05-14T12:07:00+00:00")
    event = MagicMock(
        asset="BATTERY",
        decision="BATTERY_NO_CHARGE",
        from_time="2026-05-14T12:00:00+00:00",
        to_time="2026-05-14T12:15:00+00:00",
        end_time="2026-05-14T12:15:00+00:00",
    )
    optimizations = MagicMock(events=[event])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await setup_integration(system)

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "calendar", DOMAIN, "sys-1_ai_decisions_calendar"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    # A calendar entity reports "on" when `event` is non-None.
    assert state.state == "on"
    message = state.attributes.get("message", "")
    # Translated name differs per HA language; both DE and EN strings match
    # the "AI: <battery charge lock>" idiom.
    assert "charge lock" in message.lower() or "ladesperre" in message.lower()


async def test_calendar_async_get_events_history(
    hass: HomeAssistant, mock_system_factory, setup_integration
) -> None:
    """Historical phases from the Recorder are reconstructed into events."""
    system = mock_system_factory(system_id="sys-1", optimizations=MagicMock(events=[]))
    await setup_integration(system)
    now = dt.datetime.now(UTC)
    history_start = now - dt.timedelta(hours=4)

    battery_no_charge_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, "sys-1_optimization_battery_no_charge"
    )
    assert battery_no_charge_id is not None
    phase_start = now - dt.timedelta(hours=2)
    phase_end = now - dt.timedelta(hours=1)
    stub_states = {
        battery_no_charge_id: [
            _state(battery_no_charge_id, "on", phase_start),
            _state(battery_no_charge_id, "off", phase_end),
        ]
    }

    with (
        patch.object(
            calendar_module,
            "get_significant_states",
            return_value=stub_states,
        ),
        patch.object(calendar_module, "get_instance") as get_instance_mock,
    ):
        get_instance_mock.return_value.async_add_executor_job = AsyncMock(
            side_effect=lambda fn, *a, **kw: fn(*a, **kw)
        )
        events = await hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": "calendar.test_home_ai_decisions_calendar",
                "start_date_time": history_start.isoformat(),
                "end_date_time": now.isoformat(),
            },
            blocking=True,
            return_response=True,
        )
    reply = events["calendar.test_home_ai_decisions_calendar"]  # type: ignore[index]
    returned = reply["events"]
    assert len(returned) == 1
    # Events are snapped to 15-min slot boundaries; start floors, end ceils.
    from custom_components.onekommafive.calendar import _snap_ceil, _snap_floor

    assert returned[0]["start"] == _snap_floor(phase_start).isoformat()
    assert returned[0]["end"] == _snap_ceil(phase_end).isoformat()
    # Stable machine-readable match key for blueprints (language-independent).
    assert returned[0]["description"] == "optimization_battery_no_charge"


async def test_calendar_recorder_failure_degrades_gracefully(
    hass: HomeAssistant, mock_system_factory, setup_integration, caplog
) -> None:
    """Recorder exceptions skip history but still return proxy events."""
    import logging

    system = mock_system_factory(system_id="sys-1", optimizations=MagicMock(events=[]))
    entry = await setup_integration(system)
    now = dt.datetime.now(UTC)
    forecast = _price_forecast(now + dt.timedelta(minutes=5), 12, 0.20)
    entry.runtime_data.price_coordinator.data = MagicMock(forecast=forecast)

    with (
        patch.object(
            calendar_module,
            "get_significant_states",
            side_effect=RuntimeError("recorder exploded"),
        ),
        patch.object(calendar_module, "get_instance") as get_instance_mock,
        caplog.at_level(
            logging.WARNING, logger="custom_components.onekommafive.calendar"
        ),
    ):
        get_instance_mock.return_value.async_add_executor_job = AsyncMock(
            side_effect=lambda fn, *a, **kw: fn(*a, **kw)
        )
        events = await hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": "calendar.test_home_ai_decisions_calendar",
                "start_date_time": (now - dt.timedelta(hours=2)).isoformat(),
                "end_date_time": (now + dt.timedelta(hours=4)).isoformat(),
            },
            blocking=True,
            return_response=True,
        )
    reply = events["calendar.test_home_ai_decisions_calendar"]  # type: ignore[index]
    returned = reply["events"]
    # History collapses to zero, but proxy events still materialize.
    assert returned, "expected proxy events despite recorder failure"
    assert all(e["description"] in {"proxy_cheap", "proxy_expensive"} for e in returned)
    assert "Recorder history fetch failed" in caplog.text


async def test_calendar_async_get_events_proxy(
    hass: HomeAssistant, mock_system_factory, setup_integration
) -> None:
    """Future proxy events materialise from the price forecast."""
    system = mock_system_factory(system_id="sys-1", optimizations=MagicMock(events=[]))
    entry = await setup_integration(system)
    now = dt.datetime.now(UTC)

    forecast = _price_forecast(now + dt.timedelta(minutes=5), 12, 0.20)
    entry.runtime_data.price_coordinator.data = MagicMock(forecast=forecast)

    with (
        patch.object(calendar_module, "get_significant_states", return_value={}),
        patch.object(calendar_module, "get_instance") as get_instance_mock,
    ):
        get_instance_mock.return_value.async_add_executor_job = AsyncMock(
            side_effect=lambda fn, *a, **kw: fn(*a, **kw)
        )
        events = await hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": "calendar.test_home_ai_decisions_calendar",
                "start_date_time": now.isoformat(),
                "end_date_time": (now + dt.timedelta(hours=6)).isoformat(),
            },
            blocking=True,
            return_response=True,
        )
    reply = events["calendar.test_home_ai_decisions_calendar"]  # type: ignore[index]
    returned = reply["events"]
    assert returned, "expected at least one proxy event from the forecast"
    assert all(e["start"] >= now.isoformat() for e in returned)
    # Each proxy event carries a stable description key for blueprint matching.
    assert all(e["description"] in {"proxy_cheap", "proxy_expensive"} for e in returned)


def test_calendar_event_wraps_matching_spec_label() -> None:
    """CalendarEvent carries the translated spec label as its summary."""
    now = dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
    event = CalendarEvent(
        start=now,
        end=now + dt.timedelta(minutes=15),
        summary="AI: Batterie-Ladesperre",
    )
    assert "Ladesperre" in event.summary
