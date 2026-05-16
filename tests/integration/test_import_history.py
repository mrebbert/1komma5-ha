"""Tier-2 tests for the `onekommafive.import_history` and `clear_history` services.

These tests stub the recorder API surface (`async_import_statistics`,
`get_last_statistics`) and the `system.get_energy_historical` SDK call, then
drive the service and assert on the captured writes.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    ALL_STATISTIC_KEYS,
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)

# ----------------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------------

UTC = datetime.UTC


@dataclass
class _Slot:
    """EnergySlot stand-in: only the attributes the helpers read.

    All 10 fields plus battery_soc populated with non-zero values so every
    sensor in the backfill mapping ends up with at least one delta per hour.
    """

    production: float | None = 0.1
    grid_supply: float | None = 0.2
    grid_feed_in: float | None = 0.05
    consumption_household_total: float | None = 0.5
    consumption_heat_pump_total: float | None = 0.3
    consumption_ev_total: float | None = 0.2
    consumption_ac_total: float | None = 0.1
    battery_charge: float | None = 0.3
    battery_discharge: float | None = 0.1
    battery_soc: float | None = 0.5


def _day_payload(day: datetime.date) -> MagicMock:
    """24 hourly slots with deterministic non-zero values."""
    ts: dict[str, _Slot] = {}
    for h in range(24):
        key = f"{day.isoformat()}T{h:02d}:00Z"
        ts[key] = _Slot()
    return MagicMock(timeseries=ts)


def _empty_payload() -> MagicMock:
    return MagicMock(timeseries={})


async def _setup(hass: HomeAssistant, system) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-1",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-1"},
    )
    entry.add_to_hass(hass)
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@pytest.fixture
def captured_imports():
    """Capture all `async_import_statistics(hass, metadata, stats)` calls."""
    calls: list[tuple[str, list]] = []

    def _capture(hass, metadata, stats):
        calls.append((metadata["statistic_id"], list(stats)))

    with patch(
        "custom_components.onekommafive.services.async_import_statistics",
        side_effect=_capture,
    ):
        yield calls


@pytest.fixture
def no_existing_stats():
    """Make `get_last_statistics` always return an empty dict (no anchor, no end_before)."""
    with patch(
        "custom_components.onekommafive.services.get_recorder_instance"
    ) as mock_get_instance:
        recorder = MagicMock()

        # async_add_executor_job → coroutine; call func(*args) synchronously and wrap
        async def _exec_job(func, *args):
            return func(*args)

        recorder.async_add_executor_job.side_effect = _exec_job
        mock_get_instance.return_value = recorder

        with patch(
            "custom_components.onekommafive.services.get_last_statistics",
            return_value={},
        ):
            yield recorder


@pytest.fixture
def no_throttle():
    """Skip the throttle so 30-day backfills don't take 15 seconds."""
    with patch("custom_components.onekommafive.services.BACKFILL_THROTTLE_SECONDS", 0):
        yield


def _market_prices_for(days: list[datetime.date], price: float = 0.30) -> MagicMock:
    """Build a MarketPrices mock with hourly prices for the given days."""
    pricedict: dict[str, float] = {}
    for d in days:
        for h in range(24):
            pricedict[f"{d.isoformat()}T{h:02d}:00Z"] = price
    return MagicMock(prices_with_grid_costs_and_vat=pricedict)


# ----------------------------------------------------------------------------
# import_history
# ----------------------------------------------------------------------------


async def test_import_history_bounded_happy_path(
    hass: HomeAssistant,
    mock_system_factory,
    captured_imports,
    no_existing_stats,
    no_throttle,
) -> None:
    """`days_back=3` walks 3 days and returns the expected counts."""
    system = mock_system_factory(system_id="sys-1")
    system.get_energy_historical.side_effect = lambda d, _e, _r: _day_payload(d)
    await _setup(hass, system)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    response = await hass.services.async_call(
        DOMAIN,
        "import_history",
        {"days_back": 3, "config_entry_id": entry.entry_id},
        blocking=True,
        return_response=True,
    )

    assert response["days_walked"] == 3
    assert response["failed_days"] == []
    # Some stats must have been written (count itself is asserted elsewhere)
    assert response["imported"] > 0


async def test_import_history_writes_expected_stats_count(
    hass: HomeAssistant,
    mock_system_factory,
    captured_imports,
    no_existing_stats,
    no_throttle,
) -> None:
    """2 days × 24 h × 17 sensors = 816 stats written when prices are available."""
    system = mock_system_factory(system_id="sys-1")
    system.get_energy_historical.side_effect = lambda d, _e, _r: _day_payload(d)
    today = datetime.date.fromisoformat("2026-05-14")
    days = [today - datetime.timedelta(days=i) for i in (1, 2)]
    system.get_prices.return_value = _market_prices_for(days)
    await _setup(hass, system)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch("custom_components.onekommafive.services.dt_util") as mock_dt:
        mock_dt.utcnow.return_value = datetime.datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        await hass.services.async_call(
            DOMAIN,
            "import_history",
            {"days_back": 2, "config_entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
        )

    # 10 kWh + 1 derived consumption + 1 SoC + 5 cost + 1 revenue = 17 sensors
    sensors_written = {sid: len(s) for sid, s in captured_imports}
    assert len(sensors_written) == 17, sensors_written
    assert all(count == 48 for count in sensors_written.values())


async def test_import_history_walk_back_stops_at_empty_days(
    hass: HomeAssistant,
    mock_system_factory,
    captured_imports,
    no_existing_stats,
    no_throttle,
) -> None:
    """Walk-back stops after 7 consecutive empty days; reports `days_walked` of valid days."""
    system = mock_system_factory(system_id="sys-1")
    today = datetime.date.fromisoformat("2026-05-14")

    def _by_day(d, _e, _r):
        # Days within [today-3, today-1] are valid; older returns empty
        if today - datetime.timedelta(days=3) <= d < today:
            return _day_payload(d)
        return _empty_payload()

    system.get_energy_historical.side_effect = _by_day
    await _setup(hass, system)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch("custom_components.onekommafive.services.dt_util") as mock_dt:
        mock_dt.utcnow.return_value = datetime.datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        response = await hass.services.async_call(
            DOMAIN,
            "import_history",
            {"config_entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
        )

    assert response["days_walked"] == 3  # valid days collected
    assert response["failed_days"] == []


async def test_import_history_walk_back_outage_tolerance(
    hass: HomeAssistant,
    mock_system_factory,
    captured_imports,
    no_existing_stats,
    no_throttle,
) -> None:
    """A 6-day outage in the middle is tolerated (under the 7-day threshold)."""
    system = mock_system_factory(system_id="sys-1")
    today = datetime.date.fromisoformat("2026-05-14")
    valid_days = {
        # Recent 5 days: valid
        today - datetime.timedelta(days=i)
        for i in range(1, 6)
    } | {
        # 6-day gap days 6..11 are empty
        # Then valid again days 12..16
        today - datetime.timedelta(days=i)
        for i in range(12, 17)
    }

    def _by_day(d, _e, _r):
        return _day_payload(d) if d in valid_days else _empty_payload()

    system.get_energy_historical.side_effect = _by_day
    await _setup(hass, system)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch("custom_components.onekommafive.services.dt_util") as mock_dt:
        mock_dt.utcnow.return_value = datetime.datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        response = await hass.services.async_call(
            DOMAIN,
            "import_history",
            {"config_entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
        )

    # 5 recent + 5 older = 10 valid days walked
    assert response["days_walked"] == 10


async def test_import_history_one_failing_day_bounded(
    hass: HomeAssistant,
    mock_system_factory,
    captured_imports,
    no_existing_stats,
    no_throttle,
) -> None:
    """A non-4xx exception for one day → logged, walk continues, listed in `failed_days`."""
    system = mock_system_factory(system_id="sys-1")
    today = datetime.date.fromisoformat("2026-05-14")
    target_fail = today - datetime.timedelta(days=2)

    def _by_day(d, _e, _r):
        if d == target_fail:
            raise RuntimeError("simulated transient error")
        return _day_payload(d)

    system.get_energy_historical.side_effect = _by_day
    await _setup(hass, system)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch("custom_components.onekommafive.services.dt_util") as mock_dt:
        mock_dt.utcnow.return_value = datetime.datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        response = await hass.services.async_call(
            DOMAIN,
            "import_history",
            {"days_back": 3, "config_entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
        )

    assert response["failed_days"] == [target_fail.isoformat()]
    assert response["days_walked"] == 2  # 3 days requested, 1 failed


# ----------------------------------------------------------------------------
# clear_history
# ----------------------------------------------------------------------------


async def test_cost_invariant_sum_equals_total_per_hour(
    hass: HomeAssistant,
    mock_system_factory,
    captured_imports,
    no_existing_stats,
    no_throttle,
) -> None:
    """`heat_pump + ev_charger + household + ac == electricity_cost` per hour."""
    system = mock_system_factory(system_id="sys-1")
    system.get_energy_historical.side_effect = lambda d, _e, _r: _day_payload(d)
    today = datetime.date.fromisoformat("2026-05-14")
    days = [today - datetime.timedelta(days=1)]
    system.get_prices.return_value = _market_prices_for(days, price=0.25)
    await _setup(hass, system)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch("custom_components.onekommafive.services.dt_util") as mock_dt:
        mock_dt.utcnow.return_value = datetime.datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        await hass.services.async_call(
            DOMAIN,
            "import_history",
            {"days_back": 1, "config_entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
        )

    # Pull stats per sensor key from captured imports
    def diffs_for(suffix: str) -> list[float]:
        for sid, stats in captured_imports:
            if sid.endswith(suffix):
                return _consecutive_diffs(stats)
        raise AssertionError(f"Sensor ending in {suffix!r} not written")

    total = diffs_for("_electricity_cost")
    parts_per_hour = [
        sum(p)
        for p in zip(
            diffs_for("_heat_pump_cost"),
            diffs_for("_ev_charger_cost"),
            diffs_for("_household_cost"),
            diffs_for("_ac_cost"),
            strict=True,
        )
    ]
    # 24 stat entries → 23 consecutive diffs
    assert len(total) == 23
    for t, p in zip(total, parts_per_hour, strict=True):
        assert p == pytest.approx(t, abs=1e-9)


async def test_missing_price_hour_skips_cost_only(
    hass: HomeAssistant,
    mock_system_factory,
    captured_imports,
    no_existing_stats,
    no_throttle,
) -> None:
    """A price gap → cost sensors skip that hour; energy sensors unaffected."""
    system = mock_system_factory(system_id="sys-1")
    system.get_energy_historical.side_effect = lambda d, _e, _r: _day_payload(d)
    today = datetime.date.fromisoformat("2026-05-14")
    days = [today - datetime.timedelta(days=1)]

    # Build a price dict missing hour 12 specifically
    price_dict: dict[str, float] = {}
    target_day = days[0]
    for h in range(24):
        if h == 12:
            continue
        price_dict[f"{target_day.isoformat()}T{h:02d}:00Z"] = 0.30
    system.get_prices.return_value = MagicMock(prices_with_grid_costs_and_vat=price_dict)

    await _setup(hass, system)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch("custom_components.onekommafive.services.dt_util") as mock_dt:
        mock_dt.utcnow.return_value = datetime.datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        await hass.services.async_call(
            DOMAIN,
            "import_history",
            {"days_back": 1, "config_entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
        )

    counts = {sid: len(stats) for sid, stats in captured_imports}
    # Cost sensors: 24 - 1 = 23 hours
    for suffix in (
        "_electricity_cost",
        "_heat_pump_cost",
        "_ev_charger_cost",
        "_household_cost",
        "_ac_cost",
    ):
        matched = next(c for sid, c in counts.items() if sid.endswith(suffix))
        assert matched == 23, f"{suffix}: {matched}"
    # An energy sensor (PV) is unaffected: full 24 hours
    pv_count = next(c for sid, c in counts.items() if sid.endswith("_pv_energy"))
    assert pv_count == 24


def _consecutive_diffs(stats: list) -> list[float]:
    """Differences between consecutive cumulative sums.

    Returns ``N-1`` values for ``N`` input entries; the first sum is the
    anchor offset (not a real per-bucket delta) and is dropped.
    """
    return [stats[i]["sum"] - stats[i - 1]["sum"] for i in range(1, len(stats))]


async def test_clear_history_requires_confirm(hass: HomeAssistant, mock_system_factory) -> None:
    """Without `confirm: true` the service raises and clears nothing."""
    system = mock_system_factory(system_id="sys-1")
    await _setup(hass, system)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with pytest.raises(HomeAssistantError, match="confirm=true"):
        await hass.services.async_call(
            DOMAIN,
            "clear_history",
            {"confirm": False, "config_entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
        )


async def test_clear_history_calls_recorder(hass: HomeAssistant, mock_system_factory) -> None:
    """With `confirm: true` the recorder's clear is called with the integration's stat IDs."""
    system = mock_system_factory(system_id="sys-1")
    await _setup(hass, system)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with patch(
        "custom_components.onekommafive.services.get_recorder_instance"
    ) as mock_get_instance:
        recorder = MagicMock()
        mock_get_instance.return_value = recorder

        response = await hass.services.async_call(
            DOMAIN,
            "clear_history",
            {"confirm": True, "config_entry_id": entry.entry_id},
            blocking=True,
            return_response=True,
        )

    # Returned shape
    assert response["cleared"] == len(response["statistic_ids"])
    # All returned IDs should be sensor-domain entities created by the integration
    assert all(sid.startswith("sensor.") for sid in response["statistic_ids"])
    # If at least one entity was registered, the recorder should have been called
    if response["cleared"] > 0:
        recorder.async_clear_statistics.assert_called_once()
        called_ids = recorder.async_clear_statistics.call_args[0][0]
        assert set(called_ids) == set(response["statistic_ids"])
        # Should not exceed the set of keys the integration owns
        assert len(called_ids) <= len(ALL_STATISTIC_KEYS)
