"""Sensor entity descriptions for the 1KOMMA5° integration.

Pure data: dataclass descriptions for each sensor category. The actual
SENSORS tuples and entity classes live in ``sensor.py`` and
``sensor_entities.py`` respectively.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntityDescription

from .coordinator import LiveData, OptimizationData, PriceData


@dataclass(frozen=True, kw_only=True)
class OneKomma5SensorDescription(SensorEntityDescription):
    """Sensor entity description with value accessor."""

    value_fn: Callable[[LiveData], Any]


@dataclass(frozen=True, kw_only=True)
class OneKomma5PriceSensorDescription(SensorEntityDescription):
    """Price sensor entity description with value accessor."""

    value_fn: Callable[[PriceData], Any]


@dataclass(frozen=True, kw_only=True)
class OneKomma5EVSensorDescription(SensorEntityDescription):
    """EV sensor entity description with value accessor."""

    value_fn: Callable[[Any], Any]  # Any = EVCharger


@dataclass(frozen=True, kw_only=True)
class OneKomma5OptimizationSensorDescription(SensorEntityDescription):
    """Optimization sensor entity description with value accessor."""

    value_fn: Callable[[OptimizationData], Any]
    attr_fn: Callable[[OptimizationData], dict[str, Any] | None] = lambda _: None
