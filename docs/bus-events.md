# Bus events

The integration fires three Home Assistant bus events for state changes that are better modelled as events than as entities. All events are automation-triggerable via `platform: event`. See the main [README](../README.md) for the full services overview; this file carries the per-event payload shapes and example automations.

## `onekommafive_notification` (since v0.1.52)

Fires once per newly-observed 1KOMMA5° cloud notification (energy market thresholds, system health alerts, dynamic-pulse events, …). Enables automations that react to the same push notifications the mobile app receives — no email/webhook/tap-detection needed.

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

**Example — surface every cloud notification as an HA persistent notification:**

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
| `decision` | string | `BATTERY_CHARGE_FROM_GRID`, `HEATPUMP_RECOMMEND_ON`, … |
| `from`, `to` | string | ISO-8601 slot range |
| `market_price` | float \| null | EUR/MWh |
| `market_price_currency` | string \| null | Typically `EUR` |
| `state_of_charge` | int \| null | Battery SoC at decision time (0–100) |

**Example — turn on a non-essential load when the AI plans grid charging:**

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

## `onekommafive_negative_price_started` / `onekommafive_negative_price_ended`

Fired on positive↔negative edges of the active 15-min slot. First refresh after HA start primes the tracker without firing. Granularity = coordinator interval (1 h).

**Event data:** `system_id` (string), `price` (float, EUR/kWh), `negative_price_slots_remaining` (int).

See the `notify_negative_price_started.yaml` blueprint for a ready-made notification automation.
