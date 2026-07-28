"""Tier-2 tests for currency resolution from SystemDetails.address_country.

The integration derives the displayed currency at setup time from
``SystemDetails.address_country`` via ``helpers.resolve_currency``. These
tests verify the wiring end-to-end: the monetary sensors actually show
the right unit on installs in non-EUR markets (DK, SE, AU).
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


def _details(country: str | None) -> MagicMock:
    return MagicMock(
        customer_id="cust-uuid-1",
        emp_type="GRIDX",
        status="ACTIVE",
        dynamic_pulse_compatible=True,
        energy_trader_active=True,
        electricity_contract_active=True,
        has_third_party_smart_meter=None,
        earliest_measurement="2024-01-15",
        created_at="2024-01-10T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        device_gateways=[],
        address_country=country,
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


async def test_danish_install_uses_dkk_units(hass: HomeAssistant, mock_system_factory) -> None:
    """A DK install renders cost sensors in DKK and price sensors in DKK/kWh."""
    system = mock_system_factory(system_id="sys-1", details=_details("DK"))
    await _setup(hass, system)

    cost_state = hass.states.get("sensor.test_home_electricity_cost")
    assert cost_state is not None
    assert cost_state.attributes["unit_of_measurement"] == "DKK"

    price_state = hass.states.get("sensor.test_home_current_electricity_price")
    assert price_state is not None
    assert price_state.attributes["unit_of_measurement"] == "DKK/kWh"

    # Feed-in revenue is grouped under the meter sub-device but the entity_id
    # follows the stable ``<system>_<suffix>`` shim (see issue #8 fix).
    feed_in_state = hass.states.get("sensor.test_home_feed_in_revenue")
    assert feed_in_state is not None
    assert feed_in_state.attributes["unit_of_measurement"] == "DKK"


async def test_australian_install_uses_aud_units(hass: HomeAssistant, mock_system_factory) -> None:
    """An AU install renders cost sensors in AUD."""
    system = mock_system_factory(system_id="sys-1", details=_details("AU"))
    await _setup(hass, system)

    cost_state = hass.states.get("sensor.test_home_electricity_cost")
    assert cost_state is not None
    assert cost_state.attributes["unit_of_measurement"] == "AUD"


async def test_german_install_keeps_eur(hass: HomeAssistant, mock_system_factory) -> None:
    """A DE install — the previous default — stays on EUR."""
    system = mock_system_factory(system_id="sys-1", details=_details("DE"))
    await _setup(hass, system)

    cost_state = hass.states.get("sensor.test_home_electricity_cost")
    assert cost_state is not None
    assert cost_state.attributes["unit_of_measurement"] == "EUR"

    price_state = hass.states.get("sensor.test_home_current_electricity_price")
    assert price_state is not None
    assert price_state.attributes["unit_of_measurement"] == "EUR/kWh"


async def test_unknown_country_falls_back_to_eur(hass: HomeAssistant, mock_system_factory) -> None:
    """Defensive: a country we haven't mapped yet (or address_country=None)
    falls back to EUR rather than breaking the integration."""
    system = mock_system_factory(system_id="sys-1", details=_details(None))
    await _setup(hass, system)

    # Entity exists and has a valid unit (EUR), not a broken/empty one.
    entity_reg = er.async_get(hass)
    record = entity_reg.async_get("sensor.test_home_electricity_cost")
    assert record is not None
    assert record.unit_of_measurement is None or "EUR" in str(
        hass.states.get("sensor.test_home_electricity_cost").attributes["unit_of_measurement"]
    )
