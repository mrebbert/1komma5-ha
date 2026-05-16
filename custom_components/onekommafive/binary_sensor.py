"""Binary sensor platform for the 1KOMMA5° integration."""

from __future__ import annotations

import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .entity import (
    OneKomma5OptimizationEntity,
    OneKomma5PriceEntity,
    QuarterHourUpdateMixin,
)
from .helpers import active_optimization_event


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities from a config entry."""
    data = entry.runtime_data
    system_id = data.system.id()
    async_add_entities(
        [
            OneKomma5CheapElectricitySensor(
                data.price_coordinator,
                system_id,
                data.system_name,
            ),
            OneKomma5CheapestHourNowSensor(
                data.price_coordinator,
                system_id,
                data.system_name,
            ),
            OneKomma5OptimizationBatteryGridChargeSensor(
                data.optimization_coordinator,
                system_id,
                data.system_name,
            ),
            OneKomma5OptimizationHeatPumpRecommendedSensor(
                data.optimization_coordinator,
                system_id,
                data.system_name,
            ),
        ]
    )


class OneKomma5CheapElectricitySensor(
    QuarterHourUpdateMixin, OneKomma5PriceEntity, BinarySensorEntity
):
    """Binary sensor that is ON when the current electricity price is below the daily average."""

    _attr_translation_key = "cheap_electricity"

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, "cheap_electricity")

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update so the sensor reflects the active slot."""
        await super().async_added_to_hass()
        self._async_register_quarter_hour_update()

    @property
    def is_on(self) -> bool | None:
        """Return True when current price is below the daily average."""
        if self.coordinator.data is None:
            return None
        current = self._dynamic_current_price()
        average = self.coordinator.data.market_prices.average_price_all_in
        if current is None or average is None or average <= 0:
            return None
        return current < average

    @property
    def icon(self) -> str:
        """Return icon reflecting cheap/expensive state."""
        return "mdi:lightning-bolt" if self.is_on else "mdi:lightning-bolt-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose current price, average and their difference."""
        if self.coordinator.data is None:
            return None
        current = self._dynamic_current_price()
        average = self.coordinator.data.market_prices.average_price_all_in
        attrs: dict[str, Any] = {"current_price": current, "average_price": average}
        if current is not None and average is not None:
            attrs["difference"] = round(current - average, 6)
        return attrs


class OneKomma5CheapestHourNowSensor(
    QuarterHourUpdateMixin, OneKomma5PriceEntity, BinarySensorEntity
):
    """Binary sensor that is ON when the current 15-min slot is the cheapest in the next 24h."""

    _attr_translation_key = "cheapest_hour_now"

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, "cheapest_hour_now")

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update so the sensor reflects the active slot."""
        await super().async_added_to_hass()
        self._async_register_quarter_hour_update()

    def _min_forecast_price(self) -> float | None:
        """Return the minimum price in the upcoming 24h forecast."""
        if self.coordinator.data is None or not self.coordinator.data.forecast:
            return None
        prices = [s["price"] for s in self.coordinator.data.forecast]
        return min(prices) if prices else None

    @property
    def is_on(self) -> bool | None:
        """Return True if the current slot price equals the cheapest in the forecast."""
        current = self._dynamic_current_price()
        cheapest = self._min_forecast_price()
        if current is None or cheapest is None:
            return None
        # Use a small tolerance to handle float comparison
        return abs(current - cheapest) < 1e-9

    @property
    def icon(self) -> str:
        """Return icon reflecting state."""
        return "mdi:cash-clock" if self.is_on else "mdi:cash-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose current price, cheapest price and the cheapest slot start."""
        if self.coordinator.data is None:
            return None
        current = self._dynamic_current_price()
        forecast = self.coordinator.data.forecast
        if not forecast:
            return {"current_price": current}
        cheapest = min(forecast, key=lambda s: s["price"])
        return {
            "current_price": current,
            "cheapest_price": cheapest["price"],
            "cheapest_slot_start": cheapest["start"],
        }


class OneKomma5OptimizationBatteryGridChargeSensor(
    QuarterHourUpdateMixin, OneKomma5OptimizationEntity, BinarySensorEntity
):
    """Binary sensor that is ON when the AI's currently active BATTERY decision
    is ``BATTERY_CHARGE_FROM_GRID`` — i.e. the HEMS has decided to pull from the
    grid right now to bridge upcoming high-price periods.
    """

    _attr_translation_key = "optimization_battery_grid_charge"

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, "optimization_battery_grid_charge")

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update so the sensor flips off at slot ends."""
        await super().async_added_to_hass()
        self._async_register_quarter_hour_update()

    def _active_battery_event(self) -> Any | None:
        if self.coordinator.data is None:
            return None
        return active_optimization_event(
            self.coordinator.data.events,
            asset="BATTERY",
            now=datetime.datetime.now(tz=datetime.UTC),
        )

    @property
    def is_on(self) -> bool | None:
        """Return True only when an active BATTERY_CHARGE_FROM_GRID slot exists."""
        if self.coordinator.data is None:
            return None
        event = self._active_battery_event()
        if event is None:
            return False
        return event.decision == "BATTERY_CHARGE_FROM_GRID"

    @property
    def icon(self) -> str:
        """Return icon reflecting state."""
        return "mdi:battery-arrow-up" if self.is_on else "mdi:battery-arrow-up-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the active BATTERY decision details, if any."""
        event = self._active_battery_event()
        if event is None:
            return None
        return {
            "decision": event.decision,
            "from": event.from_time,
            "to": event.to_time,
            "market_price": event.market_price,
            "state_of_charge": event.state_of_charge,
        }


class OneKomma5OptimizationHeatPumpRecommendedSensor(
    QuarterHourUpdateMixin, OneKomma5OptimizationEntity, BinarySensorEntity
):
    """Binary sensor that is ON when the AI's currently active HEATPUMP decision
    is ``HEATPUMP_RECOMMEND_ON`` — i.e. the HEMS suggests running the heat pump
    in the current slot to exploit favourable electricity prices.
    """

    _attr_translation_key = "optimization_heat_pump_recommended"

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, "optimization_heat_pump_recommended")

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update so the sensor flips at slot ends."""
        await super().async_added_to_hass()
        self._async_register_quarter_hour_update()

    def _active_heat_pump_event(self) -> Any | None:
        if self.coordinator.data is None:
            return None
        return active_optimization_event(
            self.coordinator.data.events,
            asset="HEATPUMP",
            now=datetime.datetime.now(tz=datetime.UTC),
        )

    @property
    def is_on(self) -> bool | None:
        """Return True only when an active HEATPUMP_RECOMMEND_ON slot exists."""
        if self.coordinator.data is None:
            return None
        event = self._active_heat_pump_event()
        if event is None:
            return False
        return event.decision == "HEATPUMP_RECOMMEND_ON"

    @property
    def icon(self) -> str:
        """Return icon reflecting state."""
        return "mdi:heat-pump" if self.is_on else "mdi:heat-pump-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the active HEATPUMP decision details, if any."""
        event = self._active_heat_pump_event()
        if event is None:
            return None
        return {
            "decision": event.decision,
            "from": event.from_time,
            "to": event.to_time,
            "market_price": event.market_price,
        }
