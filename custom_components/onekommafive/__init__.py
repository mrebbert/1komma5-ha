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

from .const import CONF_PASSWORD, CONF_SYSTEM_ID, CONF_USERNAME, DOMAIN
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
    sdk_version: str | None  # installed onekommafive SDK version; cached to keep diag async-safe
    wallboxes: list[Any]  # physical wallboxes, cached at setup; drives multi-wallbox sub-devices
    wallbox_device_ids: dict[
        str, str
    ]  # {Wallbox.id: device_registry id}; used to via_device the paired EV
    device_gateways: list[
        Any
    ]  # Heartbeat gateways from SDK v0.4.0 endpoint; surfaces in diagnostics


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


def _remove_stale_wallbox_devices(
    *,
    device_registry: dr.DeviceRegistry,
    entry_id: str,
    system_id: str,
    wallboxes: list[Any],
) -> None:
    """Delete wallbox sub-devices whose id is no longer reported by the API.

    Covers three drift cases: (a) a physical wallbox was removed from the site,
    (b) the account transitioned from single-wallbox (identifier
    ``(DOMAIN, f"{system_id}_wallbox")``) to multi-wallbox
    (per-wb ``_wallbox_<id>``), (c) the reverse transition. Anything under this
    entry whose identifier starts with ``f"{system_id}_wallbox"`` but does not
    match one of the currently-valid keys is removed from the device registry.
    """
    from .entity import wallbox_sub_device_key

    keep = {
        f"{system_id}_{wallbox_sub_device_key(wb.id, len(wallboxes))}"
        for wb in wallboxes
        if getattr(wb, "id", None)
    }
    stale_prefix = f"{system_id}_wallbox"
    for device in list(device_registry.devices.values()):
        if entry_id not in device.config_entries:
            continue
        our_ids = [ident for ident in device.identifiers if ident[0] == DOMAIN]
        if not our_ids:
            continue
        suffix = our_ids[0][1]
        if not suffix.startswith(stale_prefix) or suffix in keep:
            continue
        _LOGGER.info("Removing stale wallbox sub-device %s", suffix)
        device_registry.async_remove_device(device.id)


def _setup_wallbox_sub_devices(
    *,
    device_registry: dr.DeviceRegistry,
    entry: OneKomma5ConfigEntry,
    system_id: str,
    parent_device_id: str,
    wallboxes: list[Any],
    system_status_coordinator: OneKomma5SystemStatusCoordinator,
) -> dict[str, str]:
    """Pre-create one HA sub-device per physical wallbox and return ``{Wallbox.id: device_id}``.

    Multi-wallbox setups get one sub-device per Wallbox with its own
    manufacturer / model / firmware and ``Wallbox.name`` as label. Single-
    wallbox setups keep the historical ``(DOMAIN, f"{system_id}_wallbox")``
    identifier and the translated ``device.wallbox.name`` label so existing
    area assignments and device_registry entries stay intact. The vehicle
    sub-devices (see ``OneKomma5EVEntity``) via_device onto the matching
    wallbox so HA renders "Vehicle under Wallbox" in the UI.
    """
    from .entity import asset_device_info, wallbox_sub_device_key

    ev_charger_assets: list[Any] = []
    if system_status_coordinator.data is not None:
        ev_charger_assets = system_status_coordinator.data.assets_by_type_list.get("EV_CHARGER", [])
    wallbox_device_ids: dict[str, str] = {}
    wallbox_count = len(wallboxes)
    for wallbox in wallboxes:
        wb_id = getattr(wallbox, "id", None)
        if not wb_id:
            continue
        # Multi-wallbox: name-match to enrich the sub-device with the
        # matching Asset's manufacturer/model/firmware. Single-wallbox: take
        # the one EV_CHARGER asset (implicit pairing, no name lookup).
        if wallbox_count > 1:
            matching_asset = next(
                (a for a in ev_charger_assets if getattr(a, "name", None) == wallbox.name),
                None,
            )
            explicit_name = wallbox.name
        else:
            matching_asset = ev_charger_assets[0] if ev_charger_assets else None
            explicit_name = None
        key = wallbox_sub_device_key(wb_id, wallbox_count)
        di = asset_device_info(
            system_id, key, matching_asset, parent_device_id, explicit_name=explicit_name
        )
        wallbox_device = device_registry.async_get_or_create(config_entry_id=entry.entry_id, **di)
        wallbox_device_ids[wb_id] = wallbox_device.id
    return wallbox_device_ids


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register integration-wide services once on HA startup."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OneKomma5ConfigEntry) -> bool:
    """Set up 1KOMMA5° from a config entry."""
    from onekommafive.client import Client
    from onekommafive.errors import AuthenticationError, RequestError
    from onekommafive.systems import Systems

    from .helpers import sdk_version as _read_sdk_version

    username: str = entry.data[CONF_USERNAME]
    password: str = entry.data[CONF_PASSWORD]
    system_id: str = entry.data[CONF_SYSTEM_ID]

    try:

        def _fetch_system() -> tuple[
            object,
            str,
            object | None,
            PriceGuarantee | None,
            float | None,
            str | None,
            list[Any],
            list[Any],
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
            sdk_version = _read_sdk_version()
            # Wallbox inventory rarely changes; reload picks up hardware
            # additions. Failure is non-fatal (e.g. transient upstream error);
            # empty list means multi-wallbox sub-devices are skipped this run.
            wallboxes = _safe_fetch("Wallboxes", system.get_wallboxes) or []
            # Heartbeat gateways (SDK v0.4.0). 1K5-backend installs return
            # an empty list here; GRIDX installs return one gateway per
            # HEMS box. Non-fatal on failure.
            device_gateways = _safe_fetch("Device gateways", system.get_device_gateways) or []
            return (
                system,
                name,
                details,
                price_guarantee,
                co2_saved_kg,
                sdk_version,
                wallboxes,
                device_gateways,
            )

        (
            system,
            system_name,
            details,
            price_guarantee,
            co2_saved_kg,
            sdk_version,
            wallboxes,
            device_gateways,
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
    live_coordinator = OneKomma5LiveCoordinator(
        hass, system, is_1k5=is_1k5_backend(emp_type), entry_id=entry.entry_id
    )
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

    device_registry = dr.async_get(hass)
    parent_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **system_device_info(system_id, system_name),
    )

    wallbox_device_ids = _setup_wallbox_sub_devices(
        device_registry=device_registry,
        entry=entry,
        system_id=system_id,
        parent_device_id=parent_device.id,
        wallboxes=wallboxes,
        system_status_coordinator=system_status_coordinator,
    )
    _remove_stale_wallbox_devices(
        device_registry=device_registry,
        entry_id=entry.entry_id,
        system_id=system_id,
        wallboxes=wallboxes,
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
        sdk_version=sdk_version,
        wallboxes=wallboxes,
        wallbox_device_ids=wallbox_device_ids,
        device_gateways=device_gateways,
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


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: OneKomma5ConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Let the user delete sub-devices from the HA devices view.

    Live sub-devices (system parent, inverter / heat pump / meter / wallbox /
    battery / vehicle) get re-created on the next reload, so deleting one by
    accident is safe. Orphaned sub-devices from earlier releases (like the
    empty gateway sub-device from a pre-v0.1.60 build) simply stay gone.
    """
    return True
