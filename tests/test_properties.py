"""Property-based tests for the pure-function helpers in ``helpers.py``.

Hypothesis generates many input combinations per property and shrinks any
failure to a minimal reproducer. Line-coverage misses edge-cases that random
inputs trip (empty lists, boundary timestamps, extreme floats, …) — these
tests target the places where a hand-written example-based test would miss
the exact combination that breaks the invariant.

Scope: three functions in ``helpers.py`` where real-world payloads vary over
a wide input space.

- ``get_current_price`` — slot-end timestamps as keys, "next end after now"
- ``trapezoidal_delta_kwh`` — accumulator semantics
- ``find_cheapest_window`` — sliding-window minimum over a forecast
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st


def _load_helpers() -> object:
    """Load ``helpers.py`` directly via importlib — Tier-1 isolation (no HA)."""
    path = (
        Path(__file__).resolve().parent.parent
        / "custom_components"
        / "onekommafive"
        / "helpers.py"
    )
    spec = importlib.util.spec_from_file_location("onekommafive_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_helpers = _load_helpers()


# --------------------------------------------------------------------------
# get_current_price
# --------------------------------------------------------------------------


_now = datetime.datetime.now(tz=datetime.UTC)
_offsets = st.integers(min_value=-10_000, max_value=10_000)  # seconds from now
_prices = st.floats(
    min_value=-1.0, max_value=5.0, allow_nan=False, allow_infinity=False
)


@st.composite
def _price_dicts(draw: st.DrawFn) -> dict[str, float]:
    """Produce ``{iso_timestamp_end: price}`` dicts with 0–20 slots."""
    offsets = draw(st.lists(_offsets, min_size=0, max_size=20, unique=True))
    prices = draw(st.lists(_prices, min_size=len(offsets), max_size=len(offsets)))
    return {
        (_now + datetime.timedelta(seconds=offset)).isoformat(): price
        for offset, price in zip(offsets, prices, strict=True)
    }


@given(_price_dicts())
@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_get_current_price_picks_smallest_future_end(prices: dict[str, float]) -> None:
    """The result must correspond to the slot with the smallest end > now."""
    now = datetime.datetime.now(tz=datetime.UTC)
    future = {
        k: v for k, v in prices.items() if datetime.datetime.fromisoformat(k) > now
    }
    result = _helpers.get_current_price(prices)
    if not future:
        assert result is None
        return
    expected_key = min(future, key=lambda k: datetime.datetime.fromisoformat(k))
    assert result == future[expected_key]


@given(_price_dicts())
def test_get_current_price_returns_none_on_empty_or_past_only(
    prices: dict[str, float],
) -> None:
    """Empty input or purely-past slots → ``None``."""
    now = datetime.datetime.now(tz=datetime.UTC)
    all_past = prices and all(datetime.datetime.fromisoformat(k) <= now for k in prices)
    if not prices or all_past:
        assert _helpers.get_current_price(prices) is None


# --------------------------------------------------------------------------
# trapezoidal_delta_kwh
# --------------------------------------------------------------------------


_power_w = st.floats(
    min_value=-100.0, max_value=20_000.0, allow_nan=False, allow_infinity=False
)
_duration_seconds = st.integers(min_value=1, max_value=3_600)


@given(_power_w, _power_w, _duration_seconds)
@settings(max_examples=200)
def test_trapezoidal_delta_kwh_matches_hand_formula(
    p1: float, p2: float, duration_s: int
) -> None:
    """Result equals ``avg_w * duration_h / 1000`` when avg_w > 0, else None."""
    t1 = _now
    t2 = _now + datetime.timedelta(seconds=duration_s)
    avg_w = (p1 + p2) / 2
    expected = avg_w * (duration_s / 3600) / 1000 if avg_w > 0 else None
    result = _helpers.trapezoidal_delta_kwh(p1, t1, p2, t2)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert abs(result - expected) < 1e-9


@given(_power_w, _duration_seconds)
def test_trapezoidal_delta_kwh_constant_power_closed_form(
    p: float, duration_s: int
) -> None:
    """Constant power ``p`` over ``duration_s`` yields ``p * duration_h / 1000``."""
    assume(p > 0)
    t1 = _now
    t2 = _now + datetime.timedelta(seconds=duration_s)
    result = _helpers.trapezoidal_delta_kwh(p, t1, p, t2)
    expected = p * (duration_s / 3600) / 1000
    assert result is not None
    assert abs(result - expected) < 1e-9


@given(_power_w, _power_w, _duration_seconds)
def test_trapezoidal_delta_kwh_zero_duration_is_zero_or_none(
    p1: float, p2: float, _duration_s: int
) -> None:
    """Zero duration always maps to 0 kWh (or None if avg_w ≤ 0)."""
    t1 = _now
    t2 = _now
    result = _helpers.trapezoidal_delta_kwh(p1, t1, p2, t2)
    avg_w = (p1 + p2) / 2
    if avg_w > 0:
        assert result == 0
    else:
        assert result is None


# --------------------------------------------------------------------------
# find_cheapest_window
# --------------------------------------------------------------------------


@st.composite
def _forecast_slots(draw: st.DrawFn) -> list[dict[str, object]]:
    """Build a list of consecutive 15-min slots starting at a random anchor."""
    anchor = _now.replace(minute=0, second=0, microsecond=0)
    count = draw(st.integers(min_value=1, max_value=40))
    prices_list = draw(st.lists(_prices, min_size=count, max_size=count))
    slots: list[dict[str, object]] = []
    for i, price in enumerate(prices_list):
        start = anchor + datetime.timedelta(minutes=15 * i)
        end = start + datetime.timedelta(minutes=15)
        slots.append(
            {"start": start.isoformat(), "end": end.isoformat(), "price": price}
        )
    return slots


@given(_forecast_slots(), st.integers(min_value=1, max_value=10))
@settings(max_examples=200)
def test_find_cheapest_window_average_is_minimum(
    forecast: list[dict[str, object]], slot_count: int
) -> None:
    """The result's ``average_price`` equals the minimum sliding-window mean."""
    result = _helpers.find_cheapest_window(forecast, slot_count)
    if slot_count > len(forecast):
        assert result is None
        return
    assert result is not None
    windows = [
        forecast[i : i + slot_count] for i in range(len(forecast) - slot_count + 1)
    ]
    expected_min = min(sum(s["price"] for s in w) / slot_count for w in windows)
    assert abs(result["average_price"] - round(expected_min, 6)) < 1e-6
    assert result["slot_count"] == slot_count


@given(_forecast_slots(), st.integers(min_value=1, max_value=10))
def test_find_cheapest_window_bounds_align_with_slots(
    forecast: list[dict[str, object]], slot_count: int
) -> None:
    """``start`` and ``end`` match one of the valid windows end-to-end."""
    result = _helpers.find_cheapest_window(forecast, slot_count)
    if result is None:
        return
    starts = {s["start"] for s in forecast}
    ends = {s["end"] for s in forecast}
    assert result["start"] in starts
    assert result["end"] in ends


@given(_forecast_slots())
def test_find_cheapest_window_slot_count_too_large_is_none(
    forecast: list[dict[str, object]],
) -> None:
    """``slot_count`` > ``len(forecast)`` always returns None."""
    assert _helpers.find_cheapest_window(forecast, len(forecast) + 1) is None
