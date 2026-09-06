"""Sensor platform for the 1KOMMA5° integration.

This file contains:
- The SENSORS configuration tuples (which sensors to create)
- ``async_setup_entry`` (platform entry point)

Sensor entity classes live in ``sensor_entities.py`` and dataclass
descriptions in ``sensor_descriptions.py``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .const import (
    CONF_CHARGING_WINDOW_DURATION_MINUTES,
    CONF_FEED_IN_TARIFF,
    DEFAULT_CHARGING_WINDOW_DURATION_MINUTES,
    DEFAULT_FEED_IN_TARIFF,
)
from .entity import apply_stable_entity_ids, resolve_asset, resolve_assets_by_type
from .helpers import get_current_price
from .sensor_descriptions import (
    OneKomma5EVSensorDescription,
    OneKomma5OptimizationSensorDescription,
    OneKomma5PriceSensorDescription,
    OneKomma5SensorDescription,
    OneKomma5WeatherSensorDescription,
)
from .sensor_entities import (
    CURRENCY_EUR_PER_KWH,
    OneKomma5ActiveFeaturesSensor,
    OneKomma5CheapestChargingWindowSensor,
    OneKomma5CheapestChargingWindowTomorrowSensor,
    OneKomma5ConsumerCostSensor,
    OneKomma5CostSensor,
    OneKomma5DailySavingsSensor,
    OneKomma5DiagnosticSensor,
    OneKomma5DynamicPulsePriceGuaranteeSensor,
    OneKomma5EnergySensor,
    OneKomma5EVSensor,
    OneKomma5FeedInRevenueSensor,
    OneKomma5LiveSensor,
    OneKomma5OptimizationSensor,
    OneKomma5PriceSensor,
    OneKomma5StablePriceSensor,
    OneKomma5SystemAgeDaysSensor,
    OneKomma5WeatherSensor,
)

CONSUMER_COST_SPECS: tuple[tuple[str, str, str | None], ...] = (
    ("heat_pumps_power", "heat_pump_cost", "heat_pump"),
    ("ev_chargers_power", "ev_charger_cost", "wallbox"),
    ("household_power", "household_cost", None),  # stays on system parent
    ("acs_power", "ac_cost", None),  # ACS mocked by API, stays on parent
)

# Power sensors for which an energy counterpart (kWh) is created.
# Bidirectional sensors (battery_power, grid_power) are excluded intentionally —
# grid_consumption_power / grid_feed_in_power already cover those directions.
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
            round(d.tomorrow_average_price, 6) if d.tomorrow_average_price is not None else None
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
        value_fn=lambda ev: ev.capacity_wh() / 1000 if ev.capacity_wh() is not None else None,
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
                        "to": e.to_time,
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
        value_fn=lambda d: round(d.energy_bought, 2) if d.energy_bought is not None else None,
    ),
    OneKomma5OptimizationSensorDescription(
        key="optimization_energy_sold",
        translation_key="optimization_energy_sold",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: round(d.energy_sold, 2) if d.energy_sold is not None else None,
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
        options=[
            "battery_charge_from_grid",
            "battery_no_charge",
            "battery_no_discharge",
            "heatpump_recommend_on",
            "heatpump_auto",
        ],
        value_fn=lambda d: d.last_event.decision.lower() if d.last_event else None,
        attr_fn=lambda d: (
            {
                "asset": d.last_event.asset,
                "from": d.last_event.from_time,
                "to": d.last_event.to_time,
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
    weather_coordinator = data.weather_coordinator
    system = data.system
    system_id = system.id()
    system_name = data.system_name
    currency = data.currency

    # Resolve assets-by-type once for sub-device DeviceInfo lookup.
    # Empty dict when SystemStatusCoordinator has no data yet (first-refresh
    # rate-limit) — entities fall back to the system parent until a later
    # reload picks the sub-devices up.
    assets_by_type = resolve_assets_by_type(data)

    def _resolve_asset(device_key: str | None) -> Any | None:
        return resolve_asset(assets_by_type, device_key)

    # FoxESS-style installs expose the battery as its own `BATTERY` asset
    # separate from the inverter (`PV_SYSTEM`); Sungrow-style installs report
    # a single `HYBRID` asset with the battery integrated. Re-parent the
    # battery-related power/energy sensors to the dedicated `battery`
    # sub-device only when the cloud actually reports a separate `BATTERY`
    # asset — otherwise keep the historical `inverter` grouping so
    # single-`HYBRID` users don't grow an empty battery device.
    _BATTERY_ENTITY_KEYS = frozenset(
        {
            "battery_power",
            "battery_soc",
            "battery_charge_power",
            "battery_discharge_power",
        }
    )

    def _adapt(desc: OneKomma5SensorDescription) -> OneKomma5SensorDescription:
        if desc.key in _BATTERY_ENTITY_KEYS and "BATTERY" in assets_by_type:
            return replace(desc, device_key="battery")
        return desc

    # Battery-split re-routing runs once per descriptor; the three loops below
    # then reuse the adapted view instead of re-adapting on every iteration.
    adapted_live = tuple(_adapt(d) for d in LIVE_SENSORS)
    adapted_battery_split = tuple(_adapt(d) for d in BATTERY_SPLIT_DESCRIPTORS)

    entities: list[SensorEntity] = []

    # Live overview sensors
    entities.extend(
        OneKomma5LiveSensor(
            live_coordinator,
            system_id,
            system_name,
            adapted,
            asset=_resolve_asset(adapted.device_key),
            parent_device_id=data.system_device_id,
        )
        for adapted in adapted_live
    )

    # Energy sensors (trapezoidal integration of power sensors)
    entities.extend(
        OneKomma5EnergySensor(
            live_coordinator,
            system_id,
            system_name,
            adapted,
            asset=_resolve_asset(adapted.device_key),
            parent_device_id=data.system_device_id,
        )
        for adapted in adapted_live
        if adapted.key in ENERGY_SENSOR_KEYS
    )

    # Battery split energy sensors (charge / discharge direction)
    entities.extend(
        OneKomma5EnergySensor(
            live_coordinator,
            system_id,
            system_name,
            adapted,
            asset=_resolve_asset(adapted.device_key),
            parent_device_id=data.system_device_id,
        )
        for adapted in adapted_battery_split
    )

    # Price sensors
    entities.extend(
        OneKomma5PriceSensor(price_coordinator, system_id, system_name, desc, currency=currency)
        for desc in PRICE_SENSORS
    )

    # Stable price sensor (hold-last-valid)
    stable_price_sensor = OneKomma5StablePriceSensor(
        price_coordinator, system_id, system_name, currency=currency
    )
    entities.append(stable_price_sensor)

    # Cheapest charging window today (timestamp sensor + window attributes).
    # Duration is option-driven (default 60 min, multiples of 15).
    charging_window_duration = entry.options.get(
        CONF_CHARGING_WINDOW_DURATION_MINUTES,
        DEFAULT_CHARGING_WINDOW_DURATION_MINUTES,
    )
    entities.append(
        OneKomma5CheapestChargingWindowSensor(
            price_coordinator, system_id, system_name, charging_window_duration
        )
    )
    entities.append(
        OneKomma5CheapestChargingWindowTomorrowSensor(
            price_coordinator, system_id, system_name, charging_window_duration
        )
    )

    # Accumulated electricity cost sensor
    entities.append(
        OneKomma5CostSensor(
            live_coordinator, system_id, system_name, stable_price_sensor, currency=currency
        )
    )

    # Per-consumer cost sensors — proportional share of the grid-import cost.
    # Sum of the four equals `electricity_cost` (invariant verified by tests).
    entities.extend(
        OneKomma5ConsumerCostSensor(
            live_coordinator,
            system_id,
            system_name,
            stable_price_sensor,
            attr,
            key,
            device_key=device_key,
            asset=_resolve_asset(device_key),
            currency=currency,
            parent_device_id=data.system_device_id,
        )
        for attr, key, device_key in CONSUMER_COST_SPECS
    )

    # Feed-in revenue sensor — parented to the meter sub-device.
    feed_in_tariff = entry.options.get(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)
    entities.append(
        OneKomma5FeedInRevenueSensor(
            live_coordinator,
            system_id,
            system_name,
            feed_in_tariff,
            asset=_resolve_asset("meter"),
            currency=currency,
            parent_device_id=data.system_device_id,
        )
    )

    # Optimization sensors
    entities.extend(
        OneKomma5OptimizationSensor(
            optimization_coordinator, system_id, system_name, desc, currency=currency
        )
        for desc in OPTIMIZATION_SENSORS
    )

    # Weather sensors (sunshine forecast — extra to the WeatherEntity)
    entities.extend(
        OneKomma5WeatherSensor(weather_coordinator, system_id, system_name, desc)
        for desc in WEATHER_SENSORS
    )

    # EV (vehicle) sensors — one set per vehicle, hung under the system parent.
    if live_coordinator.data:
        for ev in live_coordinator.data.ev_chargers:
            entities.extend(
                OneKomma5EVSensor(
                    live_coordinator, system_id, system_name, ev, desc, data.system_device_id
                )
                for desc in EV_SENSORS
            )

    # Daily savings sensor (cloud-computed, resets at local midnight)
    entities.append(
        OneKomma5DailySavingsSensor(
            data.energy_coordinator,
            system_id,
            system_name,
            currency=currency,
            co2_saved_kg=data.co2_saved_kg,
        )
    )

    # Dynamic-Pulse price-guarantee sensor. Only created when the account has
    # a DYNAMIC_PULSE subscription AND the guarantee field is populated —
    # accounts without DP get no unavailable sensor to worry about.
    if data.price_guarantee is not None and data.price_guarantee.value_eur_per_kwh is not None:
        entities.append(
            OneKomma5DynamicPulsePriceGuaranteeSensor(
                data.system_status_coordinator,
                system_id,
                system_name,
                data.price_guarantee.value_eur_per_kwh,
                data.price_guarantee.version,
                currency=currency,
            )
        )

    # Diagnostic sensors (last successful update per coordinator)
    entities.extend(
        OneKomma5DiagnosticSensor(coordinator, system_id, system_name, key)
        for coordinator, key in (
            (live_coordinator, "diag_live_update"),
            (price_coordinator, "diag_price_update"),
            (optimization_coordinator, "diag_optimization_update"),
            (weather_coordinator, "diag_weather_update"),
            (data.system_status_coordinator, "diag_system_status_update"),
            (data.energy_coordinator, "diag_energy_update"),
            (data.notifications_coordinator, "diag_notification_update"),
        )
    )

    entities.append(
        OneKomma5ActiveFeaturesSensor(
            data.system_status_coordinator,
            system_id,
            system_name,
        )
    )

    entities.append(
        OneKomma5SystemAgeDaysSensor(
            data.system_status_coordinator,
            system_id,
            system_name,
            data.details,
        )
    )

    apply_stable_entity_ids(entities, SENSOR_DOMAIN)
    async_add_entities(entities)
