"""`OneKomma5CheapestHourNowSensor` must bound the comparison to the next 24h.

The price coordinator fetches today + tomorrow (up to 30h). Without a horizon
filter, a slightly cheaper slot on the next calendar day keeps the sensor
stuck at OFF for the whole current day. The regression surfaced live: 730
state changes over several weeks, never once ON.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from custom_components.onekommafive.binary_sensor import (
    OneKomma5CheapestHourNowSensor,
)


def _slot(start: datetime.datetime, price: float) -> dict:
    end = start + datetime.timedelta(minutes=15)
    return {"start": start.isoformat(), "end": end.isoformat(), "price": price}


def _instance_with_forecast(forecast, current_price: float):
    """Build a `OneKomma5CheapestHourNowSensor` without running `__init__`."""
    sensor = OneKomma5CheapestHourNowSensor.__new__(OneKomma5CheapestHourNowSensor)
    sensor.coordinator = SimpleNamespace(
        data=SimpleNamespace(
            forecast=forecast,
            all_in_prices=None,
            current_price=current_price,
        )
    )
    return sensor


def _build_today_tomorrow_forecast(
    now: datetime.datetime,
    today_price: float,
    tomorrow_price: float,
) -> list[dict]:
    """24h at `today_price` starting at `now`, then 24h at `tomorrow_price`.

    A one-minute buffer in front of the tomorrow block protects against
    sub-second clock drift between the test and the sensor code (both read
    their own wall clock).
    """
    slots: list[dict] = []
    for i in range(96):
        slots.append(_slot(now + datetime.timedelta(minutes=15 * i), today_price))
    tomorrow_offset = datetime.timedelta(hours=24, minutes=1)
    for i in range(96):
        slots.append(
            _slot(
                now + tomorrow_offset + datetime.timedelta(minutes=15 * i),
                tomorrow_price,
            )
        )
    return slots


class TestCheapestHourNow24hHorizon:
    """ON state must depend only on slots within the next 24h."""

    def test_on_when_current_is_min_today_even_if_tomorrow_cheaper(self) -> None:
        """Core regression: tomorrow is 0.05 €, today floor 0.20 €, current is
        the first today-slot at 0.20 € → sensor must flip ON (today's min)."""
        now = datetime.datetime.now(datetime.UTC)
        forecast = _build_today_tomorrow_forecast(
            now, today_price=0.20, tomorrow_price=0.05
        )
        sensor = _instance_with_forecast(forecast, current_price=0.20)

        assert sensor.is_on is True

    def test_off_when_a_cheaper_slot_lies_within_24h(self) -> None:
        """Honours the 24h window: a 0.15 € slot in 6h beats the current 0.20 €."""
        now = datetime.datetime.now(datetime.UTC)
        forecast = [
            _slot(now, 0.20),
            _slot(now + datetime.timedelta(hours=6), 0.15),
            _slot(now + datetime.timedelta(hours=25), 0.05),  # beyond horizon
        ]
        sensor = _instance_with_forecast(forecast, current_price=0.20)

        assert sensor.is_on is False

    def test_min_forecast_price_ignores_slots_beyond_24h(self) -> None:
        """`_min_forecast_price` must drop slots whose start is ≥ now+24h."""
        now = datetime.datetime.now(datetime.UTC)
        forecast = [
            _slot(now, 0.25),
            _slot(now + datetime.timedelta(hours=23, minutes=59), 0.18),
            _slot(now + datetime.timedelta(hours=24, minutes=1), 0.05),
        ]
        sensor = _instance_with_forecast(forecast, current_price=0.25)

        assert sensor._min_forecast_price() == 0.18

    def test_cheapest_slot_start_attribute_points_to_today(self) -> None:
        """`extra_state_attributes.cheapest_slot_start` is the within-24h minimum,
        not the global forecast minimum."""
        now = datetime.datetime.now(datetime.UTC)
        today_min_start = now + datetime.timedelta(hours=3)
        tomorrow_min_start = now + datetime.timedelta(hours=28)
        forecast = [
            _slot(now, 0.25),
            _slot(today_min_start, 0.18),
            _slot(tomorrow_min_start, 0.05),
        ]
        sensor = _instance_with_forecast(forecast, current_price=0.25)

        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert attrs["cheapest_price"] == 0.18
        assert attrs["cheapest_slot_start"] == today_min_start.isoformat()

    def test_empty_forecast_returns_none(self) -> None:
        sensor = _instance_with_forecast([], current_price=0.20)

        assert sensor.is_on is None
        assert sensor.extra_state_attributes == {"current_price": 0.20}
