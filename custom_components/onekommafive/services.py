"""Services for the 1KOMMA5° integration."""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, cast

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .helpers import find_cheapest_window, find_most_expensive_window

SERVICE_GET_CHEAPEST_WINDOW = "get_cheapest_window"
SERVICE_GET_MOST_EXPENSIVE_WINDOW = "get_most_expensive_window"
SERVICE_REFRESH_NOW = "refresh_now"
SERVICE_GET_HEARTBEAT_METRICS = "get_heartbeat_metrics"
SERVICE_ASSIGN_EV_TO_WALLBOX = "assign_ev_to_wallbox"

# Keep in sync with services.yaml and the translations.
REFRESH_COORDINATORS: tuple[str, ...] = (
    "live",
    "price",
    "optimization",
    "weather",
    "system_status",
    "energy",
    "notifications",
    "all",
)

# Keep in sync with services.yaml and the translations. Windows correspond to
# the fields on `onekommafive.models.HeartbeatPrices`.
HEARTBEAT_METRICS_WINDOWS: tuple[str, ...] = (
    "day",
    "week",
    "month",
    "half_year",
    "year",
)

REFRESH_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("coordinator", default="live"): vol.In(REFRESH_COORDINATORS),
        vol.Optional("config_entry_id"): cv.string,
    }
)

HEARTBEAT_METRICS_SCHEMA = vol.Schema(
    {
        vol.Required("window"): vol.In(HEARTBEAT_METRICS_WINDOWS),
        vol.Optional("config_entry_id"): cv.string,
    }
)

ASSIGN_EV_SCHEMA = vol.Schema(
    {
        vol.Required("wallbox_id"): cv.string,
        vol.Required("ev_id"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
    }
)

WINDOW_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("duration_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=15, max=1800)
        ),
        vol.Optional("earliest_start"): cv.datetime,
        vol.Optional("latest_end"): cv.datetime,
        vol.Optional("config_entry_id"): cv.string,
    }
)


def _resolve_config_entry(hass: HomeAssistant, call: ServiceCall) -> Any:
    """Pick the target config entry for a service call.

    Multi-system installs must specify ``config_entry_id`` explicitly; single-
    system installs auto-pick their only entry. Raises ``HomeAssistantError``
    with user-facing messages for the four failure paths (no entry, unknown
    entry, ambiguous). Shared by ``refresh_now`` and ``get_heartbeat_metrics``.
    """
    config_entry_id = call.data.get("config_entry_id")
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="no_integration_configured",
        )
    if config_entry_id is not None:
        entry = next((e for e in entries if e.entry_id == config_entry_id), None)
        if entry is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="config_entry_not_found",
                translation_placeholders={"config_entry_id": config_entry_id},
            )
        return entry
    if len(entries) == 1:
        return entries[0]
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="multiple_entries_ambiguous",
    )


def _ensure_aware(dt: datetime.datetime) -> datetime.datetime:
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.UTC)
    return dt


def _resolve_window_inputs(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[
    list[dict[str, Any]], int, datetime.datetime | None, datetime.datetime | None
]:
    """Resolve service call inputs into forecast + constraints.

    Returns ``(forecast, slot_count, earliest_start, latest_end)`` or raises
    ``HomeAssistantError`` for any user-facing validation failure.
    """
    duration_minutes: int = call.data["duration_minutes"]
    slot_count_needed = duration_minutes // 15
    if slot_count_needed < 1:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="duration_too_short",
        )

    earliest_start = call.data.get("earliest_start")
    latest_end = call.data.get("latest_end")
    if earliest_start is not None:
        earliest_start = _ensure_aware(earliest_start)
    if latest_end is not None:
        latest_end = _ensure_aware(latest_end)

    entry = _resolve_config_entry(hass, call)
    coordinator = entry.runtime_data.price_coordinator
    if coordinator.data is None or not coordinator.data.forecast:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="no_price_forecast",
        )

    forecast = coordinator.data.forecast
    if len(forecast) < slot_count_needed:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="forecast_too_short",
            translation_placeholders={
                "available": str(len(forecast)),
                "needed": str(slot_count_needed),
            },
        )

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
        entry = _resolve_config_entry(hass, call)
        target = call.data["coordinator"]
        all_coords = entry.runtime_data.named_coordinators()
        selected = all_coords if target == "all" else {target: all_coords[target]}

        results = await asyncio.gather(
            *(c.async_refresh() for c in selected.values()),
            return_exceptions=True,
        )
        refreshed: list[str] = []
        failed: list[str] = []
        for name, coord, result in zip(
            selected, selected.values(), results, strict=True
        ):
            if isinstance(result, BaseException) or not coord.last_update_success:
                failed.append(name)
            else:
                refreshed.append(name)
        # str lists are valid JSON; cast past mypy's invariant JsonValueType.
        return cast(ServiceResponse, {"refreshed": refreshed, "failed": failed})

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_NOW,
        _refresh_now,
        schema=REFRESH_SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def _get_heartbeat_metrics(call: ServiceCall) -> ServiceResponse:
        """Return the requested HeartbeatPrices window as a flat dict.

        Absent windows respond ``{"available": false, "window": <name>}`` so
        callers can branch on it instead of tripping over missing fields.
        """
        entry = _resolve_config_entry(hass, call)
        window = call.data["window"]
        prices = await entry.runtime_data.system.get_heartbeat_prices()
        win = getattr(prices, window, None)
        if win is None:
            return cast(ServiceResponse, {"window": window, "available": False})
        fields = {k: v for k, v in asdict(win).items() if k != "raw"}
        return cast(ServiceResponse, {"window": window, "available": True, **fields})

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_HEARTBEAT_METRICS,
        _get_heartbeat_metrics,
        schema=HEARTBEAT_METRICS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def _assign_ev_to_wallbox(call: ServiceCall) -> ServiceResponse:
        """Bind a vehicle profile to a wallbox.

        Wraps ``EVCharger.assign_charger(wallbox_id)`` (SDK ≥ 0.5.0). The
        1KOMMA5° backend is 1:1 exclusive — the previously bound EV, if any,
        is released automatically. ``previous_ev_id`` is captured from the
        live-coordinator cache before the write so automations can log the
        swap; it is ``None`` when the wallbox had no assignment or when the
        cache is not yet populated.
        """
        entry = _resolve_config_entry(hass, call)
        wallbox_id: str = call.data["wallbox_id"]
        ev_id: str = call.data["ev_id"]
        data = entry.runtime_data

        live = data.live_coordinator.data
        if live is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="live_data_not_ready",
            )
        target_ev = next((ev for ev in live.ev_chargers if ev.id() == ev_id), None)
        if target_ev is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="vehicle_not_found",
                translation_placeholders={"ev_id": ev_id},
            )

        known_wallbox_ids: set[str] = set()
        previous_ev_id: str | None = None
        for wb in getattr(live, "wallboxes", []) or []:
            wb_id = getattr(wb, "id", None)
            if wb_id:
                known_wallbox_ids.add(wb_id)
            if wb_id == wallbox_id:
                previous_ev_id = getattr(wb, "assigned_ev_id", None)
        if known_wallbox_ids and wallbox_id not in known_wallbox_ids:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="wallbox_not_found",
                translation_placeholders={"wallbox_id": wallbox_id},
            )

        await target_ev.assign_charger(wallbox_id)
        await data.live_coordinator.async_request_refresh()
        return cast(
            ServiceResponse,
            {"success": True, "previous_ev_id": previous_ev_id},
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ASSIGN_EV_TO_WALLBOX,
        _assign_ev_to_wallbox,
        schema=ASSIGN_EV_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
