"""Base entity for the 1KOMMA5° integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import (
    OneKomma5EnergyCoordinator,
    OneKomma5LiveCoordinator,
    OneKomma5NotificationsCoordinator,
    OneKomma5OptimizationCoordinator,
    OneKomma5PriceCoordinator,
    OneKomma5SystemStatusCoordinator,
    OneKomma5WeatherCoordinator,
)

# HA ≥ 2026.7 deprecates DeviceInfo.via_device (tuple) in favour of
# via_device_id (device_registry id string). Prefer the new form when
# available; fall back cleanly on older HA installs.
_HAS_VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__


def _set_via(di: DeviceInfo, system_id: str, parent_device_id: str | None) -> DeviceInfo:
    """Set the correct via_device* key on ``di`` for the installed HA version."""
    if _HAS_VIA_DEVICE_ID and parent_device_id is not None:
        # via_device_id exists on HA ≥ 2026.7 only; local test HA (2026.2)
        # lacks the TypedDict key so mypy complains — runtime guard makes
        # this safe.
        di["via_device_id"] = parent_device_id  # type: ignore[typeddict-unknown-key]
    else:
        di["via_device"] = (DOMAIN, system_id)
    return di


def system_device_info(system_id: str, system_name: str) -> DeviceInfo:
    """Build the canonical DeviceInfo for a 1KOMMA5° system."""
    return DeviceInfo(
        identifiers={(DOMAIN, system_id)},
        name=system_name,
        manufacturer="1KOMMA5°",
        model="Heartbeat",
        configuration_url="https://app.1komma5grad.com",
    )


# Map from sub-device key (used in DeviceInfo identifier suffix and
# translation_key) to the SDK ``Asset.type`` strings that resolve to it.
# Some manufacturers (FoxESS) expose the inverter as two assets (BATTERY +
# PV_SYSTEM) instead of a single HYBRID; both variants map to the same
# `inverter` sub-device from an HA UX perspective. First-match wins in
# `_resolve_asset` so a HYBRID beats a PV_SYSTEM for the same install.
ASSET_TYPES_BY_DEVICE_KEY: dict[str, tuple[str, ...]] = {
    "inverter": ("HYBRID", "PV_SYSTEM"),
    "heat_pump": ("HEAT_PUMP",),
    "meter": ("METER",),
    "wallbox": ("EV_CHARGER",),
    "battery": ("BATTERY",),
}

# Backward-compatible flat map used by call-sites that look up a single
# asset_type per device_key. First entry per key wins; readers that need
# full coverage should iterate ``ASSET_TYPES_BY_DEVICE_KEY[key]`` instead.
ASSET_TYPE_BY_DEVICE_KEY: dict[str, str] = {
    key: types[0] for key, types in ASSET_TYPES_BY_DEVICE_KEY.items()
}


def resolve_asset(assets_by_type: dict[str, Any], device_key: str | None) -> Any | None:
    """Return the first matching asset for ``device_key`` or ``None``.

    Iterates the tuple of candidate asset types (e.g. HYBRID, PV_SYSTEM
    for the inverter sub-device) — first match wins.
    """
    if device_key is None:
        return None
    for asset_type in ASSET_TYPES_BY_DEVICE_KEY.get(device_key, ()):
        if (asset := assets_by_type.get(asset_type)) is not None:
            return asset
    return None


def asset_device_info(
    system_id: str,
    device_key: str,
    asset: Any | None,
    parent_device_id: str | None = None,
) -> DeviceInfo:
    """Build a DeviceInfo for an asset sub-device.

    ``device_key`` is the stable identifier suffix and translation key
    (``inverter`` / ``heat_pump`` / ``meter`` / ``wallbox``). The translated
    label comes from ``device.<device_key>.name`` in ``strings.json``.

    ``asset`` is the matching :class:`onekommafive.models.sites.Asset` from
    the SystemStatusCoordinator's ``assets_by_type`` map. When the asset is
    ``None`` (asset not yet fetched / not present), manufacturer / model /
    firmware fall back to ``None`` so HA shows only the translated label.

    ``parent_device_id`` is the device_registry id of the system parent
    device (captured at setup time on ``OneKomma5Data.system_device_id``);
    used to set ``via_device_id`` instead of the deprecated ``via_device``
    identifier tuple.

    PII contract: only ``manufacturer``, ``model`` and ``firmware`` from the
    asset payload are exposed — never ``id``, ``serial_number``,
    ``network_address`` or asset ``name``.
    """
    di = DeviceInfo(
        identifiers={(DOMAIN, f"{system_id}_{device_key}")},
        translation_key=device_key,
        manufacturer=getattr(asset, "manufacturer", None) if asset else None,
        model=getattr(asset, "model", None) if asset else None,
        sw_version=getattr(asset, "firmware", None) if asset else None,
    )
    return _set_via(di, system_id, parent_device_id)


class _BaseSystemEntity[C: DataUpdateCoordinator[Any]](CoordinatorEntity[C]):
    """Generic base for all entities tied to a 1KOMMA5° system device.

    The five typed `OneKomma5*Entity` aliases below just bind the coordinator
    type parameter — same idiom as `OneKomma5BaseCoordinator[T]`.

    Entities sit on the system parent device by default. To re-parent an
    entity to an asset sub-device (inverter / heat_pump / meter / wallbox),
    pass ``device_key=`` to ``__init__`` (or set ``_device_key`` as a
    class-var) and pass the matching ``asset=`` resolved against the
    SystemStatusCoordinator's ``assets_by_type`` map.
    """

    _attr_has_entity_name = True
    _device_key: str | None = None  # subclasses may override

    def __init__(
        self,
        coordinator: C,
        system_id: str,
        system_name: str,
        unique_id_suffix: str,
        *,
        device_key: str | None = None,
        asset: Any | None = None,
        parent_device_id: str | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._system_id = system_id
        self._attr_unique_id = f"{system_id}_{unique_id_suffix}"
        self._stable_object_id = f"{slugify(system_name)}_{unique_id_suffix}"
        key = device_key if device_key is not None else self._device_key
        if key is not None and asset is not None:
            self._attr_device_info = asset_device_info(system_id, key, asset, parent_device_id)
        else:
            self._attr_device_info = system_device_info(system_id, system_name)
            # Asked for a sub-device but the hardware isn't reported by the
            # cloud → hide by default so the device list stays clean.
            if key is not None:
                self._attr_entity_registry_enabled_default = False


class OneKomma5Entity(_BaseSystemEntity[OneKomma5LiveCoordinator]):
    """Base entity for live-data entities."""


class OneKomma5PriceEntity(_BaseSystemEntity[OneKomma5PriceCoordinator]):
    """Base entity for price-data entities."""

    def _dynamic_current_price(self) -> float | None:
        """Look up the current price using the dynamic helper if available."""
        from .helpers import get_current_price  # local import to avoid cycles

        if self.coordinator.data is None:
            return None
        if self.coordinator.data.all_in_prices:
            return get_current_price(self.coordinator.data.all_in_prices)
        return self.coordinator.data.current_price


class OneKomma5OptimizationEntity(_BaseSystemEntity[OneKomma5OptimizationCoordinator]):
    """Base entity for optimization-data entities."""


class OneKomma5SystemStatusEntity(_BaseSystemEntity[OneKomma5SystemStatusCoordinator]):
    """Base entity for system-status entities (connectivity, active features)."""


class OneKomma5WeatherEntity(_BaseSystemEntity[OneKomma5WeatherCoordinator]):
    """Base entity for sensors backed by the weather coordinator."""


class OneKomma5EnergyEntity(_BaseSystemEntity[OneKomma5EnergyCoordinator]):
    """Base entity for sensors backed by the energy (today) coordinator."""


class OneKomma5NotificationsEntity(_BaseSystemEntity[OneKomma5NotificationsCoordinator]):
    """Base entity for sensors backed by the notifications coordinator.

    Currently only used by the ``diag_notification_update`` diagnostic
    timestamp — the notifications coordinator has no user-facing sensors,
    it emits ``EVENT_NOTIFICATION`` bus events instead.
    """


class OneKomma5EVEntity(CoordinatorEntity[OneKomma5LiveCoordinator]):
    """Base entity for EV (vehicle) entities.

    The vehicle is a sub-device under the system parent, named consistently
    with the asset sub-devices: a translated label ("Elektrofahrzeug" /
    "Vehicle") plus the real manufacturer and model from the EV profile.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OneKomma5LiveCoordinator,
        system_id: str,
        system_name: str,
        ev: Any,
        unique_id_suffix: str,
        parent_device_id: str | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._system_id = system_id
        self._ev_id = ev.id()
        self._attr_unique_id = f"{system_id}_{self._ev_id}_{unique_id_suffix}"
        # ev_id in the object_id so multi-vehicle installs don't collide.
        self._stable_object_id = f"{slugify(system_name)}_{slugify(self._ev_id)}_{unique_id_suffix}"
        self._attr_device_info = _set_via(
            DeviceInfo(
                identifiers={(DOMAIN, f"{system_id}_{self._ev_id}")},
                translation_key="vehicle",
                manufacturer=ev.manufacturer(),
                model=ev.model(),
            ),
            system_id,
            parent_device_id,
        )

    def _get_ev(self) -> Any | None:
        """Return the current EV charger object from coordinator data."""
        if self.coordinator.data is None:
            return None
        for ev in self.coordinator.data.ev_chargers:
            if ev.id() == self._ev_id:
                return ev
        return None


def apply_stable_entity_ids(entities: Any, platform: str) -> None:
    """Force each entity's ``entity_id`` to ``<platform>.<stable_object_id>``.

    Called from every platform's ``async_setup_entry`` just before
    ``async_add_entities`` so fresh-install entity_ids stay
    ``<platform>.<system_slug>_<code_suffix>`` regardless of HA language or
    sub-device parenting (see issue #8). Existing entries are preserved —
    HA's entity_registry looks up by ``unique_id`` first, and the object_id
    passed at add-time is only a hint used for fresh registrations.
    """
    for entity in entities:
        entity.entity_id = f"{platform}.{entity._stable_object_id}"


class QuarterHourUpdateMixin:
    """Mixin: subscribe an entity to quarter-hour boundary state updates.

    Use ``self._async_register_quarter_hour_update()`` from
    ``async_added_to_hass`` after the parent ``super().async_added_to_hass()``
    call. The entity's ``async_write_ha_state`` is invoked at :00/:15/:30/:45.

    Useful for entities whose state depends on the active 15-minute price
    slot but whose data coordinator updates less frequently.
    """

    hass: Any  # provided by HA Entity base class

    def _async_register_quarter_hour_update(self) -> None:
        self.async_on_remove(  # type: ignore[attr-defined]
            async_track_time_change(
                self.hass,
                self._quarter_hour_update,
                minute=[0, 15, 30, 45],
                second=[0],
            )
        )

    @callback
    def _quarter_hour_update(self, _now: datetime) -> None:
        """Re-evaluate state at quarter-hour boundaries."""
        self.async_write_ha_state()  # type: ignore[attr-defined]
