"""Tier-2 tests for multi-wallbox sub-devices + vehicle pairing (phase 2).

Two orthogonal behaviours the integration must preserve:

1. **Single-wallbox compat.** When exactly one ``EV_CHARGER`` asset is
   present the sub-device keeps the historical identifier
   ``(DOMAIN, f"{system_id}_wallbox")`` — area assignments, device_registry
   entries and dashboards from pre-phase-2 installs must not shift.

2. **Multi-wallbox split.** When more than one wallbox is present, one
   sub-device per :class:`Wallbox` (keyed on ``wallbox_<Wallbox.id>``)
   with the wallbox's own manufacturer / model / firmware, and each
   vehicle (:class:`EVCharger`) parented via ``via_device_id`` on its
   paired wallbox sub-device (via ``assigned_charger_id``).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
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
    name: str | None = None,
    manufacturer: str = "go-e",
    model: str = "HOMEfix 11kW",
    firmware: str | None = "60.5",
    connection_status: str = "CONNECTED",
) -> MagicMock:
    # `name` is a Mock meta-attribute; assign it after construction so it
    # becomes a real attribute value instead of the Mock's own name.
    asset = MagicMock(
        type=asset_type,
        connection_status=connection_status,
        manufacturer=manufacturer,
        model=model,
        firmware=firmware,
    )
    asset.name = name
    return asset


def _wallbox(*, id_: str, name: str, assigned_ev_id: str | None = None) -> MagicMock:
    wallbox = MagicMock(id=id_, assigned_ev_id=assigned_ev_id)
    wallbox.name = name
    return wallbox


def _ev(*, id_: str, assigned_charger_id: str | None) -> MagicMock:
    from onekommafive.models import ChargingMode

    ev = MagicMock()
    ev.id.return_value = id_
    ev.manufacturer.return_value = "Volkswagen"
    ev.model.return_value = "ID.5"
    ev.assigned_charger_id = assigned_charger_id
    ev.charging_mode.return_value = ChargingMode.SOLAR_CHARGE
    ev.target_soc.return_value = 80.0
    ev.current_soc.return_value = 50.0
    ev.capacity_wh.return_value = 77000.0
    ev.primary_schedule_departure_soc.return_value = 100.0
    ev.primary_schedule_departure_time.return_value = "07:00"
    return ev


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


async def test_single_wallbox_keeps_historical_sub_device_identifier(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Compat frontier: one wallbox → identifier stays `(DOMAIN, "sys-1_wallbox")`.

    This is the load-bearing invariant of phase 2. Existing installs (the
    overwhelming majority) must not see their wallbox sub-device change
    identity — that would drop area assignments and rename the device in
    every existing dashboard.
    """
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("EV_CHARGER", name="Wallbox")],
        wallboxes=[_wallbox(id_="wb-1", name="Wallbox")],
    )
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)

    devices = dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    identifiers = {next(iter(d.identifiers))[1] for d in devices}

    assert "sys-1_wallbox" in identifiers
    assert "sys-1_wallbox_wb-1" not in identifiers


async def test_multi_wallbox_yields_instance_sub_devices(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Two wallboxes → two `sys-1_wallbox_<id>` sub-devices, each with its
    own manufacturer / model / firmware from the matching Asset payload."""
    system = mock_system_factory(
        system_id="sys-1",
        assets=[
            _asset(
                "EV_CHARGER", name="Garage", manufacturer="go-e", model="HOMEfix", firmware="60.5"
            ),
            _asset(
                "EV_CHARGER",
                name="Carport",
                manufacturer="Enphase",
                model="EVSE_IQ2",
                firmware="1.2.3",
            ),
        ],
        wallboxes=[
            _wallbox(id_="wb-a", name="Garage"),
            _wallbox(id_="wb-b", name="Carport"),
        ],
    )
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)

    devices = {
        next(iter(d.identifiers))[1]: d
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    }

    assert "sys-1_wallbox_wb-a" in devices
    assert "sys-1_wallbox_wb-b" in devices
    # The aggregate `sys-1_wallbox` sub-device also stays: aggregate sensors
    # (`ev_chargers_power`, `ev_charger_cost`, `wallbox_connected`) are not
    # bound to a specific wallbox — they parent on the aggregate sub-device.
    # Instance sub-devices carry the per-hardware DeviceInfo and the paired
    # vehicles.
    assert "sys-1_wallbox" in devices

    a = devices["sys-1_wallbox_wb-a"]
    b = devices["sys-1_wallbox_wb-b"]
    assert (a.manufacturer, a.model, a.sw_version) == ("go-e", "HOMEfix", "60.5")
    assert (b.manufacturer, b.model, b.sw_version) == ("Enphase", "EVSE_IQ2", "1.2.3")
    # Wallbox.name is used as the display label on multi-wallbox instances
    # (no translation for dynamic keys).
    assert a.name == "Garage"
    assert b.name == "Carport"


async def test_vehicle_parents_under_paired_wallbox(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Vehicle A ↔ Wallbox A, Vehicle B ↔ Wallbox B; each vehicle sub-
    device via_device_ids onto its paired wallbox."""
    system = mock_system_factory(
        system_id="sys-1",
        assets=[
            _asset("EV_CHARGER", name="Garage"),
            _asset("EV_CHARGER", name="Carport"),
        ],
        wallboxes=[
            _wallbox(id_="wb-a", name="Garage", assigned_ev_id="ev-a"),
            _wallbox(id_="wb-b", name="Carport", assigned_ev_id="ev-b"),
        ],
        ev_chargers=[
            _ev(id_="ev-a", assigned_charger_id="wb-a"),
            _ev(id_="ev-b", assigned_charger_id="wb-b"),
        ],
    )
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)

    devices = {
        next(iter(d.identifiers))[1]: d
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    }
    wb_a = devices["sys-1_wallbox_wb-a"]
    wb_b = devices["sys-1_wallbox_wb-b"]
    vehicle_a = devices["sys-1_ev-a"]
    vehicle_b = devices["sys-1_ev-b"]

    identifiers_by_id = {d.id: next(iter(d.identifiers))[1] for d in devices.values()}
    assert vehicle_a.via_device_id == wb_a.id, (
        f"vehicle A parents on {identifiers_by_id.get(vehicle_a.via_device_id, vehicle_a.via_device_id)!r}, expected wb-a"
    )
    assert vehicle_b.via_device_id == wb_b.id, (
        f"vehicle B parents on {identifiers_by_id.get(vehicle_b.via_device_id, vehicle_b.via_device_id)!r}, expected wb-b"
    )


async def test_unpaired_vehicle_falls_back_to_system_parent(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Vehicle without assigned_charger_id → parents on the system device,
    not on any wallbox sub-device."""
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("EV_CHARGER", name="Wallbox")],
        wallboxes=[_wallbox(id_="wb-1", name="Wallbox", assigned_ev_id=None)],
        ev_chargers=[_ev(id_="ev-orphan", assigned_charger_id=None)],
    )
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)

    devices = {
        next(iter(d.identifiers))[1]: d
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    }
    parent = devices["sys-1"]
    vehicle = devices["sys-1_ev-orphan"]
    assert vehicle.via_device_id == parent.id


async def test_vehicle_entities_unique_ids_are_unchanged_across_wallbox_split(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Sub-device split must NOT rewrite Vehicle-Entity unique_ids — that
    would drop long-term statistics history for the charging-mode select,
    target-SoC number, departure-time control and vehicle sensors."""
    system = mock_system_factory(
        system_id="sys-1",
        assets=[
            _asset("EV_CHARGER", name="Garage"),
            _asset("EV_CHARGER", name="Carport"),
        ],
        wallboxes=[
            _wallbox(id_="wb-a", name="Garage", assigned_ev_id="ev-a"),
            _wallbox(id_="wb-b", name="Carport", assigned_ev_id="ev-b"),
        ],
        ev_chargers=[
            _ev(id_="ev-a", assigned_charger_id="wb-a"),
            _ev(id_="ev-b", assigned_charger_id="wb-b"),
        ],
    )
    entry = await _setup(hass, system)
    entity_reg = er.async_get(hass)
    unique_ids = {
        r.unique_id for r in er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    }
    # Unique_ids carry the vehicle id, never the wallbox sub-device key.
    for expected in (
        "sys-1_ev-a_charging_mode_select",
        "sys-1_ev-b_charging_mode_select",
        "sys-1_ev-a_departure_time",
        "sys-1_ev-b_departure_time",
    ):
        assert expected in unique_ids, f"unique_id {expected!r} missing"
