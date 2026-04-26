"""Base entity for the 1KOMMA5° integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    OneKomma5LiveCoordinator,
    OneKomma5OptimizationCoordinator,
    OneKomma5PriceCoordinator,
)


class OneKomma5Entity(CoordinatorEntity[OneKomma5LiveCoordinator]):
    """Base entity for live-data entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OneKomma5LiveCoordinator,
        system_id: str,
        system_name: str,
        unique_id_suffix: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._system_id = system_id
        self._attr_unique_id = f"{system_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, system_id)},
            name=system_name,
            manufacturer="1KOMMA5°",
            model="Heartbeat",
        )


class OneKomma5PriceEntity(CoordinatorEntity[OneKomma5PriceCoordinator]):
    """Base entity for price-data entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OneKomma5PriceCoordinator,
        system_id: str,
        system_name: str,
        unique_id_suffix: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._system_id = system_id
        self._attr_unique_id = f"{system_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, system_id)},
            name=system_name,
            manufacturer="1KOMMA5°",
            model="Heartbeat",
        )

    def _dynamic_current_price(self) -> float | None:
        """Look up the current price using the dynamic helper if available."""
        from .helpers import get_current_price  # local import to avoid cycles

        if self.coordinator.data is None:
            return None
        if self.coordinator.data.all_in_prices:
            return get_current_price(self.coordinator.data.all_in_prices)
        return self.coordinator.data.current_price


class OneKomma5OptimizationEntity(CoordinatorEntity[OneKomma5OptimizationCoordinator]):
    """Base entity for optimization-data entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OneKomma5OptimizationCoordinator,
        system_id: str,
        system_name: str,
        unique_id_suffix: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._system_id = system_id
        self._attr_unique_id = f"{system_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, system_id)},
            name=system_name,
            manufacturer="1KOMMA5°",
            model="Heartbeat",
        )


class OneKomma5EVEntity(CoordinatorEntity[OneKomma5LiveCoordinator]):
    """Base entity for EV charger entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OneKomma5LiveCoordinator,
        system_id: str,
        system_name: str,
        ev_id: str,
        ev_label: str,
        unique_id_suffix: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._system_id = system_id
        self._ev_id = ev_id
        self._attr_unique_id = f"{system_id}_{ev_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{system_id}_{ev_id}")},
            name=ev_label,
            manufacturer="1KOMMA5°",
            model="EV Charger",
            via_device=(DOMAIN, system_id),
        )

    def _get_ev(self) -> object | None:
        """Return the current EV charger object from coordinator data."""
        if self.coordinator.data is None:
            return None
        for ev in self.coordinator.data.ev_chargers:
            if ev.id() == self._ev_id:
                return ev
        return None


class QuarterHourUpdateMixin:
    """Mixin: subscribe an entity to quarter-hour boundary state updates.

    Use ``self._async_register_quarter_hour_update()`` from
    ``async_added_to_hass`` after the parent ``super().async_added_to_hass()``
    call. The entity's ``async_write_ha_state`` is invoked at :00/:15/:30/:45.

    Useful for entities whose state depends on the active 15-minute price
    slot but whose data coordinator updates less frequently.
    """

    hass: Any  # provided by HA Entity base class

    def _async_register_quarter_hour_update(self) -> None:
        self.async_on_remove(  # type: ignore[attr-defined]
            async_track_time_change(
                self.hass,
                self._quarter_hour_update,
                minute=[0, 15, 30, 45],
                second=[0],
            )
        )

    @callback
    def _quarter_hour_update(self, _now: datetime) -> None:
        """Re-evaluate state at quarter-hour boundaries."""
        self.async_write_ha_state()  # type: ignore[attr-defined]
