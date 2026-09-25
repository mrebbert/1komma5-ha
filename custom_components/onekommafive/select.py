"""Select platform for the 1KOMMA5° integration.

Two select entities:
- ``OneKomma5ChargingModeSelect`` — per vehicle, sets the charging strategy
  (smart / quick / solar).
- ``OneKomma5WallboxAssignmentSelect`` — per wallbox, binds a vehicle profile
  to the physical wallbox (SDK ≥ 0.5.0 ``EVCharger.assign_charger``). The
  1KOMMA5° model is 1:1 exclusive; the backend releases any previously bound
  vehicle in the same PATCH.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import OneKomma5ConfigEntry
from .coordinator import OneKomma5LiveCoordinator
from .entity import (
    OneKomma5EVEntity,
    apply_stable_entity_ids,
    attach_to_wallbox_sub_device,
)

_LOGGER = logging.getLogger(__name__)

# HA translation keys must be lowercase; the API uses UPPER_CASE enum values.
CHARGING_MODE_OPTIONS = ["smart_charge", "quick_charge", "solar_charge"]

# Coordinator-based reads; see binary_sensor.py for the rationale.
PARALLEL_UPDATES = 0


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
                    system_id,
                    system_name,
                    ev,
                    data,
                )
            )

    wallboxes = getattr(data, "wallboxes", None) or []
    wallbox_count = len(wallboxes)
    for wallbox in wallboxes:
        wb_id = getattr(wallbox, "id", None)
        if not wb_id:
            continue
        entities.append(
            OneKomma5WallboxAssignmentSelect(
                live_coordinator,
                system_id,
                system_name,
                wallbox,
                wallbox_count=wallbox_count,
            )
        )

    apply_stable_entity_ids(entities, SELECT_DOMAIN)
    async_add_entities(entities)


def _ev_slug(ev: Any) -> str:
    """Return the stable option slug for a vehicle profile.

    Uses the human-readable name when set (typical, so ``bmw_i3`` /
    ``tesla_model_y`` land in HA), else falls back to the vehicle id so the
    option remains unique.
    """
    name = getattr(ev, "name", lambda: None)()
    return slugify(name) if name else slugify(ev.id())


class OneKomma5ChargingModeSelect(OneKomma5EVEntity, SelectEntity):
    """Select entity to control the EV charging mode."""

    _attr_translation_key = "ev_charging_mode"
    _attr_options = CHARGING_MODE_OPTIONS

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        ev: Any,
        data: Any,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, system_id, system_name, ev, "charging_mode_select", data)

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


class OneKomma5WallboxAssignmentSelect(CoordinatorEntity[OneKomma5LiveCoordinator], SelectEntity):
    """Select entity that binds a vehicle profile to a wallbox.

    Rides the 30-second live coordinator so app-side assignment changes
    surface in HA within one tick. Both ``Wallbox.assigned_ev_id`` (the
    state) and the vehicle inventory (the options) live in the same
    ``LiveData`` payload; one refresh keeps the entity consistent.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "wallbox_assigned_vehicle"
    _attr_icon = "mdi:car-electric"

    def __init__(
        self,
        coordinator: OneKomma5LiveCoordinator,
        system_id: str,
        system_name: str,
        wallbox: Any,
        *,
        wallbox_count: int = 1,
    ) -> None:
        """Initialize the assignment select."""
        super().__init__(coordinator)
        self._system_id = system_id
        self._wallbox_id = wallbox.id
        self._attr_unique_id = f"{system_id}_{self._wallbox_id}_assigned_vehicle"
        self._stable_object_id = (
            f"{slugify(system_name)}_{slugify(self._wallbox_id)}_assigned_vehicle"
        )
        self._attr_device_info = attach_to_wallbox_sub_device(system_id, wallbox.id, wallbox_count)

    def _ev_chargers(self) -> list[Any]:
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.ev_chargers

    def _current_wallbox(self) -> Any | None:
        if self.coordinator.data is None:
            return None
        for wb in getattr(self.coordinator.data, "wallboxes", []):
            if getattr(wb, "id", None) == self._wallbox_id:
                return wb
        return None

    @property
    def options(self) -> list[str]:
        """Return the current vehicle slugs eligible for this wallbox."""
        return [_ev_slug(ev) for ev in self._ev_chargers()]

    @property
    def current_option(self) -> str | None:
        """Return the slug of the vehicle currently bound to this wallbox."""
        wb = self._current_wallbox()
        if wb is None:
            return None
        assigned_ev_id = getattr(wb, "assigned_ev_id", None)
        if not assigned_ev_id:
            return None
        for ev in self._ev_chargers():
            if ev.id() == assigned_ev_id:
                return _ev_slug(ev)
        return None

    async def async_select_option(self, option: str) -> None:
        """Bind ``option`` (an EV slug) to this wallbox."""
        target_ev: Any | None = None
        for ev in self._ev_chargers():
            if _ev_slug(ev) == option:
                target_ev = ev
                break
        if target_ev is None:
            _LOGGER.warning(
                "Vehicle slug %r not found for wallbox %s; cannot assign",
                option,
                self._wallbox_id,
            )
            return
        await self.hass.async_add_executor_job(target_ev.assign_charger, self._wallbox_id)
        await self.coordinator.async_request_refresh()
