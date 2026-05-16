"""Pure helper functions for the 1KOMMA5° integration.

This module intentionally avoids importing Home Assistant or any heavy
runtime dependencies, so its functions can be unit-tested in isolation.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any


def get_current_price(prices: dict[str, float]) -> float | None:
    """Return the price for the active 15-minute slot.

    API timestamps represent the END of each 15-minute delivery slot, so the
    active slot is the one with the smallest end timestamp strictly after now.
    """
    if not prices:
        return None
    now = datetime.datetime.now(tz=datetime.UTC)

    best_value: float | None = None
    best_time: datetime.datetime | None = None

    for key, value in prices.items():
        try:
            slot_time = datetime.datetime.fromisoformat(key.replace("Z", "+00:00"))
            if slot_time.tzinfo is None:
                slot_time = slot_time.replace(tzinfo=datetime.UTC)
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
        now = datetime.datetime.now(tz=datetime.UTC)
    cutoff = now + datetime.timedelta(hours=horizon_hours)
    slots: list[dict[str, Any]] = []

    for key, value in prices.items():
        try:
            end = datetime.datetime.fromisoformat(key.replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=datetime.UTC)
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


def active_optimization_event(
    events: list[Any],
    asset: str,
    now: datetime.datetime,
) -> Any | None:
    """Return the optimization event currently active for ``asset``, or ``None``.

    "Active" means ``from_time <= now < to_time``. The first matching event in
    iteration order wins (the API typically returns at most one event per
    asset per slot, so order does not matter in practice).
    """
    for event in events:
        if getattr(event, "asset", None) != asset:
            continue
        from_raw = getattr(event, "from_time", None)
        to_raw = getattr(event, "to_time", None)
        if not from_raw or not to_raw:
            continue
        try:
            from_dt = datetime.datetime.fromisoformat(from_raw.replace("Z", "+00:00"))
            to_dt = datetime.datetime.fromisoformat(to_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if from_dt.tzinfo is None:
            from_dt = from_dt.replace(tzinfo=datetime.UTC)
        if to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=datetime.UTC)
        if from_dt <= now < to_dt:
            return event
    return None


def trapezoidal_delta_kwh(
    last_power_w: float,
    last_time: datetime.datetime,
    current_power_w: float,
    current_time: datetime.datetime,
) -> float | None:
    """Compute the delta kWh between two power samples via trapezoidal integration.

    Returns ``None`` when the average power between the samples is non-positive
    (no accumulation should happen).
    """
    dt_hours = (current_time - last_time).total_seconds() / 3600
    avg_w = (last_power_w + current_power_w) / 2
    if avg_w <= 0:
        return None
    return avg_w * dt_hours / 1000


def _find_window(
    forecast: list[dict[str, Any]],
    slot_count: int,
    is_better: Callable[[float, float], bool],
    earliest_start: datetime.datetime | None = None,
    latest_end: datetime.datetime | None = None,
) -> dict[str, Any] | None:
    """Find a contiguous slot window optimized by the supplied comparator.

    ``is_better(candidate_avg, current_best_avg)`` returns True when the
    candidate window should replace the current best.
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
        if best_avg is None or is_better(avg, best_avg):
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


def find_cheapest_window(
    forecast: list[dict[str, Any]],
    slot_count: int,
    earliest_start: datetime.datetime | None = None,
    latest_end: datetime.datetime | None = None,
) -> dict[str, Any] | None:
    """Find the cheapest contiguous window of ``slot_count`` 15-min slots."""
    return _find_window(
        forecast,
        slot_count,
        lambda candidate, best: candidate < best,
        earliest_start,
        latest_end,
    )


def find_most_expensive_window(
    forecast: list[dict[str, Any]],
    slot_count: int,
    earliest_start: datetime.datetime | None = None,
    latest_end: datetime.datetime | None = None,
) -> dict[str, Any] | None:
    """Find the most expensive contiguous window of ``slot_count`` 15-min slots."""
    return _find_window(
        forecast,
        slot_count,
        lambda candidate, best: candidate > best,
        earliest_start,
        latest_end,
    )


# Map 1KOMMA5° weather symbol IDs to Home Assistant WeatherEntity condition strings.
# Day variants are <100; night variants are day_id + 100. Library source:
# .venv/.../onekommafive/models.py (WEATHER_SYMBOLS).
_WEATHER_SYMBOL_TO_CONDITION: dict[int, str] = {
    1: "sunny",
    2: "sunny",
    3: "partlycloudy",
    4: "cloudy",
    5: "rainy",
    8: "rainy",
    15: "pouring",
    101: "clear-night",
    102: "clear-night",
    103: "partlycloudy",
    104: "cloudy",
    105: "rainy",
    108: "rainy",
    115: "pouring",
}


def weather_symbol_to_ha_condition(symbol_id: int | None) -> str | None:
    """Translate a 1KOMMA5° weather symbol ID to an HA WeatherEntity condition.

    Returns ``None`` for unknown IDs and for ``None`` input so the WeatherEntity
    falls back to its previous state instead of raising.
    """
    if symbol_id is None:
        return None
    return _WEATHER_SYMBOL_TO_CONDITION.get(symbol_id)


def _parse_iso_hour(iso: str) -> datetime.datetime:
    """Parse an API hour key like ``"2026-01-01T01:00Z"`` to a UTC datetime."""
    return datetime.datetime.fromisoformat(iso)


def energy_buckets_to_kwh_deltas(
    timeseries: dict[str, Any],
    field: str,
) -> list[tuple[datetime.datetime, float]]:
    """Extract ``(hour_start_utc, kwh)`` pairs for one field of a day's energy buckets.

    ``timeseries`` is ``EnergyData.timeseries`` — a dict keyed by the API's
    ISO-hour string (``"2026-01-01T01:00Z"``) with ``EnergySlot`` values.
    Buckets where the named field is ``None`` are skipped (e.g. ``consumption_ac_total``
    for systems without an AC unit).
    """
    out: list[tuple[datetime.datetime, float]] = []
    for iso_key, slot in timeseries.items():
        value = getattr(slot, field, None)
        if value is None:
            continue
        out.append((_parse_iso_hour(iso_key), float(value)))
    return out


def soc_buckets_to_measurement_stats(
    timeseries: dict[str, Any],
) -> list[tuple[datetime.datetime, float]]:
    """Extract ``(hour_start_utc, soc_percent)`` pairs from a day's energy buckets.

    The API returns ``battery_soc`` as a fraction ``[0..1]``; HA's
    ``battery_soc`` sensor uses percent. Multiplied by 100 here. Buckets with
    ``None`` SoC are skipped.
    """
    out: list[tuple[datetime.datetime, float]] = []
    for iso_key, slot in timeseries.items():
        soc = getattr(slot, "battery_soc", None)
        if soc is None:
            continue
        out.append((_parse_iso_hour(iso_key), float(soc) * 100.0))
    return out


def consumer_cost_deltas(
    timeseries: dict[str, Any],
    prices_by_hour: dict[datetime.datetime, float],
) -> dict[str, list[tuple[datetime.datetime, float]]]:
    """Compute per-consumer hourly cost (€) deltas via proportional allocation.

    Mirrors the live cost-sensor formulas:

        share = consumer_h_kwh / consumption_h_kwh
        cost  = grid_supply_h × share × price_h

    The total ``electricity_cost`` is ``grid_supply × price`` for the same hour
    — therefore the four consumer-cost deltas sum to ``electricity_cost`` at
    every hour (invariant, tested).

    Hours are skipped (no entries written) when:
    - the price for that hour is missing (would silently understate cost)
    - ``grid_supply`` is ``None``
    - the total consumption is 0 (no allocation possible without dividing by
      zero — matches the live sensor's None-skip)

    ``consumption_ac_total = None`` (no AC installed) is treated as 0 in the
    denominator so AC share is naturally 0.

    Returns a dict keyed by translation_key:
    ``electricity_cost``, ``heat_pump_cost``, ``ev_charger_cost``,
    ``household_cost``, ``ac_cost``.
    """
    result: dict[str, list[tuple[datetime.datetime, float]]] = {
        "electricity_cost": [],
        "heat_pump_cost": [],
        "ev_charger_cost": [],
        "household_cost": [],
        "ac_cost": [],
    }
    for iso_key, slot in timeseries.items():
        hour = _parse_iso_hour(iso_key)
        price = prices_by_hour.get(hour)
        if price is None:
            continue
        grid_supply = getattr(slot, "grid_supply", None)
        if grid_supply is None:
            continue
        # Total cost
        result["electricity_cost"].append((hour, grid_supply * price))
        # Per-consumer share — None means 0 share for that consumer
        ht = getattr(slot, "consumption_household_total", None) or 0.0
        hp = getattr(slot, "consumption_heat_pump_total", None) or 0.0
        ev = getattr(slot, "consumption_ev_total", None) or 0.0
        ac = getattr(slot, "consumption_ac_total", None) or 0.0
        consumption_total = ht + hp + ev + ac
        if consumption_total == 0:
            continue
        scale = grid_supply * price / consumption_total
        result["heat_pump_cost"].append((hour, hp * scale))
        result["ev_charger_cost"].append((hour, ev * scale))
        result["household_cost"].append((hour, ht * scale))
        result["ac_cost"].append((hour, ac * scale))
    return result


def feed_in_revenue_deltas(
    timeseries: dict[str, Any],
    feed_in_tariff: float,
) -> list[tuple[datetime.datetime, float]]:
    """Compute hourly feed-in revenue (€) deltas.

    Returns ``(hour_start_utc, kwh × tariff)`` for every bucket where
    ``grid_feed_in`` is non-None. Hours without feed-in produce a 0-value
    entry (the cumulative sum is still well-defined).
    """
    out: list[tuple[datetime.datetime, float]] = []
    for iso_key, slot in timeseries.items():
        feed_in = getattr(slot, "grid_feed_in", None)
        if feed_in is None:
            continue
        out.append((_parse_iso_hour(iso_key), float(feed_in) * feed_in_tariff))
    return out


def extract_hourly_prices(
    market_prices: Any,
) -> dict[datetime.datetime, float]:
    """Parse ``MarketPrices.prices_with_grid_costs_and_vat`` to UTC-hour → price."""
    raw = getattr(market_prices, "prices_with_grid_costs_and_vat", None) or {}
    return {_parse_iso_hour(k): float(v) for k, v in raw.items()}


def accumulate_to_stats(
    deltas: list[tuple[datetime.datetime, float]],
    anchor_sum: float,
    end_before: datetime.datetime | None = None,
) -> list[dict[str, Any]]:
    """Build ``StatisticData``-shape dicts from per-hour deltas.

    Each output dict has ``{"start": datetime, "sum": cumulative_value}``.

    Backfilled buckets are OLDER than the live anchor (we only ever fill in
    front of existing data) — so the cumulative ``sum`` must rise from a low
    starting point up to ``anchor_sum`` at the most recent backfilled bucket.
    That way the Energy Dashboard's per-period ``sum[end] - sum[start]``
    arithmetic stays continuous at the backfill/live boundary.

    Concretely:

    - oldest emitted bucket: ``sum = anchor_sum - total_delta + first_delta``
    - newest emitted bucket: ``sum = anchor_sum``

    where ``total_delta`` is the sum of all deltas that survive ``end_before``.

    ``anchor_sum`` is the existing live sensor's ``sum`` at its earliest
    timestamp — pass ``0.0`` if no live stats exist yet.

    ``end_before`` excludes any bucket whose ``start`` is at or after that
    timestamp — caller passes the start of the oldest existing statistic to
    avoid duplicate inserts.

    Output is sorted chronologically regardless of input order.
    """
    sorted_deltas = sorted(deltas, key=lambda pair: pair[0])
    if end_before is not None:
        sorted_deltas = [(s, d) for s, d in sorted_deltas if s < end_before]
    if not sorted_deltas:
        return []

    total_delta = sum(d for _, d in sorted_deltas)
    running = anchor_sum - total_delta
    out: list[dict[str, Any]] = []
    for start, delta in sorted_deltas:
        running += delta
        out.append({"start": start, "sum": running})
    return out
