"""Services for the 1KOMMA5° integration."""
from __future__ import annotations

import datetime
import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_GET_CHEAPEST_WINDOW = "get_cheapest_window"

SERVICE_GET_CHEAPEST_WINDOW_SCHEMA = vol.Schema(
    {
        vol.Required("duration_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=15, max=1800)
        ),
        vol.Optional("earliest_start"): cv.datetime,
        vol.Optional("latest_end"): cv.datetime,
        vol.Optional("config_entry_id"): cv.string,
    }
)


def _parse_iso(value: str) -> datetime.datetime:
    """Parse an ISO-8601 timestamp, ensuring it is timezone-aware."""
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _ensure_aware(dt: datetime.datetime) -> datetime.datetime:
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def _handle_get_cheapest_window(call: ServiceCall) -> ServiceResponse:
        """Find the cheapest contiguous window in the price forecast."""
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
            entry = next(
                (e for e in entries if e.entry_id == config_entry_id), None
            )
            if entry is None:
                raise HomeAssistantError(
                    f"Config entry '{config_entry_id}' not found"
                )
        elif len(entries) == 1:
            entry = entries[0]
        else:
            raise HomeAssistantError(
                "Multiple 1KOMMA5° entries configured — specify config_entry_id"
            )

        coordinator = entry.runtime_data.price_coordinator
        if coordinator.data is None or not coordinator.data.forecast:
            raise HomeAssistantError("No price forecast available yet")

        forecast = coordinator.data.forecast
        if len(forecast) < slot_count_needed:
            raise HomeAssistantError(
                f"Forecast covers {len(forecast)} slots, need {slot_count_needed}"
            )

        best_avg: float | None = None
        best_start: datetime.datetime | None = None
        best_end: datetime.datetime | None = None

        for i in range(len(forecast) - slot_count_needed + 1):
            window = forecast[i : i + slot_count_needed]
            window_start = _parse_iso(window[0]["start"])
            window_end = _parse_iso(window[-1]["end"])

            if earliest_start is not None and window_start < earliest_start:
                continue
            if latest_end is not None and window_end > latest_end:
                continue

            avg = sum(s["price"] for s in window) / len(window)
            if best_avg is None or avg < best_avg:
                best_avg = avg
                best_start = window_start
                best_end = window_end

        if best_avg is None:
            return {
                "found": False,
                "start": None,
                "end": None,
                "average_price": None,
                "slot_count": 0,
            }

        return {
            "found": True,
            "start": best_start.isoformat(),
            "end": best_end.isoformat(),
            "average_price": round(best_avg, 6),
            "slot_count": slot_count_needed,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CHEAPEST_WINDOW,
        _handle_get_cheapest_window,
        schema=SERVICE_GET_CHEAPEST_WINDOW_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
