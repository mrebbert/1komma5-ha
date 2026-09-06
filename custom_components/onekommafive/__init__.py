"""The 1KOMMA5° integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import CONF_PASSWORD, CONF_SYSTEM_ID, CONF_USERNAME
from .coordinator import (
    OneKomma5EnergyCoordinator,
    OneKomma5LiveCoordinator,
    OneKomma5NotificationsCoordinator,
    OneKomma5OptimizationCoordinator,
    OneKomma5PriceCoordinator,
    OneKomma5SystemStatusCoordinator,
    OneKomma5WeatherCoordinator,
)
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.TIME,
    Platform.WEATHER,
]


@dataclass(frozen=True)
class PriceGuarantee:
    """DP price-guarantee snapshot; value normalized to EUR/kWh."""

    value_eur_per_kwh: float | None
    version: str | None


@dataclass
class OneKomma5Data:
    """Runtime data stored in the config entry."""

    live_coordinator: OneKomma5LiveCoordinator
    price_coordinator: OneKomma5PriceCoordinator
    optimization_coordinator: OneKomma5OptimizationCoordinator
    weather_coordinator: OneKomma5WeatherCoordinator
    system_status_coordinator: OneKomma5SystemStatusCoordinator
    energy_coordinator: OneKomma5EnergyCoordinator
    notifications_coordinator: OneKomma5NotificationsCoordinator
    system: Any  # onekommafive.system.System (SDK ships no type hints → Any)
    system_name: str  # pre-fetched in executor to avoid blocking calls in async context
    # Full SystemDetails captured once at setup. Used only for diagnostics —
    # never surfaced as entities. None if the call failed at setup.
    details: object | None
    customer_id: str | None  # sliced off details for the system-status coordinator
    currency: str  # ISO 4217 code derived from details.address_country (default EUR)
    price_guarantee: PriceGuarantee | None
    co2_saved_kg: float | None  # lifetime CO2 saved (kg), captured once at setup
    system_device_id: str  # device_registry ID of the system parent device (via_device_id)
    emp_type: str | None  # SystemDetails.emp_type, e.g. "GRIDX" or "1K5"


type OneKomma5ConfigEntry = ConfigEntry[OneKomma5Data]


def _safe_fetch[T](label: str, fn: Callable[[], T]) -> T | None:
    """Run a setup-time SDK call; log and swallow any failure."""
    try:
        return fn()
    except Exception as err:
        _LOGGER.warning("%s fetch failed: %s", label, err)
        return None


def _extract_co2_saved(system: Any) -> float | None:
    """Return lifetime CO2 saved in kg from get_impact_overview, or None on failure."""
    impact = _safe_fetch("Impact overview", system.get_impact_overview)
    if impact is None:
        return None
    value = getattr(impact, "co2_savings_kg", None)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_price_guarantee(system: Any, customer_id: str | None) -> PriceGuarantee | None:
    """Return DP price-guarantee (ct/kWh → EUR/kWh) or None on any failure."""
    if customer_id is None:
        return None
    subs = _safe_fetch("Subscriptions", lambda: system.get_subscriptions(customer_id))
    if subs is None:
        return None
    for sub in getattr(subs, "subscriptions", []) or []:
        if getattr(sub, "type", None) != "DYNAMIC_PULSE":
            continue
        raw_value = getattr(sub, "price_guarantee_value", None)
        if raw_value is None:
            return None
        unit = (getattr(sub, "price_guarantee_unit", None) or "").lower()
        version = getattr(sub, "price_guarantee_version", None)
        try:
            value_eur_per_kwh = float(raw_value) / 100 if "ct" in unit else float(raw_value)
        except (TypeError, ValueError):
            return None
        return PriceGuarantee(value_eur_per_kwh=value_eur_per_kwh, version=version)
    return None


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register integration-wide services once on HA startup."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OneKomma5ConfigEntry) -> bool:
    """Set up 1KOMMA5° from a config entry."""
    from onekommafive.client import Client
    from onekommafive.errors import AuthenticationError, RequestError
    from onekommafive.systems import Systems

    username: str = entry.data[CONF_USERNAME]
    password: str = entry.data[CONF_PASSWORD]
    system_id: str = entry.data[CONF_SYSTEM_ID]

    try:

        def _fetch_system() -> tuple[
            object, str, object | None, PriceGuarantee | None, float | None
        ]:
            client = Client(username, password)
            system = Systems(client).get_system(system_id)
            # system.info() makes a blocking HTTP call — keep it in the executor
            info = system.info()
            name = (
                info.name
                or (f"1KOMMA5° {info.address_city}" if info.address_city else None)
                or f"1KOMMA5° {system.id()[:8]}"
            )
            # SystemDetails is rarely-changing metadata — fetched once at setup
            # and cached. Failure is non-fatal: it only means the diagnostics
            # dump lacks the extra fields and the active-features endpoint
            # is skipped (customer_id is required for that call).
            details = _safe_fetch("System details", system.get_details)
            cust_id = getattr(details, "customer_id", None) if details else None
            price_guarantee = _extract_price_guarantee(system, cust_id)
            co2_saved_kg = _extract_co2_saved(system)
            return system, name, details, price_guarantee, co2_saved_kg

        (
            system,
            system_name,
            details,
            price_guarantee,
            co2_saved_kg,
        ) = await hass.async_add_executor_job(_fetch_system)
    except AuthenticationError as err:
        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
    except RequestError as err:
        raise ConfigEntryNotReady(f"Cannot connect to 1KOMMA5° API: {err}") from err

    customer_id = getattr(details, "customer_id", None) if details else None
    from .helpers import resolve_currency

    currency = resolve_currency(getattr(details, "address_country", None) if details else None)

    from .entity import get_emp_type, is_1k5_backend

    emp_type = get_emp_type(details)
    live_coordinator = OneKomma5LiveCoordinator(hass, system, is_1k5=is_1k5_backend(emp_type))
    price_coordinator = OneKomma5PriceCoordinator(hass, system)
    optimization_coordinator = OneKomma5OptimizationCoordinator(hass, system)
    weather_coordinator = OneKomma5WeatherCoordinator(hass, system)
    system_status_coordinator = OneKomma5SystemStatusCoordinator(hass, system, customer_id)
    energy_coordinator = OneKomma5EnergyCoordinator(hass, system)
    notifications_coordinator = OneKomma5NotificationsCoordinator(hass, system, entry.entry_id)

    await live_coordinator.async_config_entry_first_refresh()

    # Only the live coordinator is critical for setup. The rest are non-critical:
    # async_refresh() logs failures and never raises here, so a rate-limited or
    # temporarily-unavailable first fetch just leaves those entities unavailable
    # until the next scheduled interval — setup proceeds regardless.
    for coordinator in (
        price_coordinator,
        optimization_coordinator,
        weather_coordinator,
        system_status_coordinator,
        energy_coordinator,
        notifications_coordinator,
    ):
        await coordinator.async_refresh()

    # Pre-create the system parent device so child DeviceInfo entries can link
    # via `via_device_id` (device_registry id string) instead of the deprecated
    # `via_device` (identifier tuple). Deprecation removes the tuple form in
    # HA 2027.8; this migration keeps the log clean now.
    from .entity import system_device_info

    parent_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **system_device_info(system_id, system_name),
    )

    entry.runtime_data = OneKomma5Data(
        live_coordinator=live_coordinator,
        price_coordinator=price_coordinator,
        optimization_coordinator=optimization_coordinator,
        weather_coordinator=weather_coordinator,
        system_status_coordinator=system_status_coordinator,
        energy_coordinator=energy_coordinator,
        notifications_coordinator=notifications_coordinator,
        system=system,
        system_name=system_name,
        details=details,
        customer_id=customer_id,
        currency=currency,
        price_guarantee=price_guarantee,
        co2_saved_kg=co2_saved_kg,
        system_device_id=parent_device.id,
        emp_type=emp_type,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: OneKomma5ConfigEntry) -> None:
    """Reload the integration when options change so option-driven entities re-instantiate."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: OneKomma5ConfigEntry) -> bool:
    """Unload a 1KOMMA5° config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
