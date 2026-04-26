"""Sensor entity classes for the 1KOMMA5° integration.

The actual SENSORS configuration tuples and the platform's
``async_setup_entry`` live in ``sensor.py``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import LiveData
from .entity import (
    OneKomma5Entity,
    OneKomma5EVEntity,
    OneKomma5OptimizationEntity,
    OneKomma5PriceEntity,
    QuarterHourUpdateMixin,
    system_device_info,
)
from .helpers import trapezoidal_delta_kwh
from .sensor_descriptions import (
    OneKomma5EVSensorDescription,
    OneKomma5OptimizationSensorDescription,
    OneKomma5PriceSensorDescription,
    OneKomma5SensorDescription,
)

CURRENCY_EUR_PER_KWH = "EUR/kWh"


class OneKomma5LiveSensor(OneKomma5Entity, SensorEntity):
    """Sensor for live energy data."""

    entity_description: OneKomma5SensorDescription

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        description: OneKomma5SensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class OneKomma5PriceSensor(QuarterHourUpdateMixin, OneKomma5PriceEntity, SensorEntity):
    """Sensor for electricity market prices."""

    entity_description: OneKomma5PriceSensorDescription

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        description: OneKomma5PriceSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update for the dynamic current-price sensor."""
        await super().async_added_to_hass()
        if self.entity_description.key == "current_electricity_price":
            self._async_register_quarter_hour_update()

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the price forecast on the current-price sensor."""
        if self.entity_description.key != "current_electricity_price":
            return None
        if self.coordinator.data is None:
            return None
        forecast = self.coordinator.data.forecast
        attrs: dict[str, Any] = {"forecast": forecast}
        if forecast:
            cheapest = min(forecast, key=lambda s: s["price"])
            attrs["cheapest_future_hour"] = cheapest["start"]
            attrs["cheapest_future_price"] = cheapest["price"]
        return attrs


class OneKomma5EVSensor(OneKomma5EVEntity, SensorEntity):
    """Sensor for EV charger data."""

    entity_description: OneKomma5EVSensorDescription

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        ev_id: str,
        ev_label: str,
        description: OneKomma5EVSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, ev_id, ev_label, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        ev = self._get_ev()
        if ev is None:
            return None
        return self.entity_description.value_fn(ev)


class OneKomma5AccumulatingSensor(OneKomma5Entity, RestoreSensor):
    """Base class for sensors that accumulate via trapezoidal integration of a power signal.

    Subclasses provide:
    - ``_get_power_w(data)`` — the power value in W to integrate
    - ``_get_kwh_multiplier()`` — multiplier for delta_kWh (None to skip the sample)

    The accumulated value is persisted across restarts via RestoreSensor.
    """

    _accumulator_precision: int = 3

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        unique_id_suffix: str,
    ) -> None:
        super().__init__(coordinator, system_id, system_name, unique_id_suffix)
        self._accumulated: float = 0.0
        self._last_power: float | None = None
        self._last_time: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore accumulated value after HA restart."""
        await super().async_added_to_hass()
        if (restored := await self.async_get_last_sensor_data()) and restored.native_value is not None:
            try:
                self._accumulated = float(restored.native_value)
            except (TypeError, ValueError):
                self._accumulated = 0.0

    def _get_power_w(self, data: LiveData) -> float | None:
        """Return the power signal (W) to integrate. Subclasses override."""
        raise NotImplementedError

    def _get_kwh_multiplier(self) -> float | None:
        """Return the multiplier applied to delta_kWh. Return None to skip the sample."""
        return 1.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Integrate power over elapsed time and accumulate."""
        if self.coordinator.data is None:
            return
        power_w = self._get_power_w(self.coordinator.data)
        if power_w is None:
            return
        now = dt_util.utcnow()
        if self._last_power is not None and self._last_time is not None:
            delta_kwh = trapezoidal_delta_kwh(
                self._last_power, self._last_time, power_w, now
            )
            if delta_kwh is not None:
                multiplier = self._get_kwh_multiplier()
                if multiplier is not None:
                    self._accumulated += delta_kwh * multiplier
        self._last_power = power_w
        self._last_time = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the accumulated value rounded to the configured precision."""
        return round(self._accumulated, self._accumulator_precision)


class OneKomma5EnergySensor(OneKomma5AccumulatingSensor):
    """Energy sensor (kWh) derived from a power sensor via trapezoidal integration."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3
    _accumulator_precision = 3

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        description: OneKomma5SensorDescription,
    ) -> None:
        super().__init__(coordinator, system_id, system_name, f"{description.key}_energy")
        self._power_fn = description.value_fn
        self._attr_translation_key = f"{description.key}_energy"

    def _get_power_w(self, data: LiveData) -> float | None:
        return self._power_fn(data)


class OneKomma5StablePriceSensor(QuarterHourUpdateMixin, OneKomma5PriceEntity, RestoreSensor):
    """Stable electricity price sensor with hold-last-valid logic.

    Exposes the last known valid electricity price, surviving unavailable/zero
    API responses across coordinator updates and HA restarts.
    """

    _attr_translation_key = "stable_electricity_price"
    _attr_icon = "mdi:currency-eur"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CURRENCY_EUR_PER_KWH
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        """Initialize the stable price sensor."""
        super().__init__(coordinator, system_id, system_name, "stable_electricity_price")
        self._stable_price: float | None = None
        if coordinator.data is not None:
            price = self._dynamic_current_price()
            if price is not None:
                self._stable_price = price

    @property
    def stable_price(self) -> float | None:
        """Return the last known valid electricity price."""
        return self._stable_price

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator; fall back to restored state if coordinator has no price."""
        await super().async_added_to_hass()
        if self._stable_price is None:
            if (restored := await self.async_get_last_sensor_data()) and restored.native_value is not None:
                try:
                    self._stable_price = float(restored.native_value)
                    self.async_write_ha_state()
                except (TypeError, ValueError):
                    pass
        self._async_register_quarter_hour_update()

    @callback
    def _quarter_hour_update(self, _now: datetime) -> None:
        """Override mixin handler: refresh the stable price (not just the state)."""
        self._update_stable_price()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update stable price if the new value is valid."""
        self._update_stable_price()

    def _update_stable_price(self) -> None:
        """Update stable price from current dynamic price."""
        price = self._dynamic_current_price()
        if price is not None:
            self._stable_price = price
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the stable electricity price."""
        if self._stable_price is None:
            return None
        return round(self._stable_price, 6)


class OneKomma5CostSensor(OneKomma5AccumulatingSensor):
    """Accumulated electricity cost sensor (€) derived from grid import power × dynamic price.

    Negative prices reduce the accumulated cost (you get paid for
    consuming electricity).  Accumulation is skipped when price is unavailable.
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2
    _attr_translation_key = "electricity_cost"
    _attr_icon = "mdi:currency-eur"
    _accumulator_precision = 4

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        stable_price_sensor: OneKomma5StablePriceSensor,
    ) -> None:
        super().__init__(coordinator, system_id, system_name, "electricity_cost")
        self._stable_price_sensor = stable_price_sensor

    def _get_power_w(self, data: LiveData) -> float | None:
        return data.live_overview.grid_consumption_power

    def _get_kwh_multiplier(self) -> float | None:
        return self._stable_price_sensor.stable_price


class OneKomma5FeedInRevenueSensor(OneKomma5AccumulatingSensor):
    """Accumulated feed-in revenue sensor (€) derived from grid export power × fixed tariff.

    The tariff is configurable via the integration's options flow and defaults
    to DEFAULT_FEED_IN_TARIFF.  The integration reloads on options change so
    the sensor always starts fresh with the updated tariff.
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2
    _attr_translation_key = "feed_in_revenue"
    _attr_icon = "mdi:transmission-tower-export"
    _accumulator_precision = 4

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        feed_in_tariff: float,
    ) -> None:
        super().__init__(coordinator, system_id, system_name, "feed_in_revenue")
        self._feed_in_tariff = feed_in_tariff

    def _get_power_w(self, data: LiveData) -> float | None:
        return data.live_overview.grid_feed_in_power

    def _get_kwh_multiplier(self) -> float | None:
        return self._feed_in_tariff if self._feed_in_tariff > 0 else None


class OneKomma5OptimizationSensor(OneKomma5OptimizationEntity, SensorEntity):
    """Sensor for optimization event data."""

    entity_description: OneKomma5OptimizationSensorDescription

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        description: OneKomma5OptimizationSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.attr_fn(self.coordinator.data)


class OneKomma5DiagnosticSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic sensor tracking the last successful coordinator update.

    This is the only entity that needs to work with any of the three
    coordinator types, so it inherits ``CoordinatorEntity`` directly and
    builds the device info via ``system_device_info``.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        key: str,
        translation_key: str,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{system_id}_{key}"
        self._attr_translation_key = translation_key
        self._attr_device_info = system_device_info(system_id, system_name)
        self._last_success: datetime | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Record timestamp on successful coordinator update."""
        if self.coordinator.last_update_success:
            self._last_success = dt_util.utcnow()
        self.async_write_ha_state()

    @property
    def native_value(self) -> datetime | None:
        """Return the last successful update timestamp."""
        return self._last_success


def get_ev_label(ev: Any) -> str:
    """Build a human-readable label for an EV charger device."""
    parts = [p for p in (ev.manufacturer(), ev.model()) if p]
    return " ".join(parts) if parts else f"EV {ev.id()[:8]}"
