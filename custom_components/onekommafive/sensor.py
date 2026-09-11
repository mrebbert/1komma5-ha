"""Sensor platform for the 1KOMMA5° integration.

This file only wires descriptions to entities in ``async_setup_entry``.
Description dataclasses and the SENSORS tuples live in
``sensor_descriptions.py``; entity classes live in ``sensor_entities.py``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .const import (
    CONF_CHARGING_WINDOW_DURATION_MINUTES,
    CONF_FEED_IN_TARIFF,
    DEFAULT_CHARGING_WINDOW_DURATION_MINUTES,
    DEFAULT_FEED_IN_TARIFF,
)
from .entity import (
    apply_stable_entity_ids,
    ev_wallbox_parent,
    resolve_asset,
    resolve_assets_by_type,
)
from .sensor_descriptions import (
    BATTERY_SPLIT_DESCRIPTORS,
    CONSUMER_COST_SPECS,
    ENERGY_SENSOR_KEYS,
    EV_SENSORS,
    LIVE_SENSORS,
    OPTIMIZATION_SENSORS,
    PRICE_SENSORS,
    WEATHER_SENSORS,
    OneKomma5SensorDescription,
)
from .sensor_entities import (
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

    # EV (vehicle) sensors — one set per vehicle, hung under the paired
    # wallbox sub-device (when the cloud reports a pairing) or the system
    # parent (unpaired vehicle / single-wallbox setup).
    if live_coordinator.data:
        for ev in live_coordinator.data.ev_chargers:
            wb_device_id, wb_identifier = ev_wallbox_parent(ev, data)
            entities.extend(
                OneKomma5EVSensor(
                    live_coordinator,
                    system_id,
                    system_name,
                    ev,
                    desc,
                    data.system_device_id,
                    wallbox_device_id=wb_device_id,
                    wallbox_parent_identifier=wb_identifier,
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
