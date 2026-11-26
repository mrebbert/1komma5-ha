"""The charging-mode select offers the modes the vendor reports for the site."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import CONF_SYSTEM_ID, DOMAIN

from .test_charging_mode_select import _ev_charger


async def _setup(hass: HomeAssistant, system) -> str:
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
        mock_systems_cls.return_value.get_system = AsyncMock(return_value=system)
        mock_systems_cls.return_value.get_systems = AsyncMock(return_value=[system])
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return next(
        s.entity_id
        for s in hass.states.async_all("select")
        if s.entity_id.endswith("_charging_mode_select")
    )


async def test_options_follow_vendor_list_and_unknown_mode(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Offered modes become options; a new, unlisted active mode stays selectable."""
    from onekommafive.models import ChargingMode

    ev = _ev_charger()
    ev.charging_mode.return_value = ChargingMode("FUTURE_CHARGE")
    system = mock_system_factory(system_id="sys-1", ev_chargers=[ev])
    system.get_displayed_ev_charging_modes = AsyncMock(
        return_value=[
            ChargingMode.PROGRAM_CHARGE,
            ChargingMode.SOLAR_CHARGE,
            ChargingMode.QUICK_CHARGE,
        ]
    )
    entity_id = await _setup(hass, system)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["options"] == [
        "program_charge",
        "solar_charge",
        "quick_charge",
        "future_charge",
    ]
    assert state.state == "future_charge"


async def test_options_fall_back_to_defaults_when_fetch_fails(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """A failing endpoint leaves the three default modes in place."""
    system = mock_system_factory(system_id="sys-1", ev_chargers=[_ev_charger()])
    system.get_displayed_ev_charging_modes = AsyncMock(side_effect=RuntimeError("x"))
    entity_id = await _setup(hass, system)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["options"] == [
        "smart_charge",
        "quick_charge",
        "solar_charge",
    ]
