"""DataUpdateCoordinator for the 1KOMMA5° integration."""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    LIVE_UPDATE_INTERVAL_SECONDS,
    OPTIMIZATION_UPDATE_INTERVAL_SECONDS,
    PRICE_UPDATE_INTERVAL_SECONDS,
)
from .helpers import (
    aggregate_optimization_events,
    build_forecast,
    get_current_price,
    split_prices_by_date,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class LiveData:
    """Container for live data fetched from the API."""

    live_overview: Any  # onekommafive.models.LiveOverview
    ev_chargers: list[Any]  # list[onekommafive.ev_charger.EVCharger]
    ems_settings: Any  # onekommafive.models.EmsSettings


@dataclass
class PriceData:
    """Container for market price data fetched from the API."""

    market_prices: Any  # onekommafive.models.MarketPrices
    current_price: float | None
    current_price_with_grid_costs: float | None
    forecast: list[dict[str, Any]]  # sorted list of {start, end, price} dicts
    all_in_prices: dict[str, float] = None  # full price dict for dynamic lookups
    grid_prices: dict[str, float] = None  # full grid-cost price dict
    negative_price_slots_today: int = 0
    negative_price_slots_tomorrow: int | None = None
    tomorrow_average_price: float | None = None
    tomorrow_lowest_price: float | None = None
    tomorrow_highest_price: float | None = None


@dataclass
class OptimizationData:
    """Container for optimization event data fetched from the API."""

    events: list[Any]  # list[OptimizationEvent]
    event_count: int
    total_cost: float | None
    energy_bought: float | None
    energy_sold: float | None
    last_event: Any | None  # OptimizationEvent or None


class OneKomma5BaseCoordinator[T](DataUpdateCoordinator[T]):
    """Base coordinator handling executor dispatch and error wrapping.

    Subclasses provide:
    - the constructor's ``name`` and ``interval_seconds``
    - ``_data_label`` (used in UpdateFailed messages)
    - ``_fetch()`` returning the typed data container
    """

    _data_label: str = "data"

    def __init__(
        self,
        hass: HomeAssistant,
        system: Any,
        *,
        name: str,
        interval_seconds: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=datetime.timedelta(seconds=interval_seconds),
        )
        self._system = system

    async def _async_update_data(self) -> T:
        """Fetch data via the executor, wrapping errors as UpdateFailed."""
        try:
            return await self.hass.async_add_executor_job(self._fetch)
        except Exception as err:
            from onekommafive.errors import ApiError

            if isinstance(err, ApiError):
                raise UpdateFailed(
                    f"API error fetching {self._data_label}: {err}"
                ) from err
            raise UpdateFailed(f"Error fetching {self._data_label}: {err}") from err

    def _fetch(self) -> T:
        """Synchronous fetch implementation. Override in subclasses."""
        raise NotImplementedError


class OneKomma5LiveCoordinator(OneKomma5BaseCoordinator[LiveData]):
    """Coordinator for live energy data, EV charger state, and EMS settings."""

    _data_label = "live data"

    def __init__(self, hass: HomeAssistant, system: Any) -> None:
        super().__init__(
            hass, system,
            name="1KOMMA5° Live",
            interval_seconds=LIVE_UPDATE_INTERVAL_SECONDS,
        )

    def _fetch(self) -> LiveData:
        """Fetch all live data synchronously."""
        live_overview = self._system.get_live_overview()
        ev_chargers = self._system.get_ev_chargers()
        try:
            ems_settings = self._system.get_ems_settings()
        except Exception:
            _LOGGER.debug("EMS settings not available (no DeviceGateway?), skipping")
            ems_settings = None
        return LiveData(
            live_overview=live_overview,
            ev_chargers=ev_chargers,
            ems_settings=ems_settings,
        )


class OneKomma5PriceCoordinator(OneKomma5BaseCoordinator[PriceData]):
    """Coordinator for electricity market price data."""

    _data_label = "price data"

    def __init__(self, hass: HomeAssistant, system: Any) -> None:
        super().__init__(
            hass, system,
            name="1KOMMA5° Prices",
            interval_seconds=PRICE_UPDATE_INTERVAL_SECONDS,
        )

    def _fetch(self) -> PriceData:
        """Fetch price data synchronously.

        Always fetches today and tomorrow so the forecast covers up to 30 hours
        (e.g. 16:00 today → 23:59 tomorrow).  Tomorrow's prices may not yet be
        available early in the day — the second API call is silently skipped in
        that case.
        """
        now = datetime.datetime.now()
        window_end = now + datetime.timedelta(hours=24)

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

        market_prices = self._system.get_prices(today_start, today_end, resolution="15m")
        all_in_prices: dict[str, float] = dict(market_prices.prices_with_grid_costs_and_vat)
        grid_prices: dict[str, float] = dict(market_prices.prices_with_grid_costs)

        # Always try to fetch tomorrow's prices to maximise the forecast horizon
        if window_end.date() > now.date():
            tomorrow_start = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            tomorrow_end = tomorrow_start.replace(hour=23, minute=59, second=59)
            try:
                tomorrow_prices = self._system.get_prices(
                    tomorrow_start, tomorrow_end, resolution="15m"
                )
                all_in_prices.update(tomorrow_prices.prices_with_grid_costs_and_vat)
                grid_prices.update(tomorrow_prices.prices_with_grid_costs)
            except Exception:
                _LOGGER.debug("Tomorrow's prices not yet available")

        current_price = get_current_price(all_in_prices)
        current_price_with_grid_costs = get_current_price(grid_prices)
        forecast = build_forecast(all_in_prices, horizon_hours=30)

        # Price statistics: split by date
        today_prices, tomorrow_prices_list = split_prices_by_date(
            all_in_prices, now.date(), now.date() + datetime.timedelta(days=1)
        )

        negative_price_slots_today = sum(1 for p in today_prices if p < 0)

        tomorrow_average = None
        tomorrow_lowest = None
        tomorrow_highest = None
        negative_slots_tomorrow: int | None = None
        if tomorrow_prices_list:
            tomorrow_average = sum(tomorrow_prices_list) / len(tomorrow_prices_list)
            tomorrow_lowest = min(tomorrow_prices_list)
            tomorrow_highest = max(tomorrow_prices_list)
            negative_slots_tomorrow = sum(1 for p in tomorrow_prices_list if p < 0)

        return PriceData(
            market_prices=market_prices,
            current_price=current_price,
            current_price_with_grid_costs=current_price_with_grid_costs,
            forecast=forecast,
            all_in_prices=all_in_prices,
            grid_prices=grid_prices,
            negative_price_slots_today=negative_price_slots_today,
            negative_price_slots_tomorrow=negative_slots_tomorrow,
            tomorrow_average_price=tomorrow_average,
            tomorrow_lowest_price=tomorrow_lowest,
            tomorrow_highest_price=tomorrow_highest,
        )


class OneKomma5OptimizationCoordinator(OneKomma5BaseCoordinator[OptimizationData]):
    """Coordinator for AI optimization event data."""

    _data_label = "optimization data"

    def __init__(self, hass: HomeAssistant, system: Any) -> None:
        super().__init__(
            hass, system,
            name="1KOMMA5° Optimizations",
            interval_seconds=OPTIMIZATION_UPDATE_INTERVAL_SECONDS,
        )

    def _fetch(self) -> OptimizationData:
        """Fetch today's optimization events synchronously."""
        now = datetime.datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

        result = self._system.get_optimizations(today_start, today_end)
        agg = aggregate_optimization_events(result.events)
        return OptimizationData(events=result.events, **agg)
