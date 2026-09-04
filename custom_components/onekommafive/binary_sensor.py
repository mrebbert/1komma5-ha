"""Binary sensor platform for the 1KOMMA5° integration."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OneKomma5ConfigEntry
from .entity import (
    ASSET_TYPES_BY_DEVICE_KEY,
    OneKomma5OptimizationEntity,
    OneKomma5PriceEntity,
    OneKomma5SystemStatusEntity,
    QuarterHourUpdateMixin,
    apply_stable_entity_ids,
    resolve_asset,
)
from .helpers import active_optimization_event


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities from a config entry."""
    data = entry.runtime_data
    system_id = data.system.id()
    assets_by_type = (
        data.system_status_coordinator.data.assets_by_type
        if data.system_status_coordinator.data is not None
        else {}
    )
    entities: list = [
        OneKomma5CheapElectricitySensor(
            data.price_coordinator,
            system_id,
            data.system_name,
        ),
        OneKomma5CheapestHourNowSensor(
            data.price_coordinator,
            system_id,
            data.system_name,
        ),
        OneKomma5SiteConnectivitySensor(
            data.system_status_coordinator,
            system_id,
            data.system_name,
        ),
    ]

    # Per-asset connectivity sensors — only register the asset types that the
    # cloud reports for this site. Avoids permanently "unavailable" sensors on
    # systems without e.g. a heat pump.
    status_data = data.system_status_coordinator.data
    observed_types: set[str] = (
        {a.type for a in status_data.assets} if status_data and status_data.assets else set()
    )
    for device_key, translation_key in ASSET_CONNECTIVITY_SENSORS:
        candidate_types = ASSET_TYPES_BY_DEVICE_KEY[device_key]
        matched_type = next((t for t in candidate_types if t in observed_types), None)
        if matched_type is not None:
            entities.append(
                OneKomma5AssetTypeConnectivitySensor(
                    data.system_status_coordinator,
                    system_id,
                    data.system_name,
                    matched_type,
                    translation_key,
                    device_key=device_key,
                    asset=assets_by_type.get(matched_type),
                    parent_device_id=data.system_device_id,
                )
            )

    entities.extend(
        OneKomma5OptimizationDecisionSensor(
            data.optimization_coordinator,
            system_id,
            data.system_name,
            spec,
            asset=resolve_asset(assets_by_type, spec.device_key),
            parent_device_id=data.system_device_id,
        )
        for spec in OPTIMIZATION_DECISION_SENSORS
    )

    # Per-feature binary sensors — one Boolean per known feature flag in the
    # SystemStatusCoordinator's active_features list. Lets automations gate
    # on `condition: state binary_sensor.<sys>_dynamic_tariff_active is on`
    # without having to parse the active_features attribute list manually.
    entities.extend(
        OneKomma5ActiveFeatureBinarySensor(
            data.system_status_coordinator,
            system_id,
            data.system_name,
            feature_name,
            translation_key,
        )
        for feature_name, translation_key in ACTIVE_FEATURE_BINARY_SENSORS
    )

    entities.extend(
        OneKomma5DetailsFlagSensor(
            data.system_status_coordinator,
            system_id,
            data.system_name,
            data.details,
            attr,
            translation_key,
            icon,
        )
        for attr, translation_key, icon in DETAILS_FLAG_SENSORS
    )

    apply_stable_entity_ids(entities, BINARY_SENSOR_DOMAIN)
    async_add_entities(entities)


class OneKomma5CheapElectricitySensor(
    QuarterHourUpdateMixin, OneKomma5PriceEntity, BinarySensorEntity
):
    """Binary sensor that is ON when the current electricity price is below the daily average."""

    _attr_translation_key = "cheap_electricity"

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, "cheap_electricity")

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update so the sensor reflects the active slot."""
        await super().async_added_to_hass()
        self._async_register_quarter_hour_update()

    @property
    def is_on(self) -> bool | None:
        """Return True when current price is below the daily average."""
        if self.coordinator.data is None:
            return None
        current = self._dynamic_current_price()
        average = self.coordinator.data.market_prices.average_price_all_in
        if current is None or average is None or average <= 0:
            return None
        return current < average

    @property
    def icon(self) -> str:
        """Return icon reflecting cheap/expensive state."""
        return "mdi:lightning-bolt" if self.is_on else "mdi:lightning-bolt-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose current price, average and their difference."""
        if self.coordinator.data is None:
            return None
        current = self._dynamic_current_price()
        average = self.coordinator.data.market_prices.average_price_all_in
        attrs: dict[str, Any] = {"current_price": current, "average_price": average}
        if current is not None and average is not None:
            attrs["difference"] = round(current - average, 6)
        return attrs


class OneKomma5CheapestHourNowSensor(
    QuarterHourUpdateMixin, OneKomma5PriceEntity, BinarySensorEntity
):
    """Binary sensor that is ON when the current 15-min slot is the cheapest in the next 24h."""

    _attr_translation_key = "cheapest_hour_now"

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, system_id, system_name, "cheapest_hour_now")

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update so the sensor reflects the active slot."""
        await super().async_added_to_hass()
        self._async_register_quarter_hour_update()

    def _min_forecast_price(self) -> float | None:
        """Return the minimum price in the upcoming 24h forecast."""
        if self.coordinator.data is None or not self.coordinator.data.forecast:
            return None
        prices = [s["price"] for s in self.coordinator.data.forecast]
        return min(prices) if prices else None

    @property
    def is_on(self) -> bool | None:
        """Return True if the current slot price equals the cheapest in the forecast."""
        current = self._dynamic_current_price()
        cheapest = self._min_forecast_price()
        if current is None or cheapest is None:
            return None
        # Use a small tolerance to handle float comparison
        return abs(current - cheapest) < 1e-9

    @property
    def icon(self) -> str:
        """Return icon reflecting state."""
        return "mdi:cash-clock" if self.is_on else "mdi:cash-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose current price, cheapest price and the cheapest slot start."""
        if self.coordinator.data is None:
            return None
        current = self._dynamic_current_price()
        forecast = self.coordinator.data.forecast
        if not forecast:
            return {"current_price": current}
        cheapest = min(forecast, key=lambda s: s["price"])
        return {
            "current_price": current,
            "cheapest_price": cheapest["price"],
            "cheapest_slot_start": cheapest["start"],
        }


@dataclass(frozen=True)
class OptimizationDecisionSpec:
    """Spec for one ``OneKomma5OptimizationDecisionSensor``.

    ``asset`` is the SDK optimization-event asset string ("BATTERY" / "HEATPUMP");
    ``decision`` is the exact decision-string that flips this sensor ON. ``key``
    doubles as translation key and unique_id suffix.
    """

    key: str
    asset: str
    decision: str
    device_key: str
    icon_on: str
    icon_off: str
    include_soc: bool = False


OPTIMIZATION_DECISION_SENSORS: tuple[OptimizationDecisionSpec, ...] = (
    OptimizationDecisionSpec(
        key="optimization_battery_grid_charge",
        asset="BATTERY",
        decision="BATTERY_CHARGE_FROM_GRID",
        device_key="inverter",
        icon_on="mdi:battery-arrow-up",
        icon_off="mdi:battery-arrow-up-outline",
        include_soc=True,
    ),
    OptimizationDecisionSpec(
        key="optimization_heat_pump_recommended",
        asset="HEATPUMP",
        decision="HEATPUMP_RECOMMEND_ON",
        device_key="heat_pump",
        icon_on="mdi:heat-pump",
        icon_off="mdi:heat-pump-outline",
    ),
)


class OneKomma5OptimizationDecisionSensor(
    QuarterHourUpdateMixin, OneKomma5OptimizationEntity, BinarySensorEntity
):
    """ON when the currently active optimization event for the configured
    asset (BATTERY / HEATPUMP) matches the configured decision string."""

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        spec: OptimizationDecisionSpec,
        *,
        asset: Any | None = None,
        parent_device_id: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            system_id,
            system_name,
            spec.key,
            device_key=spec.device_key,
            asset=asset,
            parent_device_id=parent_device_id,
        )
        self._spec = spec
        self._attr_translation_key = spec.key

    async def async_added_to_hass(self) -> None:
        """Register quarter-hour update so the sensor flips at slot ends."""
        await super().async_added_to_hass()
        self._async_register_quarter_hour_update()

    def _active_event(self) -> Any | None:
        if self.coordinator.data is None:
            return None
        return active_optimization_event(
            self.coordinator.data.events,
            asset=self._spec.asset,
            now=datetime.datetime.now(tz=datetime.UTC),
        )

    @property
    def is_on(self) -> bool | None:
        """Return True only when the configured decision is currently active."""
        if self.coordinator.data is None:
            return None
        event = self._active_event()
        if event is None:
            return False
        return event.decision == self._spec.decision

    @property
    def icon(self) -> str:
        """Return icon reflecting state."""
        return self._spec.icon_on if self.is_on else self._spec.icon_off

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the active decision details, if any."""
        event = self._active_event()
        if event is None:
            return None
        attrs: dict[str, Any] = {
            "decision": event.decision,
            "from": event.from_time,
            "to": event.to_time,
            "market_price": event.market_price,
        }
        if self._spec.include_soc:
            attrs["state_of_charge"] = event.state_of_charge
        return attrs


def _redact_asset(asset: Any) -> dict[str, Any]:
    """Strip asset attrs that may carry secrets (serial, IP, opaque id/name)."""
    return {
        "manufacturer": getattr(asset, "manufacturer", None),
        "model": getattr(asset, "model", None),
        "firmware": getattr(asset, "firmware", None),
        "connection_status": getattr(asset, "connection_status", None),
    }


class OneKomma5SiteConnectivitySensor(OneKomma5SystemStatusEntity, BinarySensorEntity):
    """Binary sensor reflecting whether the 1KOMMA5° cloud sees the site as CONNECTED."""

    _attr_translation_key = "site_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: Any, system_id: str, system_name: str) -> None:
        super().__init__(coordinator, system_id, system_name, "site_connected")

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None or self.coordinator.data.site_status is None:
            return None
        return self.coordinator.data.site_status == "CONNECTED"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        return {
            "site_status": self.coordinator.data.site_status,
            "asset_count": len(self.coordinator.data.assets),
        }


class OneKomma5AssetTypeConnectivitySensor(OneKomma5SystemStatusEntity, BinarySensorEntity):
    """Per-asset-type connectivity binary sensor.

    AND-logic: ``is_on`` is True only when **every** asset of the configured
    type reports ``connection_status == "CONNECTED"``. A single offline device
    flips the sensor OFF.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        asset_type: str,
        translation_key: str,
        *,
        device_key: str | None = None,
        asset: Any | None = None,
        parent_device_id: str | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            system_id,
            system_name,
            translation_key,
            device_key=device_key,
            asset=asset,
            parent_device_id=parent_device_id,
        )
        self._asset_type = asset_type
        self._attr_translation_key = translation_key

    def _assets(self) -> list[Any]:
        if self.coordinator.data is None:
            return []
        return [a for a in self.coordinator.data.assets if a.type == self._asset_type]

    @property
    def is_on(self) -> bool | None:
        assets = self._assets()
        if not assets:
            return None
        return all(a.connection_status == "CONNECTED" for a in assets)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        assets = self._assets()
        if not assets:
            return None
        return {
            "count": len(assets),
            "connected_count": sum(1 for a in assets if a.connection_status == "CONNECTED"),
            "assets": [_redact_asset(a) for a in assets],
        }


ASSET_CONNECTIVITY_SENSORS = (
    ("inverter", "inverter_connected"),
    ("heat_pump", "heat_pump_connected"),
    ("meter", "meter_connected"),
    ("wallbox", "wallbox_connected"),
)


class OneKomma5ActiveFeatureBinarySensor(OneKomma5SystemStatusEntity, BinarySensorEntity):
    """Binary sensor reflecting whether a specific feature flag is active.

    Splits the `aktive_funktionen` counter sensor (which exposes only a list
    via attributes) into a Boolean entity per feature, so automations can
    gate on `condition: state binary_sensor.X is on` without parsing
    attribute lists.
    """

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        feature_name: str,
        translation_key: str,
    ) -> None:
        super().__init__(coordinator, system_id, system_name, translation_key)
        self._feature_name = feature_name
        self._attr_translation_key = translation_key

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self._feature_name in self.coordinator.data.active_features


# (feature flag in the SDK, translation key in strings.json / locales)
ACTIVE_FEATURE_BINARY_SENSORS = (
    ("DYNAMIC_TARIFF", "dynamic_tariff_active"),
    ("TIME_OF_USE_OPTIMIZATION", "time_of_use_active"),
    ("SMART_CHARGING", "smart_charging_active"),
)


# (SystemDetails attribute, translation key, icon). Both flags surface as
# ``binary_sensor.<system>_<translation_key>``; key doubles as the unique_id
# suffix so registry entries stay stable.
DETAILS_FLAG_SENSORS: tuple[tuple[str, str, str], ...] = (
    ("energy_trader_active", "energy_trader_active", "mdi:transmission-tower"),
    ("dynamic_pulse_compatible", "dynamic_pulse_compatible", "mdi:flash"),
)


class OneKomma5DetailsFlagSensor(OneKomma5SystemStatusEntity, BinarySensorEntity):
    """Binary sensor exposing one Boolean attribute of ``SystemDetails``."""

    def __init__(
        self,
        coordinator: Any,
        system_id: str,
        system_name: str,
        details: Any | None,
        attr: str,
        translation_key: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator, system_id, system_name, translation_key)
        self._details = details
        self._details_attr = attr
        self._attr_translation_key = translation_key
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        if self._details is None:
            return None
        return getattr(self._details, self._details_attr, None)
