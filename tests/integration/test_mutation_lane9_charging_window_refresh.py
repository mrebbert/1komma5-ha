"""Adversarial assertions targeting `_refresh_window` survivors on both
``OneKomma5CheapestChargingWindowSensor`` (today) and
``OneKomma5CheapestChargingWindowTomorrowSensor``.

Lane 9 of the mutation-score push. Each test instantiates the sensor
with a minimal coordinator stub and drives `_refresh_window` directly
against a crafted forecast, bypassing the HA entity-lifecycle plumbing.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import Any

import pytest
from freezegun import freeze_time
from homeassistant.util import dt as dt_util

from custom_components.onekommafive.sensor_entities import (
    OneKomma5CheapestChargingWindowSensor,
    OneKomma5CheapestChargingWindowTomorrowSensor,
)


@pytest.fixture
def _utc_tz():
    """Pin HA's default timezone to UTC so day-boundary math is predictable."""
    original = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(dt.UTC)
    try:
        yield
    finally:
        dt_util.set_default_time_zone(original)


def _slot(start_iso: str, end_iso: str, price: float) -> dict[str, Any]:
    return {"start": start_iso, "end": end_iso, "price": price}


def _mk_today_sensor(forecast: list[dict[str, Any]] | None) -> Any:
    data = SimpleNamespace(forecast=forecast) if forecast is not None else None
    coordinator = SimpleNamespace(data=data)
    sensor = OneKomma5CheapestChargingWindowSensor.__new__(
        OneKomma5CheapestChargingWindowSensor
    )
    sensor.coordinator = coordinator
    sensor._slot_count = 2  # 30 min window
    sensor._duration_minutes = 30
    sensor._window = None
    return sensor


def _mk_tomorrow_sensor(forecast: list[dict[str, Any]] | None) -> Any:
    data = SimpleNamespace(forecast=forecast) if forecast is not None else None
    coordinator = SimpleNamespace(data=data)
    sensor = OneKomma5CheapestChargingWindowTomorrowSensor.__new__(
        OneKomma5CheapestChargingWindowTomorrowSensor
    )
    sensor.coordinator = coordinator
    sensor._slot_count = 2  # 30 min window
    sensor._duration_minutes = 30
    sensor._window = None
    return sensor


# ---------------------------------------------------------------------------
# OneKomma5CheapestChargingWindowSensor (today)
# ---------------------------------------------------------------------------


class TestTodayRefreshDataGuard:
    """`data is None or not forecast` — mut_5 (``or`` → ``and``)."""

    @freeze_time("2026-04-26T10:00:00+00:00")
    def test_none_coordinator_data_does_not_access_forecast(self, _utc_tz) -> None:
        """When ``data is None`` the function must return; a mutation that
        turns the OR into AND would short-circuit to False and then raise
        AttributeError on ``self.coordinator.data.forecast``."""
        sensor = _mk_today_sensor(forecast=None)
        sensor._refresh_window()
        assert sensor._window is None


class TestTodayRefreshEarliestStart:
    """`earliest_start=dt_util.as_utc(now_local)` — mut_25 / mut_29 class."""

    @freeze_time("2026-04-26T12:00:00+00:00")
    def test_past_slot_cheaper_than_future_is_not_chosen(self, _utc_tz) -> None:
        forecast = [
            _slot("2026-04-26T08:00:00+00:00", "2026-04-26T08:15:00+00:00", 0.05),
            _slot("2026-04-26T08:15:00+00:00", "2026-04-26T08:30:00+00:00", 0.05),
            _slot("2026-04-26T13:00:00+00:00", "2026-04-26T13:15:00+00:00", 0.40),
            _slot("2026-04-26T13:15:00+00:00", "2026-04-26T13:30:00+00:00", 0.40),
        ]
        sensor = _mk_today_sensor(forecast=forecast)
        sensor._refresh_window()
        assert sensor._window is not None
        assert sensor._window["start"].startswith("2026-04-26T13:00:00")
        assert sensor._window["average_price"] == 0.40


# ---------------------------------------------------------------------------
# OneKomma5CheapestChargingWindowTomorrowSensor
# ---------------------------------------------------------------------------


class TestTomorrowRefreshDataGuard:
    """`data is None or not forecast` — mut_2 (``or`` → ``and``)."""

    @freeze_time("2026-04-26T10:00:00+00:00")
    def test_none_coordinator_data_does_not_access_forecast(self, _utc_tz) -> None:
        sensor = _mk_tomorrow_sensor(forecast=None)
        sensor._refresh_window()
        assert sensor._window is None


class TestTomorrowRefreshLatestEnd:
    """`latest_end=dt_util.as_utc(end_of_tomorrow)` — mut_22 / mut_26 class.

    Pinned UTC-local so ``tomorrow`` is calendar-day aligned on UTC."""

    @freeze_time("2026-04-26T10:00:00+00:00")
    def test_day_after_tomorrow_slot_cheaper_than_tomorrow_is_not_chosen(
        self, _utc_tz
    ) -> None:
        forecast = [
            # Tomorrow (2026-04-27 UTC) — moderate price
            _slot("2026-04-27T09:00:00+00:00", "2026-04-27T09:15:00+00:00", 0.30),
            _slot("2026-04-27T09:15:00+00:00", "2026-04-27T09:30:00+00:00", 0.30),
            # Day-after-tomorrow (2026-04-28 UTC) — much cheaper, must be ignored
            _slot("2026-04-28T02:00:00+00:00", "2026-04-28T02:15:00+00:00", 0.01),
            _slot("2026-04-28T02:15:00+00:00", "2026-04-28T02:30:00+00:00", 0.01),
        ]
        sensor = _mk_tomorrow_sensor(forecast=forecast)
        sensor._refresh_window()
        assert sensor._window is not None
        assert sensor._window["start"].startswith("2026-04-27T09:00:00")
        assert sensor._window["average_price"] == 0.30
