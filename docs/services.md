---
title: Services & bus events
description: HA services (get_cheapest_window, refresh_now, get_heartbeat_metrics, assign_ev_to_wallbox) and the three automation bus events exposed by the 1KOMMA5° integration.
---

# Services & bus events

All services register globally in `async_setup`, so they stay live for the whole HA session even if an entry reloads.

## `onekommafive.get_cheapest_window` / `get_most_expensive_window`

Find the cheapest (or most expensive) contiguous slot in the price forecast — for scheduling flexible loads or load shedding.

| Field | Required | Description |
|-------|----------|-------------|
| `duration_minutes` | yes | Window length (multiple of 15) |
| `earliest_start` | no | Window must not start before |
| `latest_end` | no | Window must not end after |
| `config_entry_id` | no | Only required with multiple systems configured |

**Response:**

```yaml
found: true
start: "2026-04-27T01:30:00+00:00"
end: "2026-04-27T03:30:00+00:00"
average_price: 0.0823
slot_count: 8
```

??? example "Start the dishwasher at the cheapest 2-hour window before 7 AM"

    ```yaml
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: onekommafive.get_cheapest_window
        data:
          duration_minutes: 120
          latest_end: "{{ (now().replace(hour=7, minute=0, second=0) + timedelta(days=1)).isoformat() }}"
        response_variable: window
      - if: "{{ window.found }}"
        then:
          - service: switch.turn_on
            target:
              entity_id: switch.dishwasher_start
    ```

## `onekommafive.refresh_now`

Force an immediate refresh of one (or all) data coordinators. Useful after a power outage, for debugging, and as a reset hook in automations.

| Field | Default | Description |
|-------|---------|-------------|
| `coordinator` | `live` | One of `live`, `price`, `optimization`, `weather`, `system_status`, `energy`, `notifications`, `heartbeat_prices`, `all` |
| `config_entry_id` | — | Only required with multiple systems configured |

Response: `{"refreshed": [...], "failed": [...]}`. `all` runs every coordinator in parallel; per-coordinator failures land in `failed` but do not raise.

## `onekommafive.get_heartbeat_metrics`

On-demand fetch of aggregated 1KOMMA5° Heartbeat metrics for a chosen time window — PV production, grid consumption/feed-in, tariffs, costs, revenue. Cloud-computed, so the numbers reflect what 1KOMMA5° itself sees, useful for comparing against your locally-integrated `*_energy` / `electricity_cost` / `feed_in_revenue` Long-Term Statistics.

| Field | Values | Description |
|-------|--------|-------------|
| `window` | `day` \| `week` \| `month` \| `half_year` \| `year` | Aggregation window (required) |
| `config_entry_id` | — | Only required with multiple systems configured |

Response is a flat dict with all populated `HeartbeatPriceWindow` fields (~22 fields per window: `pv_produced_kwh`, `grid_feed_in_kwh`, `grid_feed_in_compensation_eur`, `grid_consumed_kwh`, `grid_consumption_cost_eur`, `total_consumption_kwh`, `total_energy_cost_eur`, `vat`, plus a couple of composite/marketing metrics you can choose to ignore). Absent windows respond `{"window": ..., "available": false}` so callers can branch on it.

??? example "Compare cloud vs local monthly grid-import figure"

    ```yaml
    alias: 1KOMMA5° cloud vs local monthly grid check
    trigger:
      - platform: time
        at: "03:00:00"
    action:
      - service: onekommafive.get_heartbeat_metrics
        data:
          window: month
        response_variable: cloud
      - service: notify.persistent_notification
        data:
          title: Grid import — cloud vs local
          message: >
            Cloud month: {{ cloud.grid_consumed_kwh | round(1) }} kWh /
            {{ cloud.grid_consumption_cost_eur | round(2) }} EUR.
            Compare against `sensor.<sys>_grid_consumption_power_energy`
            Long-Term Statistics for the same window in the History panel.
    ```

## `onekommafive.assign_ev_to_wallbox`

Bind a vehicle profile to a wallbox — the id-addressed counterpart to the `select.<sys>_<wallbox>_assigned_vehicle` entity, for scripts that carry the identifiers as data. Available since **v0.1.63**; wraps the same SDK write path (`EVCharger.assign_charger`, v0.5.0+).

| Field | Required | Description |
|-------|----------|-------------|
| `wallbox_id` | yes | UUID of the target wallbox — from the wallbox sub-device's diagnostics dump or from the SDK's `system.get_wallboxes()` |
| `ev_id` | yes | UUID of the vehicle profile |
| `config_entry_id` | no | Only required with multiple systems configured |

**Response:**

```yaml
success: true
previous_ev_id: "ev-uuid-a"   # null when the wallbox had no assignment
```

`previous_ev_id` is captured from the local system-status cache before the write, so an automation can log the swap. Unknown ids raise a clear `HomeAssistantError`. **No detach path**: `ev_id` is required — the 1KOMMA5° model is 1:1 exclusive, and setting one vehicle releases the previously bound one automatically in the same call.

# Bus events

Three Home Assistant bus events for state changes that are better modelled as events than as entities. All events are automation-triggerable via `platform: event`.

## `onekommafive_notification`

Available since **v0.1.52**. Fires once per newly-observed 1KOMMA5° cloud notification (energy market thresholds, system health alerts, dynamic-pulse events, ...). Enables automations that react to the same push notifications the mobile app receives — no email/webhook/tap-detection needed.

**Event data (flat JSON):**

| Field | Type | Description |
|-------|------|-------------|
| `system_id` | string | System UUID |
| `notification_id` | string | Unique per notification |
| `type` | string | e.g. `ENERGY_MARKET_UPPER_TARGET_REACHED`, `SYSTEM_HEALTH` |
| `title` | string \| null | Already localized to your account language |
| `body` | string \| null | Already localized |
| `locale` | string \| null | e.g. `"de"` |
| `created_at` | string \| null | ISO-8601 |
| `meta` | dict | Type-specific extras (e.g. `meta.price.value` for price thresholds) |

**Semantics:** dedup state persists across HA restarts via `homeassistant.helpers.storage.Store` under `.storage/onekommafive.notifications.<entry_id>`. First refresh after a fresh install primes silently — no replay of history. Which notification types reach HA is controlled entirely by your **1KOMMA5° app** notification settings (Settings → Notifications); the API filters at source.

??? example "Surface every cloud notification as an HA persistent notification"

    ```yaml
    alias: 1KOMMA5° notification passthrough
    trigger:
      - platform: event
        event_type: onekommafive_notification
    action:
      - service: persistent_notification.create
        data:
          title: "1KOMMA5°: {{ trigger.event.data.title }}"
          message: "{{ trigger.event.data.body }}"
          notification_id: "onekommafive_{{ trigger.event.data.notification_id }}"
    ```

Filter by `type` (e.g. `event_data: {type: ENERGY_MARKET_UPPER_TARGET_REACHED}`) to react only to specific notification kinds.

## `onekommafive_optimization_decision`

Fires per new Heartbeat AI decision (BATTERY / HEATPUMP). First refresh after HA start fires one event for the most recent decision so the wiring is immediately verifiable in Developer Tools → Events; earlier decisions of the day are not replayed.

| Field | Type | Description |
|-------|------|-------------|
| `system_id` | string | System UUID |
| `asset` | string | `BATTERY` or `HEATPUMP` |
| `decision` | string | `BATTERY_CHARGE_FROM_GRID`, `HEATPUMP_RECOMMEND_ON`, ... |
| `from`, `to` | string | ISO-8601 slot range |
| `market_price` | float \| null | EUR/MWh |
| `market_price_currency` | string \| null | Typically `EUR` |
| `state_of_charge` | int \| null | Battery SoC at decision time (0–100) |

??? example "Turn on a non-essential load when the AI plans grid charging"

    ```yaml
    trigger:
      - platform: event
        event_type: onekommafive_optimization_decision
        event_data:
          decision: BATTERY_CHARGE_FROM_GRID
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.dishwasher
    ```

## `onekommafive_negative_price_started` / `onekommafive_negative_price_ended` { #negative-price-edges }

Fired on positive↔negative edges of the active 15-min slot. First refresh after HA start primes the tracker without firing. Granularity equals the coordinator interval (1 h).

**Event data:** `system_id` (string), `price` (float, EUR/kWh), `negative_price_slots_remaining` (int).

See the [`notify_negative_price_started.yaml` blueprint](https://github.com/mrebbert/1komma5-ha/blob/main/blueprints/automation/onekommafive/notify_negative_price_started.yaml) for a ready-made notification automation.
