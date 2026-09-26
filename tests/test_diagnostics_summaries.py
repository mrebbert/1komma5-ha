"""Tier-1 tests for the ``diagnostics.py`` summary helpers.

Each ``_*_summary`` helper returns ``{}`` when its coordinator payload is
``None``. This module covers those eight guard branches without needing a
running Home Assistant instance.
"""

from __future__ import annotations

from custom_components.onekommafive.diagnostics import (
    _assets_redacted,
    _energy_summary,
    _live_summary,
    _notifications_summary,
    _optimization_summary,
    _price_summary,
    _system_status_summary,
    _weather_summary,
)


def test_live_summary_none_returns_empty() -> None:
    assert _live_summary(None) == {}


def test_price_summary_none_returns_empty() -> None:
    assert _price_summary(None) == {}


def test_optimization_summary_none_returns_empty() -> None:
    assert _optimization_summary(None) == {}


def test_weather_summary_none_returns_empty() -> None:
    assert _weather_summary(None) == {}


def test_energy_summary_none_returns_empty() -> None:
    assert _energy_summary(None) == {}


def test_notifications_summary_none_returns_empty() -> None:
    assert _notifications_summary(None) == {}


def test_system_status_summary_none_returns_empty() -> None:
    assert _system_status_summary(None) == {}


def test_assets_redacted_none_returns_empty() -> None:
    assert _assets_redacted(None) == {}
