"""Tier-2 tests for the four optimization-decision binary sensors added in
v0.1.66: grid-discharge, no-charge, no-discharge (all on BATTERY), and
ev-grid-charge (on the EV asset / wallbox sub-device).

Each test pins ``ON`` for the matching decision; OFF for an unrelated
decision on the same asset is covered by the pre-existing
``test_heat_pump_recommendation`` pattern and the shared ``is_on``
implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.binary_sensor import (
    OPTIMIZATION_DECISION_SENSORS,
)
from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _event(asset: str, decision: str) -> MagicMock:
    """Build a single optimisation event covering 12:00–12:15 UTC."""
    return MagicMock(
        asset=asset,
        decision=decision,
        from_time="2026-05-14T12:00:00+00:00",
        to_time="2026-05-14T12:15:00+00:00",
        end_time="2026-05-14T12:15:00+00:00",
        slot_count=1,
        timestamp="2026-05-14T12:00:00+00:00",
        market_price=5.0,
        market_price_currency="EUR",
        state_of_charge=60,
    )


async def _setup(hass: HomeAssistant, system: MagicMock) -> MockConfigEntry:
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
        mock_systems_cls.return_value.get_system = AsyncMock(return_value=system)
        mock_systems_cls.return_value.get_systems = AsyncMock(return_value=[system])
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, key: str) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "binary_sensor", "onekommafive", f"sys-1_{key}"
    )
    assert entity_id is not None, f"{key} binary sensor not registered"
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


def test_six_decision_specs_registered() -> None:
    """OPTIMIZATION_DECISION_SENSORS carries the full six-decision set."""
    keys = {spec.key for spec in OPTIMIZATION_DECISION_SENSORS}
    assert keys == {
        "optimization_battery_grid_charge",
        "optimization_battery_grid_discharge",
        "optimization_battery_no_charge",
        "optimization_battery_no_discharge",
        "optimization_ev_grid_charge",
        "optimization_heat_pump_recommended",
    }


async def test_battery_grid_discharge_on(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    freezer.move_to("2026-05-14T12:07:00+00:00")
    optimizations = MagicMock(events=[_event("BATTERY", "BATTERY_DISCHARGE_TO_GRID")])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await _setup(hass, system)

    assert _state(hass, "optimization_battery_grid_discharge") == "on"


async def test_battery_no_charge_on(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    freezer.move_to("2026-05-14T12:07:00+00:00")
    optimizations = MagicMock(events=[_event("BATTERY", "BATTERY_NO_CHARGE")])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await _setup(hass, system)

    assert _state(hass, "optimization_battery_no_charge") == "on"


async def test_battery_no_discharge_on(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    freezer.move_to("2026-05-14T12:07:00+00:00")
    optimizations = MagicMock(events=[_event("BATTERY", "BATTERY_NO_DISCHARGE")])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await _setup(hass, system)

    assert _state(hass, "optimization_battery_no_discharge") == "on"


async def test_ev_grid_charge_on(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    freezer.move_to("2026-05-14T12:07:00+00:00")
    optimizations = MagicMock(events=[_event("EV", "EV_CHARGE_FROM_GRID")])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await _setup(hass, system)

    assert _state(hass, "optimization_ev_grid_charge") == "on"
