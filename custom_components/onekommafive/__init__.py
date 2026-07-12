"""The 1KOMMA5° integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_PASSWORD, CONF_SYSTEM_ID, CONF_USERNAME
from .coordinator import (
    OneKomma5EnergyCoordinator,
    OneKomma5LiveCoordinator,
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


@dataclass
class OneKomma5Data:
    """Runtime data stored in the config entry."""

    live_coordinator: OneKomma5LiveCoordinator
    price_coordinator: OneKomma5PriceCoordinator
    optimization_coordinator: OneKomma5OptimizationCoordinator
    weather_coordinator: OneKomma5WeatherCoordinator
    system_status_coordinator: OneKomma5SystemStatusCoordinator
    energy_coordinator: OneKomma5EnergyCoordinator
    system: Any  # onekommafive.system.System (SDK ships no type hints → Any)
    system_name: str  # pre-fetched in executor to avoid blocking calls in async context
    # Full SystemDetails captured once at setup. Used only for diagnostics —
    # never surfaced as entities. None if the call failed at setup.
    details: object | None
    customer_id: str | None  # sliced off details for the system-status coordinator
    currency: str  # ISO 4217 code derived from details.address_country (default EUR)


type OneKomma5ConfigEntry = ConfigEntry[OneKomma5Data]


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

        def _fetch_system() -> tuple[object, str, object | None]:
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
            try:
                details = system.get_details()
            except Exception as err:  # pragma: no cover - defensive
                _LOGGER.warning("System details fetch failed: %s", err)
                details = None
            return system, name, details

        system, system_name, details = await hass.async_add_executor_job(_fetch_system)
    except AuthenticationError as err:
        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
    except RequestError as err:
        raise ConfigEntryNotReady(f"Cannot connect to 1KOMMA5° API: {err}") from err

    customer_id = getattr(details, "customer_id", None) if details else None
    from .helpers import resolve_currency

    currency = resolve_currency(getattr(details, "address_country", None) if details else None)

    live_coordinator = OneKomma5LiveCoordinator(hass, system)
    price_coordinator = OneKomma5PriceCoordinator(hass, system)
    optimization_coordinator = OneKomma5OptimizationCoordinator(hass, system)
    weather_coordinator = OneKomma5WeatherCoordinator(hass, system)
    system_status_coordinator = OneKomma5SystemStatusCoordinator(hass, system, customer_id)
    energy_coordinator = OneKomma5EnergyCoordinator(hass, system)

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
    ):
        await coordinator.async_refresh()

    entry.runtime_data = OneKomma5Data(
        live_coordinator=live_coordinator,
        price_coordinator=price_coordinator,
        optimization_coordinator=optimization_coordinator,
        weather_coordinator=weather_coordinator,
        system_status_coordinator=system_status_coordinator,
        energy_coordinator=energy_coordinator,
        system=system,
        system_name=system_name,
        details=details,
        customer_id=customer_id,
        currency=currency,
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
