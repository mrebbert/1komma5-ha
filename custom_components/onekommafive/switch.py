"""Switch platform for the 1KOMMA5° integration (EMS auto mode)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .entity import OneKomma5Entity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities from a config entry."""
    data = entry.runtime_data
    system = data.system
    system_id = system.id()
    system_name = data.system_name

    async_add_entities(
        [OneKomma5EMSSwitch(data.live_coordinator, system, system_id, system_name)]
    )


class OneKomma5EMSSwitch(OneKomma5Entity, SwitchEntity):
    """Switch to enable or disable EMS auto mode."""

    _attr_translation_key = "ems_auto_mode"

    def __init__(
        self,
        coordinator: Any,
        system: Any,
        system_id: str,
        system_name: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, system_id, system_name, "ems_auto_mode")
        self._system = system

    @property
    def is_on(self) -> bool | None:
        """Return True when EMS is in auto mode."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.ems_settings.auto_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable EMS auto mode."""
        await self.hass.async_add_executor_job(self._system.set_ems_mode, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable EMS auto mode (switch to manual)."""
        await self.hass.async_add_executor_job(self._system.set_ems_mode, False)
        await self.coordinator.async_request_refresh()


