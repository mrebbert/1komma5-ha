"""Switch platform for the 1KOMMA5° integration (EMS auto mode)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .const import DOMAIN
from .entity import OneKomma5Entity, apply_stable_entity_ids, is_1k5_backend

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

    # 1K5-backend installs don't expose the GridX-scoped EMS-settings
    # endpoint, so `get_ems_settings()` returns 30401 and the switch
    # would be permanently unavailable. Skip creating it entirely and
    # remove any stale registry entry left from a prior GRIDX run.
    if is_1k5_backend(data.emp_type):
        _LOGGER.debug("Skipping EMS auto-mode switch: emp_type=1K5 has no GridX EMS endpoint")
        registry = er.async_get(hass)
        stale = registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, f"{system_id}_ems_auto_mode")
        if stale is not None:
            registry.async_remove(stale)
        return

    entities = [OneKomma5EMSSwitch(data.live_coordinator, system, system_id, system_name)]
    apply_stable_entity_ids(entities, SWITCH_DOMAIN)
    async_add_entities(entities)


class OneKomma5EMSSwitch(OneKomma5Entity, SwitchEntity):
    """Switch to enable or disable EMS auto mode.

    Demoted to ``EntityCategory.DIAGNOSTIC`` because empirically the cloud's
    auto-override toggle appears to be cosmetic — the official 1KOMMA5° app
    doesn't expose it, and there is no observable behavioural change on the
    HEMS when the switch flips. Kept around in case the upstream cloud
    re-activates the override on some setups; see Memory's API behaviour
    notes for the full reasoning.
    """

    _attr_translation_key = "ems_auto_mode"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
    def available(self) -> bool:
        """Return True when EMS settings are available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.ems_settings is not None
        )

    @property
    def is_on(self) -> bool | None:
        """Return True when EMS is in auto mode."""
        if self.coordinator.data is None or self.coordinator.data.ems_settings is None:
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
