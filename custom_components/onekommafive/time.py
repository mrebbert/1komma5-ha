"""Time platform for the 1KOMMA5° integration (EV departure time)."""
from __future__ import annotations

import datetime
import logging
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .entity import OneKomma5EVEntity, get_ev_label

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up time entities from a config entry."""
    data = entry.runtime_data
    live_coordinator = data.live_coordinator
    system_id = data.system.id()
    system_name = data.system_name

    entities: list[TimeEntity] = []

    if live_coordinator.data:
        for ev in live_coordinator.data.ev_chargers:
            entities.append(
                OneKomma5EVDepartureTime(
                    live_coordinator,
                    ev,
                    system_id,
                    system_name,
                    ev.id(),
                    get_ev_label(ev),
                )
            )

    async_add_entities(entities)


class OneKomma5EVDepartureTime(OneKomma5EVEntity, TimeEntity):
    """Time entity to set the daily primary departure time for the EV charger."""

    _attr_translation_key = "ev_departure_time"

    def __init__(
        self,
        coordinator: Any,
        ev_charger: Any,
        system_id: str,
        system_name: str,
        ev_id: str,
        ev_label: str,
    ) -> None:
        """Initialize the time entity."""
        super().__init__(coordinator, system_id, system_name, ev_id, ev_label, "departure_time")
        self._ev_charger = ev_charger

    @property
    def native_value(self) -> datetime.time | None:
        """Return the current primary departure time."""
        ev = self._get_ev()
        if ev is None:
            return None
        value = ev.primary_schedule_departure_time()
        if value is None:
            return None
        try:
            return datetime.time.fromisoformat(value)  # "HH:MM" → datetime.time
        except ValueError:
            _LOGGER.warning("Could not parse departure time: %s", value)
            return None

    async def async_set_value(self, value: datetime.time) -> None:
        """Send the new departure time to the API."""
        ev = self._get_ev()
        if ev is None:
            _LOGGER.warning("EV charger %s not found, cannot set departure time", self._ev_id)
            return
        await self.hass.async_add_executor_job(ev.set_primary_departure_time, value.strftime("%H:%M"))
        await self.coordinator.async_request_refresh()


