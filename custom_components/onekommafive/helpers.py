"""Pure helper functions for the 1KOMMA5° integration.

This module intentionally avoids importing Home Assistant or any heavy
runtime dependencies, so its functions can be unit-tested in isolation.
"""
from __future__ import annotations

import datetime
from typing import Any


def get_current_price(prices: dict[str, float]) -> float | None:
    """Return the price for the active 15-minute slot.

    API timestamps represent the END of each 15-minute delivery slot, so the
    active slot is the one with the smallest end timestamp strictly after now.
    """
    if not prices:
        return None
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    best_value: float | None = None
    best_time: datetime.datetime | None = None

    for key, value in prices.items():
        try:
            slot_time = datetime.datetime.fromisoformat(key.replace("Z", "+00:00"))
            if slot_time.tzinfo is None:
                slot_time = slot_time.replace(tzinfo=datetime.timezone.utc)
            if slot_time > now and (best_time is None or slot_time < best_time):
                best_time = slot_time
                best_value = value
        except ValueError:
            continue

    return best_value


def build_forecast(
    prices: dict[str, float],
    horizon_hours: int = 24,
    now: datetime.datetime | None = None,
) -> list[dict[str, Any]]:
    """Build a sorted forecast list compatible with the Tibber/ENTSO-E format.

    API timestamps represent the END of each 15-minute delivery slot.
    Only slots whose delivery period overlaps [now, now + horizon_hours]
    are included.
    """
    slot_duration = datetime.timedelta(minutes=15)
    if now is None:
        now = datetime.datetime.now(tz=datetime.timezone.utc)
    cutoff = now + datetime.timedelta(hours=horizon_hours)
    slots: list[dict[str, Any]] = []

    for key, value in prices.items():
        try:
            end = datetime.datetime.fromisoformat(key.replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=datetime.timezone.utc)
            start = end - slot_duration
            if end <= now or start >= cutoff:
                continue
            slots.append(
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "price": round(value, 6),
                }
            )
        except ValueError:
            continue

    slots.sort(key=lambda s: s["start"])
    return slots


def split_prices_by_date(
    all_in_prices: dict[str, float], today: datetime.date, tomorrow: datetime.date
) -> tuple[list[float], list[float]]:
    """Split a price dict into today's and tomorrow's price lists by ISO date prefix."""
    today_str = today.strftime("%Y-%m-%d")
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    today_prices = [v for k, v in all_in_prices.items() if today_str in k]
    tomorrow_prices = [v for k, v in all_in_prices.items() if tomorrow_str in k]
    return today_prices, tomorrow_prices


def aggregate_optimization_events(events: list[Any]) -> dict[str, Any]:
    """Aggregate a list of optimization events into summary statistics.

    Returns a dict with: event_count, total_cost, energy_bought, energy_sold,
    last_event. Fields that have no values aggregate to None (not zero) so HA
    sensors render as 'unknown' rather than misleading zeros.
    """
    costs = [e.total_cost for e in events if e.total_cost is not None]
    bought = [e.energy_bought for e in events if e.energy_bought is not None]
    sold = [e.energy_sold for e in events if e.energy_sold is not None]

    last_event = None
    if events:
        last_event = max(events, key=lambda e: e.from_time or e.timestamp)

    return {
        "event_count": len(events),
        "total_cost": sum(costs) if costs else None,
        "energy_bought": sum(bought) if bought else None,
        "energy_sold": sum(sold) if sold else None,
        "last_event": last_event,
    }


def find_cheapest_window(
    forecast: list[dict[str, Any]],
    slot_count: int,
    earliest_start: datetime.datetime | None = None,
    latest_end: datetime.datetime | None = None,
) -> dict[str, Any] | None:
    """Find the cheapest contiguous window of `slot_count` 15-min slots in the forecast.

    Returns a dict with start, end, average_price, slot_count or None if no
    window matching the constraints exists. Forecast slot timestamps are
    parsed; the function is otherwise pure.
    """
    if slot_count < 1 or len(forecast) < slot_count:
        return None

    best_avg: float | None = None
    best_start: datetime.datetime | None = None
    best_end: datetime.datetime | None = None

    for i in range(len(forecast) - slot_count + 1):
        window = forecast[i : i + slot_count]
        window_start = datetime.datetime.fromisoformat(window[0]["start"])
        window_end = datetime.datetime.fromisoformat(window[-1]["end"])

        if earliest_start is not None and window_start < earliest_start:
            continue
        if latest_end is not None and window_end > latest_end:
            continue

        avg = sum(s["price"] for s in window) / len(window)
        if best_avg is None or avg < best_avg:
            best_avg = avg
            best_start = window_start
            best_end = window_end

    if best_avg is None:
        return None

    return {
        "start": best_start.isoformat(),
        "end": best_end.isoformat(),
        "average_price": round(best_avg, 6),
        "slot_count": slot_count,
    }
