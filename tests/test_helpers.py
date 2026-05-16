"""Tests for the pure helper functions."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from helpers import (  # type: ignore[import-not-found]
    accumulate_to_stats,
    active_optimization_event,
    aggregate_optimization_events,
    build_forecast,
    consumer_cost_deltas,
    energy_buckets_to_kwh_deltas,
    extract_hourly_prices,
    feed_in_revenue_deltas,
    find_cheapest_window,
    find_most_expensive_window,
    get_current_price,
    soc_buckets_to_measurement_stats,
    split_prices_by_date,
    trapezoidal_delta_kwh,
    weather_symbol_to_ha_condition,
)

UTC = datetime.UTC


def _at(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute, second, tzinfo=UTC)


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
            _StubEvent(
                total_cost=1.0, energy_bought=2.0, energy_sold=0.5, from_time="2026-04-26T09:00:00Z"
            ),
            _StubEvent(
                total_cost=2.0,
                energy_bought=3.0,
                energy_sold=None,
                from_time="2026-04-26T10:00:00Z",
            ),
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
            forecast,
            slot_count=2,
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
            forecast,
            slot_count=2,
            latest_end=datetime.datetime(2026, 4, 26, 10, 30, tzinfo=UTC),
        )
        assert result is not None
        assert result["end"] == "2026-04-26T10:30:00+00:00"

    def test_no_window_matches_constraints(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.10),
        ]
        result = find_cheapest_window(
            forecast,
            slot_count=1,
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


# ----------------------------------------------------------------------------
# find_most_expensive_window
# ----------------------------------------------------------------------------


class TestFindMostExpensiveWindow:
    def test_returns_none_when_forecast_too_short(self) -> None:
        forecast = [_slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.1)]
        assert find_most_expensive_window(forecast, slot_count=4) is None

    def test_finds_most_expensive_two_slot_window(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.10),
            _slot("2026-04-26T10:15:00+00:00", "2026-04-26T10:30:00+00:00", 0.40),
            _slot("2026-04-26T10:30:00+00:00", "2026-04-26T10:45:00+00:00", 0.50),
            _slot("2026-04-26T10:45:00+00:00", "2026-04-26T11:00:00+00:00", 0.20),
        ]
        result = find_most_expensive_window(forecast, slot_count=2)
        assert result is not None
        # Most expensive 2-slot window is index 1+2: (0.40 + 0.50) / 2 = 0.45
        assert result["start"] == "2026-04-26T10:15:00+00:00"
        assert result["end"] == "2026-04-26T10:45:00+00:00"
        assert result["average_price"] == 0.45
        assert result["slot_count"] == 2

    def test_respects_earliest_start(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.50),
            _slot("2026-04-26T10:15:00+00:00", "2026-04-26T10:30:00+00:00", 0.50),
            _slot("2026-04-26T10:30:00+00:00", "2026-04-26T10:45:00+00:00", 0.10),
            _slot("2026-04-26T10:45:00+00:00", "2026-04-26T11:00:00+00:00", 0.10),
        ]
        result = find_most_expensive_window(
            forecast,
            slot_count=2,
            earliest_start=datetime.datetime(2026, 4, 26, 10, 30, tzinfo=UTC),
        )
        assert result is not None
        assert result["start"] == "2026-04-26T10:30:00+00:00"
        assert result["average_price"] == 0.10  # only post-30 slots are eligible

    def test_handles_negative_prices(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", -0.05),
            _slot("2026-04-26T10:15:00+00:00", "2026-04-26T10:30:00+00:00", -0.10),
        ]
        result = find_most_expensive_window(forecast, slot_count=1)
        assert result is not None
        # Most expensive (least negative) is -0.05
        assert result["average_price"] == -0.05


# ----------------------------------------------------------------------------
# active_optimization_event
# ----------------------------------------------------------------------------


@dataclass
class _ActiveStubEvent:
    asset: str
    decision: str
    from_time: str | None
    to_time: str | None


class TestActiveOptimizationEvent:
    def test_returns_none_for_empty_list(self) -> None:
        assert active_optimization_event([], "BATTERY", _at(2026, 5, 8, 12, 0)) is None

    def test_finds_active_event_in_window(self) -> None:
        events = [
            _ActiveStubEvent(
                asset="BATTERY",
                decision="BATTERY_CHARGE_FROM_GRID",
                from_time="2026-05-08T12:00:00Z",
                to_time="2026-05-08T12:15:00Z",
            ),
        ]
        result = active_optimization_event(events, "BATTERY", _at(2026, 5, 8, 12, 7))
        assert result is events[0]

    def test_excludes_event_before_from_time(self) -> None:
        events = [
            _ActiveStubEvent(
                asset="BATTERY",
                decision="BATTERY_CHARGE_FROM_GRID",
                from_time="2026-05-08T12:00:00Z",
                to_time="2026-05-08T12:15:00Z",
            ),
        ]
        assert active_optimization_event(events, "BATTERY", _at(2026, 5, 8, 11, 59)) is None

    def test_excludes_event_at_or_after_to_time(self) -> None:
        events = [
            _ActiveStubEvent(
                asset="BATTERY",
                decision="BATTERY_CHARGE_FROM_GRID",
                from_time="2026-05-08T12:00:00Z",
                to_time="2026-05-08T12:15:00Z",
            ),
        ]
        # to_time is exclusive
        assert active_optimization_event(events, "BATTERY", _at(2026, 5, 8, 12, 15)) is None

    def test_filters_by_asset(self) -> None:
        events = [
            _ActiveStubEvent(
                asset="HEATPUMP",
                decision="HEATPUMP_RECOMMEND_ON",
                from_time="2026-05-08T12:00:00Z",
                to_time="2026-05-08T12:15:00Z",
            ),
        ]
        assert active_optimization_event(events, "BATTERY", _at(2026, 5, 8, 12, 7)) is None

    def test_skips_events_with_invalid_timestamps(self) -> None:
        events = [
            _ActiveStubEvent(asset="BATTERY", decision="X", from_time=None, to_time=None),
            _ActiveStubEvent(
                asset="BATTERY", decision="X", from_time="garbage", to_time="2026-05-08T12:15:00Z"
            ),
            _ActiveStubEvent(
                asset="BATTERY",
                decision="BATTERY_NO_CHARGE",
                from_time="2026-05-08T12:00:00Z",
                to_time="2026-05-08T12:15:00Z",
            ),
        ]
        result = active_optimization_event(events, "BATTERY", _at(2026, 5, 8, 12, 5))
        assert result is events[2]


# ----------------------------------------------------------------------------
# trapezoidal_delta_kwh
# ----------------------------------------------------------------------------


class TestTrapezoidalDeltaKwh:
    def test_constant_1kw_for_1_hour_yields_1kwh(self) -> None:
        result = trapezoidal_delta_kwh(
            1000.0,
            _at(2026, 4, 26, 10, 0),
            1000.0,
            _at(2026, 4, 26, 11, 0),
        )
        assert result == pytest.approx(1.0)

    def test_returns_none_for_negative_average(self) -> None:
        result = trapezoidal_delta_kwh(
            -100.0,
            _at(2026, 4, 26, 10, 0),
            -100.0,
            _at(2026, 4, 26, 11, 0),
        )
        assert result is None

    def test_returns_none_for_zero_average(self) -> None:
        result = trapezoidal_delta_kwh(
            0.0,
            _at(2026, 4, 26, 10, 0),
            0.0,
            _at(2026, 4, 26, 11, 0),
        )
        assert result is None

    def test_averages_power_over_interval(self) -> None:
        # 0W → 1000W over 1 hour → avg 500W → 0.5 kWh
        result = trapezoidal_delta_kwh(
            0.0,
            _at(2026, 4, 26, 10, 0),
            1000.0,
            _at(2026, 4, 26, 11, 0),
        )
        assert result == pytest.approx(0.5)

    def test_30_second_sample_at_2kw(self) -> None:
        # 2000W constant for 30s → 2000 * (30/3600) / 1000 ≈ 0.01667 kWh
        result = trapezoidal_delta_kwh(
            2000.0,
            _at(2026, 4, 26, 10, 0, 0),
            2000.0,
            datetime.datetime(2026, 4, 26, 10, 0, 30, tzinfo=UTC),
        )
        assert result == pytest.approx(2000 * (30 / 3600) / 1000)


# ----------------------------------------------------------------------------
# weather_symbol_to_ha_condition
# ----------------------------------------------------------------------------


class TestWeatherSymbolToHaCondition:
    @pytest.mark.parametrize(
        "symbol_id,expected",
        [
            (1, "sunny"),
            (2, "sunny"),
            (3, "partlycloudy"),
            (4, "cloudy"),
            (5, "rainy"),
            (8, "rainy"),
            (15, "pouring"),
            (101, "clear-night"),
            (102, "clear-night"),
            (103, "partlycloudy"),
            (104, "cloudy"),
            (105, "rainy"),
            (108, "rainy"),
            (115, "pouring"),
        ],
    )
    def test_known_symbols_map_to_ha_conditions(self, symbol_id: int, expected: str) -> None:
        assert weather_symbol_to_ha_condition(symbol_id) == expected

    def test_none_symbol_returns_none(self) -> None:
        assert weather_symbol_to_ha_condition(None) is None

    def test_unknown_symbol_returns_none(self) -> None:
        # 999 is not in our mapping; the WeatherEntity should fall back rather
        # than crash, so the helper returns None.
        assert weather_symbol_to_ha_condition(999) is None


# ----------------------------------------------------------------------------
# energy_buckets_to_kwh_deltas / soc_buckets_to_measurement_stats / accumulate_to_stats
# ----------------------------------------------------------------------------


@dataclass
class _StubSlot:
    """Stand-in for ``EnergySlot`` — exposes the attributes the helpers read."""

    production: float | None = None
    grid_supply: float | None = None
    grid_feed_in: float | None = None
    consumption_household_total: float | None = None
    consumption_heat_pump_total: float | None = None
    consumption_ev_total: float | None = None
    consumption_ac_total: float | None = None
    battery_charge: float | None = None
    battery_discharge: float | None = None
    battery_soc: float | None = None


def _h(hour: int) -> datetime.datetime:
    return datetime.datetime(2026, 1, 1, hour, 0, tzinfo=UTC)


class TestEnergyBucketsToKwhDeltas:
    def test_empty_dict_returns_empty_list(self) -> None:
        assert energy_buckets_to_kwh_deltas({}, "production") == []

    def test_extracts_per_hour_kwh(self) -> None:
        ts = {
            "2026-01-01T00:00Z": _StubSlot(production=0.5),
            "2026-01-01T01:00Z": _StubSlot(production=1.25),
        }
        result = sorted(energy_buckets_to_kwh_deltas(ts, "production"))
        assert result == [(_h(0), 0.5), (_h(1), 1.25)]

    def test_skips_none_values(self) -> None:
        # AC unit not installed → consumption_ac_total is None
        ts = {
            "2026-01-01T00:00Z": _StubSlot(consumption_ac_total=None),
            "2026-01-01T01:00Z": _StubSlot(consumption_ac_total=0.2),
        }
        result = energy_buckets_to_kwh_deltas(ts, "consumption_ac_total")
        assert len(result) == 1
        assert result[0] == (_h(1), 0.2)

    def test_unknown_field_returns_empty(self) -> None:
        ts = {"2026-01-01T00:00Z": _StubSlot(production=0.5)}
        # `getattr(slot, field, None)` for an unknown field returns None → skip
        assert energy_buckets_to_kwh_deltas(ts, "nonexistent_field") == []

    def test_accepts_full_iso_timestamp(self) -> None:
        ts = {"2026-01-01T01:00:00Z": _StubSlot(production=1.0)}
        result = energy_buckets_to_kwh_deltas(ts, "production")
        assert result == [(_h(1), 1.0)]


class TestSocBucketsToMeasurementStats:
    def test_fraction_to_percent(self) -> None:
        ts = {
            "2026-01-01T00:00Z": _StubSlot(battery_soc=0.05),
            "2026-01-01T01:00Z": _StubSlot(battery_soc=0.92),
        }
        result = dict(soc_buckets_to_measurement_stats(ts))
        assert result[_h(0)] == pytest.approx(5.0)
        assert result[_h(1)] == pytest.approx(92.0)

    def test_skips_none(self) -> None:
        ts = {
            "2026-01-01T00:00Z": _StubSlot(battery_soc=None),
            "2026-01-01T01:00Z": _StubSlot(battery_soc=0.5),
        }
        result = soc_buckets_to_measurement_stats(ts)
        assert len(result) == 1
        assert result[0] == (_h(1), pytest.approx(50.0))

    def test_empty_input(self) -> None:
        assert soc_buckets_to_measurement_stats({}) == []


class TestAccumulateToStats:
    def test_empty_deltas(self) -> None:
        assert accumulate_to_stats([], anchor_sum=0.0) == []

    def test_ends_at_anchor(self) -> None:
        """Newest backfilled bucket has sum == anchor; live continues from there."""
        deltas = [(_h(0), 1.0), (_h(1), 2.0), (_h(2), 0.5)]
        result = accumulate_to_stats(deltas, anchor_sum=10.0)
        assert result[-1]["sum"] == pytest.approx(10.0)

    def test_starts_below_anchor_by_total_minus_first_delta(self) -> None:
        """Oldest bucket sum = anchor - total + first_delta."""
        deltas = [(_h(0), 1.0), (_h(1), 2.0), (_h(2), 0.5)]
        # total = 3.5; anchor - total = -3.5; +first_delta(1.0) = -2.5
        result = accumulate_to_stats(deltas, anchor_sum=0.0)
        assert result[0]["sum"] == pytest.approx(-2.5)

    def test_consecutive_diffs_recover_input_deltas(self) -> None:
        """Differences between consecutive sums == input deltas (post-first)."""
        deltas = [(_h(0), 1.0), (_h(1), 2.0), (_h(2), 0.5)]
        result = accumulate_to_stats(deltas, anchor_sum=10.0)
        diffs = [result[i]["sum"] - result[i - 1]["sum"] for i in range(1, len(result))]
        assert diffs == [pytest.approx(2.0), pytest.approx(0.5)]

    def test_sorts_chronologically(self) -> None:
        deltas = [(_h(2), 0.5), (_h(0), 1.0), (_h(1), 2.0)]
        result = accumulate_to_stats(deltas, anchor_sum=0.0)
        assert [r["start"] for r in result] == [_h(0), _h(1), _h(2)]
        # Sums end at anchor (0.0), so reversed cumulative
        assert result[-1]["sum"] == pytest.approx(0.0)

    def test_end_before_cuts_list_and_anchors_to_cut(self) -> None:
        """`end_before` cuts deltas; the LAST remaining bucket anchors to anchor."""
        deltas = [(_h(0), 1.0), (_h(1), 2.0), (_h(2), 0.5)]
        # Caller has existing stats starting at hour 1 — only hour 0 is new.
        result = accumulate_to_stats(deltas, anchor_sum=10.0, end_before=_h(1))
        # Only hour 0 survives, and its sum equals the anchor (cut-over point)
        assert result == [{"start": _h(0), "sum": pytest.approx(10.0)}]

    def test_end_before_equal_excludes(self) -> None:
        # The condition is `start >= end_before`, so the bucket AT end_before
        # is excluded — that's the bucket the caller already has.
        deltas = [(_h(0), 1.0), (_h(1), 2.0)]
        result = accumulate_to_stats(deltas, anchor_sum=0.0, end_before=_h(1))
        assert len(result) == 1
        assert result[0]["start"] == _h(0)


# ----------------------------------------------------------------------------
# consumer_cost_deltas / feed_in_revenue_deltas / extract_hourly_prices
# ----------------------------------------------------------------------------


class TestConsumerCostDeltas:
    def _slot(self, **kwargs: float | None) -> _StubSlot:
        defaults = {
            "grid_supply": 1.0,
            "consumption_household_total": 0.5,
            "consumption_heat_pump_total": 0.3,
            "consumption_ev_total": 0.2,
            "consumption_ac_total": 0.0,
        }
        return _StubSlot(**(defaults | kwargs))

    def test_full_allocation_sums_to_total_cost(self) -> None:
        # All non-zero consumers, single hour
        ts = {"2026-01-01T01:00Z": self._slot()}
        prices = {_h(1): 0.30}
        result = consumer_cost_deltas(ts, prices)
        total = result["electricity_cost"][0][1]
        parts = sum(
            v[0][1]
            for v in (
                result["heat_pump_cost"],
                result["ev_charger_cost"],
                result["household_cost"],
                result["ac_cost"],
            )
        )
        assert parts == pytest.approx(total, abs=1e-9)

    def test_missing_price_hour_is_skipped(self) -> None:
        ts = {
            "2026-01-01T00:00Z": self._slot(),  # has price
            "2026-01-01T01:00Z": self._slot(),  # missing price
        }
        prices = {_h(0): 0.30}
        result = consumer_cost_deltas(ts, prices)
        # Only hour 0 has entries
        assert len(result["electricity_cost"]) == 1
        assert result["electricity_cost"][0][0] == _h(0)
        for k in ("heat_pump_cost", "ev_charger_cost", "household_cost", "ac_cost"):
            assert len(result[k]) == 1
            assert result[k][0][0] == _h(0)

    def test_zero_consumption_skips_per_consumer(self) -> None:
        # Hour with grid_supply but zero consumption everywhere — division
        # by zero would crash; helper skips the per-consumer split.
        ts = {
            "2026-01-01T01:00Z": _StubSlot(
                grid_supply=1.0,
                consumption_household_total=0.0,
                consumption_heat_pump_total=0.0,
                consumption_ev_total=0.0,
                consumption_ac_total=0.0,
            )
        }
        prices = {_h(1): 0.30}
        result = consumer_cost_deltas(ts, prices)
        # Total IS recorded — grid_supply was paid for, regardless of consumer split
        assert len(result["electricity_cost"]) == 1
        # Per-consumer slots are empty because we don't know the split
        for k in ("heat_pump_cost", "ev_charger_cost", "household_cost", "ac_cost"):
            assert result[k] == []

    def test_ac_none_treated_as_zero_share(self) -> None:
        ts = {
            "2026-01-01T01:00Z": _StubSlot(
                grid_supply=1.0,
                consumption_household_total=0.5,
                consumption_heat_pump_total=0.5,
                consumption_ev_total=0.0,
                consumption_ac_total=None,  # no AC installed
            )
        }
        prices = {_h(1): 0.30}
        result = consumer_cost_deltas(ts, prices)
        assert result["ac_cost"][0][1] == pytest.approx(0.0)
        # The 1 kWh at 0.30 €/kWh is split 50/50 between household and heat_pump
        assert result["household_cost"][0][1] == pytest.approx(0.15)
        assert result["heat_pump_cost"][0][1] == pytest.approx(0.15)

    def test_grid_supply_none_skips_hour_entirely(self) -> None:
        ts = {"2026-01-01T01:00Z": _StubSlot(grid_supply=None)}
        prices = {_h(1): 0.30}
        result = consumer_cost_deltas(ts, prices)
        for v in result.values():
            assert v == []

    def test_negative_price_hour_produces_negative_cost(self) -> None:
        ts = {"2026-01-01T01:00Z": self._slot()}
        prices = {_h(1): -0.05}
        result = consumer_cost_deltas(ts, prices)
        # 1 kWh × -0.05 €/kWh = -0.05 € total
        assert result["electricity_cost"][0][1] == pytest.approx(-0.05)


class TestFeedInRevenueDeltas:
    def test_basic_multiplication(self) -> None:
        ts = {
            "2026-01-01T00:00Z": _StubSlot(grid_feed_in=0.0),
            "2026-01-01T01:00Z": _StubSlot(grid_feed_in=2.5),
        }
        result = feed_in_revenue_deltas(ts, feed_in_tariff=0.0803)
        result_dict = dict(result)
        assert result_dict[_h(0)] == pytest.approx(0.0)
        assert result_dict[_h(1)] == pytest.approx(2.5 * 0.0803)

    def test_none_feed_in_skipped(self) -> None:
        ts = {"2026-01-01T01:00Z": _StubSlot(grid_feed_in=None)}
        result = feed_in_revenue_deltas(ts, feed_in_tariff=0.0803)
        assert result == []


class TestExtractHourlyPrices:
    def test_parses_iso_keys_to_utc_datetimes(self) -> None:
        class _MP:
            prices_with_grid_costs_and_vat = {
                "2026-01-01T00:00Z": "0.10",
                "2026-01-01T01:00Z": 0.15,
            }

        result = extract_hourly_prices(_MP())
        assert result[_h(0)] == pytest.approx(0.10)
        assert result[_h(1)] == pytest.approx(0.15)

    def test_handles_missing_field(self) -> None:
        class _MP:
            pass

        assert extract_hourly_prices(_MP()) == {}
