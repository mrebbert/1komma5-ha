"""Weather platform for the 1KOMMA5° integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OneKomma5ConfigEntry
from .coordinator import OneKomma5WeatherCoordinator
from .entity import system_device_info
from .helpers import weather_symbol_to_ha_condition


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the 1KOMMA5° weather entity."""
    data = entry.runtime_data
    system_id = data.system.id()
    async_add_entities([OneKomma5Weather(data.weather_coordinator, system_id, data.system_name)])


class OneKomma5Weather(CoordinatorEntity[OneKomma5WeatherCoordinator], WeatherEntity):
    """1KOMMA5° system weather forecast."""

    _attr_has_entity_name = True
    _attr_name = None  # use device name
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY

    def __init__(
        self,
        coordinator: OneKomma5WeatherCoordinator,
        system_id: str,
        system_name: str,
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{system_id}_weather"
        self._attr_device_info = system_device_info(system_id, system_name)

    def _current_slot(self) -> Any | None:
        """Return the first forecast slot (the active 3-hour bucket)."""
        if self.coordinator.data is None:
            return None
        forecasts = self.coordinator.data.weather.forecasts
        return forecasts[0] if forecasts else None

    @property
    def condition(self) -> str | None:
        slot = self._current_slot()
        if slot is None:
            return None
        return weather_symbol_to_ha_condition(slot.weather_symbol_id)

    @property
    def native_temperature(self) -> float | None:
        slot = self._current_slot()
        return slot.temperature_celsius if slot else None

    @property
    def native_wind_speed(self) -> float | None:
        slot = self._current_slot()
        return slot.wind_speed if slot else None

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the per-slot forecast (3-hour buckets, ~48h horizon)."""
        if self.coordinator.data is None:
            return None
        return [
            Forecast(
                datetime=slot.period_start,
                condition=weather_symbol_to_ha_condition(slot.weather_symbol_id),
                native_temperature=slot.temperature_celsius,
                native_precipitation=slot.precipitation_mm,
                precipitation_probability=slot.precipitation_probability,
                native_wind_speed=slot.wind_speed,
            )
            for slot in self.coordinator.data.weather.forecasts
        ]
