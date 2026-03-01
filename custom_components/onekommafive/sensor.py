"""Sensor platform for the 1KOMMA5° integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .coordinator import LiveData, PriceData
from .entity import OneKomma5Entity, OneKomma5EVEntity, OneKomma5PriceEntity

CURRENCY_EUR_PER_KWH = "EUR/kWh"


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
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: d.current_price,
    ),
    OneKomma5PriceSensorDescription(
        key="average_electricity_price",
        translation_key="average_electricity_price",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: d.market_prices.average_price_all_in,
    ),
    OneKomma5PriceSensorDescription(
        key="lowest_electricity_price",
        translation_key="lowest_electricity_price",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: d.market_prices.lowest_price_all_in,
    ),
    OneKomma5PriceSensorDescription(
        key="highest_electricity_price",
        translation_key="highest_electricity_price",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EUR_PER_KWH,
        suggested_display_precision=4,
        value_fn=lambda d: d.market_prices.highest_price_all_in,
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    data = entry.runtime_data
    live_coordinator = data.live_coordinator
    price_coordinator = data.price_coordinator
    system = data.system
    system_id = system.id()
    system_name = data.system_name

    entities: list[SensorEntity] = []

    # Live overview sensors
    entities.extend(
        OneKomma5LiveSensor(live_coordinator, system_id, system_name, desc)
        for desc in LIVE_SENSORS
    )

    # Price sensors
    entities.extend(
        OneKomma5PriceSensor(price_coordinator, system_id, system_name, desc)
        for desc in PRICE_SENSORS
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
        return {"forecast": self.coordinator.data.forecast}


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


def _get_ev_label(ev: Any) -> str:
    parts = [p for p in (ev.manufacturer(), ev.model()) if p]
    return " ".join(parts) if parts else f"EV {ev.id()[:8]}"
