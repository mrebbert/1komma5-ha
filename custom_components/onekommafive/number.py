"""Number platform for the 1KOMMA5° integration (EV SoC control)."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .entity import OneKomma5EVEntity, get_ev_label

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class OneKomma5EVNumberDescription(NumberEntityDescription):
    """Number entity description for EV-related sliders."""

    value_fn: Callable[[Any], float | None]
    set_fn: Callable[[Any, float], None]  # called via executor
    available_fn: Callable[[Any], bool] = lambda _: True


def _ev_smart_charge_available(ev: Any) -> bool:
    """True only when the EV charger is in SMART_CHARGE mode."""
    from onekommafive.models import ChargingMode

    return ev.charging_mode() == ChargingMode.SMART_CHARGE


EV_NUMBER_DEFAULTS = {
    "device_class": NumberDeviceClass.BATTERY,
    "native_unit_of_measurement": PERCENTAGE,
    "native_min_value": 0.0,
    "native_max_value": 100.0,
    "native_step": 1.0,
    "mode": NumberMode.SLIDER,
}

EV_NUMBERS: tuple[OneKomma5EVNumberDescription, ...] = (
    OneKomma5EVNumberDescription(
        key="current_soc_number",
        translation_key="ev_current_soc",
        value_fn=lambda ev: ev.current_soc(),
        set_fn=lambda ev, value: ev.set_current_soc(value),
        available_fn=_ev_smart_charge_available,
        **EV_NUMBER_DEFAULTS,
    ),
    OneKomma5EVNumberDescription(
        key="target_soc_number",
        translation_key="ev_target_soc_number",
        value_fn=lambda ev: ev.target_soc(),
        set_fn=lambda ev, value: ev.set_target_soc(value),
        **EV_NUMBER_DEFAULTS,
    ),
)


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
            ev_id = ev.id()
            ev_label = get_ev_label(ev)
            entities.extend(
                OneKomma5EVNumber(
                    live_coordinator, system_id, system_name, ev_id, ev_label, desc,
                )
                for desc in EV_NUMBERS
            )

    async_add_entities(entities)


class OneKomma5EVNumber(OneKomma5EVEntity, NumberEntity):
    """Number entity for EV-related sliders, behaviour driven by a description."""

    entity_description: OneKomma5EVNumberDescription

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        ev_id: str,
        ev_label: str,
        description: OneKomma5EVNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, system_id, system_name, ev_id, ev_label, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the current value via the description's value_fn."""
        ev = self._get_ev()
        if ev is None:
            return None
        return self.entity_description.value_fn(ev)

    @property
    def available(self) -> bool:
        """Combine the parent availability with the description's check."""
        if not super().available:
            return False
        ev = self._get_ev()
        if ev is None:
            return False
        return self.entity_description.available_fn(ev)

    async def async_set_native_value(self, value: float) -> None:
        """Send the new value to the API via the executor."""
        ev = self._get_ev()
        if ev is None:
            _LOGGER.warning(
                "EV charger %s not found, cannot set %s",
                self._ev_id, self.entity_description.key,
            )
            return
        await self.hass.async_add_executor_job(
            self.entity_description.set_fn, ev, value
        )
        await self.coordinator.async_request_refresh()
