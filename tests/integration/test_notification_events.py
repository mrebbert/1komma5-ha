"""Tier-2 tests for the ``onekommafive_notification`` bus event.

The notifications coordinator polls `system.get_notifications()` and emits
one bus event per newly-observed notification (based on lexicographic
`created_at` comparison against a persistent sentinel stored via HA's
`Store` API). First refresh after a fresh install primes silently.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import Event, HomeAssistant, callback
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
    EVENT_NOTIFICATION,
)


def _notif(
    *,
    id: str,
    created_at: str,
    type: str = "ENERGY_MARKET_UPPER_TARGET_REACHED",
    title: str | None = "Energiepreise steigen",
    body: str | None = "Achtung! Preise um 22:00 auf 20 ct/kWh.",
    locale: str | None = "de",
    meta: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a stub Notification dataclass-like object the coordinator can walk."""
    return MagicMock(
        id=id,
        type=type,
        title=title,
        body=body,
        locale=locale,
        system_id="sys-1",
        created_at=created_at,
        read=True,
        dismissed=False,
        meta=meta or {"price": {"value": 20.4, "unit": "ct/kWh"}},
    )


@pytest.fixture
def captured_events(hass: HomeAssistant) -> list[Event]:
    """Subscribe to the notification bus event and return the growing list."""
    events: list[Event] = []

    @callback
    def _listener(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(EVENT_NOTIFICATION, _listener)
    return events


async def _setup_entry(
    hass: HomeAssistant,
    system: MagicMock,
    *,
    system_id: str = "sys-1",
    stored: dict | None = None,
) -> MockConfigEntry:
    """Bring the integration up with the given mock system, optionally pre-seeding Store."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=system_id,
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: system_id},
    )
    entry.add_to_hass(hass)
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
        patch("custom_components.onekommafive.coordinator.Store") as mock_store_cls,
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]
        # Fresh Store-backed sentinel — stored=None means "cold start, no
        # persisted state"; stored={...} pre-seeds the sentinel.
        store_instance = MagicMock()
        store_instance.async_load = AsyncMock(return_value=stored)
        store_instance.async_save = AsyncMock()
        mock_store_cls.return_value = store_instance
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        # Expose the store mock so tests can assert on save calls.
        entry.runtime_data.notifications_coordinator._store = store_instance
    return entry


async def test_first_refresh_primes_silently(
    hass: HomeAssistant, mock_system_factory, captured_events
) -> None:
    """Store empty + non-empty batch: no events fire; sentinel gets saved."""
    system = mock_system_factory(
        system_id="sys-1",
        notifications=[
            _notif(id="n1", created_at="2026-08-01T09:00:00Z"),
            _notif(id="n2", created_at="2026-08-01T10:00:00Z"),
            _notif(id="n3", created_at="2026-08-01T11:00:00Z"),
        ],
    )
    entry = await _setup_entry(hass, system, stored=None)

    assert captured_events == []
    # Sentinel saved with the max seen created_at
    save_mock = entry.runtime_data.notifications_coordinator._store.async_save
    save_mock.assert_awaited()
    args, _ = save_mock.await_args
    assert args[0] == {"last_seen_created_at": "2026-08-01T11:00:00Z"}


async def test_second_refresh_fires_only_new_item(
    hass: HomeAssistant, mock_system_factory, captured_events
) -> None:
    """After priming, a strictly-newer notification fires exactly one event."""
    system = mock_system_factory(
        system_id="sys-1",
        notifications=[
            _notif(id="n1", created_at="2026-08-01T09:00:00Z"),
            _notif(id="n2", created_at="2026-08-01T10:00:00Z"),
        ],
    )
    entry = await _setup_entry(hass, system, stored=None)
    # Prime pass produced 0 events (see prior test)
    assert captured_events == []

    # Change the batch to include an older + a strictly-newer notification.
    system.get_notifications.return_value = MagicMock(
        notifications=[
            _notif(id="n1", created_at="2026-08-01T09:00:00Z"),
            _notif(id="n2", created_at="2026-08-01T10:00:00Z"),
            _notif(
                id="n3",
                created_at="2026-08-01T12:00:00Z",
                type="ENERGY_MARKET_LOWER_TARGET_REACHED",
                title="Preise fallen",
                body="Gute Nachrichten!",
                meta={"price": {"value": -0.5, "unit": "ct/kWh"}},
            ),
        ]
    )
    await entry.runtime_data.notifications_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(captured_events) == 1
    e = captured_events[0]
    assert e.data["notification_id"] == "n3"
    assert e.data["type"] == "ENERGY_MARKET_LOWER_TARGET_REACHED"
    assert e.data["title"] == "Preise fallen"
    assert e.data["body"] == "Gute Nachrichten!"
    assert e.data["locale"] == "de"
    assert e.data["meta"]["price"]["value"] == -0.5
    assert e.data["system_id"] == "sys-1"
    assert e.data["created_at"] == "2026-08-01T12:00:00Z"


async def test_no_change_no_event(
    hass: HomeAssistant, mock_system_factory, captured_events
) -> None:
    """Refresh returning the same batch fires nothing."""
    batch = [
        _notif(id="n1", created_at="2026-08-01T09:00:00Z"),
        _notif(id="n2", created_at="2026-08-01T10:00:00Z"),
    ]
    system = mock_system_factory(system_id="sys-1", notifications=batch)
    entry = await _setup_entry(hass, system, stored=None)
    assert captured_events == []

    # Same batch, second refresh — no strictly-newer items.
    await entry.runtime_data.notifications_coordinator.async_refresh()
    await hass.async_block_till_done()
    assert captured_events == []


async def test_persistent_dedup_across_restart(
    hass: HomeAssistant, mock_system_factory, captured_events
) -> None:
    """Pre-seeded Store: notifications older-or-equal to sentinel don't re-fire."""
    system = mock_system_factory(
        system_id="sys-1",
        notifications=[
            _notif(id="n1", created_at="2026-08-01T09:00:00Z"),
            _notif(id="n2", created_at="2026-08-01T10:00:00Z"),
        ],
    )
    # Sentinel already at 10:00 — nothing in the batch is strictly newer.
    await _setup_entry(hass, system, stored={"last_seen_created_at": "2026-08-01T10:00:00Z"})
    assert captured_events == []


async def test_created_at_none_is_skipped(
    hass: HomeAssistant, mock_system_factory, captured_events
) -> None:
    """A notification without a created_at field is silently ignored, no crash."""
    system = mock_system_factory(
        system_id="sys-1",
        notifications=[_notif(id="n_broken", created_at=None)],
    )
    await _setup_entry(hass, system, stored=None)
    assert captured_events == []


async def test_multiple_new_items_fire_in_temporal_order(
    hass: HomeAssistant, mock_system_factory, captured_events
) -> None:
    """When several notifications are strictly newer, events fire oldest-first."""
    system = mock_system_factory(
        system_id="sys-1",
        notifications=[_notif(id="n1", created_at="2026-08-01T09:00:00Z")],
    )
    entry = await _setup_entry(hass, system, stored=None)
    assert captured_events == []

    # Add three strictly-newer notifications; expect three events in ascending order.
    system.get_notifications.return_value = MagicMock(
        notifications=[
            _notif(id="n1", created_at="2026-08-01T09:00:00Z"),
            _notif(id="n3", created_at="2026-08-01T12:00:00Z"),
            _notif(id="n2", created_at="2026-08-01T10:00:00Z"),
            _notif(id="n4", created_at="2026-08-01T14:00:00Z"),
        ]
    )
    await entry.runtime_data.notifications_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert [e.data["notification_id"] for e in captured_events] == ["n2", "n3", "n4"]
