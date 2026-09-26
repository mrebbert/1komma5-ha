"""Sensor description dataclasses and catalogues for the 1KOMMA5° integration.

Pure data: dataclass descriptions plus the SENSORS tuples for each category.
The actual entity classes live in ``sensor_entities.py``; the platform
setup (``async_setup_entry``) that wires descriptions to entities lives in
``sensor.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower

from .coordinator import LiveData, OptimizationData, PriceData, WeatherData
from .helpers import get_current_price

_LOGGER = logging.getLogger(__name__)

CURRENCY_EUR_PER_KWH = "EUR/kWh"


@dataclass(frozen=True, kw_only=True)
class OneKomma5SensorDescription(SensorEntityDescription):
    """Sensor entity description with value accessor."""

    value_fn: Callable[[LiveData], Any]
    device_key: str | None = (
        None  # sub-device key (inverter / heat_pump / meter / wallbox); None = system parent
    )


@dataclass(frozen=True, kw_only=True)
class OneKomma5PriceSensorDescription(SensorEntityDescription):
    """Price sensor entity description with value accessor."""

    value_fn: Callable[[PriceData], Any]
    device_key: str | None = None


@dataclass(frozen=True, kw_only=True)
class OneKomma5EVSensorDescription(SensorEntityDescription):
    """EV sensor entity description with value accessor."""

    value_fn: Callable[[Any], Any]  # Any = EVCharger


@dataclass(frozen=True, kw_only=True)
class OneKomma5OptimizationSensorDescription(SensorEntityDescription):
    """Optimization sensor entity description with value accessor."""

    value_fn: Callable[[OptimizationData], Any]
    attr_fn: Callable[[OptimizationData], dict[str, Any] | None] = lambda _: None
    device_key: str | None = None


@dataclass(frozen=True, kw_only=True)
class OneKomma5WeatherSensorDescription(SensorEntityDescription):
    """Weather sensor entity description with value accessor."""

    value_fn: Callable[[WeatherData], Any]
    device_key: str | None = None


# Consumer-cost allocation table: (power sensor key, cost sensor key, sub-device key).
# `None` sub-device keeps the cost sensor on the system parent (no dedicated device).
CONSUMER_COST_SPECS: tuple[tuple[str, str, str | None], ...] = (
    ("heat_pumps_power", "heat_pump_cost", "heat_pump"),
    ("ev_chargers_power", "ev_charger_cost", "wallbox"),
    ("household_power", "household_cost", None),
    ("acs_power", "ac_cost", None),
)

# Power sensors for which an energy counterpart (kWh) is created. Bidirectional
# sensors (battery_power, grid_power) are excluded intentionally; the split
# counterparts (grid_consumption_power / grid_feed_in_power) already cover
# both directions.
ENERGY_SENSOR_KEYS = frozenset(
    {
        "pv_power",
        "grid_consumption_power",
        "grid_feed_in_power",
        "consumption_power",
        "household_power",
        "ev_chargers_power",
        "heat_pumps_power",
        "acs_power",
    }
)


LIVE_SENSORS: tuple[OneKomma5SensorDescription, ...] = (
    OneKomma5SensorDescription(
        key="pv_power",
        translation_key="pv_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.pv_power,
        device_key="inverter",
    ),
    OneKomma5SensorDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.battery_power,
        device_key="inverter",
    ),
    OneKomma5SensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: d.live_overview.battery_soc,
        device_key="inverter",
    ),
    OneKomma5SensorDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.grid_power,
        device_key="meter",
    ),
    OneKomma5SensorDescription(
        key="grid_consumption_power",
        translation_key="grid_consumption_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.grid_consumption_power,
        device_key="meter",
    ),
    OneKomma5SensorDescription(
        key="grid_feed_in_power",
        translation_key="grid_feed_in_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.grid_feed_in_power,
        device_key="meter",
    ),
    OneKomma5SensorDescription(
        key="consumption_power",
        translation_key="consumption_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.consumption_power,
        device_key="meter",
    ),
    OneKomma5SensorDescription(
        key="household_power",
        translation_key="household_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.household_power,
        device_key="meter",
    ),
    OneKomma5SensorDescription(
        key="ev_chargers_power",
        translation_key="ev_chargers_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.ev_chargers_power,
        device_key="wallbox",
    ),
    OneKomma5SensorDescription(
        key="heat_pumps_power",
        translation_key="heat_pumps_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.live_overview.heat_pumps_power,
        device_key="heat_pump",
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
        value_fn=lambda d: (
            get_current_price(d.all_in_prices) if d.all_in_prices else d.current_price
        ),
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
        value_fn=lambda d: (
            round(d.tomorrow_average_price, 6)
            if d.tomorrow_average_price is not None
            else None
        ),
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
        value_fn=lambda d: (
            max(d.live_overview.battery_power, 0)
            if d.live_overview.battery_power is not None
            else None
        ),
        device_key="inverter",
    ),
    OneKomma5SensorDescription(
        key="battery_discharge_power",
        translation_key="battery_discharge_power_energy",
        value_fn=lambda d: (
            max(-d.live_overview.battery_power, 0)
            if d.live_overview.battery_power is not None
            else None
        ),
        device_key="inverter",
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
    # Static vehicle spec — nominal battery capacity (Wh → kWh). No state_class:
    # a near-constant value would only draw a flat line in Long-Term Statistics.
    OneKomma5EVSensorDescription(
        key="ev_battery_capacity",
        translation_key="ev_battery_capacity",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        icon="mdi:car-battery",
        value_fn=lambda ev: (
            ev.capacity_wh() / 1000 if ev.capacity_wh() is not None else None
        ),
    ),
    # Scheduled departure SoC target — distinct from `target_soc` (the manual
    # override). Read-only in the SDK, so a sensor rather than a number.
    OneKomma5EVSensorDescription(
        key="ev_scheduled_departure_soc",
        translation_key="ev_scheduled_departure_soc",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        icon="mdi:battery-clock",
        value_fn=lambda ev: ev.primary_schedule_departure_soc(),
    ),
)

# Known values of ``OptimizationEvent.decision`` — mirrors the ENUM options
# on the ``optimization_last_decision`` sensor. The SDK documents this list
# as explicitly non-exhaustive; ``_coerce_known_decision`` folds unknown
# values to ``None`` and logs once so HA's ENUM validation does not raise.
_KNOWN_DECISIONS: frozenset[str] = frozenset(
    {
        "battery_charge_from_grid",
        "battery_discharge_to_grid",
        "battery_no_charge",
        "battery_no_discharge",
        "ev_charge_from_grid",
        "heatpump_recommend_on",
        "heatpump_auto",
    }
)


def _coerce_known_decision(value: str | None) -> str | None:
    """Return ``value.lower()`` if it is a known decision, else ``None``.

    Logs the first unknown value seen so a new cloud-side enum surfaces in
    the log without spamming on every 15-minute refresh.
    """
    if value is None:
        return None
    lowered = value.lower()
    if lowered in _KNOWN_DECISIONS:
        return lowered
    _LOGGER.warning(
        "Unknown optimization decision %r; extend _KNOWN_DECISIONS + sensor "
        "options to surface it. Sensor stays 'unknown' meanwhile.",
        value,
    )
    return None


OPTIMIZATION_SENSORS: tuple[OneKomma5OptimizationSensorDescription, ...] = (
    OneKomma5OptimizationSensorDescription(
        key="optimization_event_count",
        translation_key="optimization_event_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:counter",
        value_fn=lambda d: d.event_count,
        attr_fn=lambda d: (
            {
                "decisions": [
                    {
                        "asset": e.asset,
                        "decision": e.decision,
                        "from": e.from_time,
                        "to": getattr(e, "end_time", None) or e.to_time,
                        "slot_count": getattr(e, "slot_count", 1),
                        "market_price": e.market_price,
                    }
                    for e in d.events
                ]
            }
            if d.events
            else None
        ),
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
        value_fn=lambda d: (
            round(d.energy_bought, 2) if d.energy_bought is not None else None
        ),
    ),
    OneKomma5OptimizationSensorDescription(
        key="optimization_energy_sold",
        translation_key="optimization_energy_sold",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: (
            round(d.energy_sold, 2) if d.energy_sold is not None else None
        ),
    ),
    OneKomma5OptimizationSensorDescription(
        key="optimization_last_decision",
        translation_key="optimization_last_decision",
        icon="mdi:brain",
        device_class=SensorDeviceClass.ENUM,
        # HA's translation-key validation requires lowercase `[a-z0-9-_]+`;
        # the SDK enum is uppercase (`BATTERY_CHARGE_FROM_GRID`, …), so we
        # lowercase the value at the sensor layer. Automations that match
        # on the state must use lowercase too.
        # The SDK's `decision` field is explicitly documented as "not
        # exhaustive"; the coerce below folds unknown values to `None` so a
        # new cloud-side enum value does not crash the sensor with a
        # ValueError from HA's ENUM validation.
        options=[
            "battery_charge_from_grid",
            "battery_discharge_to_grid",
            "battery_no_charge",
            "battery_no_discharge",
            "ev_charge_from_grid",
            "heatpump_recommend_on",
            "heatpump_auto",
        ],
        value_fn=lambda d: (
            _coerce_known_decision(d.last_event.decision) if d.last_event else None
        ),
        attr_fn=lambda d: (
            {
                "asset": d.last_event.asset,
                "from": d.last_event.from_time,
                "to": getattr(d.last_event, "end_time", None) or d.last_event.to_time,
                "slot_count": getattr(d.last_event, "slot_count", 1),
                "market_price": d.last_event.market_price,
                "state_of_charge": d.last_event.state_of_charge,
            }
            if d.last_event
            else None
        ),
    ),
)


WEATHER_SENSORS: tuple[OneKomma5WeatherSensorDescription, ...] = (
    OneKomma5WeatherSensorDescription(
        key="weather_sunshine_today",
        translation_key="weather_sunshine_today",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="min",
        icon="mdi:weather-sunny",
        value_fn=lambda d: d.weather.today.sunshine_minutes,
    ),
    OneKomma5WeatherSensorDescription(
        key="weather_sunshine_tomorrow",
        translation_key="weather_sunshine_tomorrow",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="min",
        icon="mdi:weather-sunny",
        value_fn=lambda d: d.weather.tomorrow.sunshine_minutes,
    ),
)
