"""Tier-2 tests for entities that surface `SystemDetails` fields.

Covers the three entities introduced for backlog items #1, #2, #3:

- ``binary_sensor.<sys>_energy_trader_active`` from ``SystemDetails.energy_trader_active``
- ``binary_sensor.<sys>_dynamic_pulse_compatible`` from ``SystemDetails.dynamic_pulse_compatible``
- ``sensor.<sys>_system_age_days`` derived from ``SystemDetails.earliest_measurement``

All three are populated once at setup (``SystemDetails`` is rarely-changing
metadata, fetched by ``get_details()``) — they don't track a coordinator's
data, but subscribe to the system-status coordinator so device parenting and
availability propagate from there.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from homeassistant.const import EntityCategory
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


def _resolve(hass: HomeAssistant, domain: str, suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, "onekommafive", f"sys-1_{suffix}")
    assert entity_id is not None, f"{domain}.<sys-1_{suffix}> not in registry"
    return entity_id


async def test_energy_trader_active_on(hass: HomeAssistant, mock_system_factory) -> None:
    """Binary sensor reflects `details.energy_trader_active=True`."""
    system = mock_system_factory(system_id="sys-1")  # default fixture has energy_trader_active=True
    await _setup(hass, system)
    state = hass.states.get(_resolve(hass, "binary_sensor", "energy_trader_active"))
    assert state is not None
    assert state.state == "on"


async def test_energy_trader_active_off(hass: HomeAssistant, mock_system_factory) -> None:
    """Binary sensor reflects `details.energy_trader_active=False`."""
    details = MagicMock(
        customer_id="cust-uuid-1",
        emp_type="GRIDX",
        status="ACTIVE",
        dynamic_pulse_compatible=True,
        energy_trader_active=False,
        electricity_contract_active=True,
        has_third_party_smart_meter=None,
        earliest_measurement="2024-01-15",
        created_at="2024-01-10T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        device_gateways=[],
    )
    system = mock_system_factory(system_id="sys-1", details=details)
    await _setup(hass, system)
    state = hass.states.get(_resolve(hass, "binary_sensor", "energy_trader_active"))
    assert state.state == "off"


async def test_dynamic_pulse_compatible_on(hass: HomeAssistant, mock_system_factory) -> None:
    """Binary sensor reflects `details.dynamic_pulse_compatible=True`."""
    system = mock_system_factory(system_id="sys-1")
    await _setup(hass, system)
    state = hass.states.get(_resolve(hass, "binary_sensor", "dynamic_pulse_compatible"))
    assert state.state == "on"


async def test_system_age_days_from_earliest_measurement(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """`sensor.<sys>_system_age_days` = days between today and earliest_measurement."""
    today = dt_util.now().date()
    start = today - timedelta(days=542)
    details = MagicMock(
        customer_id="cust-uuid-1",
        emp_type="GRIDX",
        status="ACTIVE",
        dynamic_pulse_compatible=True,
        energy_trader_active=True,
        electricity_contract_active=True,
        has_third_party_smart_meter=None,
        earliest_measurement=start.isoformat(),
        created_at="2024-01-10T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        device_gateways=[],
    )
    system = mock_system_factory(system_id="sys-1", details=details)
    await _setup(hass, system)
    state = hass.states.get(_resolve(hass, "sensor", "system_age_days"))
    assert state is not None
    assert state.state == "542"
    assert state.attributes.get("unit_of_measurement") == "d"


async def test_system_age_days_diagnostic_category(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """`system_age_days` lives under DIAGNOSTIC so it doesn't crowd the main device card."""
    system = mock_system_factory(system_id="sys-1")
    await _setup(hass, system)
    entity_id = _resolve(hass, "sensor", "system_age_days")
    entry = er.async_get(hass).async_get(entity_id)
    assert entry is not None
    assert entry.entity_category is EntityCategory.DIAGNOSTIC


async def test_details_none_yields_unknown(hass: HomeAssistant, mock_system_factory) -> None:
    """All three entities return ``unknown`` when details fetch failed (details=None)."""
    system = mock_system_factory(system_id="sys-1")
    system.get_details.side_effect = RuntimeError("simulated details fetch failure")
    await _setup(hass, system)
    for domain, suffix in (
        ("binary_sensor", "energy_trader_active"),
        ("binary_sensor", "dynamic_pulse_compatible"),
        ("sensor", "system_age_days"),
    ):
        state = hass.states.get(_resolve(hass, domain, suffix))
        assert state is not None, f"{domain}.<sys-1_{suffix}> missing"
        assert state.state == "unknown", f"{domain}.<sys-1_{suffix}> should be unknown"


async def test_system_age_days_invalid_earliest(hass: HomeAssistant, mock_system_factory) -> None:
    """Garbage in `earliest_measurement` → state is `unknown`, no exception bubbles."""
    details = MagicMock(
        customer_id="cust-uuid-1",
        emp_type="GRIDX",
        status="ACTIVE",
        dynamic_pulse_compatible=True,
        energy_trader_active=True,
        electricity_contract_active=True,
        has_third_party_smart_meter=None,
        earliest_measurement="not-a-date",
        created_at=None,
        updated_at=None,
        device_gateways=[],
    )
    system = mock_system_factory(system_id="sys-1", details=details)
    await _setup(hass, system)
    state = hass.states.get(_resolve(hass, "sensor", "system_age_days"))
    assert state.state == "unknown"


async def test_clamped_to_zero_if_future_date(hass: HomeAssistant, mock_system_factory) -> None:
    """earliest_measurement in the future (clock skew) → 0, not negative."""
    future = (dt_util.now().date() + timedelta(days=10)).isoformat()
    details = MagicMock(
        customer_id="cust-uuid-1",
        emp_type="GRIDX",
        status="ACTIVE",
        dynamic_pulse_compatible=True,
        energy_trader_active=True,
        electricity_contract_active=True,
        has_third_party_smart_meter=None,
        earliest_measurement=future,
        created_at=None,
        updated_at=None,
        device_gateways=[],
    )
    system = mock_system_factory(system_id="sys-1", details=details)
    await _setup(hass, system)
    state = hass.states.get(_resolve(hass, "sensor", "system_age_days"))
    assert state.state == "0"
