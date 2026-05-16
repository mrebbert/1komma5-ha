"""Diagnostics support for the 1KOMMA5° integration.

Home Assistant calls ``async_get_config_entry_diagnostics`` when the user
downloads diagnostics for this integration. The output is a JSON-serialisable
dict that bug reporters can attach to issues.

We never emit credentials, the system_id (which doubles as a tenant
identifier in the 1KOMMA5° backend), or the human-readable system name
(may contain the site address). Coordinator state is summarised — full
data payloads can be large and are not needed for triage.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import OneKomma5ConfigEntry
from .const import CONF_PASSWORD, CONF_SYSTEM_ID, CONF_USERNAME

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, CONF_SYSTEM_ID, "system_id", "unique_id"}


def _coordinator_snapshot(coord: Any) -> dict[str, Any]:
    """Summarise a coordinator's runtime state for diagnostics."""
    update_interval = coord.update_interval
    return {
        "name": coord.name,
        "update_interval_seconds": (update_interval.total_seconds() if update_interval else None),
        "last_update_success": coord.last_update_success,
        "last_exception": repr(coord.last_exception) if coord.last_exception else None,
        "data_type": type(coord.data).__name__ if coord.data is not None else None,
        "data_present": coord.data is not None,
    }


def _live_summary(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    return {
        "has_live_overview": data.live_overview is not None,
        "ev_charger_count": len(data.ev_chargers) if data.ev_chargers else 0,
        "ems_settings_present": data.ems_settings is not None,
    }


def _price_summary(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    return {
        "current_price": data.current_price,
        "forecast_slot_count": len(data.forecast) if data.forecast else 0,
        "all_in_price_keys": len(data.all_in_prices) if data.all_in_prices else 0,
        "negative_slots_today": data.negative_price_slots_today,
        "negative_slots_tomorrow": data.negative_price_slots_tomorrow,
        "has_tomorrow_data": data.tomorrow_average_price is not None,
    }


def _optimization_summary(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    return {
        "event_count": data.event_count,
        "last_decision": (data.last_event.decision if data.last_event is not None else None),
    }


def _weather_summary(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    weather = data.weather
    return {
        "has_today": getattr(weather, "today", None) is not None,
        "has_tomorrow": getattr(weather, "tomorrow", None) is not None,
        "forecast_slot_count": (
            len(weather.forecasts) if getattr(weather, "forecasts", None) else 0
        ),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OneKomma5ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data

    diag: dict[str, Any] = {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "version": entry.version,
            "unique_id_set": entry.unique_id is not None,
        },
        "coordinators": {
            "live": {
                **_coordinator_snapshot(data.live_coordinator),
                "summary": _live_summary(data.live_coordinator.data),
            },
            "price": {
                **_coordinator_snapshot(data.price_coordinator),
                "summary": _price_summary(data.price_coordinator.data),
            },
            "optimization": {
                **_coordinator_snapshot(data.optimization_coordinator),
                "summary": _optimization_summary(data.optimization_coordinator.data),
            },
            "weather": {
                **_coordinator_snapshot(data.weather_coordinator),
                "summary": _weather_summary(data.weather_coordinator.data),
            },
        },
    }

    try:
        from importlib.metadata import version

        diag["sdk_version"] = version("onekommafive")
    except Exception:
        diag["sdk_version"] = None

    return diag
