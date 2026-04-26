"""Sensor platform for the 1KOMMA5° integration.

This file contains:
- The SENSORS configuration tuples (which sensors to create)
- ``async_setup_entry`` (platform entry point)

Sensor entity classes live in ``sensor_entities.py`` and dataclass
descriptions in ``sensor_descriptions.py``.
"""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .const import CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF
from .helpers import get_current_price
from .sensor_descriptions import (
    OneKomma5EVSensorDescription,
    OneKomma5OptimizationSensorDescription,
    OneKomma5PriceSensorDescription,
    OneKomma5SensorDescription,
)
from .entity import get_ev_label
from .sensor_entities import (
    CURRENCY_EUR_PER_KWH,
    OneKomma5CostSensor,
    OneKomma5DiagnosticSensor,
    OneKomma5EnergySensor,
    OneKomma5EVSensor,
    OneKomma5FeedInRevenueSensor,
    OneKomma5LiveSensor,
    OneKomma5OptimizationSensor,
    OneKomma5PriceSensor,
    OneKomma5StablePriceSensor,
)

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
    # Optimization aggregations are daily snapshots that reset at midnight when
    # the coordinator fetches a new day's events. They are intentionally NOT
    # state_class TOTAL/TOTAL_INCREASING — that would feed Long-Term Statistics
    # with a reset every midnight (without last_reset HA records the drop as
    # an anomaly). Device class is still useful for unit formatting.
    OneKomma5OptimizationSensorDescription(
        key="optimization_total_cost",
        translation_key="optimization_total_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        icon="mdi:piggy-bank-outline",
        value_fn=lambda d: round(d.total_cost, 2) if d.total_cost is not None else None,
    ),
    OneKomma5OptimizationSensorDescription(
        key="optimization_energy_bought",
        translation_key="optimization_energy_bought",
        device_class=SensorDeviceClass.ENERGY,
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
            ev_label = get_ev_label(ev)
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
