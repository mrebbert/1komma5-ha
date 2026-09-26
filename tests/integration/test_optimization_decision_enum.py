"""Tier-2 test for the optimization_last_decision sensor's ENUM metadata.

Setting ``device_class=SensorDeviceClass.ENUM`` + ``options=[...]`` is what
lets HA translate state values via ``entity.sensor.<key>.state.<value>``.
Without these, ``state=BATTERY_CHARGE_FROM_GRID`` would be displayed
verbatim. This test pins both pieces of metadata.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
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


async def test_last_decision_sensor_is_enum_with_known_options(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """device_class=ENUM + options is what makes HA translate the state."""
    system = mock_system_factory(system_id="sys-1")
    await _setup(hass, system)

    entity_reg = er.async_get(hass)
    entity_id = entity_reg.async_get_entity_id(
        "sensor", "onekommafive", "sys-1_optimization_last_decision"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    # ENUM device_class requires HA to surface the options list verbatim
    assert state.attributes["device_class"] == SensorDeviceClass.ENUM.value
    assert set(state.attributes["options"]) == {
        "battery_charge_from_grid",
        "battery_discharge_to_grid",
        "battery_no_charge",
        "battery_no_discharge",
        "ev_charge_from_grid",
        "heatpump_recommend_on",
        "heatpump_auto",
    }


async def test_unknown_decision_coerces_to_unknown_state(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Cloud may ship enum values not in our options list; the sensor must
    stay ``unknown`` instead of raising ValueError from HA's ENUM validation.

    Regression for a live report on 2026-09-11 where the sensor crashed on
    ``EV_CHARGE_FROM_GRID`` because the value was missing from the options.
    The fix hardens ``_coerce_known_decision`` so future new decisions
    degrade cleanly.
    """
    last_event = MagicMock(
        decision="TOTALLY_UNKNOWN_FUTURE_DECISION",
        asset="BATTERY",
        from_time="2026-09-11T09:00:00Z",
        to_time="2026-09-11T09:15:00Z",
        market_price=42.0,
        state_of_charge=50,
    )
    optimizations = MagicMock(events=[last_event])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await _setup(hass, system)

    entity_reg = er.async_get(hass)
    entity_id = entity_reg.async_get_entity_id(
        "sensor", "onekommafive", "sys-1_optimization_last_decision"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unknown"


async def test_battery_discharge_to_grid_is_known(hass: HomeAssistant, mock_system_factory) -> None:
    """Regression for issue #23 (2026-09-22): the cloud started emitting
    ``BATTERY_DISCHARGE_TO_GRID`` (battery trades energy back to the grid at
    high spot prices). The value must coerce to its lowercase key and land
    in the sensor state, not degrade to ``unknown``.
    """
    last_event = MagicMock(
        decision="BATTERY_DISCHARGE_TO_GRID",
        asset="BATTERY",
        from_time="2026-09-22T16:15:00Z",
        to_time="2026-09-22T16:30:00Z",
        market_price=448.625,
        state_of_charge=None,
    )
    optimizations = MagicMock(events=[last_event])
    system = mock_system_factory(system_id="sys-1", optimizations=optimizations)
    await _setup(hass, system)

    entity_reg = er.async_get(hass)
    entity_id = entity_reg.async_get_entity_id(
        "sensor", "onekommafive", "sys-1_optimization_last_decision"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "battery_discharge_to_grid"
