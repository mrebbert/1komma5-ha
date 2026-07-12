"""Tier-2 tests for the daily-savings sensor.

Surfaces ``EnergyData.savings_eur`` (cloud-computed daily savings, verified
populated on live data). Daily running total that resets at local midnight →
``state_class=TOTAL`` with ``last_reset`` pinned to the start of the local day.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
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


def _resolve(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_daily_savings"
    )
    assert entity_id is not None
    return entity_id


async def test_state_reflects_savings_eur(hass: HomeAssistant, mock_system_factory) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        energy=MagicMock(savings_eur=5.41, self_sufficiency=0.95, updated_at="2026-07-12T14:00Z"),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "5.41"
    assert state.attributes["device_class"] == SensorDeviceClass.MONETARY
    assert state.attributes["state_class"] == SensorStateClass.TOTAL


async def test_rounds_to_two_decimals(hass: HomeAssistant, mock_system_factory) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        energy=MagicMock(savings_eur=5.4149, self_sufficiency=0.9, updated_at=None),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "5.41"


async def test_none_savings_is_unknown(hass: HomeAssistant, mock_system_factory) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        energy=MagicMock(savings_eur=None, self_sufficiency=None, updated_at=None),
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "unknown"


async def test_last_reset_is_local_midnight(hass: HomeAssistant, mock_system_factory) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        energy=MagicMock(savings_eur=1.23, self_sufficiency=0.5, updated_at=None),
    )
    await _setup(hass, system)

    # last_reset is exposed via the entity object; assert it is today's local midnight.
    from custom_components.onekommafive import sensor_entities

    # Find the entity instance through the platform is overkill; verify the
    # property logic directly against the same dt helper the entity uses.
    expected = dt_util.start_of_local_day()
    sensor = sensor_entities.OneKomma5DailySavingsSensor.__new__(
        sensor_entities.OneKomma5DailySavingsSensor
    )
    assert sensor.last_reset == expected
