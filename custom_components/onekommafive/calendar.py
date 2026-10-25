"""Calendar platform for the 1KOMMA5° integration."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from homeassistant.components import recorder as _recorder
from homeassistant.components.binary_sensor.const import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
)
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from . import OneKomma5ConfigEntry
from .binary_sensor import OPTIMIZATION_DECISION_SENSORS, OptimizationDecisionSpec
from .const import DOMAIN
from .entity import OneKomma5OptimizationEntity, apply_stable_entity_ids
from .helpers import active_optimization_event

if TYPE_CHECKING:
    from .coordinator import (
        OneKomma5OptimizationCoordinator,
        OneKomma5PriceCoordinator,
    )

# `get_instance` is exposed by recorder/__init__.py via `from .util import
# get_instance`; mypy's strict mode treats that as a non-exported attribute
# because recorder has no `__all__`. Access it via the already-imported
# module to sidestep the attr-defined complaint uniformly.
get_instance = _recorder.get_instance  # type: ignore[attr-defined]

PARALLEL_UPDATES = 0

MIN_PROXY_SLOTS = 2  # drop single-slot (<30 min) proxy blocks as noise
CHEAP_PERCENTILE = 0.33
EXPENSIVE_PERCENTILE = 0.67
SLOT_MINUTES = 15  # AI decisions are rendered on the native 15-min grid

PROXY_CHEAP_KEY = "proxy_cheap"
PROXY_EXPENSIVE_KEY = "proxy_expensive"

# Fallback proxy labels per supported HA language. Kept inline because the
# strings live outside the standard HA translation categories; the Decision
# labels themselves are fetched via async_get_translations from the existing
# binary_sensor entries so they stay in sync with Lovelace.
_PROXY_LABELS: dict[str, dict[str, str]] = {
    "de": {
        PROXY_CHEAP_KEY: "Preis-Proxy: günstig (EV-Laden empfohlen)",
        PROXY_EXPENSIVE_KEY: "Preis-Proxy: teuer (Batterieentladung empfohlen)",
    },
    "en": {
        PROXY_CHEAP_KEY: "Price proxy: cheap (EV charging suggested)",
        PROXY_EXPENSIVE_KEY: "Price proxy: expensive (battery discharge suggested)",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OneKomma5ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AI-decisions calendar entity from a config entry."""
    data = entry.runtime_data
    entity = OneKomma5DecisionCalendar(
        optimization_coordinator=data.optimization_coordinator,
        price_coordinator=data.price_coordinator,
        system_id=data.system.id(),
        system_name=data.system_name,
    )
    apply_stable_entity_ids([entity], "calendar")
    async_add_entities([entity])


def _entity_ids_for_specs(hass: HomeAssistant, system_id: str) -> dict[str, str]:
    """Resolve binary_sensor entity_ids via the entity_registry.

    Keyed by spec.key. Entries missing from the registry (asset not present
    or sensor manually disabled) are skipped — the calendar then simply
    yields no history for that decision type.
    """
    registry = er.async_get(hass)
    out: dict[str, str] = {}
    for spec in OPTIMIZATION_DECISION_SENSORS:
        entity_id = registry.async_get_entity_id(
            BINARY_SENSOR_DOMAIN, DOMAIN, f"{system_id}_{spec.key}"
        )
        if entity_id is not None:
            out[spec.key] = entity_id
    return out


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Return the linear-interpolated percentile of a pre-sorted list.

    ``sorted_values`` must be non-empty and sorted ascending; ``pct`` is in
    [0, 1]. Returns the single element unchanged when the list is of length 1.
    """
    if not sorted_values:
        msg = "percentile requires at least one value"
        raise ValueError(msg)
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = pct * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _snap_floor(t: dt.datetime) -> dt.datetime:
    """Floor a UTC datetime to the current 15-min slot boundary."""
    return t.replace(
        minute=(t.minute // SLOT_MINUTES) * SLOT_MINUTES,
        second=0,
        microsecond=0,
    )


def _snap_ceil(t: dt.datetime) -> dt.datetime:
    """Ceil a UTC datetime to the next 15-min slot boundary.

    Values within 5 seconds past a boundary floor rather than ceil, so
    microsecond jitter from recorder ``last_changed`` does not inflate a
    phase by a full slot.
    """
    floored = _snap_floor(t)
    if (t - floored).total_seconds() > 5:
        return floored + dt.timedelta(minutes=SLOT_MINUTES)
    return floored


def _quantize_and_merge(
    phases: list[tuple[dt.datetime, dt.datetime]],
) -> list[tuple[dt.datetime, dt.datetime]]:
    """Snap phases to 15-min boundaries and merge adjacent or overlapping ones."""
    snapped: list[tuple[dt.datetime, dt.datetime]] = []
    for start, end in phases:
        s = _snap_floor(start)
        e = _snap_ceil(end)
        if e > s:
            snapped.append((s, e))
    if not snapped:
        return []
    snapped.sort()
    merged: list[tuple[dt.datetime, dt.datetime]] = [snapped[0]]
    for start, end in snapped[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _is_ambiguous_local_slot(slot_utc: dt.datetime) -> bool:
    """True if the slot's local wall-clock representation is DST-ambiguous.

    Fall-back repeats the same local wall clock for two different UTC
    instants, which cannot be rendered unambiguously by a local-time
    calendar. We skip such slots to avoid duplicate rows.
    """
    local_tz = dt_util.DEFAULT_TIME_ZONE
    local = slot_utc.astimezone(local_tz)
    naive = local.replace(tzinfo=None)
    fold0 = naive.replace(tzinfo=local_tz, fold=0).utcoffset()
    fold1 = naive.replace(tzinfo=local_tz, fold=1).utcoffset()
    return fold0 != fold1


def _slot_dominant_decisions(
    phases_per_summary: dict[str, list[tuple[dt.datetime, dt.datetime]]],
    window_start: dt.datetime,
    window_end: dt.datetime,
) -> dict[dt.datetime, str]:
    """Return the decision with the most ``on`` seconds for each 15-min slot."""
    if not phases_per_summary:
        return {}
    slot_duration = dt.timedelta(minutes=SLOT_MINUTES)
    cur = _snap_floor(dt_util.as_utc(window_start))
    end = _snap_ceil(dt_util.as_utc(window_end))
    winners: dict[dt.datetime, str] = {}
    while cur < end:
        slot_end = cur + slot_duration
        if _is_ambiguous_local_slot(cur):
            cur = slot_end
            continue
        scores: dict[str, float] = {}
        for summary, phases in phases_per_summary.items():
            total = 0.0
            for p_start, p_end in phases:
                ov_start = max(p_start, cur)
                ov_end = min(p_end, slot_end)
                if ov_end > ov_start:
                    total += (ov_end - ov_start).total_seconds()
            if total > 0:
                scores[summary] = total
        if scores:
            winners[cur] = max(scores, key=lambda s: scores[s])
        cur = slot_end
    return winners


def _collapse_slot_winners(
    winners: dict[dt.datetime, str],
) -> list[tuple[dt.datetime, dt.datetime, str]]:
    """Merge consecutive slots sharing a winner into (start, end, summary) blocks."""
    if not winners:
        return []
    slot_duration = dt.timedelta(minutes=SLOT_MINUTES)
    sorted_items = sorted(winners.items())
    blocks: list[list[Any]] = []
    for slot_start, summary in sorted_items:
        if blocks and blocks[-1][2] == summary and blocks[-1][1] == slot_start:
            blocks[-1][1] = slot_start + slot_duration
        else:
            blocks.append([slot_start, slot_start + slot_duration, summary])
    return [(b[0], b[1], b[2]) for b in blocks]


def _split_at_dst_transition(
    start: dt.datetime, end: dt.datetime
) -> list[tuple[dt.datetime, dt.datetime]]:
    """Split a phase around a DST transition; drops the ambiguous straddle slot."""
    local_tz = dt_util.DEFAULT_TIME_ZONE
    start_offset = start.astimezone(local_tz).utcoffset()
    end_offset = end.astimezone(local_tz).utcoffset()
    if start_offset == end_offset:
        return [(start, end)]
    low, high = start, end
    while (high - low) > dt.timedelta(minutes=1):
        mid = low + (high - low) / 2
        if mid.astimezone(local_tz).utcoffset() == start_offset:
            low = mid
        else:
            high = mid
    before = _snap_floor(low)
    after = _snap_ceil(high)
    parts: list[tuple[dt.datetime, dt.datetime]] = []
    if before > start:
        parts.append((start, before))
    if end > after:
        parts.append((after, end))
    return parts


def _reconstruct_phases(
    states: list[Any], window_end: dt.datetime
) -> list[tuple[dt.datetime, dt.datetime]]:
    """Return raw UTC ``on`` phases; trailing ``on`` clamps to ``window_end``."""
    window_end_utc = dt_util.as_utc(window_end)
    phases: list[tuple[dt.datetime, dt.datetime]] = []
    phase_start: dt.datetime | None = None
    for state in states:
        is_on = state.state == STATE_ON
        changed = dt_util.as_utc(state.last_changed)
        if is_on and phase_start is None:
            phase_start = changed
        elif not is_on and phase_start is not None:
            phases.append((phase_start, changed))
            phase_start = None
    if phase_start is not None:
        phases.append((phase_start, window_end_utc))
    return phases


def _proxy_blocks(
    forecast: list[dict[str, Any]],
    window_start: dt.datetime,
    window_end: dt.datetime,
) -> list[tuple[str, dt.datetime, dt.datetime]]:
    """Return ``(category, start, end)`` price-proxy blocks for the window."""
    if not forecast or window_end <= window_start:
        return []
    prices_sorted = sorted(s["price"] for s in forecast)
    cheap_threshold = _percentile(prices_sorted, CHEAP_PERCENTILE)
    expensive_threshold = _percentile(prices_sorted, EXPENSIVE_PERCENTILE)
    # Degenerate forecast (all prices identical) → no proxy signal.
    if cheap_threshold == expensive_threshold:
        return []

    blocks: list[tuple[str, dt.datetime, dt.datetime]] = []
    current_class: str | None = None
    block_start: dt.datetime | None = None
    block_end: dt.datetime | None = None
    block_slot_count = 0

    for slot in forecast:
        slot_start = dt_util.as_utc(dt.datetime.fromisoformat(slot["start"]))
        slot_end = dt_util.as_utc(dt.datetime.fromisoformat(slot["end"]))
        if slot_end <= window_start or slot_start >= window_end:
            continue
        price = slot["price"]
        if price < cheap_threshold:
            slot_class: str | None = PROXY_CHEAP_KEY
        elif price > expensive_threshold:
            slot_class = PROXY_EXPENSIVE_KEY
        else:
            slot_class = None

        contiguous = (
            slot_class == current_class
            and block_end is not None
            and slot_start == block_end
        )
        if contiguous:
            block_end = slot_end
            block_slot_count += 1
            continue

        if (
            current_class is not None
            and block_slot_count >= MIN_PROXY_SLOTS
            and block_start is not None
            and block_end is not None
        ):
            blocks.append((current_class, block_start, block_end))

        if slot_class is None:
            current_class = None
            block_start = block_end = None
            block_slot_count = 0
            continue
        current_class = slot_class
        block_start = slot_start
        block_end = slot_end
        block_slot_count = 1

    if (
        current_class is not None
        and block_slot_count >= MIN_PROXY_SLOTS
        and block_start is not None
        and block_end is not None
    ):
        blocks.append((current_class, block_start, block_end))

    return blocks


class OneKomma5DecisionCalendar(CalendarEntity, OneKomma5OptimizationEntity):
    """Aggregated calendar of past AI decisions + price-based proxy for the future."""

    _attr_translation_key = "ai_decisions"

    def __init__(
        self,
        *,
        optimization_coordinator: OneKomma5OptimizationCoordinator,
        price_coordinator: OneKomma5PriceCoordinator,
        system_id: str,
        system_name: str,
    ) -> None:
        """Initialize the calendar entity."""
        super().__init__(
            optimization_coordinator,
            system_id,
            system_name,
            "ai_decisions_calendar",
        )
        self._price_coordinator = price_coordinator
        self._decision_labels: dict[str, str] = {}
        self._translations_lang: str | None = None

    async def async_added_to_hass(self) -> None:
        """Load translations for the Decision labels on first use."""
        await super().async_added_to_hass()
        await self._refresh_translations()

    async def _refresh_translations(self) -> None:
        """Fetch component translations, re-fetch if the UI language changed."""
        language = self.hass.config.language
        if self._translations_lang == language and self._decision_labels:
            return
        translations = await async_get_translations(
            self.hass, language, "entity", {DOMAIN}
        )
        labels: dict[str, str] = {}
        for spec in OPTIMIZATION_DECISION_SENSORS:
            tkey = f"component.{DOMAIN}.entity.binary_sensor.{spec.key}.name"
            labels[spec.key] = translations.get(tkey, spec.key)
        self._decision_labels = labels
        self._translations_lang = language

    def _proxy_label(self, spec_key: str) -> str:
        """Return the inline proxy label for the current UI language."""
        language = (self.hass.config.language or "en").split("-")[0]
        table = _PROXY_LABELS.get(language, _PROXY_LABELS["en"])
        return table.get(spec_key, spec_key)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the currently running decision event, if any.

        Scans the three distinct asset types (BATTERY, EV, HEATPUMP) for an
        active event, labels it with the matching spec's translated name, and
        wraps it as a ``CalendarEvent``.
        """
        if self.coordinator.data is None:
            return None
        now = dt_util.utcnow()
        best: tuple[OptimizationDecisionSpec, Any] | None = None
        for asset in ("BATTERY", "EV", "HEATPUMP"):
            active = active_optimization_event(
                self.coordinator.data.events, asset=asset, now=now
            )
            if active is None:
                continue
            spec = next(
                (
                    s
                    for s in OPTIMIZATION_DECISION_SENSORS
                    if s.asset == asset and s.decision == active.decision
                ),
                None,
            )
            if spec is None:
                continue
            if best is None or _event_start(active) < _event_start(best[1]):
                best = (spec, active)
        if best is None:
            return None
        spec, active = best
        start = _event_start(active)
        end = _event_end(active)
        if end is None:
            return None
        summary = self._decision_labels.get(spec.key, spec.key)
        return CalendarEvent(
            start=start, end=end, summary=summary, description=spec.key
        )

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: dt.datetime,
        end_date: dt.datetime,
    ) -> list[CalendarEvent]:
        """Return decision events in ``[start_date, end_date]``.

        Historical blocks come from the Recorder's state history of the six
        decision binary sensors; proxy blocks for the future come from the
        price-coordinator forecast. The two never overlap: the handover
        boundary is the current UTC instant.
        """
        await self._refresh_translations()
        now = dt_util.utcnow()
        history_end = min(end_date, now)
        proxy_start = max(start_date, now)

        events: list[CalendarEvent] = []
        if history_end > start_date:
            events.extend(await self._history_events(hass, start_date, history_end))
        if end_date > proxy_start:
            events.extend(self._proxy_events(proxy_start, end_date))

        events.sort(key=lambda e: e.start)
        return events

    async def _history_events(
        self,
        hass: HomeAssistant,
        start: dt.datetime,
        end: dt.datetime,
    ) -> list[CalendarEvent]:
        """Reconstruct historical decision events from the Recorder.

        Six decision sensors may stay ``on`` concurrently across coordinator
        refresh boundaries. We resolve by 15-min slot: for each slot the
        decision with the most ``on`` seconds wins, and consecutive slots
        with the same winner collapse into one event.
        """
        entity_id_map = _entity_ids_for_specs(hass, self._system_id)
        if not entity_id_map:
            return []
        entity_ids = list(entity_id_map.values())
        recorder = get_instance(hass)
        state_map = await recorder.async_add_executor_job(
            get_significant_states,
            hass,
            start,
            end,
            entity_ids,
            None,
            True,
            True,
        )
        phases_per_key: dict[str, list[tuple[dt.datetime, dt.datetime]]] = {}
        for spec_key, entity_id in entity_id_map.items():
            states = state_map.get(entity_id, [])
            phases = _reconstruct_phases(states, end)
            if not phases:
                continue
            phases_per_key.setdefault(spec_key, []).extend(phases)
        slot_winners = _slot_dominant_decisions(phases_per_key, start, end)
        events: list[CalendarEvent] = []
        for block_start, block_end, spec_key in _collapse_slot_winners(slot_winners):
            summary = self._decision_labels.get(spec_key, spec_key)
            for sub_start, sub_end in _split_at_dst_transition(block_start, block_end):
                events.append(
                    CalendarEvent(
                        start=sub_start,
                        end=sub_end,
                        summary=summary,
                        description=spec_key,
                    )
                )
        return events

    def _proxy_events(
        self, start: dt.datetime, end: dt.datetime
    ) -> list[CalendarEvent]:
        """Return price-proxy events in ``[start, end]`` (future-only)."""
        price_data = self._price_coordinator.data
        forecast = getattr(price_data, "forecast", None) if price_data else None
        if not forecast:
            return []
        blocks = _proxy_blocks(forecast, start, end)
        return [
            CalendarEvent(
                start=block_start,
                end=block_end,
                summary=self._proxy_label(category),
                description=category,
            )
            for category, block_start, block_end in blocks
        ]


def _event_start(event: Any) -> dt.datetime:
    """Parse ``OptimizationEvent.from_time`` into a UTC-aware datetime."""
    parsed = dt.datetime.fromisoformat(event.from_time)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return dt_util.as_utc(parsed)


def _event_end(event: Any) -> dt.datetime | None:
    """Parse the SDK event's ``end_time`` (property, with ``to_time`` fallback)."""
    raw = getattr(event, "end_time", None) or getattr(event, "to_time", None)
    if raw is None:
        return None
    if isinstance(raw, dt.datetime):
        return dt_util.as_utc(raw if raw.tzinfo else raw.replace(tzinfo=dt.UTC))
    parsed = dt.datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return dt_util.as_utc(parsed)
