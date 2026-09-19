"""Tier-2 tests for the Heartbeat-gateway sub-device introduced with SDK v0.4.0.

Single-gateway installs (GRIDX default) keep the static
``(DOMAIN, "sys-1_gateway")`` identifier so the translated
``device.gateway.name`` label surfaces.

Multi-gateway installs pick up an instance identifier per hardware and use
the installer name as label (no translation for instance keys).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _gateway(
    *,
    id_: str,
    type_: str = "GRIDX",
    installer_name: str | None = "1KOMMA5° Rheinland",
    installation_date: str | None = "2024-05-12",
) -> MagicMock:
    return MagicMock(
        id=id_,
        type=type_,
        installer_name=installer_name,
        installation_date=installation_date,
        serial_number="SN-must-not-leak",
        gridx_start_code="START-must-not-leak",
        gridx_system_id="GX-SYS-must-not-leak",
        gridx_gateway_id="GX-GW-must-not-leak",
        installer_id="INSTALLER-UUID-must-not-leak",
        claimed_by_user_id="USER-UUID-must-not-leak",
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


async def test_single_gateway_gets_static_sub_device_identifier(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """One gateway → static `(DOMAIN, "sys-1_gateway")` identifier."""
    system = mock_system_factory(
        system_id="sys-1",
        device_gateways=[_gateway(id_="gw-1")],
    )
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)

    devices = {
        next(iter(d.identifiers))[1]: d
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    }
    assert "sys-1_gateway" in devices
    assert "sys-1_gateway_gw-1" not in devices

    gw = devices["sys-1_gateway"]
    assert gw.manufacturer == "1KOMMA5°"
    assert gw.model == "GRIDX"
    assert gw.sw_version == "2024-05-12"
    # translation_key stays intact for the static single-gateway case
    assert gw.name is None or gw.name == "Heartbeat gateway"


async def test_multi_gateway_yields_instance_sub_devices(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Two gateways → two `sys-1_gateway_<id>` sub-devices, each with the
    installer name as label (no translation for instance keys)."""
    system = mock_system_factory(
        system_id="sys-1",
        device_gateways=[
            _gateway(id_="gw-a", installer_name="1KOMMA5° Rheinland"),
            _gateway(id_="gw-b", installer_name="1KOMMA5° Bayern"),
        ],
    )
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)

    devices = {
        next(iter(d.identifiers))[1]: d
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    }
    assert "sys-1_gateway_gw-a" in devices
    assert "sys-1_gateway_gw-b" in devices

    a = devices["sys-1_gateway_gw-a"]
    b = devices["sys-1_gateway_gw-b"]
    assert (a.manufacturer, a.model) == ("1KOMMA5°", "GRIDX")
    assert (b.manufacturer, b.model) == ("1KOMMA5°", "GRIDX")
    assert a.name == "1KOMMA5° Rheinland"
    assert b.name == "1KOMMA5° Bayern"


async def test_1k5_backend_without_gateway_creates_no_sub_device(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """1K5-native backend installs return an empty gateway list; no sub-device
    should appear."""
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(
            emp_type="1K5",
            customer_id="cust-uuid-1",
            device_gateways=[],
            address_country="DE",
        ),
        device_gateways=[],
    )
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)
    identifiers = {
        next(iter(d.identifiers))[1]
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    }
    assert "sys-1_gateway" not in identifiers
    assert not any(i.startswith("sys-1_gateway_") for i in identifiers)


async def test_diagnostics_includes_gateways_pii_safe(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """The diagnostics dump surfaces type / installer_name / installation_date
    but keeps ids and the GridX identifiers out."""
    from custom_components.onekommafive.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    system = mock_system_factory(
        system_id="sys-1",
        device_gateways=[
            _gateway(id_="gw-1", installer_name="1KOMMA5° Rheinland"),
        ],
    )
    entry = await _setup(hass, system)
    diag = await async_get_config_entry_diagnostics(hass, entry)

    block = diag["system"]["device_gateways"]
    assert block == [
        {
            "type": "GRIDX",
            "installer_name": "1KOMMA5° Rheinland",
            "installation_date": "2024-05-12",
        }
    ]
    # PII contract: nothing leaked into the diag payload.
    text = str(diag)
    for secret in (
        "SN-must-not-leak",
        "START-must-not-leak",
        "GX-SYS-must-not-leak",
        "GX-GW-must-not-leak",
        "INSTALLER-UUID-must-not-leak",
        "USER-UUID-must-not-leak",
    ):
        assert secret not in text
