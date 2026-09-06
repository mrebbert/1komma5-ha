"""Tier-2 tests for the diagnostics platform.

The diagnostics download is what bug reporters attach to issues, so the
contract here is:
1. credentials and the system_id must NOT appear in the output
2. all five coordinators are summarised
3. the dict is JSON-serialisable
4. PII / device secrets from the new ``system`` block stay redacted
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.onekommafive.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def _setup(hass: HomeAssistant, system) -> MockConfigEntry:
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


async def test_diagnostics_redacts_credentials_and_system_id(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Credentials and system_id must not leak into the diagnostics dump."""
    system = mock_system_factory(system_id="sys-secret-42")
    entry = await _setup(hass, system)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    serialised = json.dumps(diag)
    assert "secret@example.com" not in serialised
    assert "topsecret" not in serialised
    assert "sys-secret-42" not in serialised


async def test_diagnostics_includes_all_coordinators(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """All seven coordinator summaries are present with shape we expect."""
    system = mock_system_factory(system_id="sys-1")
    entry = await _setup(hass, system)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert set(diag["coordinators"]) == {
        "live",
        "price",
        "optimization",
        "weather",
        "system_status",
        "energy",
        "notifications",
    }
    for snap in diag["coordinators"].values():
        assert "last_update_success" in snap
        assert "update_interval_seconds" in snap
        assert "summary" in snap


async def test_diagnostics_system_block_excludes_pii_and_secrets(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """The new ``system`` block must never expose PII or device-coupling secrets.

    Specifically: customer name/email, addresses, lat/lon, gateway gridx
    start codes / serial numbers / IDs, asset serial numbers, asset network
    IPs, and asset opaque IDs all must be absent from the JSON dump.
    """
    customer = MagicMock(
        first_name="Erika",
        last_name="Mustermann-Should-Not-Leak",
        email="leaky@example.com",
    )
    gateway = MagicMock(
        id="gw-uuid-leak",
        gridx_start_code="hex-secret-leak",
        serial_number="I000-000-000-000-000-X-X-leak",
        installation_date="2024-01-15",
    )
    details = MagicMock(
        customer_id="cust-uuid-1",
        customer=customer,
        emp_type="GRIDX",
        status="ACTIVE",
        dynamic_pulse_compatible=True,
        energy_trader_active=True,
        electricity_contract_active=True,
        has_third_party_smart_meter=None,
        earliest_measurement="2024-01-15",
        created_at="2024-01-10T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        device_gateways=[gateway],
        address_line1="Musterstrasse 1 - leak",
        address_city="Hamburg-Leaky",
        address_longitude=53.123,
        address_latitude=9.987,
    )
    asset = MagicMock(
        id="asset-id-leak",
        type="EV_CHARGER",
        emp_type="GRIDX",
        name="Wallbox-Address-In-Name-leak",
        connection_status="CONNECTED",
        manufacturer="go-e",
        model="HOMEfix 11kW",
        serial_number="ev-serial-leak",
        firmware="55.6",
        network_address="192.168.13.37",
        heat_pump_meter_type=None,
    )
    system = mock_system_factory(
        system_id="sys-1",
        details=details,
        assets=[asset],
        active_features=["DYNAMIC_TARIFF"],
    )
    entry = await _setup(hass, system)

    diag = await async_get_config_entry_diagnostics(hass, entry)
    serialised = json.dumps(diag)

    # System block exists with both details and status_and_assets.
    assert "system" in diag
    assert diag["system"]["details"]["emp_type"] == "GRIDX"
    assert diag["system"]["details"]["earliest_measurement"] == "2024-01-15"
    assert diag["system"]["status_and_assets"]["site_status"] == "CONNECTED"
    assert diag["system"]["status_and_assets"]["active_features"] == ["DYNAMIC_TARIFF"]
    assets_out = diag["system"]["status_and_assets"]["assets"]
    assert len(assets_out) == 1
    assert assets_out[0]["manufacturer"] == "go-e"
    assert assets_out[0]["model"] == "HOMEfix 11kW"
    assert assets_out[0]["firmware"] == "55.6"

    # Everything sensitive must be filtered out of the serialised dump.
    for needle in (
        "Erika",
        "Mustermann-Should-Not-Leak",
        "leaky@example.com",
        "Musterstrasse 1 - leak",
        "Hamburg-Leaky",
        "53.123",
        "9.987",
        "gw-uuid-leak",
        "hex-secret-leak",
        "I000-000-000-000-000-X-X-leak",
        "asset-id-leak",
        "Wallbox-Address-In-Name-leak",
        "ev-serial-leak",
        "192.168.13.37",
    ):
        assert needle not in serialised, f"sensitive value leaked: {needle!r}"


async def test_diagnostics_is_json_serialisable(hass: HomeAssistant, mock_system_factory) -> None:
    """HA serialises diagnostics to JSON when the user downloads them."""
    system = mock_system_factory(system_id="sys-1")
    entry = await _setup(hass, system)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    # Must not raise.
    json.dumps(diag)
    assert diag["sdk_version"]  # version() returns a string for the installed SDK
