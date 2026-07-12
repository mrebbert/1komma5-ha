"""DataUpdateCoordinator for the 1KOMMA5° integration."""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ENERGY_UPDATE_INTERVAL_SECONDS,
    EVENT_NEGATIVE_PRICE_ENDED,
    EVENT_NEGATIVE_PRICE_STARTED,
    EVENT_OPTIMIZATION_DECISION,
    LIVE_UPDATE_INTERVAL_SECONDS,
    OPTIMIZATION_UPDATE_INTERVAL_SECONDS,
    PRICE_UPDATE_INTERVAL_SECONDS,
    SYSTEM_STATUS_UPDATE_INTERVAL_SECONDS,
    WEATHER_UPDATE_INTERVAL_SECONDS,
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
class WeatherData:
    """Container for weather data fetched from the API."""

    weather: Any  # onekommafive.models.WeatherData


@dataclass
class EnergyTodayData:
    """Container for today's aggregated energy data fetched from the API."""

    energy: Any  # onekommafive.models.EnergyData (daily running totals, reset at midnight)


@dataclass
class SystemStatusData:
    """Container for site status + asset inventory + active feature flags."""

    site_status: str | None  # "CONNECTED" / "DISCONNECTED" / None
    assets: list[Any]  # list[onekommafive.models.sites.Asset]
    active_features: list[str]  # [] when customer_id unknown or fetch failed
    assets_by_type: dict[str, Any]  # {asset.type: Asset} — first wins on duplicates


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

    Subclasses configure themselves declaratively via class vars:
    - ``_coordinator_name`` — DataUpdateCoordinator's ``name``
    - ``_interval_seconds`` — refresh interval in seconds
    - ``_data_label`` — used in UpdateFailed messages
    - ``_fetch()`` — sync fetch returning the typed data container
    """

    _data_label: str = "data"
    _coordinator_name: str = "1KOMMA5°"
    _interval_seconds: int = 60

    def __init__(self, hass: HomeAssistant, system: Any) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=self._coordinator_name,
            update_interval=datetime.timedelta(seconds=self._interval_seconds),
        )
        self._system = system

    async def _async_update_data(self) -> T:
        """Fetch data via the executor, wrapping errors as UpdateFailed."""
        try:
            return await self.hass.async_add_executor_job(self._fetch)
        except Exception as err:
            from onekommafive.errors import ApiError

            if isinstance(err, ApiError):
                raise UpdateFailed(f"API error fetching {self._data_label}: {err}") from err
            raise UpdateFailed(f"Error fetching {self._data_label}: {err}") from err

    def _fetch(self) -> T:
        """Synchronous fetch implementation. Override in subclasses."""
        raise NotImplementedError


class OneKomma5LiveCoordinator(OneKomma5BaseCoordinator[LiveData]):
    """Coordinator for live energy data, EV charger state, and EMS settings."""

    _data_label = "live data"
    _coordinator_name = "1KOMMA5° Live"
    _interval_seconds = LIVE_UPDATE_INTERVAL_SECONDS

    # Number of consecutive None ems_settings results before the repair issue
    # fires. 5 × 30 s = 2.5 min — fast enough to be useful, slow enough to
    # avoid noise from transient API blips.
    _EMS_FAILURE_THRESHOLD = 5
    _EMS_ISSUE_ID = "ems_settings_unavailable"

    def __init__(self, hass: HomeAssistant, system: Any) -> None:
        super().__init__(hass, system)
        self._ems_failure_count = 0
        self._ems_issue_active = False

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

    async def _async_update_data(self) -> LiveData:
        """Wrap the base fetch with EMS-availability tracking for the repair issue."""
        data = await super()._async_update_data()
        self._update_ems_repair_issue(data.ems_settings is not None)
        return data

    def _update_ems_repair_issue(self, ems_available: bool) -> None:
        """Track consecutive EMS failures and create / delete the repair issue."""
        from homeassistant.helpers import issue_registry as ir

        from .const import DOMAIN

        if ems_available:
            self._ems_failure_count = 0
            if self._ems_issue_active:
                ir.async_delete_issue(self.hass, DOMAIN, self._EMS_ISSUE_ID)
                self._ems_issue_active = False
            return
        self._ems_failure_count += 1
        if self._ems_failure_count >= self._EMS_FAILURE_THRESHOLD and not self._ems_issue_active:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._EMS_ISSUE_ID,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=self._EMS_ISSUE_ID,
            )
            self._ems_issue_active = True


class OneKomma5PriceCoordinator(OneKomma5BaseCoordinator[PriceData]):
    """Coordinator for electricity market price data."""

    _data_label = "price data"
    _coordinator_name = "1KOMMA5° Prices"
    _interval_seconds = PRICE_UPDATE_INTERVAL_SECONDS

    # None on the first refresh primes the tracker without firing an event.
    _last_active_was_negative: bool | None = None

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

    async def _async_update_data(self) -> PriceData:
        """Fetch + fire HA bus events for negative-price edge transitions."""
        data = await super()._async_update_data()
        self._fire_negative_price_edge_events(data)
        return data

    def _fire_negative_price_edge_events(self, data: PriceData) -> None:
        """Fire negative-price edge events. Granularity = coordinator refresh interval."""
        if data.current_price is None:
            return
        is_negative_now = data.current_price <= 0
        previous = self._last_active_was_negative
        self._last_active_was_negative = is_negative_now

        if previous is None or previous == is_negative_now:
            return

        payload = {
            "system_id": self._system.id(),
            "price": data.current_price,
            "negative_price_slots_remaining": data.negative_price_slots_today,
        }
        event_type = EVENT_NEGATIVE_PRICE_STARTED if is_negative_now else EVENT_NEGATIVE_PRICE_ENDED
        _LOGGER.debug("Firing %s: %s", event_type, payload)
        self.hass.bus.async_fire(event_type, payload)


class OneKomma5OptimizationCoordinator(OneKomma5BaseCoordinator[OptimizationData]):
    """Coordinator for AI optimization event data."""

    _data_label = "optimization data"
    _coordinator_name = "1KOMMA5° Optimizations"
    _interval_seconds = OPTIMIZATION_UPDATE_INTERVAL_SECONDS

    # Highest from_time we have already fired an event for. None on first
    # run — we initialise from the first fetch without firing to avoid
    # spamming N events at startup.
    _last_fired_from_time: str | None = None

    def _fetch(self) -> OptimizationData:
        """Fetch today's optimization events synchronously."""
        now = datetime.datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

        result = self._system.get_optimizations(today_start, today_end)
        agg = aggregate_optimization_events(result.events)
        return OptimizationData(events=result.events, **agg)

    async def _async_update_data(self) -> OptimizationData:
        """Fetch + fire HA bus events for newly observed decisions."""
        data = await super()._async_update_data()
        self._fire_new_decision_events(data.events)
        return data

    def _fire_new_decision_events(self, events: list[Any]) -> None:
        """Fire onekommafive_optimization_decision for each event newer than the last seen.

        On the very first refresh after Home Assistant starts, only the most
        recent decision is fired (so the user gets immediate confirmation the
        wiring works without replaying every event from earlier in the day).
        Subsequent refreshes fire one event per new decision.
        """
        if not events:
            _LOGGER.debug("No optimization events from API; nothing to fire")
            return

        sorted_events = sorted(events, key=lambda e: e.from_time or e.timestamp)
        latest_from_time = sorted_events[-1].from_time or sorted_events[-1].timestamp

        if self._last_fired_from_time is None:
            events_to_fire = [sorted_events[-1]]
            _LOGGER.debug(
                "First refresh — firing 1 event for the latest decision (from_time=%s)",
                latest_from_time,
            )
        else:
            events_to_fire = [
                e
                for e in sorted_events
                if (e.from_time or e.timestamp) > self._last_fired_from_time
            ]
            _LOGGER.debug(
                "Refresh — %d/%d events newer than last_fired_from_time=%s will fire",
                len(events_to_fire),
                len(sorted_events),
                self._last_fired_from_time,
            )

        for event in events_to_fire:
            payload = {
                "system_id": self._system.id(),
                "asset": event.asset,
                "decision": event.decision,
                "from": event.from_time,
                "to": event.to_time,
                "market_price": event.market_price,
                "market_price_currency": event.market_price_currency,
                "state_of_charge": event.state_of_charge,
            }
            _LOGGER.debug("Firing %s: %s", EVENT_OPTIMIZATION_DECISION, payload)
            self.hass.bus.async_fire(EVENT_OPTIMIZATION_DECISION, payload)

        self._last_fired_from_time = latest_from_time


class OneKomma5WeatherCoordinator(OneKomma5BaseCoordinator[WeatherData]):
    """Coordinator for weather forecast data."""

    _data_label = "weather data"
    _coordinator_name = "1KOMMA5° Weather"
    _interval_seconds = WEATHER_UPDATE_INTERVAL_SECONDS

    def _fetch(self) -> WeatherData:
        """Fetch weather data synchronously."""
        return WeatherData(weather=self._system.get_weather())


class OneKomma5EnergyCoordinator(OneKomma5BaseCoordinator[EnergyTodayData]):
    """Coordinator for today's aggregated energy data (incl. cloud savings)."""

    _data_label = "energy data"
    _coordinator_name = "1KOMMA5° Energy"
    _interval_seconds = ENERGY_UPDATE_INTERVAL_SECONDS

    def _fetch(self) -> EnergyTodayData:
        """Fetch today's energy aggregation synchronously."""
        return EnergyTodayData(energy=self._system.get_energy_today())


class OneKomma5SystemStatusCoordinator(OneKomma5BaseCoordinator[SystemStatusData]):
    """Coordinator for site connectivity, asset inventory and active features.

    Combines two endpoints in one refresh:

    - ``get_status_and_assets()`` provides the site connectivity state and the
      list of devices known to the 1KOMMA5° cloud, each with their own
      ``connection_status``.
    - ``get_active_features(customer_id)`` returns the customer's enabled
      feature flags (``DYNAMIC_TARIFF``, ``SMART_CHARGING``, ...). The
      customer_id is captured once at setup from ``get_details()`` — if that
      failed (None passed in) we skip the features call and return an empty
      list rather than failing the whole refresh.
    """

    _data_label = "system status data"
    _coordinator_name = "1KOMMA5° System Status"
    _interval_seconds = SYSTEM_STATUS_UPDATE_INTERVAL_SECONDS

    def __init__(self, hass: HomeAssistant, system: Any, customer_id: str | None) -> None:
        super().__init__(hass, system)
        self._customer_id = customer_id

    def _fetch(self) -> SystemStatusData:
        site = self._system.get_status_and_assets()
        features: list[str] = []
        if self._customer_id:
            try:
                features = list(self._system.get_active_features(self._customer_id))
            except Exception as err:
                _LOGGER.debug("Active features fetch failed: %s", err)
        assets = list(site.assets or [])
        assets_by_type: dict[str, Any] = {}
        for asset in assets:
            asset_type = getattr(asset, "type", None)
            if not asset_type:
                continue
            if asset_type in assets_by_type:
                _LOGGER.warning(
                    "Duplicate asset of type %s; keeping first, dropping subsequent",
                    asset_type,
                )
                continue
            assets_by_type[asset_type] = asset
        return SystemStatusData(
            site_status=site.status,
            assets=assets,
            active_features=features,
            assets_by_type=assets_by_type,
        )
