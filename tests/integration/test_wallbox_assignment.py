"""Tier-2 tests for the wallbox → vehicle assignment surface (issue #24).

Two pieces:

- ``select.<sys>_<wb>_assigned_vehicle`` per wallbox, whose state reflects
  ``Wallbox.assigned_ev_id`` and whose ``async_select_option`` calls the
  SDK's ``EVCharger.assign_charger(wallbox_id)`` (v0.5.0+).
- Service ``onekommafive.assign_ev_to_wallbox`` for automations that address
  the assignment by id rather than through a select entity.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _asset(name: str, connection_status: str = "CONNECTED") -> MagicMock:
    asset = MagicMock(
        type="EV_CHARGER",
        connection_status=connection_status,
        manufacturer="go-e",
        model="HOMEfix 11kW",
        firmware="60.5",
    )
    asset.name = name
    return asset


def _wallbox(*, id_: str, name: str, assigned_ev_id: str | None = None) -> MagicMock:
    wallbox = MagicMock(id=id_, assigned_ev_id=assigned_ev_id)
    wallbox.name = name
    return wallbox


def _ev(*, id_: str, name: str, assigned_charger_id: str | None = None) -> MagicMock:
    from onekommafive.models import ChargingMode

    ev = MagicMock()
    ev.id.return_value = id_
    ev.name.return_value = name
    ev.manufacturer.return_value = "BMW"
    ev.model.return_value = "i3"
    ev.assigned_charger_id = assigned_charger_id
    ev.charging_mode.return_value = ChargingMode.SMART_CHARGE
    ev.target_soc.return_value = 80.0
    ev.current_soc.return_value = None
    ev.capacity_wh.return_value = 42000.0
    ev.primary_schedule_departure_soc.return_value = 80.0
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


def _assignment_entity_id(hass: HomeAssistant, wallbox_id: str) -> str | None:
    reg = er.async_get(hass)
    return reg.async_get_entity_id("select", DOMAIN, f"sys-1_{wallbox_id}_assigned_vehicle")


async def test_assignment_select_reflects_wallbox_state(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """`assigned_ev_id=ev-a` renders `state=bmw_i3` (the ev-a slug)."""
    ev_a = _ev(id_="ev-a", name="BMW i3", assigned_charger_id="wb-1")
    ev_b = _ev(id_="ev-b", name="Tesla Model Y")
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("Wallbox")],
        ev_chargers=[ev_a, ev_b],
        wallboxes=[_wallbox(id_="wb-1", name="Wallbox", assigned_ev_id="ev-a")],
    )
    await _setup(hass, system)

    entity_id = _assignment_entity_id(hass, "wb-1")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "bmw_i3"
    assert set(state.attributes["options"]) == {"bmw_i3", "tesla_model_y"}


async def test_assignment_select_option_calls_sdk(hass: HomeAssistant, mock_system_factory) -> None:
    """Selecting the other EV's slug PATCHes via `ev.assign_charger(wb_id)`."""
    ev_a = _ev(id_="ev-a", name="BMW i3", assigned_charger_id="wb-1")
    ev_b = _ev(id_="ev-b", name="Tesla Model Y")
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("Wallbox")],
        ev_chargers=[ev_a, ev_b],
        wallboxes=[_wallbox(id_="wb-1", name="Wallbox", assigned_ev_id="ev-a")],
    )
    await _setup(hass, system)

    entity_id = _assignment_entity_id(hass, "wb-1")
    assert entity_id is not None

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "tesla_model_y"},
        blocking=True,
    )

    ev_b.assign_charger.assert_called_once_with("wb-1")
    ev_a.assign_charger.assert_not_called()


async def test_assignment_select_unknown_assignment_is_unknown(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """When `assigned_ev_id` points at an EV the integration doesn't know,
    the state degrades to `unknown` (never surfaces a wrong slug).
    """
    ev_a = _ev(id_="ev-a", name="BMW i3")
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("Wallbox")],
        ev_chargers=[ev_a],
        wallboxes=[_wallbox(id_="wb-1", name="Wallbox", assigned_ev_id="ev-x-orphan")],
    )
    await _setup(hass, system)

    entity_id = _assignment_entity_id(hass, "wb-1")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unknown"


async def test_assign_ev_service_success(hass: HomeAssistant, mock_system_factory) -> None:
    """Service call returns `previous_ev_id` from the local cache and
    PATCHes via the SDK; the previous binding is the one captured before
    the write.
    """
    ev_a = _ev(id_="ev-a", name="BMW i3", assigned_charger_id="wb-1")
    ev_b = _ev(id_="ev-b", name="Tesla Model Y")
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("Wallbox")],
        ev_chargers=[ev_a, ev_b],
        wallboxes=[_wallbox(id_="wb-1", name="Wallbox", assigned_ev_id="ev-a")],
    )
    await _setup(hass, system)

    result = await hass.services.async_call(
        DOMAIN,
        "assign_ev_to_wallbox",
        {"wallbox_id": "wb-1", "ev_id": "ev-b"},
        blocking=True,
        return_response=True,
    )
    ev_b.assign_charger.assert_called_once_with("wb-1")
    assert result == {"success": True, "previous_ev_id": "ev-a"}


async def test_assign_ev_service_unknown_ev(hass: HomeAssistant, mock_system_factory) -> None:
    ev_a = _ev(id_="ev-a", name="BMW i3", assigned_charger_id="wb-1")
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("Wallbox")],
        ev_chargers=[ev_a],
        wallboxes=[_wallbox(id_="wb-1", name="Wallbox", assigned_ev_id="ev-a")],
    )
    await _setup(hass, system)

    with pytest.raises(HomeAssistantError, match="Vehicle 'ev-missing' not found"):
        await hass.services.async_call(
            DOMAIN,
            "assign_ev_to_wallbox",
            {"wallbox_id": "wb-1", "ev_id": "ev-missing"},
            blocking=True,
            return_response=True,
        )


async def test_assign_ev_service_unknown_wallbox(hass: HomeAssistant, mock_system_factory) -> None:
    ev_a = _ev(id_="ev-a", name="BMW i3", assigned_charger_id="wb-1")
    system = mock_system_factory(
        system_id="sys-1",
        assets=[_asset("Wallbox")],
        ev_chargers=[ev_a],
        wallboxes=[_wallbox(id_="wb-1", name="Wallbox", assigned_ev_id="ev-a")],
    )
    await _setup(hass, system)

    with pytest.raises(HomeAssistantError, match="Wallbox 'wb-missing' not found"):
        await hass.services.async_call(
            DOMAIN,
            "assign_ev_to_wallbox",
            {"wallbox_id": "wb-missing", "ev_id": "ev-a"},
            blocking=True,
            return_response=True,
        )
    ev_a.assign_charger.assert_not_called()
