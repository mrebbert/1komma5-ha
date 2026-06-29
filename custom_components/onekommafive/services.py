"""Services for the 1KOMMA5° integration."""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .helpers import find_cheapest_window, find_most_expensive_window

SERVICE_GET_CHEAPEST_WINDOW = "get_cheapest_window"
SERVICE_GET_MOST_EXPENSIVE_WINDOW = "get_most_expensive_window"
SERVICE_REFRESH_NOW = "refresh_now"

# Keep in sync with services.yaml and the translations.
REFRESH_COORDINATORS: tuple[str, ...] = (
    "live",
    "price",
    "optimization",
    "weather",
    "system_status",
    "all",
)

REFRESH_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("coordinator", default="live"): vol.In(REFRESH_COORDINATORS),
        vol.Optional("config_entry_id"): cv.string,
    }
)

WINDOW_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=15, max=1800)),
        vol.Optional("earliest_start"): cv.datetime,
        vol.Optional("latest_end"): cv.datetime,
        vol.Optional("config_entry_id"): cv.string,
    }
)


def _ensure_aware(dt: datetime.datetime) -> datetime.datetime:
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.UTC)
    return dt


def _resolve_window_inputs(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[list[dict[str, Any]], int, datetime.datetime | None, datetime.datetime | None]:
    """Resolve service call inputs into forecast + constraints.

    Returns ``(forecast, slot_count, earliest_start, latest_end)`` or raises
    ``HomeAssistantError`` for any user-facing validation failure.
    """
    duration_minutes: int = call.data["duration_minutes"]
    slot_count_needed = duration_minutes // 15
    if slot_count_needed < 1:
        raise HomeAssistantError("duration_minutes must be at least 15")

    earliest_start = call.data.get("earliest_start")
    latest_end = call.data.get("latest_end")
    if earliest_start is not None:
        earliest_start = _ensure_aware(earliest_start)
    if latest_end is not None:
        latest_end = _ensure_aware(latest_end)

    config_entry_id = call.data.get("config_entry_id")
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("No 1KOMMA5° integration configured")

    if config_entry_id is not None:
        entry = next((e for e in entries if e.entry_id == config_entry_id), None)
        if entry is None:
            raise HomeAssistantError(f"Config entry '{config_entry_id}' not found")
    elif len(entries) == 1:
        entry = entries[0]
    else:
        raise HomeAssistantError("Multiple 1KOMMA5° entries configured — specify config_entry_id")

    coordinator = entry.runtime_data.price_coordinator
    if coordinator.data is None or not coordinator.data.forecast:
        raise HomeAssistantError("No price forecast available yet")

    forecast = coordinator.data.forecast
    if len(forecast) < slot_count_needed:
        raise HomeAssistantError(f"Forecast covers {len(forecast)} slots, need {slot_count_needed}")

    return forecast, slot_count_needed, earliest_start, latest_end


def _empty_window_response() -> dict[str, Any]:
    return {
        "found": False,
        "start": None,
        "end": None,
        "average_price": None,
        "slot_count": 0,
    }


def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    def _make_window_handler(
        finder: Callable[..., dict[str, Any] | None],
    ) -> Callable[[ServiceCall], Any]:
        async def _handler(call: ServiceCall) -> ServiceResponse:
            forecast, slot_count, earliest, latest = _resolve_window_inputs(hass, call)
            result = finder(forecast, slot_count, earliest, latest)
            if result is None:
                return _empty_window_response()
            return {"found": True, **result}

        return _handler

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CHEAPEST_WINDOW,
        _make_window_handler(find_cheapest_window),
        schema=WINDOW_SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_MOST_EXPENSIVE_WINDOW,
        _make_window_handler(find_most_expensive_window),
        schema=WINDOW_SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def _refresh_now(call: ServiceCall) -> ServiceResponse:
        """Force one or all data coordinators to refresh.

        Returns ``{"refreshed": [...], "failed": [...]}`` so automations can
        gate on success — picked OPTIONAL so callers without
        ``response_variable:`` get fire-and-forget semantics.
        """
        config_entry_id = call.data.get("config_entry_id")
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("No 1KOMMA5° integration configured")
        if config_entry_id is not None:
            entry = next((e for e in entries if e.entry_id == config_entry_id), None)
            if entry is None:
                raise HomeAssistantError(f"Config entry '{config_entry_id}' not found")
        elif len(entries) == 1:
            entry = entries[0]
        else:
            raise HomeAssistantError(
                "Multiple 1KOMMA5° entries configured — specify config_entry_id"
            )

        target = call.data["coordinator"]
        all_coords: dict[str, Any] = {
            "live": entry.runtime_data.live_coordinator,
            "price": entry.runtime_data.price_coordinator,
            "optimization": entry.runtime_data.optimization_coordinator,
            "weather": entry.runtime_data.weather_coordinator,
            "system_status": entry.runtime_data.system_status_coordinator,
        }
        selected = all_coords if target == "all" else {target: all_coords[target]}

        results = await asyncio.gather(
            *(c.async_refresh() for c in selected.values()),
            return_exceptions=True,
        )
        refreshed: list[str] = []
        failed: list[str] = []
        for name, coord, result in zip(selected, selected.values(), results, strict=True):
            if isinstance(result, BaseException) or not coord.last_update_success:
                failed.append(name)
            else:
                refreshed.append(name)
        return {"refreshed": refreshed, "failed": failed}

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_NOW,
        _refresh_now,
        schema=REFRESH_SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
