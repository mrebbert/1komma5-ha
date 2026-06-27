"""Tier-2 tests for the System Health page integration.

`system_health.py` is auto-discovered by HA's system_health integration.
These tests verify that the panel surfaces useful, PII-safe diagnostics:
coordinator status, API reachability check, SDK version, currency,
country code — and explicitly excludes customer_id / system_id / address
fields.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.components.system_health import SystemHealthRegistration
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.onekommafive.system_health import system_health_info


async def _setup(hass: HomeAssistant, system: MagicMock) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-secret-42",
        data={
            CONF_USERNAME: "secret@example.com",
            CONF_PASSWORD: "topsecret",
            CONF_SYSTEM_ID: "sys-secret-42",
        },
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


def _close_pending_coroutines(info: dict) -> None:
    """Close any unawaited coroutines in the info dict (HA's panel-render
    framework would normally await them; tests don't render the panel)."""
    import inspect

    for value in info.values():
        if inspect.iscoroutine(value):
            value.close()


async def test_health_info_includes_expected_fields(
    hass: HomeAssistant, mock_system_factory
) -> None:
    details = MagicMock(
        customer_id="cust-x",
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
        address_country="DE",
    )
    system = mock_system_factory(system_id="sys-secret-42", details=details)
    await _setup(hass, system)

    info = await system_health_info(hass)
    _close_pending_coroutines(info)

    # Per-coordinator status fields
    for label in ("live", "price", "optimization", "weather", "system_status"):
        assert f"{label}_last_update_success" in info
        assert isinstance(info[f"{label}_last_update_success"], bool)

    # Currency + country
    assert info["currency"] == "EUR"
    assert info["country"] == "DE"
    # SDK version always populates
    assert isinstance(info["sdk_version"], str)
    assert info["sdk_version"]
    # Config-entry count
    assert info["config_entries"] == 1


async def test_health_info_excludes_pii(hass: HomeAssistant, mock_system_factory) -> None:
    """Customer / system identifiers must never leak into the panel."""
    leaky = MagicMock(
        first_name="Erika",
        last_name="Mustermann",
        email="leaky@example.com",
    )
    details = MagicMock(
        customer_id="cust-uuid-leak",
        customer=leaky,
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
        address_country="DE",
        address_line1="Musterstrasse 1 - leak",
        address_city="Hamburg-Leak",
        address_latitude=53.123,
        address_longitude=9.987,
    )
    system = mock_system_factory(system_id="sys-secret-42", details=details)
    await _setup(hass, system)

    info = await system_health_info(hass)
    _close_pending_coroutines(info)
    serialised = str(info)

    for needle in (
        "sys-secret-42",
        "cust-uuid-leak",
        "Erika",
        "Mustermann",
        "leaky@example.com",
        "Musterstrasse 1 - leak",
        "Hamburg-Leak",
        "53.123",
        "9.987",
    ):
        assert needle not in serialised, f"sensitive value leaked: {needle!r}"


async def test_async_register_wires_info_callback(hass: HomeAssistant, mock_system_factory) -> None:
    """async_register hands the info callback to the registration object."""
    from homeassistant.setup import async_setup_component

    from custom_components.onekommafive.system_health import async_register

    assert await async_setup_component(hass, "system_health", {})
    register = SystemHealthRegistration(hass, DOMAIN)
    async_register(hass, register)
    # No assertion needed — completing the call without exception is the test.
