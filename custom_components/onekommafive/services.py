"""Services for the 1KOMMA5° integration."""

from __future__ import annotations

import asyncio
import datetime
import logging
from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant.components.recorder import get_instance as get_recorder_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    ALL_STATISTIC_KEYS,
    BACKFILL_THROTTLE_SECONDS,
    CONF_FEED_IN_TARIFF,
    CONSUMPTION_TOTAL_KEY,
    COST_HISTORY_KEYS,
    DEFAULT_FEED_IN_TARIFF,
    DOMAIN,
    EMPTY_DAY_LIMIT,
    ENERGY_HISTORY_FIELD_MAP,
    FEED_IN_REVENUE_KEY,
    HARD_CEILING_DAYS,
    SOC_STATISTIC_KEY,
)
from .helpers import (
    accumulate_to_stats,
    consumer_cost_deltas,
    energy_buckets_to_kwh_deltas,
    extract_hourly_prices,
    feed_in_revenue_deltas,
    find_cheapest_window,
    find_most_expensive_window,
    soc_buckets_to_measurement_stats,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_GET_CHEAPEST_WINDOW = "get_cheapest_window"
SERVICE_GET_MOST_EXPENSIVE_WINDOW = "get_most_expensive_window"
SERVICE_IMPORT_HISTORY = "import_history"
SERVICE_CLEAR_HISTORY = "clear_history"

WINDOW_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=15, max=1800)),
        vol.Optional("earliest_start"): cv.datetime,
        vol.Optional("latest_end"): cv.datetime,
        vol.Optional("config_entry_id"): cv.string,
    }
)


IMPORT_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Optional("days_back"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=HARD_CEILING_DAYS)
        ),
        vol.Optional("config_entry_id"): cv.string,
    }
)

CLEAR_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Required("confirm"): cv.boolean,
        vol.Optional("config_entry_id"): cv.string,
    }
)


def _ensure_aware(dt: datetime.datetime) -> datetime.datetime:
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.UTC)
    return dt


def _resolve_entry(hass: HomeAssistant, call: ServiceCall) -> Any:
    """Resolve the config entry from the call's optional ``config_entry_id``.

    Raises ``HomeAssistantError`` if no integration is configured, the given
    id is unknown, or multiple entries exist without a disambiguating id.
    """
    config_entry_id = call.data.get("config_entry_id")
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("No 1KOMMA5° integration configured")

    if config_entry_id is not None:
        entry = next((e for e in entries if e.entry_id == config_entry_id), None)
        if entry is None:
            raise HomeAssistantError(f"Config entry '{config_entry_id}' not found")
        return entry
    if len(entries) == 1:
        return entries[0]
    raise HomeAssistantError("Multiple 1KOMMA5° entries configured — specify config_entry_id")


def _resolve_window_inputs(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[list[dict[str, Any]], int, datetime.datetime | None, datetime.datetime | None]:
    """Resolve service call inputs into forecast + constraints.

    Returns ``(forecast, slot_count, earliest_start, latest_end)`` or raises
    ``HomeAssistantError`` for any user-facing validation failure.
    """
    duration_minutes: int = call.data["duration_minutes"]
    slot_count_needed = duration_minutes // 15
    if slot_count_needed < 1:
        raise HomeAssistantError("duration_minutes must be at least 15")

    earliest_start = call.data.get("earliest_start")
    latest_end = call.data.get("latest_end")
    if earliest_start is not None:
        earliest_start = _ensure_aware(earliest_start)
    if latest_end is not None:
        latest_end = _ensure_aware(latest_end)

    entry = _resolve_entry(hass, call)
    coordinator = entry.runtime_data.price_coordinator
    if coordinator.data is None or not coordinator.data.forecast:
        raise HomeAssistantError("No price forecast available yet")

    forecast = coordinator.data.forecast
    if len(forecast) < slot_count_needed:
        raise HomeAssistantError(f"Forecast covers {len(forecast)} slots, need {slot_count_needed}")

    return forecast, slot_count_needed, earliest_start, latest_end


def _empty_window_response() -> dict[str, Any]:
    return {
        "found": False,
        "start": None,
        "end": None,
        "average_price": None,
        "slot_count": 0,
    }


def _statistic_id_for(hass: HomeAssistant, entry: Any, sensor_key: str) -> str | None:
    """Look up the entity_id (= statistic_id for own-entity stats).

    Entity IDs are slugified from the user-facing name in the user's HA
    language; we can't reconstruct them — we resolve via the entity registry
    by our deterministic unique_id pattern ``{system_id}_{sensor_key}``.

    Returns ``None`` if the entity isn't registered yet (integration installed
    but never loaded).
    """
    registry = er.async_get(hass)
    system_id = entry.data["system_id"]
    return registry.async_get_entity_id("sensor", DOMAIN, f"{system_id}_{sensor_key}")


async def _fetch_hourly_prices(
    hass: HomeAssistant,
    system: Any,
    start: datetime.date,
    end: datetime.date,
) -> dict[datetime.datetime, float]:
    """Fetch hourly market prices for ``[start, end)`` in 30-day chunks.

    Failures on individual chunks are logged at warning level and the chunk's
    hours are simply omitted — cost-stat writes will skip those hours instead
    of substituting zero (which would silently understate costs).
    """
    prices: dict[datetime.datetime, float] = {}
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + datetime.timedelta(days=30), end)
        chunk_start_dt = datetime.datetime.combine(
            chunk_start, datetime.time.min, tzinfo=datetime.UTC
        )
        chunk_end_dt = datetime.datetime.combine(chunk_end, datetime.time.min, tzinfo=datetime.UTC)
        try:
            market = await hass.async_add_executor_job(
                system.get_prices, chunk_start_dt, chunk_end_dt, "1h"
            )
        except Exception as err:
            _LOGGER.warning("Price fetch failed for %s..%s: %s", chunk_start, chunk_end, err)
            chunk_start = chunk_end
            continue
        prices.update(extract_hourly_prices(market))
        chunk_start = chunk_end
        await asyncio.sleep(BACKFILL_THROTTLE_SECONDS)
    return prices


async def _handle_import_history(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Walk the energy-historical API backwards, write Long-Term Statistics.

    Walk strategy depends on whether `days_back` was passed:
    - bounded: fixed range `[today - days_back, today)`, all errors counted
      in `failed_days`, no early stop.
    - unbounded: walk until ``EMPTY_DAY_LIMIT`` consecutive empty days, hard
      ceiling at ``HARD_CEILING_DAYS``.

    See the plan file `enchanted-jumping-teacup.md` for the full design.
    """
    from onekommafive.errors import RequestError

    entry = _resolve_entry(hass, call)
    data = entry.runtime_data
    today = dt_util.utcnow().date()
    bounded = "days_back" in call.data
    fixed_start = today - datetime.timedelta(days=call.data["days_back"]) if bounded else None
    floor = today - datetime.timedelta(days=HARD_CEILING_DAYS)

    deltas_by_sensor: dict[str, list[tuple[datetime.datetime, float]]] = {}
    for key in ENERGY_HISTORY_FIELD_MAP.values():
        deltas_by_sensor[key] = []
    deltas_by_sensor[CONSUMPTION_TOTAL_KEY] = []
    soc_measurements: list[tuple[datetime.datetime, float]] = []
    failed_days: list[datetime.date] = []
    # Collected raw energy responses keyed by day — used in the second pass to
    # compute monetary stats once prices are fetched.
    energy_by_day: dict[datetime.date, Any] = {}
    consecutive_empty = 0
    walked = 0

    tag = today - datetime.timedelta(days=1)
    while tag >= floor:
        if bounded and tag < fixed_start:
            break
        try:
            energy = await hass.async_add_executor_job(
                data.system.get_energy_historical,
                tag,
                tag + datetime.timedelta(days=1),
                "1h",
            )
        except RequestError as err:
            _LOGGER.debug("Energy fetch 4xx for %s: %s", tag, err)
            if not bounded:
                consecutive_empty += 1
                if consecutive_empty >= EMPTY_DAY_LIMIT:
                    _LOGGER.info(
                        "Walk-back: %d empty days in a row, stopping at %s",
                        EMPTY_DAY_LIMIT,
                        tag,
                    )
                    break
            else:
                failed_days.append(tag)
            tag -= datetime.timedelta(days=1)
            continue
        except Exception as err:
            _LOGGER.warning("Energy fetch failed for %s: %s", tag, err)
            failed_days.append(tag)
            tag -= datetime.timedelta(days=1)
            continue

        if not energy.timeseries:
            consecutive_empty += 1
            if not bounded and consecutive_empty >= EMPTY_DAY_LIMIT:
                _LOGGER.info(
                    "Walk-back: %d empty days in a row, stopping at %s",
                    EMPTY_DAY_LIMIT,
                    tag,
                )
                break
            tag -= datetime.timedelta(days=1)
            continue
        consecutive_empty = 0
        energy_by_day[tag] = energy

        # Per-sensor extraction
        for field, sensor_key in ENERGY_HISTORY_FIELD_MAP.items():
            deltas_by_sensor[sensor_key].extend(
                energy_buckets_to_kwh_deltas(energy.timeseries, field)
            )
        # Derived consumption_power_energy: sum(household + heatPump + ev + ac)
        consumption_deltas: dict[datetime.datetime, float] = {}
        for field in (
            "consumption_household_total",
            "consumption_heat_pump_total",
            "consumption_ev_total",
            "consumption_ac_total",
        ):
            for start, value in energy_buckets_to_kwh_deltas(energy.timeseries, field):
                consumption_deltas[start] = consumption_deltas.get(start, 0.0) + value
        deltas_by_sensor[CONSUMPTION_TOTAL_KEY].extend(consumption_deltas.items())

        soc_measurements.extend(soc_buckets_to_measurement_stats(energy.timeseries))
        walked += 1
        await asyncio.sleep(BACKFILL_THROTTLE_SECONDS)
        if walked % 10 == 0:
            _LOGGER.info("Backfill progress: %d days, currently at %s", walked, tag)
        tag -= datetime.timedelta(days=1)

    # Write stats. Sum-based first, then measurement-based SoC.
    written = 0
    for sensor_key, deltas in deltas_by_sensor.items():
        if not deltas:
            continue
        statistic_id = _statistic_id_for(hass, entry, sensor_key)
        if statistic_id is None:
            _LOGGER.warning(
                "Skipping %s — entity not registered yet (reload the integration)",
                sensor_key,
            )
            continue
        last = await get_instance_executor(
            hass, get_last_statistics, hass, 1, statistic_id, True, {"start", "sum"}
        )
        anchor_sum = 0.0
        oldest_existing: datetime.datetime | None = None
        if last and statistic_id in last and last[statistic_id]:
            row = last[statistic_id][0]
            anchor_sum = float(row.get("sum") or 0.0)
            start_ts = row.get("start")
            if start_ts is not None:
                oldest_existing = datetime.datetime.fromtimestamp(start_ts, tz=datetime.UTC)
        stats = accumulate_to_stats(deltas, anchor_sum, end_before=oldest_existing)
        if not stats:
            continue
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=None,
            source="recorder",
            statistic_id=statistic_id,
            unit_of_measurement="kWh",
        )
        typed_stats: list[StatisticData] = [
            StatisticData(start=s["start"], sum=s["sum"]) for s in stats
        ]
        async_import_statistics(hass, metadata, typed_stats)
        written += len(typed_stats)

    # Monetary stats: fetch prices for the walked range, compute cost+revenue
    # deltas, write the 6 monetary sensors. Skipped when no energy days were
    # successfully fetched (no range to back-fill).
    if energy_by_day:
        oldest_day = min(energy_by_day)
        newest_day = max(energy_by_day)
        prices_by_hour = await _fetch_hourly_prices(
            hass, data.system, oldest_day, newest_day + datetime.timedelta(days=1)
        )
        feed_in_tariff = entry.options.get(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)

        cost_deltas: dict[str, list[tuple[datetime.datetime, float]]] = {
            key: [] for key in COST_HISTORY_KEYS
        }
        revenue_deltas: list[tuple[datetime.datetime, float]] = []
        for energy in energy_by_day.values():
            for k, v in consumer_cost_deltas(energy.timeseries, prices_by_hour).items():
                cost_deltas[k].extend(v)
            revenue_deltas.extend(feed_in_revenue_deltas(energy.timeseries, feed_in_tariff))

        monetary_deltas = {**cost_deltas, FEED_IN_REVENUE_KEY: revenue_deltas}
        for sensor_key, deltas in monetary_deltas.items():
            if not deltas:
                continue
            statistic_id = _statistic_id_for(hass, entry, sensor_key)
            if statistic_id is None:
                _LOGGER.warning(
                    "Skipping %s — entity not registered yet (reload the integration)",
                    sensor_key,
                )
                continue
            last = await get_instance_executor(
                hass, get_last_statistics, hass, 1, statistic_id, True, {"start", "sum"}
            )
            anchor_sum = 0.0
            oldest_existing = None
            if last and statistic_id in last and last[statistic_id]:
                row = last[statistic_id][0]
                anchor_sum = float(row.get("sum") or 0.0)
                start_ts = row.get("start")
                if start_ts is not None:
                    oldest_existing = datetime.datetime.fromtimestamp(start_ts, tz=datetime.UTC)
            stats = accumulate_to_stats(deltas, anchor_sum, end_before=oldest_existing)
            if not stats:
                continue
            async_import_statistics(
                hass,
                StatisticMetaData(
                    mean_type=StatisticMeanType.NONE,
                    has_sum=True,
                    name=None,
                    source="recorder",
                    statistic_id=statistic_id,
                    unit_of_measurement="EUR",
                ),
                [StatisticData(start=s["start"], sum=s["sum"]) for s in stats],
            )
            written += len(stats)

    # Measurement (SoC). end_before still applies; mean=min=max since the API
    # gives us one value per hour.
    if soc_measurements:
        soc_statistic_id = _statistic_id_for(hass, entry, SOC_STATISTIC_KEY)
        if soc_statistic_id is None:
            _LOGGER.warning("Skipping battery_soc — entity not registered yet")
        else:
            soc_last = await get_instance_executor(
                hass, get_last_statistics, hass, 1, soc_statistic_id, True, {"start"}
            )
            soc_oldest: datetime.datetime | None = None
            if soc_last and soc_statistic_id in soc_last and soc_last[soc_statistic_id]:
                start_ts = soc_last[soc_statistic_id][0].get("start")
                if start_ts is not None:
                    soc_oldest = datetime.datetime.fromtimestamp(start_ts, tz=datetime.UTC)
            soc_stats = [
                StatisticData(start=t, mean=v, min=v, max=v)
                for t, v in soc_measurements
                if soc_oldest is None or t < soc_oldest
            ]
            if soc_stats:
                async_import_statistics(
                    hass,
                    StatisticMetaData(
                        mean_type=StatisticMeanType.ARITHMETIC,
                        has_sum=False,
                        name=None,
                        source="recorder",
                        statistic_id=soc_statistic_id,
                        unit_of_measurement="%",
                    ),
                    soc_stats,
                )
                written += len(soc_stats)

    return {
        "imported": written,
        "days_walked": walked,
        "failed_days": [d.isoformat() for d in failed_days],
    }


async def get_instance_executor(hass: HomeAssistant, func: Callable[..., Any], *args: Any) -> Any:
    """Run ``func(*args)`` on the recorder's executor thread.

    `get_last_statistics` reads from the recorder DB and must not block the
    event loop. Routing it through the recorder's own executor keeps DB
    access serialised correctly.
    """
    return await get_recorder_instance(hass).async_add_executor_job(func, *args)


async def _handle_clear_history(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Remove all Long-Term Statistics owned by this integration for the entry.

    Destructive: there is no recovery short of a fresh backfill. Mandatory
    ``confirm=true`` parameter guards against accidental clicks.
    """
    if not call.data.get("confirm"):
        raise HomeAssistantError("Pass confirm=true to acknowledge that this is destructive")
    entry = _resolve_entry(hass, call)
    statistic_ids: list[str] = []
    for key in ALL_STATISTIC_KEYS:
        sid = _statistic_id_for(hass, entry, key)
        if sid is not None:
            statistic_ids.append(sid)
    if statistic_ids:
        get_recorder_instance(hass).async_clear_statistics(statistic_ids)
    return {
        "cleared": len(statistic_ids),
        "statistic_ids": statistic_ids,
    }


def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    def _make_window_handler(
        finder: Callable[..., dict[str, Any] | None],
    ) -> Callable[[ServiceCall], Any]:
        async def _handler(call: ServiceCall) -> ServiceResponse:
            forecast, slot_count, earliest, latest = _resolve_window_inputs(hass, call)
            result = finder(forecast, slot_count, earliest, latest)
            if result is None:
                return _empty_window_response()
            return {"found": True, **result}

        return _handler

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CHEAPEST_WINDOW,
        _make_window_handler(find_cheapest_window),
        schema=WINDOW_SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_MOST_EXPENSIVE_WINDOW,
        _make_window_handler(find_most_expensive_window),
        schema=WINDOW_SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def _import_history(call: ServiceCall) -> ServiceResponse:
        return await _handle_import_history(hass, call)

    async def _clear_history(call: ServiceCall) -> ServiceResponse:
        return await _handle_clear_history(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_HISTORY,
        _import_history,
        schema=IMPORT_HISTORY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_HISTORY,
        _clear_history,
        schema=CLEAR_HISTORY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
