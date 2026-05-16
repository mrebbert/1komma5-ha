"""Tier-2 tests for the heat-pump recommendation binary sensor.

ON when the currently active HEATPUMP optimization event has
``decision == "HEATPUMP_RECOMMEND_ON"``; OFF for ``HEATPUMP_AUTO``;
OFF when no active HEATPUMP event exists.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _hp_event(decision: str, from_time: str, to_time: str) -> MagicMock:
    return MagicMock(
        asset="HEATPUMP",
        decision=decision,
        from_time=from_time,
        to_time=to_time,
        timestamp=from_time,
        market_price=5.0,
        market_price_currency="EUR",
        state_of_charge=None,
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
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _binary_state(hass: HomeAssistant, system_id: str = "sys-1") -> str:
    """Look the entity up by unique_id since entity_id is name-derived."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "binary_sensor", "onekommafive", f"{system_id}_optimization_heat_pump_recommended"
    )
    if entity_id is None:
        raise AssertionError("optimization_heat_pump_recommended binary sensor not registered")
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


async def test_heat_pump_on_when_recommend_on_active(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """ON if a HEATPUMP_RECOMMEND_ON event covers `now`."""
    freezer.move_to("2026-05-14T12:07:00+00:00")
    optimizations = MagicMock(
        events=[
            _hp_event(
                "HEATPUMP_RECOMMEND_ON",
                "2026-05-14T12:00:00+00:00",
                "2026-05-14T12:15:00+00:00",
            )
        ]
    )
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await _setup(hass, system)

    assert _binary_state(hass) == "on"


async def test_heat_pump_off_when_auto_active(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """OFF when the active HEATPUMP event has decision HEATPUMP_AUTO."""
    freezer.move_to("2026-05-14T12:07:00+00:00")
    optimizations = MagicMock(
        events=[
            _hp_event(
                "HEATPUMP_AUTO",
                "2026-05-14T12:00:00+00:00",
                "2026-05-14T12:15:00+00:00",
            )
        ]
    )
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await _setup(hass, system)

    assert _binary_state(hass) == "off"


async def test_heat_pump_off_when_no_event_in_window(
    hass: HomeAssistant, mock_system_factory, freezer
) -> None:
    """OFF when no HEATPUMP event covers `now` (only BATTERY exists)."""
    freezer.move_to("2026-05-14T12:07:00+00:00")
    optimizations = MagicMock(
        events=[
            MagicMock(
                asset="BATTERY",
                decision="BATTERY_CHARGE_FROM_GRID",
                from_time="2026-05-14T12:00:00+00:00",
                to_time="2026-05-14T12:15:00+00:00",
                timestamp="2026-05-14T12:00:00+00:00",
                market_price=5.0,
                market_price_currency="EUR",
                state_of_charge=60,
            )
        ]
    )
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await _setup(hass, system)

    assert _binary_state(hass) == "off"
