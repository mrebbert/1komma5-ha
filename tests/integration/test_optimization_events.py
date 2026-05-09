"""Tier-2 tests for the ``onekommafive_optimization_decision`` bus event."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import Event, HomeAssistant, callback
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
    EVENT_OPTIMIZATION_DECISION,
)


def _build_event(
    *,
    asset: str = "BATTERY",
    decision: str = "BATTERY_CHARGE_FROM_GRID",
    from_time: str,
    to_time: str | None = None,
    market_price: float | None = 5.0,
    state_of_charge: int | None = 60,
) -> MagicMock:
    """Build a stub OptimizationEvent that the coordinator can introspect."""
    event = MagicMock(
        asset=asset,
        decision=decision,
        from_time=from_time,
        to_time=to_time or from_time.replace("00:00", "15:00"),
        timestamp=from_time,
        market_price=market_price,
        market_price_currency="EUR",
        state_of_charge=state_of_charge,
    )
    return event


@pytest.fixture
def captured_events(hass: HomeAssistant) -> list[Event]:
    """Subscribe to the bus event and return the growing list of fired events."""
    events: list[Event] = []

    @callback
    def _listener(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(EVENT_OPTIMIZATION_DECISION, _listener)
    return events


async def _setup_entry(
    hass: HomeAssistant,
    system: MagicMock,
    *,
    system_id: str = "sys-1",
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=system_id,
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: system_id},
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


async def test_first_refresh_fires_one_event_for_latest_decision(
    hass: HomeAssistant, mock_system_factory, captured_events
) -> None:
    """On the first refresh after startup we fire exactly one event — the latest."""
    older = _build_event(
        decision="BATTERY_NO_CHARGE",
        from_time="2026-05-08T08:00:00Z",
        to_time="2026-05-08T08:15:00Z",
        market_price=20.0,
    )
    newer = _build_event(
        decision="BATTERY_CHARGE_FROM_GRID",
        from_time="2026-05-08T10:00:00Z",
        to_time="2026-05-08T10:15:00Z",
        market_price=5.0,
    )
    optimizations = MagicMock(events=[older, newer])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)

    await _setup_entry(hass, system)

    assert len(captured_events) == 1
    assert captured_events[0].data["decision"] == "BATTERY_CHARGE_FROM_GRID"
    assert captured_events[0].data["from"] == "2026-05-08T10:00:00Z"
    assert captured_events[0].data["asset"] == "BATTERY"
    assert captured_events[0].data["market_price"] == 5.0


async def test_subsequent_refresh_fires_only_newer_events(
    hass: HomeAssistant, mock_system_factory, captured_events
) -> None:
    """A second refresh with one strictly newer event fires exactly that event."""
    initial = _build_event(
        decision="BATTERY_NO_CHARGE",
        from_time="2026-05-08T10:00:00Z",
        to_time="2026-05-08T10:15:00Z",
    )
    optimizations = MagicMock(events=[initial])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)

    entry = await _setup_entry(hass, system)
    assert len(captured_events) == 1  # initial bootstrap

    # Add a brand-new decision and refresh again
    newer = _build_event(
        decision="BATTERY_CHARGE_FROM_GRID",
        from_time="2026-05-08T10:15:00Z",
        to_time="2026-05-08T10:30:00Z",
    )
    optimizations.events = [initial, newer]

    await entry.runtime_data.optimization_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(captured_events) == 2
    assert captured_events[1].data["decision"] == "BATTERY_CHARGE_FROM_GRID"
    assert captured_events[1].data["from"] == "2026-05-08T10:15:00Z"


async def test_subsequent_refresh_without_new_events_fires_nothing(
    hass: HomeAssistant, mock_system_factory, captured_events
) -> None:
    """If the API returns the same set of events, no further bus event is fired."""
    initial = _build_event(
        decision="BATTERY_CHARGE_FROM_GRID",
        from_time="2026-05-08T10:00:00Z",
        to_time="2026-05-08T10:15:00Z",
    )
    optimizations = MagicMock(events=[initial])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)

    entry = await _setup_entry(hass, system)
    assert len(captured_events) == 1  # bootstrap

    # Same data — coordinator refresh should not duplicate
    await entry.runtime_data.optimization_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(captured_events) == 1
