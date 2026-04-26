"""The 1KOMMA5° integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_PASSWORD, CONF_SYSTEM_ID, CONF_USERNAME
from .coordinator import (
    OneKomma5LiveCoordinator,
    OneKomma5OptimizationCoordinator,
    OneKomma5PriceCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.TIME,
]


@dataclass
class OneKomma5Data:
    """Runtime data stored in the config entry."""

    live_coordinator: OneKomma5LiveCoordinator
    price_coordinator: OneKomma5PriceCoordinator
    optimization_coordinator: OneKomma5OptimizationCoordinator
    system: object  # onekommafive.system.System
    system_name: str  # pre-fetched in executor to avoid blocking calls in async context


type OneKomma5ConfigEntry = ConfigEntry[OneKomma5Data]


async def async_setup_entry(hass: HomeAssistant, entry: OneKomma5ConfigEntry) -> bool:
    """Set up 1KOMMA5° from a config entry."""
    from onekommafive.client import Client
    from onekommafive.errors import AuthenticationError, RequestError
    from onekommafive.systems import Systems

    username: str = entry.data[CONF_USERNAME]
    password: str = entry.data[CONF_PASSWORD]
    system_id: str = entry.data[CONF_SYSTEM_ID]

    try:
        def _fetch_system() -> tuple[object, str]:
            client = Client(username, password)
            system = Systems(client).get_system(system_id)
            # system.info() makes a blocking HTTP call — keep it in the executor
            info = system.info()
            name = (
                info.name
                or (f"1KOMMA5° {info.address_city}" if info.address_city else None)
                or f"1KOMMA5° {system.id()[:8]}"
            )
            return system, name

        system, system_name = await hass.async_add_executor_job(_fetch_system)
    except AuthenticationError as err:
        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
    except RequestError as err:
        raise ConfigEntryNotReady(f"Cannot connect to 1KOMMA5° API: {err}") from err

    live_coordinator = OneKomma5LiveCoordinator(hass, system)
    price_coordinator = OneKomma5PriceCoordinator(hass, system)
    optimization_coordinator = OneKomma5OptimizationCoordinator(hass, system)

    await live_coordinator.async_config_entry_first_refresh()

    # Price and optimization data is non-critical — don't block setup if the
    # API rate-limits or is temporarily unavailable.  Data will be fetched on
    # the next scheduled interval.
    try:
        await price_coordinator.async_refresh()
    except Exception:
        _LOGGER.warning("Initial price fetch failed, will retry on next interval")

    try:
        await optimization_coordinator.async_refresh()
    except Exception:
        _LOGGER.warning("Initial optimization fetch failed, will retry on next interval")

    entry.runtime_data = OneKomma5Data(
        live_coordinator=live_coordinator,
        price_coordinator=price_coordinator,
        optimization_coordinator=optimization_coordinator,
        system=system,
        system_name=system_name,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OneKomma5ConfigEntry) -> bool:
    """Unload a 1KOMMA5° config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
