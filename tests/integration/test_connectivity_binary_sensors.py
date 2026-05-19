"""Tier-2 tests for the site + per-asset-type connectivity binary sensors.

- The site_connected sensor is always registered.
- The four per-asset-type sensors are registered ONLY when an asset of that
  type was observed in the first refresh (dynamic inventory). This keeps
  the device page clean on installs without e.g. a heat pump.
- AND-logic: when more than one asset of the same type exists, the sensor
  is ON only if **all** of them report CONNECTED.
- Attributes never expose Asset.id / name / serial_number / network_address.
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


def _asset(
    asset_type: str,
    *,
    connection_status: str = "CONNECTED",
    manufacturer: str = "Acme",
    model: str = "X1",
    firmware: str = "1.0",
    name: str = "must-not-leak",
    asset_id: str = "id-must-not-leak",
    serial_number: str = "serial-must-not-leak",
    network_address: str = "ip-must-not-leak",
) -> MagicMock:
    return MagicMock(
        id=asset_id,
        type=asset_type,
        connection_status=connection_status,
        manufacturer=manufacturer,
        model=model,
        firmware=firmware,
        name=name,
        serial_number=serial_number,
        network_address=network_address,
        heat_pump_meter_type=None,
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


def _resolve(hass: HomeAssistant, unique_suffix: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        "binary_sensor", "onekommafive", f"sys-1_{unique_suffix}"
    )


async def test_full_inventory_registers_all_five_sensors(
    hass: HomeAssistant, mock_system_factory
) -> None:
    assets = [
        _asset("HYBRID"),
        _asset("HEAT_PUMP"),
        _asset("METER"),
        _asset("EV_CHARGER"),
    ]
    system = mock_system_factory(system_id="sys-1", assets=assets)
    await _setup(hass, system)

    for suffix in (
        "site_connected",
        "inverter_connected",
        "heat_pump_connected",
        "meter_connected",
        "wallbox_connected",
    ):
        assert _resolve(hass, suffix) is not None, f"missing sensor: {suffix}"


async def test_partial_inventory_skips_missing_asset_types(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """No heat pump in the API → no heat-pump connectivity sensor."""
    system = mock_system_factory(system_id="sys-1", assets=[_asset("HYBRID"), _asset("METER")])
    await _setup(hass, system)

    assert _resolve(hass, "site_connected") is not None
    assert _resolve(hass, "inverter_connected") is not None
    assert _resolve(hass, "meter_connected") is not None
    assert _resolve(hass, "heat_pump_connected") is None
    assert _resolve(hass, "wallbox_connected") is None


async def test_empty_inventory_still_registers_site_sensor(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(system_id="sys-1", assets=[])
    await _setup(hass, system)

    assert _resolve(hass, "site_connected") is not None
    assert _resolve(hass, "inverter_connected") is None


async def test_site_disconnected_flips_sensor_off(hass: HomeAssistant, mock_system_factory) -> None:
    system = mock_system_factory(
        system_id="sys-1", site_status="DISCONNECTED", assets=[_asset("HYBRID")]
    )
    await _setup(hass, system)

    entity_id = _resolve(hass, "site_connected")
    assert hass.states.get(entity_id).state == "off"


async def test_asset_disconnected_flips_matching_sensor_off(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("EV_CHARGER", connection_status="DISCONNECTED")],
    )
    await _setup(hass, system)

    entity_id = _resolve(hass, "wallbox_connected")
    assert hass.states.get(entity_id).state == "off"


async def test_and_logic_for_multiple_assets_of_same_type(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Two wallboxes, one disconnected → sensor OFF."""
    system = mock_system_factory(
        system_id="sys-1",
        assets=[
            _asset("EV_CHARGER", connection_status="CONNECTED", manufacturer="A"),
            _asset("EV_CHARGER", connection_status="DISCONNECTED", manufacturer="B"),
        ],
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass, "wallbox_connected"))
    assert state.state == "off"
    assert state.attributes["count"] == 2
    assert state.attributes["connected_count"] == 1


async def test_attributes_redact_sensitive_asset_fields(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """manufacturer/model/firmware/connection_status are exposed;
    id, name, serial_number and network_address must not appear."""
    system = mock_system_factory(
        system_id="sys-1",
        assets=[
            _asset(
                "EV_CHARGER",
                manufacturer="go-e",
                model="HOMEfix 11kW",
                firmware="55.6",
                asset_id="opaque-uuid-must-not-leak",
                name="address-must-not-leak",
                serial_number="EV-SERIAL-must-not-leak",
                network_address="192.168.42.42",
            )
        ],
    )
    await _setup(hass, system)

    state = hass.states.get(_resolve(hass, "wallbox_connected"))
    assets_attr = state.attributes["assets"]
    assert assets_attr == [
        {
            "manufacturer": "go-e",
            "model": "HOMEfix 11kW",
            "firmware": "55.6",
            "connection_status": "CONNECTED",
        }
    ]
    # Hard sanity check via dict serialisation: none of the secret values
    # should appear anywhere in the rendered attribute payload.
    rendered = str(dict(state.attributes))
    for needle in (
        "opaque-uuid-must-not-leak",
        "address-must-not-leak",
        "EV-SERIAL-must-not-leak",
        "192.168.42.42",
    ):
        assert needle not in rendered, f"leaked: {needle}"
