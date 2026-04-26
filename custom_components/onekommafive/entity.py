"""Base entity for the 1KOMMA5° integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
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
