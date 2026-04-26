"""Sensor platform for the 1KOMMA5° integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from . import OneKomma5ConfigEntry
from .const import CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF, DOMAIN
from .coordinator import LiveData, OptimizationData, PriceData, get_current_price
from .entity import (
    OneKomma5Entity,
    OneKomma5EVEntity,
    OneKomma5OptimizationEntity,
    OneKomma5PriceEntity,
)

CURRENCY_EUR_PER_KWH = "EUR/kWh"

# Power sensors for which an energy counterpart (kWh) is created.
# Bidirectional sensors (battery_power, grid_power) are excluded intentionally —
# grid_consumption_power / grid_feed_in_power already cover those directions.
ENERGY_SENSOR_KEYS = frozenset({
    "pv_power",
    "grid_consumption_power",
    "grid_feed_in_power",
    "consumption_power",
    "household_power",
    "ev_chargers_power",
    "heat_pumps_power",
    "acs_power",
})



@dataclass(frozen=True, kw_only=True)
class OneKomma5SensorDescription(SensorEntityDescription):
    """Sensor entity description with value accessor."""

    value_fn: Callable[[LiveData], Any]


@dataclass(frozen=True, kw_only=True)
class OneKomma5PriceSensorDescription(SensorEntityDescription):
    """Price sensor entity description with value accessor."""

    value_fn: Callable[[PriceData], Any]


@dataclass(frozen=True, kw_only=True)
class OneKomma5EVSensorDescription(SensorEntityDescription):
    """EV sensor entity description with value accessor."""

    value_fn: Callable[[Any], Any]  # Any = EVCharger


LIVE_SENSORS: tuple[OneKomma5SensorDescription, ...] = (
    OneKomma5SensorDescription(
        key="pv_power",
        translation_key="pv_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.pv_power,
    ),
    OneKomma5SensorDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.battery_power,
    ),
    OneKomma5SensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: d.live_overview.battery_soc,
    ),
    OneKomma5SensorDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.grid_power,
    ),
    OneKomma5SensorDescription(
        key="grid_consumption_power",
        translation_key="grid_consumption_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.grid_consumption_power,
    ),
    OneKomma5SensorDescription(
        key="grid_feed_in_power",
        translation_key="grid_feed_in_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.grid_feed_in_power,
    ),
    OneKomma5SensorDescription(
        key="consumption_power",
        translation_key="consumption_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.consumption_power,
    ),
    OneKomma5SensorDescription(
        key="household_power",
        translation_key="household_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.household_power,
    ),
    OneKomma5SensorDescription(
        key="ev_chargers_power",
        translation_key="ev_chargers_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.ev_chargers_power,
    ),
    OneKomma5SensorDescription(
        key="heat_pumps_power",
        translation_key="heat_pumps_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.heat_pumps_power,
    ),
    OneKomma5SensorDescription(
        key="acs_power",
        translation_key="acs_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.acs_power,
    ),
    OneKomma5SensorDescription(
        key="self_sufficiency",
        translation_key="self_sufficiency",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: (
            round(d.live_overview.self_sufficiency * 100, 1)
            if d.live_overview.self_sufficiency is not None
            else None
        ),
    ),
)

PRICE_SENSORS: tuple[OneKomma5PriceSensorDescription, ...] = (
    OneKomma5PriceSensorDescription(
        key="current_electricity_price",
        translation_key="current_electricity_price",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: get_current_price(d.all_in_prices) if d.all_in_prices else d.current_price,
    ),
    OneKomma5PriceSensorDescription(
        key="average_electricity_price",
        translation_key="average_electricity_price",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: d.market_prices.average_price_all_in,
    ),
    OneKomma5PriceSensorDescription(
        key="lowest_electricity_price",
        translation_key="lowest_electricity_price",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: d.market_prices.lowest_price_all_in,
    ),
    OneKomma5PriceSensorDescription(
        key="highest_electricity_price",
        translation_key="highest_electricity_price",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: d.market_prices.highest_price_all_in,
    ),
    OneKomma5PriceSensorDescription(
        key="negative_price_slots_today",
        translation_key="negative_price_slots_today",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-minus",
        value_fn=lambda d: d.negative_price_slots_today,
    ),
    OneKomma5PriceSensorDescription(
        key="negative_price_slots_tomorrow",
        translation_key="negative_price_slots_tomorrow",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-minus",
        value_fn=lambda d: d.negative_price_slots_tomorrow,
    ),
    OneKomma5PriceSensorDescription(
        key="tomorrow_average_price",
        translation_key="tomorrow_average_price",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: round(d.tomorrow_average_price, 6)
        if d.tomorrow_average_price is not None
        else None,
    ),
    OneKomma5PriceSensorDescription(
        key="tomorrow_lowest_price",
        translation_key="tomorrow_lowest_price",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: d.tomorrow_lowest_price,
    ),
    OneKomma5PriceSensorDescription(
        key="tomorrow_highest_price",
        translation_key="tomorrow_highest_price",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: d.tomorrow_highest_price,
    ),
)

# Virtual power descriptors used only for battery energy integration (not exposed as live sensors).
BATTERY_SPLIT_DESCRIPTORS: tuple[OneKomma5SensorDescription, ...] = (
    OneKomma5SensorDescription(
        key="battery_charge_power",
        translation_key="battery_charge_power_energy",
        value_fn=lambda d: max(d.live_overview.battery_power, 0)
        if d.live_overview.battery_power is not None
        else None,
    ),
    OneKomma5SensorDescription(
        key="battery_discharge_power",
        translation_key="battery_discharge_power_energy",
        value_fn=lambda d: max(-d.live_overview.battery_power, 0)
        if d.live_overview.battery_power is not None
        else None,
    ),
)

EV_SENSORS: tuple[OneKomma5EVSensorDescription, ...] = (
    OneKomma5EVSensorDescription(
        key="ev_target_soc",
        translation_key="ev_target_soc",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda ev: ev.target_soc(),
    ),
    OneKomma5EVSensorDescription(
        key="ev_charging_mode",
        translation_key="ev_charging_mode",
        value_fn=lambda ev: ev.charging_mode().value,
    ),
)


@dataclass(frozen=True, kw_only=True)
class OneKomma5OptimizationSensorDescription(SensorEntityDescription):
    """Optimization sensor entity description with value accessor."""

    value_fn: Callable[[OptimizationData], Any]
    attr_fn: Callable[[OptimizationData], dict[str, Any] | None] = lambda _: None


OPTIMIZATION_SENSORS: tuple[OneKomma5OptimizationSensorDescription, ...] = (
    OneKomma5OptimizationSensorDescription(
        key="optimization_event_count",
        translation_key="optimization_event_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:counter",
        value_fn=lambda d: d.event_count,
        attr_fn=lambda d: {
            "decisions": [
                {
                    "asset": e.asset,
                    "decision": e.decision,
                    "from": e.from_time,
                    "to": e.to_time,
                    "market_price": e.market_price,
                }
                for e in d.events
            ]
        }
        if d.events
        else None,
    ),
    OneKomma5OptimizationSensorDescription(
        key="optimization_total_cost",
        translation_key="optimization_total_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        icon="mdi:piggy-bank-outline",
        value_fn=lambda d: round(d.total_cost, 2) if d.total_cost is not None else None,
    ),
    OneKomma5OptimizationSensorDescription(
        key="optimization_energy_bought",
        translation_key="optimization_energy_bought",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: round(d.energy_bought, 2)
        if d.energy_bought is not None
        else None,
    ),
    OneKomma5OptimizationSensorDescription(
        key="optimization_energy_sold",
        translation_key="optimization_energy_sold",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: round(d.energy_sold, 2)
        if d.energy_sold is not None
        else None,
    ),
    OneKomma5OptimizationSensorDescription(
        key="optimization_last_decision",
        translation_key="optimization_last_decision",
        icon="mdi:brain",
        value_fn=lambda d: d.last_event.decision if d.last_event else None,
        attr_fn=lambda d: {
            "asset": d.last_event.asset,
            "from": d.last_event.from_time,
            "to": d.last_event.to_time,
            "market_price": d.last_event.market_price,
            "state_of_charge": d.last_event.state_of_charge,
        }
        if d.last_event
        else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    data = entry.runtime_data
    live_coordinator = data.live_coordinator
    price_coordinator = data.price_coordinator
    optimization_coordinator = data.optimization_coordinator
    system = data.system
    system_id = system.id()
    system_name = data.system_name

    entities: list[SensorEntity] = []

    # Live overview sensors
    entities.extend(
        OneKomma5LiveSensor(live_coordinator, system_id, system_name, desc)
        for desc in LIVE_SENSORS
    )

    # Energy sensors (trapezoidal integration of power sensors)
    entities.extend(
        OneKomma5EnergySensor(live_coordinator, system_id, system_name, desc)
        for desc in LIVE_SENSORS
        if desc.key in ENERGY_SENSOR_KEYS
    )

    # Battery split energy sensors (charge / discharge direction)
    entities.extend(
        OneKomma5EnergySensor(live_coordinator, system_id, system_name, desc)
        for desc in BATTERY_SPLIT_DESCRIPTORS
    )

    # Price sensors
    entities.extend(
        OneKomma5PriceSensor(price_coordinator, system_id, system_name, desc)
        for desc in PRICE_SENSORS
    )

    # Stable price sensor (hold-last-valid)
    stable_price_sensor = OneKomma5StablePriceSensor(price_coordinator, system_id, system_name)
    entities.append(stable_price_sensor)

    # Accumulated electricity cost sensor
    entities.append(OneKomma5CostSensor(live_coordinator, system_id, system_name, stable_price_sensor))

    # Feed-in revenue sensor
    feed_in_tariff = entry.options.get(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)
    entities.append(OneKomma5FeedInRevenueSensor(live_coordinator, system_id, system_name, feed_in_tariff))

    # Optimization sensors
    entities.extend(
        OneKomma5OptimizationSensor(optimization_coordinator, system_id, system_name, desc)
        for desc in OPTIMIZATION_SENSORS
    )

    # EV charger sensors (one set per charger)
    if live_coordinator.data:
        for ev in live_coordinator.data.ev_chargers:
            ev_id = ev.id()
            ev_label = _get_ev_label(ev)
            entities.extend(
                OneKomma5EVSensor(live_coordinator, system_id, system_name, ev_id, ev_label, desc)
                for desc in EV_SENSORS
            )

    # Diagnostic sensors (last successful update per coordinator)
    entities.append(OneKomma5DiagnosticSensor(
        live_coordinator, system_id, system_name,
        "diag_live_update", "diag_live_update",
    ))
    entities.append(OneKomma5DiagnosticSensor(
        price_coordinator, system_id, system_name,
        "diag_price_update", "diag_price_update",
    ))
    entities.append(OneKomma5DiagnosticSensor(
        optimization_coordinator, system_id, system_name,
        "diag_optimization_update", "diag_optimization_update",
    ))

    async_add_entities(entities)


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


class OneKomma5PriceSensor(OneKomma5PriceEntity, SensorEntity):
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
        """Register quarter-hour update for dynamic price sensors."""
        await super().async_added_to_hass()
        if self.entity_description.key == "current_electricity_price":
            self.async_on_remove(
                async_track_time_change(
                    self.hass, self._quarter_hour_update,
                    minute=[0, 15, 30, 45], second=[0],
                )
            )

    @callback
    def _quarter_hour_update(self, _now: datetime) -> None:
        """Re-evaluate the current price slot at quarter-hour boundaries."""
        self.async_write_ha_state()

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


class OneKomma5EnergySensor(OneKomma5Entity, RestoreSensor):
    """Energy sensor (kWh) derived from a power sensor via trapezoidal integration.

    The accumulated value is persisted across restarts via RestoreSensor.
    Only positive power contributions are counted so the state class
    TOTAL_INCREASING is never violated.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        description: OneKomma5SensorDescription,
    ) -> None:
        """Initialize the energy sensor."""
        super().__init__(coordinator, system_id, system_name, f"{description.key}_energy")
        self._power_fn = description.value_fn
        self._attr_translation_key = f"{description.key}_energy"
        self._kwh: float = 0.0
        self._last_power: float | None = None
        self._last_time: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore accumulated energy after HA restart."""
        await super().async_added_to_hass()
        if (restored := await self.async_get_last_sensor_data()) and restored.native_value is not None:
            try:
                self._kwh = float(restored.native_value)
            except (TypeError, ValueError):
                self._kwh = 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Integrate power (W) over elapsed time and accumulate kWh."""
        if self.coordinator.data is None:
            return
        power_w = self._power_fn(self.coordinator.data)
        if power_w is None:
            return
        now = dt_util.utcnow()
        if self._last_power is not None and self._last_time is not None:
            dt_hours = (now - self._last_time).total_seconds() / 3600
            avg_w = (self._last_power + power_w) / 2
            if avg_w > 0:
                self._kwh += avg_w * dt_hours / 1000
        self._last_power = power_w
        self._last_time = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the accumulated energy in kWh."""
        return round(self._kwh, 3)


class OneKomma5StablePriceSensor(OneKomma5PriceEntity, RestoreSensor):
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
            price = self._dynamic_price()
            if price is not None:
                self._stable_price = price

    def _dynamic_price(self) -> float | None:
        """Look up the current price dynamically from stored price data."""
        if self.coordinator.data is None:
            return None
        if self.coordinator.data.all_in_prices:
            return get_current_price(self.coordinator.data.all_in_prices)
        return self.coordinator.data.current_price

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
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._quarter_hour_update,
                minute=[0, 15, 30, 45], second=[0],
            )
        )

    @callback
    def _quarter_hour_update(self, _now: datetime) -> None:
        """Re-evaluate the current price slot at quarter-hour boundaries."""
        self._update_stable_price()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update stable price if the new value is valid."""
        self._update_stable_price()

    def _update_stable_price(self) -> None:
        """Update stable price from current dynamic price."""
        price = self._dynamic_price()
        if price is not None:
            self._stable_price = price
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the stable electricity price."""
        if self._stable_price is None:
            return None
        return round(self._stable_price, 6)


class OneKomma5CostSensor(OneKomma5Entity, RestoreSensor):
    """Accumulated electricity cost sensor (€) derived from grid import power × dynamic price.

    On each coordinator update the trapezoidal power integral is computed
    (identical to OneKomma5EnergySensor) and multiplied by the current stable
    price.  Negative prices reduce the accumulated cost (you get paid for
    consuming electricity).  Guards prevent accumulation when price is
    unavailable.
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2
    _attr_translation_key = "electricity_cost"
    _attr_icon = "mdi:currency-eur"

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        stable_price_sensor: OneKomma5StablePriceSensor,
    ) -> None:
        """Initialize the cost sensor."""
        super().__init__(coordinator, system_id, system_name, "electricity_cost")
        self._stable_price_sensor = stable_price_sensor
        self._cost: float = 0.0
        self._last_power: float | None = None
        self._last_time: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore accumulated cost after HA restart."""
        await super().async_added_to_hass()
        if (restored := await self.async_get_last_sensor_data()) and restored.native_value is not None:
            try:
                self._cost = float(restored.native_value)
            except (TypeError, ValueError):
                self._cost = 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Integrate grid import power over time and accumulate cost."""
        if self.coordinator.data is None:
            return
        power_w = self.coordinator.data.live_overview.grid_consumption_power
        if power_w is None:
            return
        now = dt_util.utcnow()
        if self._last_power is not None and self._last_time is not None:
            dt_hours = (now - self._last_time).total_seconds() / 3600
            avg_w = (self._last_power + power_w) / 2
            if avg_w > 0:
                delta_kwh = avg_w * dt_hours / 1000
                price = self._stable_price_sensor.stable_price
                if price is not None:
                    self._cost += delta_kwh * price
        self._last_power = power_w
        self._last_time = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the accumulated electricity cost in EUR."""
        return round(self._cost, 4)


class OneKomma5FeedInRevenueSensor(OneKomma5Entity, RestoreSensor):
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

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        feed_in_tariff: float,
    ) -> None:
        """Initialize the feed-in revenue sensor."""
        super().__init__(coordinator, system_id, system_name, "feed_in_revenue")
        self._feed_in_tariff = feed_in_tariff
        self._revenue: float = 0.0
        self._last_power: float | None = None
        self._last_time: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore accumulated revenue after HA restart."""
        await super().async_added_to_hass()
        if (restored := await self.async_get_last_sensor_data()) and restored.native_value is not None:
            try:
                self._revenue = float(restored.native_value)
            except (TypeError, ValueError):
                self._revenue = 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Integrate grid export power over time and accumulate revenue."""
        if self.coordinator.data is None:
            return
        power_w = self.coordinator.data.live_overview.grid_feed_in_power
        if power_w is None:
            return
        now = dt_util.utcnow()
        if self._last_power is not None and self._last_time is not None:
            dt_hours = (now - self._last_time).total_seconds() / 3600
            avg_w = (self._last_power + power_w) / 2
            if avg_w > 0 and self._feed_in_tariff > 0:
                delta_kwh = avg_w * dt_hours / 1000
                self._revenue += delta_kwh * self._feed_in_tariff
        self._last_power = power_w
        self._last_time = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the accumulated feed-in revenue in EUR."""
        return round(self._revenue, 4)


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
    """Diagnostic sensor tracking the last successful coordinator update."""

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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, system_id)},
            name=system_name,
            manufacturer="1KOMMA5°",
            model="Heartbeat",
        )
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


def _get_ev_label(ev: Any) -> str:
    parts = [p for p in (ev.manufacturer(), ev.model()) if p]
    return " ".join(parts) if parts else f"EV {ev.id()[:8]}"
