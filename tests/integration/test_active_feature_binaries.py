"""Tier-2 tests for the per-feature active-feature binary sensors.

The counter sensor `active_features` (state = number, attribute = list)
is complemented by three Boolean entities so automations can gate on
`condition: state binary_sensor.X is on` without parsing attribute lists.
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


def _entity_id(hass: HomeAssistant, translation_key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", "onekommafive", f"sys-1_{translation_key}"
    )
    assert entity_id is not None, f"binary_sensor for {translation_key} not registered"
    return entity_id


async def test_all_three_features_active_yields_three_on(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """All three feature binaries report ON when the SDK lists all three flags."""
    system = mock_system_factory(
        system_id="sys-1",
        active_features=["DYNAMIC_TARIFF", "TIME_OF_USE_OPTIMIZATION", "SMART_CHARGING"],
    )
    await _setup(hass, system)

    for key in ("dynamic_tariff_active", "time_of_use_active", "smart_charging_active"):
        state = hass.states.get(_entity_id(hass, key))
        assert state.state == "on", f"{key} should be on, got {state.state}"


async def test_missing_features_flip_off(hass: HomeAssistant, mock_system_factory) -> None:
    """Only the features the SDK lists report ON; the others stay OFF."""
    system = mock_system_factory(
        system_id="sys-1",
        active_features=["DYNAMIC_TARIFF"],
    )
    await _setup(hass, system)

    assert hass.states.get(_entity_id(hass, "dynamic_tariff_active")).state == "on"
    assert hass.states.get(_entity_id(hass, "time_of_use_active")).state == "off"
    assert hass.states.get(_entity_id(hass, "smart_charging_active")).state == "off"


async def test_empty_feature_list_all_off(hass: HomeAssistant, mock_system_factory) -> None:
    """Empty active_features → all three binaries OFF."""
    system = mock_system_factory(system_id="sys-1", active_features=[])
    await _setup(hass, system)

    for key in ("dynamic_tariff_active", "time_of_use_active", "smart_charging_active"):
        state = hass.states.get(_entity_id(hass, key))
        assert state.state == "off"


async def test_legacy_counter_sensor_still_present(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """The existing `aktive_funktionen` counter stays — kept for backward compat."""
    system = mock_system_factory(
        system_id="sys-1",
        active_features=["DYNAMIC_TARIFF", "SMART_CHARGING"],
    )
    await _setup(hass, system)

    counter_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_active_features"
    )
    assert counter_id is not None
    assert hass.states.get(counter_id).state == "2"
