"""Tier-2 test for the SDK v0.4.0 Heartbeat-gateway diagnostics block.

Sub-device presentation was rolled back before the v0.1.60 release: an
empty sub-device (no entities) rendered as an empty tile in the HA
devices view. The diagnostics block stays because it carries real
support value (type / installer / installation date, PII-safe).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
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


async def test_diagnostics_includes_gateways_pii_safe(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """The diagnostics dump surfaces type / installer_name / installation_date
    but keeps ids and every GridX identifier out."""
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
