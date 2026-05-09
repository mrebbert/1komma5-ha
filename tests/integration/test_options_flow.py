"""Tier-2 tests for the integration's options flow (feed-in tariff)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_FEED_IN_TARIFF,
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DEFAULT_FEED_IN_TARIFF,
    DOMAIN,
)


async def _setup(hass: HomeAssistant, system) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-1",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-1"},
        options={CONF_FEED_IN_TARIFF: DEFAULT_FEED_IN_TARIFF},
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


async def test_options_flow_shows_current_tariff(hass: HomeAssistant, mock_system_factory) -> None:
    """Opening the options form pre-fills the current feed-in tariff."""
    entry = await _setup(hass, mock_system_factory(system_id="sys-1"))

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    # The schema's defaults expose the current value
    schema_keys = {key.schema: key.default() for key in result["data_schema"].schema}
    assert schema_keys[CONF_FEED_IN_TARIFF] == DEFAULT_FEED_IN_TARIFF


async def test_options_flow_persists_new_tariff(hass: HomeAssistant, mock_system_factory) -> None:
    """Submitting a new tariff persists it on the config entry."""
    system = mock_system_factory(system_id="sys-1")
    entry = await _setup(hass, system)

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_FEED_IN_TARIFF: 0.12},
        )
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert entry.options[CONF_FEED_IN_TARIFF] == 0.12


async def test_options_flow_rejects_out_of_range_tariff(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Values outside [0.0, 0.5] are rejected by the schema's voluptuous range."""
    entry = await _setup(hass, mock_system_factory(system_id="sys-1"))

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with pytest.raises((vol.Invalid, vol.MultipleInvalid)):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_FEED_IN_TARIFF: 0.6},
        )
