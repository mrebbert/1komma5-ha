"""Sensor entity classes for the 1KOMMA5° integration.

The actual SENSORS configuration tuples and the platform's
``async_setup_entry`` live in ``sensor.py``.
"""

from __future__ import annotations

import datetime as _dt
import logging
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
    OneKomma5SystemStatusEntity,
    OneKomma5WeatherEntity,
    QuarterHourUpdateMixin,
    system_device_info,
)
from .helpers import find_cheapest_window, trapezoidal_delta_kwh
from .sensor_descriptions import (
    OneKomma5EVSensorDescription,
    OneKomma5OptimizationSensorDescription,
    OneKomma5PriceSensorDescription,
    OneKomma5SensorDescription,
    OneKomma5WeatherSensorDescription,
)

_LOGGER = logging.getLogger(__name__)

# Default currency-per-kWh string for installs whose country / currency
# is unknown. Live overrides come from `OneKomma5Data.currency`, resolved
# from `SystemDetails.address_country` at setup time.
CURRENCY_EUR_PER_KWH = "EUR/kWh"


def currency_per_kwh(currency: str) -> str:
    """Build the native_unit_of_measurement string for per-kWh prices."""
    return f"{currency}/kWh"


class OneKomma5LiveSensor(OneKomma5Entity, SensorEntity):
    """Sensor for live energy data."""

    entity_description: OneKomma5SensorDescription

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        description: OneKomma5SensorDescription,
        *,
        asset: Any | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            system_id,
            system_name,
            description.key,
            device_key=description.device_key,
            asset=asset,
        )
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
        *,
        currency: str = "EUR",
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, description.key)
        self.entity_description = description
        # Override the description's static EUR/kWh with the resolved currency.
        # Only set when the description carried a unit — keeps counters
        # (negative_price_slots_today/tomorrow) without an erroneous unit.
        if description.native_unit_of_measurement is not None:
            self._attr_native_unit_of_measurement = currency_per_kwh(currency)

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


class OneKomma5CheapestChargingWindowSensor(OneKomma5PriceEntity, RestoreSensor):
    """Cheapest N-min charging window that still ends today (local time).

    Duration is set via the options flow (default 60 min, must be a multiple
    of 15). Locked-in: once a window is chosen, it stays as state until its
    end has passed (or the day rolls over). Restored across HA restarts.
    After the locked window ends, the sensor re-locks the next-cheapest
    window of the remaining day; once less than the configured duration
    remains today, state is ``unknown`` until midnight.
    """

    _attr_translation_key = "cheapest_charging_window_today"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        duration_minutes: int,
    ) -> None:
        """Initialize the cheapest-window sensor with the configured duration."""
        super().__init__(coordinator, system_id, system_name, "cheapest_charging_window_today")
        self._duration_minutes = duration_minutes
        self._slot_count = duration_minutes // 15
        self._window: dict[str, Any] | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the previous window (if still valid), then evaluate."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in (
            None,
            "",
            "unknown",
            "unavailable",
        ):
            self._window = self._restore_window_from_state(last_state)
        self._refresh_window()

    def _restore_window_from_state(self, last_state: Any) -> dict[str, Any] | None:
        """Reconstruct a window dict from a restored State, validated for today.

        If the persisted ``slot_count`` differs from the currently-configured
        slot count, the user has changed the charging-window duration since
        this state was saved — discard the lock-in so the next refresh picks
        a fresh window with the new duration.
        """
        try:
            end_iso = last_state.attributes.get("end")
            avg_price = last_state.attributes.get("average_price")
            slot_count = int(last_state.attributes.get("slot_count", self._slot_count))
            if not end_iso or avg_price is None:
                return None
            if slot_count != self._slot_count:
                return None
            return self._validate_window(
                {
                    "start": last_state.state,
                    "end": end_iso,
                    "average_price": float(avg_price),
                    "slot_count": slot_count,
                }
            )
        except (ValueError, TypeError, AttributeError):
            return None

    def _validate_window(self, window: dict[str, Any]) -> dict[str, Any] | None:
        """Return the window unchanged if its lock-in is still valid; else None."""
        try:
            now_local = dt_util.now()
            start_dt = datetime.fromisoformat(window["start"])
            end_dt = datetime.fromisoformat(window["end"])
        except (ValueError, KeyError):
            return None
        # End passed → re-lock for the rest of today.
        if end_dt <= dt_util.as_utc(now_local):
            return None
        # Day rolled over → previous day's window no longer applies.
        if start_dt.astimezone(now_local.tzinfo).date() != now_local.date():
            return None
        return window

    @callback
    def _handle_coordinator_update(self) -> None:
        """On fresh coordinator data, re-evaluate the locked window."""
        self._refresh_window()
        super()._handle_coordinator_update()

    def _refresh_window(self) -> None:
        """Discard expired/wrong-day windows and lock in a fresh one if missing."""
        if self._window is not None:
            self._window = self._validate_window(self._window)
        if self._window is not None:
            return
        if self.coordinator.data is None or not self.coordinator.data.forecast:
            return
        now_local = dt_util.now()
        end_of_today_local = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        self._window = find_cheapest_window(
            self.coordinator.data.forecast,
            self._slot_count,
            earliest_start=dt_util.as_utc(now_local),
            latest_end=dt_util.as_utc(end_of_today_local),
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the start of the locked-in cheapest window."""
        if self._window is None:
            return None
        return datetime.fromisoformat(self._window["start"])

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose start/end/avg-price/duration on the sensor."""
        if self._window is None:
            return None
        return {
            "start": self._window["start"],
            "end": self._window["end"],
            "average_price": self._window["average_price"],
            "duration_minutes": self._duration_minutes,
            "slot_count": self._window["slot_count"],
        }


class OneKomma5CheapestChargingWindowTomorrowSensor(OneKomma5PriceEntity, SensorEntity):
    """Cheapest N-min charging window in tomorrow's forecast (HA-local time, no lock-in)."""

    _attr_translation_key = "cheapest_charging_window_tomorrow"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        duration_minutes: int,
    ) -> None:
        super().__init__(coordinator, system_id, system_name, "cheapest_charging_window_tomorrow")
        self._duration_minutes = duration_minutes
        self._slot_count = duration_minutes // 15
        self._window: dict[str, Any] | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_window()
        super()._handle_coordinator_update()

    def _refresh_window(self) -> None:
        self._window = None
        if self.coordinator.data is None or not self.coordinator.data.forecast:
            return
        now_local = dt_util.now()
        tomorrow_local = now_local.date() + _dt.timedelta(days=1)
        start_of_tomorrow = now_local.replace(
            year=tomorrow_local.year,
            month=tomorrow_local.month,
            day=tomorrow_local.day,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        end_of_tomorrow = start_of_tomorrow.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        self._window = find_cheapest_window(
            self.coordinator.data.forecast,
            self._slot_count,
            earliest_start=dt_util.as_utc(start_of_tomorrow),
            latest_end=dt_util.as_utc(end_of_tomorrow),
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._refresh_window()

    @property
    def native_value(self) -> datetime | None:
        if self._window is None:
            return None
        return datetime.fromisoformat(self._window["start"])

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._window is None:
            return None
        return {
            "start": self._window["start"],
            "end": self._window["end"],
            "average_price": self._window["average_price"],
            "duration_minutes": self._duration_minutes,
            "slot_count": self._window["slot_count"],
        }


class OneKomma5EVSensor(OneKomma5EVEntity, SensorEntity):
    """Sensor for EV vehicle data."""

    entity_description: OneKomma5EVSensorDescription

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        ev_id: str,
        ev_manufacturer: str | None,
        ev_model: str | None,
        description: OneKomma5EVSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            system_id,
            system_name,
            ev_id,
            ev_manufacturer,
            ev_model,
            description.key,
        )
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
        *,
        device_key: str | None = None,
        asset: Any | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            system_id,
            system_name,
            unique_id_suffix,
            device_key=device_key,
            asset=asset,
        )
        self._accumulated: float = 0.0
        self._last_power: float | None = None
        self._last_time: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore accumulated value after HA restart."""
        await super().async_added_to_hass()
        if (
            restored := await self.async_get_last_sensor_data()
        ) and restored.native_value is not None:
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
            delta_kwh = trapezoidal_delta_kwh(self._last_power, self._last_time, power_w, now)
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
        *,
        asset: Any | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            system_id,
            system_name,
            f"{description.key}_energy",
            device_key=description.device_key,
            asset=asset,
        )
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
    _attr_suggested_display_precision = 4

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        *,
        currency: str = "EUR",
    ) -> None:
        """Initialize the stable price sensor."""
        super().__init__(coordinator, system_id, system_name, "stable_electricity_price")
        self._attr_native_unit_of_measurement = currency_per_kwh(currency)
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
        if (
            self._stable_price is None
            and (restored := await self.async_get_last_sensor_data())
            and restored.native_value is not None
        ):
            try:
                self._stable_price = float(restored.native_value)
                self.async_write_ha_state()
            except (TypeError, ValueError) as err:
                _LOGGER.debug(
                    "Could not parse restored stable price %r: %s",
                    restored.native_value,
                    err,
                )
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
        *,
        currency: str = "EUR",
    ) -> None:
        super().__init__(coordinator, system_id, system_name, "electricity_cost")
        self._attr_native_unit_of_measurement = currency
        self._stable_price_sensor = stable_price_sensor

    def _get_power_w(self, data: LiveData) -> float | None:
        return data.live_overview.grid_consumption_power

    def _get_kwh_multiplier(self) -> float | None:
        return self._stable_price_sensor.stable_price


class OneKomma5ConsumerCostSensor(OneKomma5AccumulatingSensor):
    """Per-consumer share of the grid-import cost.

    Allocates ``grid_consumption_power × stable_price × dt`` proportionally to
    the consumer's share of ``consumption_power``. The four instances
    therefore sum to ``electricity_cost``.
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:currency-eur"
    _accumulator_precision = 4

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        stable_price_sensor: OneKomma5StablePriceSensor,
        consumer_power_attr: str,
        translation_key: str,
        *,
        device_key: str | None = None,
        asset: Any | None = None,
        currency: str = "EUR",
    ) -> None:
        super().__init__(
            coordinator,
            system_id,
            system_name,
            translation_key,
            device_key=device_key,
            asset=asset,
        )
        self._attr_native_unit_of_measurement = currency
        self._attr_translation_key = translation_key
        self._stable_price_sensor = stable_price_sensor
        self._consumer_power_attr = consumer_power_attr

    def _get_power_w(self, data: LiveData) -> float | None:
        lo = data.live_overview
        total = lo.consumption_power
        if total is None or total <= 0:
            return None
        consumer_power = getattr(lo, self._consumer_power_attr, None)
        grid = lo.grid_consumption_power
        if consumer_power is None or grid is None:
            return None
        return grid * (consumer_power / total)

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
    _attr_suggested_display_precision = 2
    _attr_translation_key = "feed_in_revenue"
    _attr_icon = "mdi:transmission-tower-export"
    _accumulator_precision = 4
    _device_key = "meter"

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        feed_in_tariff: float,
        *,
        asset: Any | None = None,
        currency: str = "EUR",
    ) -> None:
        super().__init__(
            coordinator,
            system_id,
            system_name,
            "feed_in_revenue",
            asset=asset,
        )
        self._attr_native_unit_of_measurement = currency
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
        *,
        currency: str = "EUR",
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, description.key)
        self.entity_description = description
        if description.device_class == SensorDeviceClass.MONETARY:
            self._attr_native_unit_of_measurement = currency

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


class OneKomma5WeatherSensor(OneKomma5WeatherEntity, SensorEntity):
    """Sensor for weather coordinator data."""

    entity_description: OneKomma5WeatherSensorDescription

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        description: OneKomma5WeatherSensorDescription,
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
    ) -> None:
        """Initialize the diagnostic sensor. ``key`` doubles as the translation key."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{system_id}_{key}"
        self._attr_translation_key = key
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


class OneKomma5SystemAgeDaysSensor(OneKomma5SystemStatusEntity, SensorEntity):
    """Days since the earliest measurement on this 1KOMMA5° system.

    Derived from `SystemDetails.earliest_measurement` (ISO date `YYYY-MM-DD`).
    The value is rebuilt on every coordinator update (15 min) so it advances
    by 1 within minutes of midnight without a special timer.
    """

    _attr_translation_key = "system_age_days"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "d"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        details: Any | None,
    ) -> None:
        super().__init__(coordinator, system_id, system_name, "system_age_days")
        self._details = details

    @property
    def native_value(self) -> int | None:
        if self._details is None:
            return None
        earliest = getattr(self._details, "earliest_measurement", None)
        if not earliest:
            return None
        try:
            start = datetime.fromisoformat(earliest).date()
        except ValueError:
            _LOGGER.debug("Invalid earliest_measurement: %r", earliest)
            return None
        delta = (dt_util.now().date() - start).days
        return max(delta, 0)


class OneKomma5ActiveFeaturesSensor(OneKomma5SystemStatusEntity, SensorEntity):
    """Diagnostic sensor exposing the customer's enabled feature flags.

    State is the number of active features; the full list lives in the
    ``features`` attribute. Hidden from the main device card by default
    via ``entity_category=DIAGNOSTIC``.
    """

    _attr_translation_key = "active_features"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:feature-search-outline"

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        super().__init__(coordinator, system_id, system_name, "active_features")

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data.active_features)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        return {"features": list(self.coordinator.data.active_features)}
