"""Tier-2 tests for the WeatherEntity + sunshine sensors.

The 1KOMMA5° library returns:
- ``today`` / ``tomorrow``: daily summaries (we expose sunshine_minutes via
  sensors)
- ``forecasts``: list of 3-hour ``WeatherSlot`` entries (the WeatherEntity
  surfaces these via ``async_forecast_hourly``)

Verify the wiring end-to-end with a mocked payload.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.components.weather import (
    SERVICE_GET_FORECASTS,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _weather_payload() -> MagicMock:
    """Build a deterministic WeatherData mock with two slots + daily summaries."""
    slot1 = MagicMock(
        period_start="2026-05-09T12:00:00Z",
        temperature_celsius=18.5,
        wind_speed=3.4,
        precipitation_mm=0.0,
        precipitation_probability=10.0,
        sunshine_minutes=180,
        weather_symbol_id=1,  # → sunny
    )
    slot2 = MagicMock(
        period_start="2026-05-09T15:00:00Z",
        temperature_celsius=19.2,
        wind_speed=4.1,
        precipitation_mm=0.5,
        precipitation_probability=40.0,
        sunshine_minutes=90,
        weather_symbol_id=3,  # → partlycloudy
    )
    return MagicMock(
        today=MagicMock(sunshine_minutes=420),
        tomorrow=MagicMock(sunshine_minutes=300),
        forecasts=[slot1, slot2],
    )


async def _setup(hass: HomeAssistant, system) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-1",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-1"},
    )
    entry.add_to_hass(hass)
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_weather_entity_reports_current_slot_condition(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """The WeatherEntity's state mirrors forecasts[0]'s mapped condition."""
    system = mock_system_factory(system_id="sys-1", weather=_weather_payload())
    await _setup(hass, system)

    weather_state = next(
        s for s in hass.states.async_all("weather") if s.entity_id.startswith("weather.")
    )
    assert weather_state.state == "sunny"  # symbol_id=1 → sunny
    assert weather_state.attributes["temperature"] == 18.5


async def test_weather_get_forecasts_service_returns_slots(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """`weather.get_forecasts` returns one Forecast dict per slot."""
    system = mock_system_factory(system_id="sys-1", weather=_weather_payload())
    await _setup(hass, system)

    weather_entity_id = next(
        s.entity_id for s in hass.states.async_all("weather") if s.entity_id.startswith("weather.")
    )

    response = await hass.services.async_call(
        "weather",
        SERVICE_GET_FORECASTS,
        {"entity_id": weather_entity_id, "type": "hourly"},
        blocking=True,
        return_response=True,
    )
    forecasts = response[weather_entity_id]["forecast"]
    assert len(forecasts) == 2
    assert forecasts[0]["condition"] == "sunny"
    assert forecasts[0]["temperature"] == 18.5
    assert forecasts[1]["condition"] == "partlycloudy"


async def test_sunshine_sensors_register_with_correct_values(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """The two sunshine sensors expose today's / tomorrow's minutes."""
    system = mock_system_factory(system_id="sys-1", weather=_weather_payload())
    await _setup(hass, system)

    today_state = next(
        s for s in hass.states.async_all("sensor") if s.entity_id.endswith("_sunshine_today")
    )
    tomorrow_state = next(
        s for s in hass.states.async_all("sensor") if s.entity_id.endswith("_sunshine_tomorrow")
    )
    assert int(float(today_state.state)) == 420
    assert int(float(tomorrow_state.state)) == 300
