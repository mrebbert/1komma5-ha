"""Number platform for the 1KOMMA5° integration (EV SoC control)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .entity import OneKomma5EVEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities from a config entry."""
    data = entry.runtime_data
    live_coordinator = data.live_coordinator
    system_id = data.system.id()
    system_name = data.system_name

    entities: list[NumberEntity] = []

    if live_coordinator.data:
        for ev in live_coordinator.data.ev_chargers:
            entities.append(
                OneKomma5EVSoCNumber(
                    live_coordinator,
                    ev,
                    system_id,
                    system_name,
                    ev.id(),
                    _get_ev_label(ev),
                )
            )

    async_add_entities(entities)


class OneKomma5EVSoCNumber(OneKomma5EVEntity, NumberEntity):
    """Number entity to manually set the EV state-of-charge in SMART_CHARGE mode."""

    _attr_translation_key = "ev_current_soc"
    _attr_device_class = NumberDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: Any,
        ev_charger: Any,
        system_id: str,
        system_name: str,
        ev_id: str,
        ev_label: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, system_id, system_name, ev_id, ev_label, "current_soc_number")
        self._ev_charger = ev_charger

    @property
    def native_value(self) -> float | None:
        """Return the current SoC value."""
        ev = self._get_ev()
        if ev is None:
            return None
        return ev.current_soc()

    @property
    def available(self) -> bool:
        """Only available in SMART_CHARGE mode."""
        if not super().available:
            return False
        ev = self._get_ev()
        if ev is None:
            return False
        from onekommafive.models import ChargingMode
        return ev.charging_mode() == ChargingMode.SMART_CHARGE

    async def async_set_native_value(self, value: float) -> None:
        """Update the EV SoC."""
        ev = self._get_ev()
        if ev is None:
            _LOGGER.warning("EV charger %s not found, cannot set SoC", self._ev_id)
            return
        await self.hass.async_add_executor_job(ev.set_current_soc, value)
        await self.coordinator.async_request_refresh()


def _get_ev_label(ev: Any) -> str:
    parts = [p for p in (ev.manufacturer(), ev.model()) if p]
    return " ".join(parts) if parts else f"EV {ev.id()[:8]}"
