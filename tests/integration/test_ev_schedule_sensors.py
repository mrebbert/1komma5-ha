"""Tier-2 tests for the two EV spec/schedule sensors.

- ``ev_battery_capacity`` surfaces the nominal capacity (Wh → kWh).
- ``ev_scheduled_departure_soc`` surfaces the schedule's departure SoC target,
  which is distinct from the manual ``target_soc`` override. Both are read-only
  (no SDK setter), hence sensors rather than number entities.
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


def _ev_charger(
    *, capacity_wh: float | None = 77000.0, departure_soc: float | None = 100.0
) -> MagicMock:
    from onekommafive.models import ChargingMode

    ev = MagicMock()
    ev.id.return_value = "ev-uuid-1"
    ev.manufacturer.return_value = "Volkswagen"
    ev.model.return_value = "ID.4"
    ev.charging_mode.return_value = ChargingMode.SOLAR_CHARGE
    ev.target_soc.return_value = 80.0
    ev.capacity_wh.return_value = capacity_wh
    ev.primary_schedule_departure_soc.return_value = departure_soc
    return ev


async def _setup(hass: HomeAssistant, ev: MagicMock, mock_system_factory) -> None:
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


def _resolve(hass: HomeAssistant, suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", f"sys-1_ev-uuid-1_{suffix}"
    )
    assert entity_id is not None
    return entity_id


async def test_battery_capacity_converts_wh_to_kwh(
    hass: HomeAssistant, mock_system_factory
) -> None:
    await _setup(hass, _ev_charger(capacity_wh=77000.0), mock_system_factory)

    state = hass.states.get(_resolve(hass, "ev_battery_capacity"))
    assert state.state == "77.0"
    assert state.attributes["unit_of_measurement"] == "kWh"


async def test_scheduled_departure_soc_is_distinct_from_target(
    hass: HomeAssistant, mock_system_factory
) -> None:
    # target_soc = 80 (manual), scheduled departure SoC = 100 (schedule).
    await _setup(hass, _ev_charger(departure_soc=100.0), mock_system_factory)

    state = hass.states.get(_resolve(hass, "ev_scheduled_departure_soc"))
    assert float(state.state) == 100.0
    assert state.attributes["unit_of_measurement"] == "%"

    target = hass.states.get(_resolve(hass, "ev_target_soc"))
    assert float(target.state) == 80.0


async def test_missing_values_are_unknown(hass: HomeAssistant, mock_system_factory) -> None:
    await _setup(hass, _ev_charger(capacity_wh=None, departure_soc=None), mock_system_factory)

    assert hass.states.get(_resolve(hass, "ev_battery_capacity")).state == "unknown"
    assert hass.states.get(_resolve(hass, "ev_scheduled_departure_soc")).state == "unknown"
