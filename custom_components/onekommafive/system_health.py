"""System Health integration for the 1KOMMA5° platform.

Surfaces anonymised diagnostics in Settings → System → Repairs →
System Information so users can paste a structured summary into bug
reports instead of running the full diagnostics-download flow.

Strictly PII-safe: no customer_id, no addresses, no system_id, no
device serials. Coordinator status and SDK version only.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from homeassistant.components.system_health import (
    SystemHealthRegistration,
    async_check_can_reach_url,
)
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register(hass: HomeAssistant, register: SystemHealthRegistration) -> None:
    """Register the System Health info callback for 1KOMMA5°."""
    register.async_register_info(system_health_info, "https://app.1komma5grad.com")


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return health diagnostics for the System Information panel."""
    info: dict[str, Any] = {
        "can_reach_api": async_check_can_reach_url(hass, "https://heartbeat.1komma5grad.com"),
        "sdk_version": _sdk_version(),
    }

    # Per-coordinator status for the loaded config entry.
    entries = list(hass.config_entries.async_entries(DOMAIN))
    info["config_entries"] = len(entries)

    for entry in entries:
        data = getattr(entry, "runtime_data", None)
        if data is None:
            continue
        for label, coord in (
            ("live", data.live_coordinator),
            ("price", data.price_coordinator),
            ("optimization", data.optimization_coordinator),
            ("weather", data.weather_coordinator),
            ("system_status", data.system_status_coordinator),
        ):
            info[f"{label}_last_update_success"] = bool(coord.last_update_success)
            # DataUpdateCoordinator's `last_update_success_time` was added in
            # HA 2024.10 and exposed publicly later; fall back gracefully so
            # older runtimes don't break the panel.
            last_dt = getattr(coord, "last_update_success_time", None)
            if isinstance(last_dt, dt.datetime):
                info[f"{label}_last_update_age"] = _format_age(last_dt)
        # Currency surfaced so non-EUR users can confirm the integration picked
        # the right one at setup time.
        info["currency"] = data.currency
        # Just the country code — no addresses / coordinates / names.
        details = getattr(data, "details", None)
        country = getattr(details, "address_country", None) if details else None
        if country:
            info["country"] = country
        break  # only one entry in practice

    return info


def _sdk_version() -> str:
    """Return the installed onekommafive SDK version, or a sentinel."""
    try:
        import importlib.metadata as md

        return md.version("onekommafive")
    except Exception:  # pragma: no cover - defensive
        return "unknown"


def _format_age(then: dt.datetime) -> str:
    """Render a 'time-since' string usable in the System Health UI."""
    delta = dt.datetime.now(tz=dt.UTC) - then
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "in the future"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"
