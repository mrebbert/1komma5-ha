"""Tier-2 tests for the EV Number entity's fall-back branches.

Covers ``native_value`` / ``available`` when the EV disappears from the
coordinator payload and ``async_set_native_value`` when the write is issued
against a missing EV.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant

from custom_components.onekommafive import OneKomma5Data
from custom_components.onekommafive.number import (
    EV_NUMBERS,
    OneKomma5EVNumber,
)


def _ev() -> MagicMock:
    from onekommafive.models import ChargingMode

    ev = MagicMock()
    ev.id.return_value = "ev-uuid-1"
    ev.name.return_value = "Test EV"
    ev.manufacturer.return_value = "BMW"
    ev.model.return_value = "i3"
    ev.assigned_charger_id = None
    ev.charging_mode.return_value = ChargingMode.SMART_CHARGE
    ev.target_soc.return_value = 80.0
    ev.current_soc.return_value = 50.0
    ev.set_target_soc = AsyncMock(return_value=None)
    ev.set_current_soc = AsyncMock(return_value=None)
    ev.set_primary_departure_time = AsyncMock(return_value=None)
    ev.set_charging_mode = AsyncMock(return_value=None)
    ev.assign_charger = AsyncMock(return_value=None)
    return ev


def _make_data(coordinator: MagicMock) -> OneKomma5Data:
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


def _build_entity(ev: MagicMock) -> OneKomma5EVNumber:
    coordinator = MagicMock()
    coordinator.data = MagicMock(ev_chargers=[ev])
    coordinator.last_update_success = True
    data = _make_data(coordinator)
    return OneKomma5EVNumber(
        coordinator,
        "sys-1",
        "Test",
        ev,
        EV_NUMBERS[1],
        data,  # target_soc description
    )


def test_native_value_returns_none_when_ev_missing() -> None:
    ev = _ev()
    entity = _build_entity(ev)
    entity.coordinator.data = MagicMock(ev_chargers=[])

    assert entity.native_value is None


def test_available_false_when_ev_missing() -> None:
    ev = _ev()
    entity = _build_entity(ev)
    entity.coordinator.data = MagicMock(ev_chargers=[])

    assert entity.available is False


async def test_async_set_native_value_skips_when_ev_missing(
    hass: HomeAssistant, caplog
) -> None:
    ev = _ev()
    entity = _build_entity(ev)
    entity.hass = hass
    entity.coordinator.data = MagicMock(ev_chargers=[])

    with caplog.at_level("WARNING", logger="custom_components.onekommafive.number"):
        await entity.async_set_native_value(75.0)
    ev.set_target_soc.assert_not_called()
    assert "cannot set" in caplog.text
