"""Select platform for the 1KOMMA5° integration (EV charging mode)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .entity import OneKomma5EVEntity

_LOGGER = logging.getLogger(__name__)

# HA translation keys must be lowercase; the API uses UPPER_CASE enum values.
CHARGING_MODE_OPTIONS = ["smart_charge", "quick_charge", "solar_charge"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities from a config entry."""
    data = entry.runtime_data
    live_coordinator = data.live_coordinator
    system = data.system
    system_id = system.id()
    system_name = data.system_name

    entities: list[SelectEntity] = []

    if live_coordinator.data:
        for ev in live_coordinator.data.ev_chargers:
            entities.append(
                OneKomma5ChargingModeSelect(
                    live_coordinator,
                    ev,
                    system_id,
                    system_name,
                    ev.id(),
                    _get_ev_label(ev),
                )
            )

    async_add_entities(entities)


class OneKomma5ChargingModeSelect(OneKomma5EVEntity, SelectEntity):
    """Select entity to control the EV charging mode."""

    _attr_translation_key = "ev_charging_mode"
    _attr_options = CHARGING_MODE_OPTIONS

    def __init__(
        self,
        coordinator: Any,
        ev_charger: Any,
        system_id: str,
        system_name: str,
        ev_id: str,
        ev_label: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, system_id, system_name, ev_id, ev_label, "charging_mode_select")
        self._ev_charger = ev_charger

    @property
    def current_option(self) -> str | None:
        """Return the currently active charging mode as a lowercase HA option key."""
        ev = self._get_ev()
        if ev is None:
            return None
        return ev.charging_mode().value.lower()

    async def async_select_option(self, option: str) -> None:
        """Change the charging mode."""
        from onekommafive.models import ChargingMode

        mode = ChargingMode(option.upper())
        ev = self._get_ev()
        if ev is None:
            _LOGGER.warning("EV charger %s not found, cannot set charging mode", self._ev_id)
            return
        await self.hass.async_add_executor_job(ev.set_charging_mode, mode)
        await self.coordinator.async_request_refresh()


def _get_ev_label(ev: Any) -> str:
    parts = [p for p in (ev.manufacturer(), ev.model()) if p]
    return " ".join(parts) if parts else f"EV {ev.id()[:8]}"
