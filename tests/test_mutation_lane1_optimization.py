"""Adversarial assertions targeting mutmut survivors in three helpers.

Lane-1 of the mutation-score push against the v0.1.67 baseline (Score 74.2 %).
Each test here is written to kill a specific mutmut survivor class — comments
name the mutation numbers from `mutation-results.txt` on commit `66083e4` so
future runs can tell what moved.

Scope:
- `active_optimization_event` (29 survivors)
- `aggregate_optimization_events` (19 survivors)
- `build_forecast` (12 survivors)
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from custom_components.onekommafive.helpers import (
    active_optimization_event,
    aggregate_optimization_events,
    build_forecast,
)


def _at(y: int, m: int, d: int, h: int, mi: int) -> datetime.datetime:
    return datetime.datetime(y, m, d, h, mi, tzinfo=datetime.UTC)


# ----------------------------------------------------------------------------
# active_optimization_event
# ----------------------------------------------------------------------------


@dataclass
class _Event:
    """Full-attribute event stub (asset / from_time / end_time / to_time)."""

    asset: str = "BATTERY"
    from_time: str | None = None
    end_time: str | None = None
    to_time: str | None = None


class _AttrMissingEvent:
    """Event stub that only sets what is explicitly passed — attribute LOOKUP
    on anything else raises AttributeError.

    Kills mutations that drop the ``getattr`` default (mut_5/15/24/30/31 on
    active_optimization_event), which turn a missing-attribute probe into a
    raised AttributeError.
    """

    def __init__(self, **kwargs: str | None) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestActiveOptimizationEventBoundary:
    """Boundary semantics `from_time <= now < end_time` (mut_63, mut_64)."""

    def test_now_equals_from_time_is_active(self) -> None:
        """`<=` on from_time — matching exactly must still return the event."""
        event = _Event(
            from_time="2026-05-08T12:00:00Z",
            end_time="2026-05-08T12:15:00Z",
        )
        result = active_optimization_event([event], "BATTERY", _at(2026, 5, 8, 12, 0))
        assert result is event

    def test_now_equals_end_time_is_not_active(self) -> None:
        """`<` on end_time — matching exactly must return None (exclusive)."""
        event = _Event(
            from_time="2026-05-08T12:00:00Z",
            end_time="2026-05-08T12:15:00Z",
        )
        assert (
            active_optimization_event([event], "BATTERY", _at(2026, 5, 8, 12, 15))
            is None
        )


class TestActiveOptimizationEventEndTimePreference:
    """`end_time or to_time` fallback (mut_19 or→and, mut_32/33 string swap)."""

    def test_end_time_wins_over_to_time_when_both_present(self) -> None:
        """`or` picks end_time (truthy); `and` would pick to_time."""
        event = _Event(
            from_time="2026-05-08T12:00:00Z",
            end_time="2026-05-08T12:15:00Z",
            to_time="2026-05-08T14:00:00Z",
        )
        # now is past end_time but before to_time:
        # original (end_time) → None, `and`-mutation would use to_time → match
        assert (
            active_optimization_event([event], "BATTERY", _at(2026, 5, 8, 12, 30))
            is None
        )

    def test_to_time_fallback_when_end_time_missing(self) -> None:
        """Only to_time populated — original falls back; string-rename mutations
        break the attribute lookup, which this round-trip pins down."""
        event = _AttrMissingEvent(
            asset="BATTERY",
            from_time="2026-05-08T12:00:00Z",
            to_time="2026-05-08T12:15:00Z",
        )
        result = active_optimization_event([event], "BATTERY", _at(2026, 5, 8, 12, 7))
        assert result is event


class TestActiveOptimizationEventNaiveTimestamps:
    """`if tzinfo is None: replace(tzinfo=UTC)` path (mut_57/60 flip,
    mut_58/59/61/62 replace variants)."""

    def test_naive_timestamps_treated_as_utc(self) -> None:
        """Naive ISO strings must still match an aware ``now``."""
        event = _Event(
            from_time="2026-05-08T12:00:00",  # no Z, no offset → naive
            end_time="2026-05-08T12:15:00",
        )
        result = active_optimization_event([event], "BATTERY", _at(2026, 5, 8, 12, 7))
        assert result is event


class TestActiveOptimizationEventIsoFormat:
    """`replace("Z", "+00:00")` must substitute both inputs (mut_44–55)."""

    def test_z_suffix_parsed_as_utc(self) -> None:
        """Z-suffixed timestamps parse. If either string's Z-replace is dropped,
        `fromisoformat` raises ValueError and the event is silently skipped."""
        event = _Event(
            from_time="2026-05-08T12:00:00Z",
            end_time="2026-05-08T12:15:00Z",
        )
        result = active_optimization_event([event], "BATTERY", _at(2026, 5, 8, 12, 7))
        assert result is event


class TestActiveOptimizationEventContinues:
    """Multi-event loop — first entry excluded, second entry matches
    (mut_9/37/56 continue→break)."""

    def test_second_event_matches_after_first_wrong_asset(self) -> None:
        events = [
            _Event(
                asset="HEATPUMP",
                from_time="2026-05-08T12:00:00Z",
                end_time="2026-05-08T12:15:00Z",
            ),
            _Event(
                asset="BATTERY",
                from_time="2026-05-08T12:00:00Z",
                end_time="2026-05-08T12:15:00Z",
            ),
        ]
        result = active_optimization_event(events, "BATTERY", _at(2026, 5, 8, 12, 7))
        assert result is events[1]

    def test_second_event_matches_after_first_invalid_timestamp(self) -> None:
        events = [
            _Event(from_time="not-a-date", end_time="2026-05-08T12:15:00Z"),
            _Event(from_time="2026-05-08T12:00:00Z", end_time="2026-05-08T12:15:00Z"),
        ]
        result = active_optimization_event(events, "BATTERY", _at(2026, 5, 8, 12, 7))
        assert result is events[1]

    def test_second_event_matches_after_first_non_string_from_time(self) -> None:
        """`isinstance(from_raw, str)` guard — first event is skipped, second
        is found. Breaks mut_56 (continue→break) too."""
        events = [
            _Event(from_time=None, end_time="2026-05-08T12:15:00Z"),
            _Event(from_time="2026-05-08T12:00:00Z", end_time="2026-05-08T12:15:00Z"),
        ]
        result = active_optimization_event(events, "BATTERY", _at(2026, 5, 8, 12, 7))
        assert result is events[1]


class TestActiveOptimizationEventMissingAttributes:
    """`getattr(..., default)` form — mut_5/15/24/30/31 drop the default."""

    def test_event_without_asset_attribute_is_skipped(self) -> None:
        """Original: getattr defaults to None → None != "BATTERY" → continue.
        Mutation (default removed) → AttributeError on the missing attr."""
        broken = _AttrMissingEvent()  # NO .asset attribute at all
        good = _Event(
            from_time="2026-05-08T12:00:00Z",
            end_time="2026-05-08T12:15:00Z",
        )
        result = active_optimization_event(
            [broken, good], "BATTERY", _at(2026, 5, 8, 12, 7)
        )
        assert result is good

    def test_event_without_from_time_attribute_is_skipped(self) -> None:
        broken = _AttrMissingEvent(asset="BATTERY")
        good = _Event(
            from_time="2026-05-08T12:00:00Z",
            end_time="2026-05-08T12:15:00Z",
        )
        result = active_optimization_event(
            [broken, good], "BATTERY", _at(2026, 5, 8, 12, 7)
        )
        assert result is good


# ----------------------------------------------------------------------------
# aggregate_optimization_events
# ----------------------------------------------------------------------------


@dataclass
class _AggEvent:
    total_cost: float | None = None
    energy_bought: float | None = None
    energy_sold: float | None = None
    slot_count: int = 1
    from_time: str | None = None
    timestamp: str = ""


class _TimestampOnlyEvent:
    """Event without a ``from_time`` attribute — forces the ``or e.timestamp``
    fallback inside the ``max`` key lambda (mut_14 or→and)."""

    def __init__(self, timestamp: str) -> None:
        self.timestamp = timestamp
        self.from_time = None
        self.total_cost = None
        self.energy_bought = None
        self.energy_sold = None
        self.slot_count = 1


class TestAggregateOptimizationEventsFieldFilters:
    """`[e.x for e in events if e.x is not None]` filter + ``sum(...) if ...``
    truthy check (mut_1–6, mut_29/30/34/35/39/40)."""

    def test_populated_costs_sum_is_exact(self) -> None:
        events = [
            _AggEvent(total_cost=1.5, from_time="2026-04-26T09:00:00Z"),
            _AggEvent(total_cost=2.25, from_time="2026-04-26T10:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["total_cost"] == 3.75

    def test_populated_bought_sum_is_exact(self) -> None:
        events = [
            _AggEvent(energy_bought=2.0, from_time="2026-04-26T09:00:00Z"),
            _AggEvent(energy_bought=1.5, from_time="2026-04-26T10:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["energy_bought"] == 3.5

    def test_populated_sold_sum_is_exact(self) -> None:
        events = [
            _AggEvent(energy_sold=0.25, from_time="2026-04-26T09:00:00Z"),
            _AggEvent(energy_sold=0.75, from_time="2026-04-26T10:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["energy_sold"] == 1.0

    def test_mixed_none_and_populated_only_counts_populated(self) -> None:
        """`is not None` filter — mut_2/4/6 flip to `is None` which would
        count only the None rows and yield None."""
        events = [
            _AggEvent(total_cost=1.0, from_time="2026-04-26T09:00:00Z"),
            _AggEvent(total_cost=None, from_time="2026-04-26T10:00:00Z"),
            _AggEvent(total_cost=4.0, from_time="2026-04-26T11:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["total_cost"] == 5.0

    def test_all_none_costs_yield_none(self) -> None:
        """`if costs else None` falsy branch. mut_29 forces ``and False`` =
        always None; mut_30 forces ``or True`` = always sum (= 0 on empty)."""
        events = [_AggEvent(from_time="2026-04-26T09:00:00Z")]
        result = aggregate_optimization_events(events)
        assert result["total_cost"] is None


class TestAggregateOptimizationEventsSlotCount:
    """`sum(getattr(e, "slot_count", 1) ...)` (mut_18/20/23/24/25/26)."""

    def test_default_slot_count_one_per_event_without_attr(self) -> None:
        """Three attr-less events must count as 3 slots (default = 1 each).
        mut_20 flips default to None → sum raises; mut_23 drops the default →
        AttributeError on the missing attr; mut_26 flips default to 2 → 6."""
        events = [
            _TimestampOnlyEvent("2026-04-26T09:00:00Z"),
            _TimestampOnlyEvent("2026-04-26T10:00:00Z"),
            _TimestampOnlyEvent("2026-04-26T11:00:00Z"),
        ]
        # strip the slot_count attribute that _TimestampOnlyEvent sets
        for e in events:
            del e.slot_count
        result = aggregate_optimization_events(events)
        assert result["event_count"] == 3

    def test_slot_count_zero_counts_zero(self) -> None:
        """mut_26 flips default from 1→2; this test uses an EXPLICIT 0 so the
        default is never reached, pinning the sum formula instead."""
        events = [
            _AggEvent(slot_count=0, from_time="2026-04-26T09:00:00Z"),
            _AggEvent(slot_count=3, from_time="2026-04-26T10:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["event_count"] == 3


class TestAggregateOptimizationEventsLastEvent:
    """`max(events, key=lambda e: e.from_time or e.timestamp)` (mut_14)."""

    def test_last_event_falls_back_to_timestamp_when_from_time_is_none(
        self,
    ) -> None:
        """Both events have ``from_time=None`` → key reduces to ``timestamp``.
        mut_14 flips `or` to `and`: ``None and timestamp`` = None, so every
        event gets the same key and ``max`` returns the first (stable), not
        the latest."""
        events = [
            _TimestampOnlyEvent("2026-04-26T09:00:00Z"),
            _TimestampOnlyEvent("2026-04-26T15:00:00Z"),
            _TimestampOnlyEvent("2026-04-26T11:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["last_event"].timestamp == "2026-04-26T15:00:00Z"


# ----------------------------------------------------------------------------
# build_forecast
# ----------------------------------------------------------------------------


class TestBuildForecastBoundary:
    """`if end <= now or start >= cutoff: continue` (mut_26/27/28/29/42)."""

    def test_slot_ending_exactly_at_now_is_excluded(self) -> None:
        """mut_27 flips `<=` to `<`: a slot that just ended would be kept."""
        prices = {"2026-04-26T10:00:00Z": 0.10}
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        assert result == []

    def test_slot_starting_exactly_at_cutoff_is_excluded(self) -> None:
        """mut_28 flips `>=` to `>`: a slot that starts at the cutoff would
        slip in."""
        # horizon = 1 h → cutoff = 11:00. A slot ending 11:15 starts at 11:00.
        prices = {"2026-04-26T11:15:00Z": 0.10}
        result = build_forecast(prices, horizon_hours=1, now=_at(2026, 4, 26, 10, 0))
        assert result == []

    def test_second_slot_included_after_first_skipped(self) -> None:
        """mut_29/42 (continue→break): the second valid slot must still appear
        after a first past slot is skipped."""
        prices = {
            "2026-04-26T08:00:00Z": 0.05,  # past, skipped
            "2026-04-26T10:30:00Z": 0.15,  # in-window
        }
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        assert len(result) == 1
        assert result[0]["price"] == 0.15

    def test_or_condition_excludes_slots_past_cutoff(self) -> None:
        """mut_26 flips `or` to `and`: a slot that is both future-of-now AND
        past-cutoff should be skipped under `or` but kept under `and` (because
        `end <= now` is False → the whole guard is False → not skip)."""
        prices = {"2026-04-26T15:00:00Z": 0.30}  # 5h in future
        result = build_forecast(prices, horizon_hours=2, now=_at(2026, 4, 26, 10, 0))
        assert result == []


class TestBuildForecastDefaults:
    """Default argument values + numerical rounding (mut_1, mut_41)."""

    def test_default_horizon_is_24_hours(self) -> None:
        """mut_1 flips default from 24 to 25. A slot at 24.5 h must be
        excluded under 24 and included under 25."""
        # now = 10:00, 24 h later = next day 10:00. Slot at 10:30 next day
        # (= 24.5 h) → excluded under 24-h horizon.
        prices = {"2026-04-27T10:30:00Z": 0.20}
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        assert result == []

    def test_price_is_rounded_to_six_decimals(self) -> None:
        """mut_41 flips 6 → 7, which would keep the raw 7th decimal."""
        prices = {"2026-04-26T10:30:00Z": 0.1234567}
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        assert result[0]["price"] == 0.123457


class TestBuildForecastTimezones:
    """Z-suffix + naive timestamp handling (mut_18/19/21/22/23)."""

    def test_z_suffix_input_produces_offset_output(self) -> None:
        """mut_18 breaks the Z replacement entirely; mut_19 flips Z to z →
        `fromisoformat` would fail to parse."""
        prices = {"2026-04-26T10:30:00Z": 0.10}
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        assert result[0]["end"].endswith("+00:00")

    def test_naive_timestamp_treated_as_utc(self) -> None:
        """mut_21 flips the tzinfo-check; mut_22/23 break the UTC assignment —
        a naive key would then compare against an aware now and crash."""
        prices = {"2026-04-26T10:30:00": 0.10}  # no Z
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        assert len(result) == 1
