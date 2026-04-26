"""Binary sensor platform for the 1KOMMA5° integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from . import OneKomma5ConfigEntry
from .coordinator import get_current_price
from .entity import OneKomma5PriceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities from a config entry."""
    data = entry.runtime_data
    system_id = data.system.id()
    async_add_entities([
        OneKomma5CheapElectricitySensor(
            data.price_coordinator, system_id, data.system_name,
        ),
        OneKomma5CheapestHourNowSensor(
            data.price_coordinator, system_id, data.system_name,
        ),
    ])


def _dynamic_current_price(coordinator: Any) -> float | None:
    """Return the current price using the dynamic lookup if available."""
    if coordinator.data is None:
        return None
    if coordinator.data.all_in_prices:
        return get_current_price(coordinator.data.all_in_prices)
    return coordinator.data.current_price


class OneKomma5CheapElectricitySensor(OneKomma5PriceEntity, BinarySensorEntity):
    """Binary sensor that is ON when the current electricity price is below the daily average."""

    _attr_translation_key = "cheap_electricity"

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, "cheap_electricity")

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update so the sensor reflects the active slot."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._quarter_hour_update,
                minute=[0, 15, 30, 45], second=[0],
            )
        )

    @callback
    def _quarter_hour_update(self, _now: datetime) -> None:
        """Re-evaluate at quarter-hour boundaries."""
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True when current price is below the daily average."""
        if self.coordinator.data is None:
            return None
        current = _dynamic_current_price(self.coordinator)
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
        current = _dynamic_current_price(self.coordinator)
        average = self.coordinator.data.market_prices.average_price_all_in
        attrs: dict[str, Any] = {"current_price": current, "average_price": average}
        if current is not None and average is not None:
            attrs["difference"] = round(current - average, 6)
        return attrs


class OneKomma5CheapestHourNowSensor(OneKomma5PriceEntity, BinarySensorEntity):
    """Binary sensor that is ON when the current 15-min slot is the cheapest in the next 24h."""

    _attr_translation_key = "cheapest_hour_now"

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, "cheapest_hour_now")

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update so the sensor reflects the active slot."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._quarter_hour_update,
                minute=[0, 15, 30, 45], second=[0],
            )
        )

    @callback
    def _quarter_hour_update(self, _now: datetime) -> None:
        """Re-evaluate at quarter-hour boundaries."""
        self.async_write_ha_state()

    def _min_forecast_price(self) -> float | None:
        """Return the minimum price in the upcoming 24h forecast."""
        if self.coordinator.data is None or not self.coordinator.data.forecast:
            return None
        prices = [s["price"] for s in self.coordinator.data.forecast]
        return min(prices) if prices else None

    @property
    def is_on(self) -> bool | None:
        """Return True if the current slot price equals the cheapest in the forecast."""
        current = _dynamic_current_price(self.coordinator)
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
        current = _dynamic_current_price(self.coordinator)
        forecast = self.coordinator.data.forecast
        if not forecast:
            return {"current_price": current}
        cheapest = min(forecast, key=lambda s: s["price"])
        return {
            "current_price": current,
            "cheapest_price": cheapest["price"],
            "cheapest_slot_start": cheapest["start"],
        }
