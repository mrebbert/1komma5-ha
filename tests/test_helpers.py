"""Tests for the pure helper functions."""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from helpers import (  # type: ignore[import-not-found]
    aggregate_optimization_events,
    build_forecast,
    find_cheapest_window,
    get_current_price,
    split_prices_by_date,
)


UTC = datetime.timezone.utc


def _at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute, tzinfo=UTC)


# ----------------------------------------------------------------------------
# get_current_price
# ----------------------------------------------------------------------------

class TestGetCurrentPrice:
    def test_empty_dict_returns_none(self) -> None:
        assert get_current_price({}) is None

    def test_picks_smallest_end_time_after_now(self) -> None:
        # API timestamps are slot END times. At 10:36 UTC the active slot is
        # the one ending at 10:45 (i.e. delivery period 10:30–10:45).
        prices = {
            "2026-04-26T10:30:00Z": 0.20,
            "2026-04-26T10:45:00Z": 0.30,
            "2026-04-26T11:00:00Z": 0.40,
        }
        with patch("helpers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _at(2026, 4, 26, 10, 36)
            mock_dt.datetime.fromisoformat = datetime.datetime.fromisoformat
            mock_dt.timezone = datetime.timezone
            assert get_current_price(prices) == 0.30

    def test_returns_none_when_all_slots_in_past(self) -> None:
        prices = {"2026-04-26T08:00:00Z": 0.20}
        with patch("helpers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _at(2026, 4, 26, 12, 0)
            mock_dt.datetime.fromisoformat = datetime.datetime.fromisoformat
            mock_dt.timezone = datetime.timezone
            assert get_current_price(prices) is None

    def test_handles_negative_prices(self) -> None:
        prices = {"2026-04-26T10:45:00Z": -0.05}
        with patch("helpers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _at(2026, 4, 26, 10, 30)
            mock_dt.datetime.fromisoformat = datetime.datetime.fromisoformat
            mock_dt.timezone = datetime.timezone
            assert get_current_price(prices) == -0.05

    def test_skips_unparsable_keys(self) -> None:
        prices = {
            "garbage": 9.99,
            "2026-04-26T10:45:00Z": 0.30,
        }
        with patch("helpers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _at(2026, 4, 26, 10, 30)
            mock_dt.datetime.fromisoformat = datetime.datetime.fromisoformat
            mock_dt.timezone = datetime.timezone
            assert get_current_price(prices) == 0.30


# ----------------------------------------------------------------------------
# build_forecast
# ----------------------------------------------------------------------------

class TestBuildForecast:
    def test_empty_input(self) -> None:
        assert build_forecast({}, now=_at(2026, 4, 26, 10, 0)) == []

    def test_filters_past_slots(self) -> None:
        prices = {
            "2026-04-26T08:00:00Z": 0.10,  # ended 2 hours ago
            "2026-04-26T10:15:00Z": 0.20,  # active slot at now=10:00
        }
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        assert len(result) == 1
        assert result[0]["price"] == 0.20

    def test_respects_horizon(self) -> None:
        prices = {
            "2026-04-26T11:00:00Z": 0.10,
            "2026-04-26T15:00:00Z": 0.20,  # 5h in the future
        }
        result = build_forecast(prices, horizon_hours=2, now=_at(2026, 4, 26, 10, 0))
        prices_in_result = [s["price"] for s in result]
        assert 0.10 in prices_in_result
        assert 0.20 not in prices_in_result

    def test_derives_start_from_end(self) -> None:
        prices = {"2026-04-26T11:00:00Z": 0.10}
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        assert result[0]["end"] == "2026-04-26T11:00:00+00:00"
        assert result[0]["start"] == "2026-04-26T10:45:00+00:00"

    def test_sorted_by_start(self) -> None:
        prices = {
            "2026-04-26T13:00:00Z": 0.30,
            "2026-04-26T11:00:00Z": 0.10,
            "2026-04-26T12:00:00Z": 0.20,
        }
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        starts = [s["start"] for s in result]
        assert starts == sorted(starts)


# ----------------------------------------------------------------------------
# split_prices_by_date
# ----------------------------------------------------------------------------

class TestSplitPricesByDate:
    def test_splits_correctly(self) -> None:
        prices = {
            "2026-04-26T10:00:00Z": 0.10,
            "2026-04-26T23:45:00Z": 0.20,
            "2026-04-27T00:15:00Z": 0.30,
            "2026-04-27T12:00:00Z": 0.40,
        }
        today, tomorrow = split_prices_by_date(
            prices, datetime.date(2026, 4, 26), datetime.date(2026, 4, 27)
        )
        assert sorted(today) == [0.10, 0.20]
        assert sorted(tomorrow) == [0.30, 0.40]

    def test_unknown_date_is_excluded(self) -> None:
        prices = {"2025-01-01T10:00:00Z": 0.10}
        today, tomorrow = split_prices_by_date(
            prices, datetime.date(2026, 4, 26), datetime.date(2026, 4, 27)
        )
        assert today == []
        assert tomorrow == []


# ----------------------------------------------------------------------------
# aggregate_optimization_events
# ----------------------------------------------------------------------------

@dataclass
class _StubEvent:
    total_cost: float | None = None
    energy_bought: float | None = None
    energy_sold: float | None = None
    from_time: str | None = None
    timestamp: str = ""


class TestAggregateOptimizationEvents:
    def test_empty_list(self) -> None:
        result = aggregate_optimization_events([])
        assert result == {
            "event_count": 0,
            "total_cost": None,
            "energy_bought": None,
            "energy_sold": None,
            "last_event": None,
        }

    def test_all_none_fields_aggregate_to_none(self) -> None:
        events = [_StubEvent(from_time="2026-04-26T10:00:00Z")]
        result = aggregate_optimization_events(events)
        assert result["event_count"] == 1
        assert result["total_cost"] is None
        assert result["energy_bought"] is None
        assert result["energy_sold"] is None
        assert result["last_event"] is events[0]

    def test_aggregates_present_values(self) -> None:
        events = [
            _StubEvent(total_cost=1.0, energy_bought=2.0, energy_sold=0.5,
                       from_time="2026-04-26T09:00:00Z"),
            _StubEvent(total_cost=2.0, energy_bought=3.0, energy_sold=None,
                       from_time="2026-04-26T10:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["event_count"] == 2
        assert result["total_cost"] == 3.0
        assert result["energy_bought"] == 5.0
        assert result["energy_sold"] == 0.5

    def test_last_event_is_latest_from_time(self) -> None:
        events = [
            _StubEvent(from_time="2026-04-26T08:00:00Z"),
            _StubEvent(from_time="2026-04-26T15:00:00Z"),
            _StubEvent(from_time="2026-04-26T11:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["last_event"].from_time == "2026-04-26T15:00:00Z"


# ----------------------------------------------------------------------------
# find_cheapest_window
# ----------------------------------------------------------------------------

def _slot(start: str, end: str, price: float) -> dict:
    return {"start": start, "end": end, "price": price}


class TestFindCheapestWindow:
    def test_returns_none_when_forecast_too_short(self) -> None:
        forecast = [_slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.1)]
        assert find_cheapest_window(forecast, slot_count=4) is None

    def test_returns_none_for_zero_slot_count(self) -> None:
        forecast = [_slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.1)]
        assert find_cheapest_window(forecast, slot_count=0) is None

    def test_finds_cheapest_two_slot_window(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.30),
            _slot("2026-04-26T10:15:00+00:00", "2026-04-26T10:30:00+00:00", 0.10),
            _slot("2026-04-26T10:30:00+00:00", "2026-04-26T10:45:00+00:00", 0.05),
            _slot("2026-04-26T10:45:00+00:00", "2026-04-26T11:00:00+00:00", 0.40),
        ]
        result = find_cheapest_window(forecast, slot_count=2)
        assert result is not None
        # Cheapest 2-slot window is index 1+2: (0.10 + 0.05) / 2 = 0.075
        assert result["start"] == "2026-04-26T10:15:00+00:00"
        assert result["end"] == "2026-04-26T10:45:00+00:00"
        assert result["average_price"] == 0.075
        assert result["slot_count"] == 2

    def test_respects_earliest_start(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.05),
            _slot("2026-04-26T10:15:00+00:00", "2026-04-26T10:30:00+00:00", 0.05),
            _slot("2026-04-26T10:30:00+00:00", "2026-04-26T10:45:00+00:00", 0.30),
            _slot("2026-04-26T10:45:00+00:00", "2026-04-26T11:00:00+00:00", 0.30),
        ]
        result = find_cheapest_window(
            forecast, slot_count=2,
            earliest_start=datetime.datetime(2026, 4, 26, 10, 30, tzinfo=UTC),
        )
        assert result is not None
        assert result["start"] == "2026-04-26T10:30:00+00:00"

    def test_respects_latest_end(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.30),
            _slot("2026-04-26T10:15:00+00:00", "2026-04-26T10:30:00+00:00", 0.30),
            _slot("2026-04-26T10:30:00+00:00", "2026-04-26T10:45:00+00:00", 0.05),
            _slot("2026-04-26T10:45:00+00:00", "2026-04-26T11:00:00+00:00", 0.05),
        ]
        result = find_cheapest_window(
            forecast, slot_count=2,
            latest_end=datetime.datetime(2026, 4, 26, 10, 30, tzinfo=UTC),
        )
        assert result is not None
        assert result["end"] == "2026-04-26T10:30:00+00:00"

    def test_no_window_matches_constraints(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.10),
        ]
        result = find_cheapest_window(
            forecast, slot_count=1,
            earliest_start=datetime.datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
        )
        assert result is None

    def test_handles_negative_prices(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.10),
            _slot("2026-04-26T10:15:00+00:00", "2026-04-26T10:30:00+00:00", -0.05),
        ]
        result = find_cheapest_window(forecast, slot_count=1)
        assert result is not None
        assert result["average_price"] == -0.05
