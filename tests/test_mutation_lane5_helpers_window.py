"""Adversarial assertions targeting mutmut survivors in two helpers.

Lane-5 of the mutation-score push: targets `helpers._find_window` (9 survivors)
and `helpers.split_prices_by_date` (9 survivors) as recorded on commit
`9ed20cf`. Each test is annotated with the specific mutmut mutation number(s)
it kills.
"""

from __future__ import annotations

import datetime

from custom_components.onekommafive.helpers import (
    find_cheapest_window,
    find_most_expensive_window,
    split_prices_by_date,
)

UTC = datetime.UTC


def _slot(start: str, end: str, price: float) -> dict:
    return {"start": start, "end": end, "price": price}


# ----------------------------------------------------------------------------
# _find_window (via public API) — slot_count guard
# ----------------------------------------------------------------------------


class TestFindWindowSlotCountGuard:
    """`if slot_count < 1 or len(forecast) < slot_count: return None`
    (mut_1 or→and, mut_2 <1→<=1, mut_3 <1→<2)."""

    def test_slot_count_one_returns_window(self) -> None:
        """mut_2 (`<=1`) and mut_3 (`<2`) would both trip the guard and
        return None on a trivially-valid slot_count=1 call."""
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.123),
        ]
        result = find_cheapest_window(forecast, slot_count=1)
        assert result is not None
        assert result["average_price"] == 0.123

    def test_slot_count_zero_does_not_crash(self) -> None:
        """mut_1 (`and` instead of `or`) would skip the guard for slot_count=0
        on a non-empty forecast, and the loop body would then IndexError on
        `window[0]["start"]` when `window = forecast[i:i+0]` returns []."""
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.1),
            _slot("2026-04-26T10:15:00+00:00", "2026-04-26T10:30:00+00:00", 0.2),
        ]
        # No exception; original returns None through the guard.
        assert find_cheapest_window(forecast, slot_count=0) is None


class TestFindWindowBoundRejection:
    """`if ... window_start < earliest_start: continue` must *continue* so a
    later window can still be picked (mut_32 flips `continue` to `break`)."""

    def test_second_window_picked_when_first_before_earliest_start(self) -> None:
        """First window ends before earliest_start, second after; original
        continues past the rejection; mutation breaks and returns None."""
        forecast = [
            _slot("2026-04-26T08:00:00+00:00", "2026-04-26T08:15:00+00:00", 0.05),
            _slot("2026-04-26T08:15:00+00:00", "2026-04-26T08:30:00+00:00", 0.05),
            _slot("2026-04-26T12:00:00+00:00", "2026-04-26T12:15:00+00:00", 0.30),
            _slot("2026-04-26T12:15:00+00:00", "2026-04-26T12:30:00+00:00", 0.30),
        ]
        result = find_cheapest_window(
            forecast,
            slot_count=2,
            earliest_start=datetime.datetime(2026, 4, 26, 11, 0, tzinfo=UTC),
        )
        assert result is not None
        # Must be the later block, not None (which the mutation would return).
        assert result["start"] == "2026-04-26T12:00:00+00:00"


class TestFindWindowRounding:
    """`"average_price": round(best_avg, 6)` (mut_62: 6→7)."""

    def test_average_price_rounded_to_six_decimals(self) -> None:
        forecast = [
            _slot("2026-04-26T10:00:00+00:00", "2026-04-26T10:15:00+00:00", 0.1234567),
        ]
        result = find_cheapest_window(forecast, slot_count=1)
        assert result is not None
        assert result["average_price"] == 0.123457  # 7th decimal rounds up


class TestFindWindowMostExpensive:
    """Same guard, same bound logic exercised through the max-comparator
    sibling. Independent coverage, no new mut IDs — but mutmut has a copy."""

    def test_most_expensive_second_window_picked_when_first_rejected(self) -> None:
        forecast = [
            _slot("2026-04-26T08:00:00+00:00", "2026-04-26T08:15:00+00:00", 0.50),
            _slot("2026-04-26T08:15:00+00:00", "2026-04-26T08:30:00+00:00", 0.50),
            _slot("2026-04-26T12:00:00+00:00", "2026-04-26T12:15:00+00:00", 0.10),
            _slot("2026-04-26T12:15:00+00:00", "2026-04-26T12:30:00+00:00", 0.10),
        ]
        result = find_most_expensive_window(
            forecast,
            slot_count=2,
            earliest_start=datetime.datetime(2026, 4, 26, 11, 0, tzinfo=UTC),
        )
        assert result is not None
        assert result["start"] == "2026-04-26T12:00:00+00:00"


# ----------------------------------------------------------------------------
# split_prices_by_date
# ----------------------------------------------------------------------------


class TestSplitPricesStrftimeFormat:
    """`"%Y-%m-%d"` must render as ``YYYY-MM-DD`` and the resulting string
    appears as a substring of each matching ISO key. Any format drift
    (mut_3/4/5 for today, mut_8/9/10 for tomorrow) would turn the output
    into an empty list."""

    def test_today_format_matches_iso_keys(self) -> None:
        """mut_3/4/5 for the today-side format."""
        prices = {
            "2026-04-26T10:00:00Z": 0.10,
            "2026-04-26T23:45:00Z": 0.20,
            "2026-04-27T00:15:00Z": 0.30,
        }
        today, _tomorrow = split_prices_by_date(
            prices, datetime.date(2026, 4, 26), datetime.date(2026, 4, 27)
        )
        assert sorted(today) == [0.10, 0.20]

    def test_tomorrow_format_matches_iso_keys(self) -> None:
        """mut_8/9/10 for the tomorrow-side format."""
        prices = {
            "2026-04-26T10:00:00Z": 0.10,
            "2026-04-27T00:15:00Z": 0.30,
            "2026-04-27T23:45:00Z": 0.40,
        }
        _today, tomorrow = split_prices_by_date(
            prices, datetime.date(2026, 4, 26), datetime.date(2026, 4, 27)
        )
        assert sorted(tomorrow) == [0.30, 0.40]


class TestSplitPricesMembershipDirection:
    """`today_str in k` and `tomorrow_str in k` — not `not in`.
    mut_12 flips today's filter, mut_14 flips tomorrow's."""

    def test_today_keeps_only_today_values_not_everything_else(self) -> None:
        """mut_12: `today_str not in k` would include tomorrow's 0.30 and 0.40
        and exclude today's 0.10 and 0.20 — the exact inverse."""
        prices = {
            "2026-04-26T10:00:00Z": 0.10,
            "2026-04-26T23:45:00Z": 0.20,
            "2026-04-27T00:15:00Z": 0.30,
            "2026-04-27T23:45:00Z": 0.40,
        }
        today, _tomorrow = split_prices_by_date(
            prices, datetime.date(2026, 4, 26), datetime.date(2026, 4, 27)
        )
        assert 0.10 in today
        assert 0.20 in today
        assert 0.30 not in today
        assert 0.40 not in today

    def test_tomorrow_keeps_only_tomorrow_values(self) -> None:
        """mut_14 analog — the inverse of today."""
        prices = {
            "2026-04-26T10:00:00Z": 0.10,
            "2026-04-26T23:45:00Z": 0.20,
            "2026-04-27T00:15:00Z": 0.30,
            "2026-04-27T23:45:00Z": 0.40,
        }
        _today, tomorrow = split_prices_by_date(
            prices, datetime.date(2026, 4, 26), datetime.date(2026, 4, 27)
        )
        assert 0.30 in tomorrow
        assert 0.40 in tomorrow
        assert 0.10 not in tomorrow
        assert 0.20 not in tomorrow


class TestSplitPricesReturnShape:
    """`tomorrow_prices = [...]` must stay a list — mut_13 replaces it with
    ``None``, which would break downstream callers (`len(tomorrow)`,
    iteration, averaging, …)."""

    def test_tomorrow_is_list_even_when_empty(self) -> None:
        prices = {"2026-04-26T10:00:00Z": 0.10}
        _today, tomorrow = split_prices_by_date(
            prices, datetime.date(2026, 4, 26), datetime.date(2026, 4, 27)
        )
        assert isinstance(tomorrow, list)
        assert tomorrow == []

    def test_tomorrow_is_list_when_populated(self) -> None:
        prices = {
            "2026-04-27T10:00:00Z": 0.30,
            "2026-04-27T23:45:00Z": 0.40,
        }
        _today, tomorrow = split_prices_by_date(
            prices, datetime.date(2026, 4, 26), datetime.date(2026, 4, 27)
        )
        assert isinstance(tomorrow, list)
        assert sorted(tomorrow) == [0.30, 0.40]
