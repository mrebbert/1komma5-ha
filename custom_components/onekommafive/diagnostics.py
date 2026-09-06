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
from .entity import asset_redacted_dict, get_emp_type, is_1k5_backend

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


def _energy_summary(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    energy = data.energy
    return {
        "savings_eur": getattr(energy, "savings_eur", None),
        "self_sufficiency": getattr(energy, "self_sufficiency", None),
        "updated_at": getattr(energy, "updated_at", None),
    }


def _notifications_summary(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    notifications = getattr(data, "notifications", None) or []
    return {"count": len(notifications)}


def _system_status_summary(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    asset_types = sorted({a.type for a in (data.assets or [])})
    return {
        "site_status": data.site_status,
        "asset_count": len(data.assets) if data.assets else 0,
        "asset_types": asset_types,
        "active_feature_count": len(data.active_features) if data.active_features else 0,
    }


def _details_redacted(details: Any) -> dict[str, Any]:
    """Redacted view of SystemDetails.

    Strictly excludes PII and gateway-coupling secrets:
    customer block, address fields, lat/lon, technical contact,
    third-party meter IDs, and the DeviceGateway.gridx_start_code /
    serial_number / id fields.
    """
    return {
        "emp_type": getattr(details, "emp_type", None),
        "status": getattr(details, "status", None),
        "dynamic_pulse_compatible": getattr(details, "dynamic_pulse_compatible", None),
        "energy_trader_active": getattr(details, "energy_trader_active", None),
        "electricity_contract_active": getattr(details, "electricity_contract_active", None),
        "has_third_party_smart_meter": getattr(details, "has_third_party_smart_meter", None),
        "earliest_measurement": getattr(details, "earliest_measurement", None),
        "created_at": getattr(details, "created_at", None),
        "updated_at": getattr(details, "updated_at", None),
        "device_gateway_count": len(getattr(details, "device_gateways", []) or []),
    }


def _assets_redacted(status_data: Any) -> dict[str, Any]:
    """Redacted view of SystemStatusData.

    Strictly excludes Asset.id, Asset.name (often contains site address),
    Asset.serial_number and Asset.network_address (local IP).
    """
    if status_data is None:
        return {}
    return {
        "site_status": status_data.site_status,
        "asset_count": len(status_data.assets) if status_data.assets else 0,
        "assets": [
            asset_redacted_dict(a, extra_keys=("type", "heat_pump_meter_type"))
            for a in (status_data.assets or [])
        ],
        "active_features": list(status_data.active_features or []),
    }


async def _wallbox_snapshot(
    hass: HomeAssistant, system: Any, details: Any
) -> list[dict[str, Any]] | None:
    """Fetch wallbox hardware summaries for pairing diagnostics.

    The EV entities (charging mode / target SoC / departure) are driven by
    a vehicle profile (`get_ev_chargers`) paired to a wallbox via
    ``Wallbox.assigned_ev_id``. When the vehicle list is empty but a wallbox
    is present, the paired-vs-unpaired state is the single most useful
    triage signal.

    Since SDK 0.2.0 the wallbox endpoint is site-scoped and works on both
    GridX and non-GridX backends, so ``get_wallboxes()`` normally succeeds
    for 1K5 installs too. The ``emp_type_1k5_native_hint`` flag stays as
    a safety net for the rare case the endpoint still returns 30401 on a
    1K5 backend (transient issue or unexpected routing).
    """
    try:
        wallboxes = await hass.async_add_executor_job(system.get_wallboxes)
    except Exception as err:
        entry: dict[str, Any] = {"error": repr(err)}
        emp_type = get_emp_type(details)
        gateway_count = len(getattr(details, "device_gateways", []) or []) if details else None
        if "30401" in entry["error"] and is_1k5_backend(emp_type) and gateway_count == 0:
            entry["emp_type_1k5_native_hint"] = True
        entry["emp_type"] = emp_type
        entry["device_gateway_count"] = gateway_count
        return [entry]
    return [
        {
            "name": getattr(w, "name", None),
            "assigned_ev_id_present": getattr(w, "assigned_ev_id", None) is not None,
        }
        for w in (wallboxes or [])
    ]


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
            "system_status": {
                **_coordinator_snapshot(data.system_status_coordinator),
                "summary": _system_status_summary(data.system_status_coordinator.data),
            },
            "energy": {
                **_coordinator_snapshot(data.energy_coordinator),
                "summary": _energy_summary(data.energy_coordinator.data),
            },
            "notifications": {
                **_coordinator_snapshot(data.notifications_coordinator),
                "summary": _notifications_summary(data.notifications_coordinator.data),
            },
        },
        "system": {
            "details": _details_redacted(data.details) if data.details else None,
            "status_and_assets": _assets_redacted(data.system_status_coordinator.data),
            "wallboxes": await _wallbox_snapshot(hass, data.system, data.details),
        },
    }

    try:
        from importlib.metadata import version

        diag["sdk_version"] = version("onekommafive")
    except Exception:
        diag["sdk_version"] = None

    return diag
