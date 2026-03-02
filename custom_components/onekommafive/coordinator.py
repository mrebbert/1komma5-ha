"""DataUpdateCoordinator for the 1KOMMA5° integration."""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import LIVE_UPDATE_INTERVAL_SECONDS, PRICE_UPDATE_INTERVAL_SECONDS

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
        ems_settings = self._system.get_ems_settings()
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

        current_price = self._get_current_price(all_in_prices)
        current_price_with_grid_costs = self._get_current_price(grid_prices)
        forecast = self._build_forecast(all_in_prices, horizon_hours=30)

        return PriceData(
            market_prices=market_prices,
            current_price=current_price,
            current_price_with_grid_costs=current_price_with_grid_costs,
            forecast=forecast,
        )

    def _build_forecast(
        self, prices: dict[str, float], horizon_hours: int = 24
    ) -> list[dict[str, Any]]:
        """Build a sorted forecast list compatible with the Tibber/ENTSO-E format.

        Only slots within [now, now + horizon_hours] are included.

        Each entry contains:
          start  – ISO-8601 string (timezone-aware)
          end    – ISO-8601 string (start + slot duration)
          price  – all-in price in EUR/kWh
        """
        slot_duration = datetime.timedelta(minutes=15)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        cutoff = now + datetime.timedelta(hours=horizon_hours)
        slots: list[dict[str, Any]] = []

        for key, value in prices.items():
            try:
                start = datetime.datetime.fromisoformat(key.replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=datetime.timezone.utc)
                if start < now or start >= cutoff:
                    continue
                slots.append(
                    {
                        "start": start.isoformat(),
                        "end": (start + slot_duration).isoformat(),
                        "price": round(value, 6),
                    }
                )
            except ValueError:
                _LOGGER.debug("Could not parse price timestamp for forecast: %s", key)

        slots.sort(key=lambda s: s["start"])
        return slots

    def _get_current_price(self, prices: dict[str, float]) -> float | None:
        """Return the price for the active 15-minute slot (latest start ≤ now).

        The API provides 15-minute resolution data, so we pick the slot whose
        start timestamp is the most recent one at or before the current time.
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
                if slot_time <= now and (best_time is None or slot_time > best_time):
                    best_time = slot_time
                    best_value = value
            except ValueError:
                _LOGGER.debug("Could not parse price timestamp: %s", key)

        return best_value
