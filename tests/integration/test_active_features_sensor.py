"""Tier-2 tests for the active-features diagnostic sensor.

State = number of active feature flags; full list lives in the ``features``
attribute. Entity category is DIAGNOSTIC, so HA hides it from the main
device card by default.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.const import EntityCategory
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


def _resolve(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_active_features"
    )
    assert entity_id is not None
    return entity_id


async def test_state_is_feature_count_and_list_in_attribute(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        active_features=["DYNAMIC_TARIFF", "TIME_OF_USE_OPTIMIZATION", "SMART_CHARGING"],
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "3"
    assert state.attributes["features"] == [
        "DYNAMIC_TARIFF",
        "TIME_OF_USE_OPTIMIZATION",
        "SMART_CHARGING",
    ]


async def test_state_zero_when_no_features(hass: HomeAssistant, mock_system_factory) -> None:
    system = mock_system_factory(system_id="sys-1", active_features=[])
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass))
    assert state.state == "0"
    assert state.attributes["features"] == []


async def test_entity_category_is_diagnostic(hass: HomeAssistant, mock_system_factory) -> None:
    system = mock_system_factory(system_id="sys-1", active_features=["DYNAMIC_TARIFF"])
    await _setup(hass, system)

    registry = er.async_get(hass)
    entry = registry.async_get(_resolve(hass))
    assert entry is not None
    assert entry.entity_category is EntityCategory.DIAGNOSTIC
