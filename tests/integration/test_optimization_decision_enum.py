"""Tier-2 test for the optimization_last_decision sensor's ENUM metadata.

Setting ``device_class=SensorDeviceClass.ENUM`` + ``options=[...]`` is what
lets HA translate state values via ``entity.sensor.<key>.state.<value>``.
Without these, ``state=BATTERY_CHARGE_FROM_GRID`` would be displayed
verbatim. This test pins both pieces of metadata.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]
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
        "battery_no_charge",
        "battery_no_discharge",
        "heatpump_recommend_on",
        "heatpump_auto",
    }
