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


def get_current_price(prices: dict[str, float]) -> float | None:
    """Return the price for the active 15-minute slot.

    API timestamps represent the END of each 15-minute delivery slot, so the
    active slot is the one with the smallest end timestamp strictly after now.
    """
    if not prices:
        return None
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    best_value: float | None = None
    best_time: datetime.datetime | None = None

    for key, value in prices.items():
        try:
            slot_time = datetime.datetime.fromisoformat(key.replace("Z", "+00:00"))
            if slot_time.tzinfo is None:
                slot_time = slot_time.replace(tzinfo=datetime.timezone.utc)
            if slot_time > now and (best_time is None or slot_time < best_time):
                best_time = slot_time
                best_value = value
        except ValueError:
            _LOGGER.debug("Could not parse price timestamp: %s", key)

    return best_value


class OneKomma5LiveCoordinator(DataUpdateCoordinator[LiveData]):
    """Coordinator for live energy data, EV charger state, and EMS settings."""

    def __init__(self, hass: HomeAssistant, system: Any) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="1KOMMA5° Live",
            update_interval=datetime.timedelta(seconds=LIVE_UPDATE_INTERVAL_SECONDS),
        )
        self._system = system

    async def _async_update_data(self) -> LiveData:
        """Fetch data from the API."""
        try:
            from onekommafive.errors import ApiError

            live_overview, ev_chargers, ems_settings = await self.hass.async_add_executor_job(
                self._fetch_live_data
            )
            return LiveData(
                live_overview=live_overview,
                ev_chargers=ev_chargers,
                ems_settings=ems_settings,
            )
        except Exception as err:
            from onekommafive.errors import ApiError
            if isinstance(err, ApiError):
                raise UpdateFailed(f"API error fetching live data: {err}") from err
            raise UpdateFailed(f"Error fetching live data: {err}") from err

    def _fetch_live_data(self) -> tuple[Any, list[Any], Any]:
        """Fetch all live data synchronously."""
        live_overview = self._system.get_live_overview()
        ev_chargers = self._system.get_ev_chargers()
        try:
            ems_settings = self._system.get_ems_settings()
        except Exception:
            _LOGGER.debug("EMS settings not available (no DeviceGateway?), skipping")
            ems_settings = None
        return live_overview, ev_chargers, ems_settings


class OneKomma5PriceCoordinator(DataUpdateCoordinator[PriceData]):
    """Coordinator for electricity market price data."""

    def __init__(self, hass: HomeAssistant, system: Any) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="1KOMMA5° Prices",
            update_interval=datetime.timedelta(seconds=PRICE_UPDATE_INTERVAL_SECONDS),
        )
        self._system = system

    async def _async_update_data(self) -> PriceData:
        """Fetch market price data from the API."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_price_data)
        except Exception as err:
            from onekommafive.errors import ApiError
            if isinstance(err, ApiError):
                raise UpdateFailed(f"API error fetching price data: {err}") from err
            raise UpdateFailed(f"Error fetching price data: {err}") from err

    def _fetch_price_data(self) -> PriceData:
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
        forecast = self._build_forecast(all_in_prices, horizon_hours=30)

        # Price statistics: split by date
        today_str = now.strftime("%Y-%m-%d")
        tomorrow_str = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        today_prices = [v for k, v in all_in_prices.items() if today_str in k]
        tomorrow_prices_list = [v for k, v in all_in_prices.items() if tomorrow_str in k]

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

    def _build_forecast(
        self, prices: dict[str, float], horizon_hours: int = 24
    ) -> list[dict[str, Any]]:
        """Build a sorted forecast list compatible with the Tibber/ENTSO-E format.

        API timestamps represent the END of each 15-minute delivery slot.
        Only slots whose delivery period overlaps [now, now + horizon_hours]
        are included.

        Each entry contains:
          start  – ISO-8601 string (timezone-aware)
          end    – ISO-8601 string (= API timestamp)
          price  – all-in price in EUR/kWh
        """
        slot_duration = datetime.timedelta(minutes=15)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        cutoff = now + datetime.timedelta(hours=horizon_hours)
        slots: list[dict[str, Any]] = []

        for key, value in prices.items():
            try:
                end = datetime.datetime.fromisoformat(key.replace("Z", "+00:00"))
                if end.tzinfo is None:
                    end = end.replace(tzinfo=datetime.timezone.utc)
                start = end - slot_duration
                if end <= now or start >= cutoff:
                    continue
                slots.append(
                    {
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "price": round(value, 6),
                    }
                )
            except ValueError:
                _LOGGER.debug("Could not parse price timestamp for forecast: %s", key)

        slots.sort(key=lambda s: s["start"])
        return slots


@dataclass
class OptimizationData:
    """Container for optimization event data fetched from the API."""

    events: list[Any]  # list[OptimizationEvent]
    event_count: int
    total_cost: float | None
    energy_bought: float | None
    energy_sold: float | None
    last_event: Any | None  # OptimizationEvent or None


class OneKomma5OptimizationCoordinator(DataUpdateCoordinator[OptimizationData]):
    """Coordinator for AI optimization event data."""

    def __init__(self, hass: HomeAssistant, system: Any) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="1KOMMA5° Optimizations",
            update_interval=datetime.timedelta(seconds=OPTIMIZATION_UPDATE_INTERVAL_SECONDS),
        )
        self._system = system

    async def _async_update_data(self) -> OptimizationData:
        """Fetch optimization event data from the API."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_optimization_data)
        except Exception as err:
            from onekommafive.errors import ApiError

            if isinstance(err, ApiError):
                raise UpdateFailed(f"API error fetching optimization data: {err}") from err
            raise UpdateFailed(f"Error fetching optimization data: {err}") from err

    def _fetch_optimization_data(self) -> OptimizationData:
        """Fetch today's optimization events synchronously."""
        now = datetime.datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

        result = self._system.get_optimizations(today_start, today_end)
        events = result.events

        costs = [e.total_cost for e in events if e.total_cost is not None]
        bought = [e.energy_bought for e in events if e.energy_bought is not None]
        sold = [e.energy_sold for e in events if e.energy_sold is not None]

        last_event = None
        if events:
            last_event = max(events, key=lambda e: e.from_time or e.timestamp)

        return OptimizationData(
            events=events,
            event_count=len(events),
            total_cost=sum(costs) if costs else None,
            energy_bought=sum(bought) if bought else None,
            energy_sold=sum(sold) if sold else None,
            last_event=last_event,
        )

