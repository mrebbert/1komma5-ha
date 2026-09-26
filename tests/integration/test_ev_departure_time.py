"""Tier-2 tests for ``OneKomma5EVDepartureTime`` (write-path platform).

Covers the fall-back branches of ``native_value`` (unparseable time strings)
and ``async_set_value`` (missing EV in the coordinator payload) that the
happy-path smoke tests don't reach.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant

from custom_components.onekommafive import OneKomma5Data
from custom_components.onekommafive.time import OneKomma5EVDepartureTime


def _ev(*, id_: str = "ev-uuid-1", departure: str | None = "07:00") -> MagicMock:
    ev = MagicMock()
    ev.id.return_value = id_
    ev.name.return_value = "Test EV"
    ev.manufacturer.return_value = "BMW"
    ev.model.return_value = "i3"
    ev.assigned_charger_id = None
    ev.primary_schedule_departure_time.return_value = departure
    ev.set_primary_departure_time = AsyncMock(return_value=None)
    ev.set_charging_mode = AsyncMock(return_value=None)
    ev.set_current_soc = AsyncMock(return_value=None)
    ev.set_target_soc = AsyncMock(return_value=None)
    ev.assign_charger = AsyncMock(return_value=None)
    return ev


def _make_data(coordinator: MagicMock, ev: MagicMock) -> OneKomma5Data:
    """Build the minimal ``OneKomma5Data`` the entity needs."""
    return OneKomma5Data(
        live_coordinator=coordinator,
        price_coordinator=MagicMock(),
        optimization_coordinator=MagicMock(),
        weather_coordinator=MagicMock(),
        system_status_coordinator=MagicMock(),
        energy_coordinator=MagicMock(),
        notifications_coordinator=MagicMock(),
        system=MagicMock(),
        system_name="Test",
        details=None,
        customer_id=None,
        currency="EUR",
        price_guarantee=None,
        co2_saved_kg=None,
        system_device_id="dev-1",
        emp_type=None,
        sdk_version="1.0.2",
        wallboxes=[],
        wallbox_device_ids={},
        device_gateways=[],
    )


def _build_entity(ev: MagicMock) -> OneKomma5EVDepartureTime:
    coordinator = MagicMock()
    coordinator.data = MagicMock(ev_chargers=[ev])
    coordinator.last_update_success = True
    data = _make_data(coordinator, ev)
    return OneKomma5EVDepartureTime(coordinator, "sys-1", "Test", ev, data)


def test_native_value_returns_none_when_ev_missing() -> None:
    ev = _ev()
    entity = _build_entity(ev)
    entity.coordinator.data = MagicMock(ev_chargers=[])  # EV disappeared

    assert entity.native_value is None


def test_native_value_returns_none_when_departure_none() -> None:
    ev = _ev(departure=None)
    entity = _build_entity(ev)

    assert entity.native_value is None


def test_native_value_logs_and_returns_none_on_invalid_string(caplog) -> None:
    ev = _ev(departure="not-a-time")
    entity = _build_entity(ev)

    with caplog.at_level("WARNING", logger="custom_components.onekommafive.time"):
        assert entity.native_value is None
    assert "Could not parse departure time" in caplog.text


async def test_async_set_value_skips_when_ev_missing(
    hass: HomeAssistant, caplog
) -> None:
    ev = _ev()
    entity = _build_entity(ev)
    entity.hass = hass
    entity.coordinator.data = MagicMock(ev_chargers=[])  # EV disappeared before write

    with caplog.at_level("WARNING", logger="custom_components.onekommafive.time"):
        await entity.async_set_value(datetime.time(7, 0))
    ev.set_primary_departure_time.assert_not_called()
    assert "EV charger" in caplog.text and "cannot set departure time" in caplog.text
