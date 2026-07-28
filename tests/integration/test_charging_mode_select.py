"""Tier-2 test for the EV charging-mode select entity.

The HA option strings are lowercase (``smart_charge``, ``quick_charge``,
``solar_charge``) but the API expects the upstream UPPERCASE enum value.
The select entity does the conversion via ``ChargingMode(option.upper())``;
a regression here would silently send the wrong format to the API.
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


def _ev_charger() -> MagicMock:
    """Build a stub EV charger the integration can introspect."""
    from onekommafive.models import ChargingMode

    ev = MagicMock()
    ev.id.return_value = "ev-uuid-1"
    ev.manufacturer.return_value = "Volkswagen"
    ev.model.return_value = "ID.4"
    ev.charging_mode.return_value = ChargingMode.SOLAR_CHARGE
    ev.target_soc.return_value = 80.0
    ev.current_soc.return_value = 50.0
    ev.primary_schedule_departure_time.return_value = "07:00"
    return ev


async def test_charging_mode_select_translates_lowercase_option_to_enum(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Calling ``select.select_option`` with ``smart_charge`` calls the API with the matching enum."""
    from onekommafive.models import ChargingMode

    ev = _ev_charger()
    system = mock_system_factory(system_id="sys-1", ev_chargers=[ev])

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

        # Find the registered select entity for the charger
        select_entity_id = next(
            state.entity_id
            for state in hass.states.async_all("select")
            if state.entity_id.endswith("_charging_mode_select")
        )

        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": select_entity_id, "option": "smart_charge"},
            blocking=True,
        )
        await hass.async_block_till_done()

    ev.set_charging_mode.assert_called_once_with(ChargingMode.SMART_CHARGE)
