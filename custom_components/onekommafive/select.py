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
from .const import DOMAIN
from .coordinator import OneKomma5LiveCoordinator, OneKomma5SystemStatusCoordinator
from .entity import (
    OneKomma5EVEntity,
    apply_stable_entity_ids,
    ev_wallbox_parent,
    wallbox_sub_device_key,
)

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
    system_status_coordinator = data.system_status_coordinator
    system = data.system
    system_id = system.id()
    system_name = data.system_name

    entities: list[SelectEntity] = []

    if live_coordinator.data:
        for ev in live_coordinator.data.ev_chargers:
            wb_device_id, wb_identifier = ev_wallbox_parent(ev, data)
            entities.append(
                OneKomma5ChargingModeSelect(
                    live_coordinator,
                    system_id,
                    system_name,
                    ev,
                    data.system_device_id,
                    wallbox_device_id=wb_device_id,
                    wallbox_parent_identifier=wb_identifier,
                )
            )

    wallboxes = getattr(data, "wallboxes", None) or []
    wallbox_count = len(wallboxes)
    for wallbox in wallboxes:
        wb_id = getattr(wallbox, "id", None)
        if not wb_id:
            continue
        key = wallbox_sub_device_key(wb_id, wallbox_count)
        entities.append(
            OneKomma5WallboxAssignmentSelect(
                system_status_coordinator,
                live_coordinator,
                system_id,
                system_name,
                wallbox,
                wallbox_parent_identifier=(DOMAIN, f"{system_id}_{key}"),
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
        parent_device_id: str,
        *,
        wallbox_device_id: str | None = None,
        wallbox_parent_identifier: tuple[str, str] | None = None,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            system_id,
            system_name,
            ev,
            "charging_mode_select",
            parent_device_id,
            wallbox_device_id=wallbox_device_id,
            wallbox_parent_identifier=wallbox_parent_identifier,
        )

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


class OneKomma5WallboxAssignmentSelect(
    CoordinatorEntity[OneKomma5SystemStatusCoordinator], SelectEntity
):
    """Select entity that binds a vehicle profile to a wallbox.

    Primary coordinator is the system-status coordinator (5-min cadence)
    because it carries the live ``Wallbox.assigned_ev_id``. The live
    coordinator supplies the vehicle inventory used to build the option
    list — the two refresh at different intervals, so both are triggered
    after a select-option write.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "wallbox_assigned_vehicle"
    _attr_icon = "mdi:car-electric"

    def __init__(
        self,
        coordinator: OneKomma5SystemStatusCoordinator,
        live_coordinator: OneKomma5LiveCoordinator,
        system_id: str,
        system_name: str,
        wallbox: Any,
        *,
        wallbox_parent_identifier: tuple[str, str] | None = None,
    ) -> None:
        """Initialize the assignment select."""
        from homeassistant.helpers.device_registry import DeviceInfo

        super().__init__(coordinator)
        self._live_coordinator = live_coordinator
        self._system_id = system_id
        self._wallbox_id = wallbox.id
        self._attr_unique_id = f"{system_id}_{self._wallbox_id}_assigned_vehicle"
        self._stable_object_id = (
            f"{slugify(system_name)}_{slugify(self._wallbox_id)}_assigned_vehicle"
        )
        # Parent the entity onto the pre-registered wallbox sub-device.
        # ``_setup_wallbox_sub_devices`` already registered that sub-device
        # with the correct via_device pointing at the system parent — we
        # must only re-declare the identifier so HA attaches this entity
        # to the existing device (never re-set via_device on ourselves,
        # which would raise "A device can not be its own via device").
        identifier = wallbox_parent_identifier or (DOMAIN, f"{system_id}_wallbox")
        self._attr_device_info = DeviceInfo(identifiers={identifier})

    def _ev_chargers(self) -> list[Any]:
        if self._live_coordinator.data is None:
            return []
        return self._live_coordinator.data.ev_chargers

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
        await self._live_coordinator.async_request_refresh()
