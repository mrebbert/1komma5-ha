"""Adversarial assertions for the Lane-6 mini-fixes.

Three remaining survivors on commit `c8e7587` after Lanes 1-5:

- `helpers.aggregate_optimization_events` mut_35 / mut_40 — the
  `if bought else None` and `if sold else None` falsy branches, which the
  mutation collapses with `or True` to always return `sum(...)` (= 0 on an
  empty list).
- `helpers.build_forecast` mut_35 — the dict key literal `"price"` renamed
  to `"XXpriceXX"`, which breaks every downstream caller that reads the
  slot's `"price"` field.

Each test is annotated with the specific mutmut mutation number(s) it kills.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from custom_components.onekommafive.helpers import (
    aggregate_optimization_events,
    build_forecast,
)


def _at(y: int, m: int, d: int, h: int, mi: int) -> datetime.datetime:
    return datetime.datetime(y, m, d, h, mi, tzinfo=datetime.UTC)


@dataclass
class _AggEvent:
    total_cost: float | None = None
    energy_bought: float | None = None
    energy_sold: float | None = None
    slot_count: int = 1
    from_time: str | None = None
    timestamp: str = ""


class TestAggregateEmptyFieldsReturnNone:
    """`sum(x) if x else None` must stay None when the filter yields []
    (mut_35 on energy_bought, mut_40 on energy_sold flip `else None` to
    `or True else None`, which always sums an empty list to 0)."""

    def test_energy_bought_is_none_when_all_inputs_none(self) -> None:
        events = [
            _AggEvent(total_cost=1.0, from_time="2026-04-26T09:00:00Z"),
            _AggEvent(total_cost=2.0, from_time="2026-04-26T10:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["energy_bought"] is None

    def test_energy_sold_is_none_when_all_inputs_none(self) -> None:
        events = [
            _AggEvent(total_cost=1.0, from_time="2026-04-26T09:00:00Z"),
            _AggEvent(total_cost=2.0, from_time="2026-04-26T10:00:00Z"),
        ]
        result = aggregate_optimization_events(events)
        assert result["energy_sold"] is None


class TestBuildForecastSlotKey:
    """Each forecast slot dict uses the literal key `"price"`
    (mut_35 renames to `"XXpriceXX"`)."""

    def test_slot_uses_price_key_not_renamed_variant(self) -> None:
        prices = {"2026-04-26T10:30:00Z": 0.123}
        result = build_forecast(prices, now=_at(2026, 4, 26, 10, 0))
        assert len(result) == 1
        slot = result[0]
        assert "price" in slot
        assert slot["price"] == 0.123
        assert "XXpriceXX" not in slot
