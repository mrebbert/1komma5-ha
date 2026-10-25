---
title: AI optimization
description: Heartbeat AI optimization decisions (grid-charge, heat-pump-recommend) surfaced as sensors, binary sensors and bus events — react to the same signals the 1KOMMA5° cloud sees.
---

# AI optimization

Heartbeat AI decisions surfaced as sensors and binary sensors, updated every 15 minutes.

| Entity | Key | Description |
|--------|-----|-------------|
| Optimization Decisions Today | `optimization_event_count` | Count of today's decisions; attribute holds the full list |
| Last Optimization Decision | `optimization_last_decision` | Most-recent decision (localized display, underlying enum stays lowercase for automation matching) |
| AI: Battery grid charging | `optimization_battery_grid_charge` | Binary — ON when the active BATTERY decision is `BATTERY_CHARGE_FROM_GRID` |
| AI: Heat pump recommended | `optimization_heat_pump_recommended` | Binary — ON when the active HEAT_PUMP decision is `HEATPUMP_RECOMMEND_ON` |

Four more binary sensors (`BATTERY_DISCHARGE_TO_GRID`, `BATTERY_NO_CHARGE`, `BATTERY_NO_DISCHARGE`, `EV_CHARGE_FROM_GRID`) ship since **v0.1.66**; `HEATPUMP_AUTO` is deliberately not exposed because it is the implicit default.

## Decision enum

Known values from the SDK, non-exhaustive by design:

`BATTERY_CHARGE_FROM_GRID`, `BATTERY_NO_CHARGE`, `BATTERY_NO_DISCHARGE`, `BATTERY_DISCHARGE_TO_GRID`, `EV_CHARGE_FROM_GRID`, `HEATPUMP_RECOMMEND_ON`, `HEATPUMP_AUTO`.

Unknown values keep the sensor at `unknown` and log a warning so a new cloud-side variant surfaces without breaking the state.

## Caveats

!!! warning "The sensors reflect the Cloud recommendation, not what the HEMS does"
    `optimization_total_cost` / `_energy_bought` / `_energy_sold` stay `unknown` — the API does not populate settlement data yet. The battery and heat-pump binaries reflect what the Cloud AI *recommends*; the Heartbeat HEMS can act independently (`optimization_heat_pump_recommended` may stay `off` while the Wärmepumpe runs on local SG-Ready). Don't gate SG-Ready or grid-charge automations on them as if they were live control signals. See [Known limitations](../limitations.md).

## AI decisions calendar (v0.1.73+)

A dedicated calendar entity renders the AI-decision timeline for Lovelace, the HA mobile app and any `calendar.get_events` consumer.

| Entity | Key | Description |
|--------|-----|-------------|
| AI decisions | `calendar.<system>_ai_decisions_calendar` | Historical decision blocks (reconstructed from the six `optimization_*` binary sensors in the Recorder) plus a price-derived proxy for the next 30 h |

**Block merging**: adjacent 15-minute slots with the same winning decision collapse into one event. If several decision sensors are concurrently `on` across a coordinator-refresh boundary, the decision with the most on-seconds inside that slot wins — the timeline stays overlap-free.

**Price proxy for the next 30 h**: slots below the 33rd price percentile mark expected `EV_CHARGE_FROM_GRID` windows; slots above the 67th percentile mark expected `BATTERY_DISCHARGE_TO_GRID` windows. Summary carries a `"Price proxy:"` prefix so the Lovelace card never confuses them with real AI decisions. Noise filter: blocks shorter than 30 min are dropped.

**Overlap rule**: historical blocks run up to the current UTC instant, price-proxy blocks start from it. No event spans the handover.

**DST fall-back caveat**: the ambiguous local hour at the Oktober fall-back (02:00–03:00 appearing twice in Berlin wall clock) is deliberately skipped. HA's calendar is local-time only and cannot distinguish the two instants that share a wall clock. One hour of decisions per year is lost in exchange for a clean, overlap-free display.

**Machine-readable key**: each event carries a stable `description` field alongside the localized `summary` — `optimization_ev_grid_charge`, `optimization_battery_grid_charge`, …, `proxy_cheap`, `proxy_expensive`. Automations and blueprints should match on `trigger.calendar_event.description` to stay language-independent.

### Blueprint: react to any calendar event

The `ai_decision_calendar_trigger.yaml` [blueprint](https://github.com/mrebbert/1komma5-ha/blob/main/blueprints/automation/onekommafive/ai_decision_calendar_trigger.yaml) wires any of the eight event classes (six AI decisions + `proxy_cheap` / `proxy_expensive`) to a user-supplied action sequence. Pick `start` or `end` plus an optional ±60 min offset. Example use cases:

- EV wallbox on quick-charge during cheap price-proxy windows (two instances, one `start` → quick, one `end` → smart).
- Notification when `optimization_battery_grid_charge` begins (bridging an upcoming high-price period).
- Script run on `optimization_heat_pump_recommended` end to log recommendation durations.

## Bus event

Bus event `onekommafive_optimization_decision` fires per new decision — payload shape and example automation on the [Services & bus events](../services.md#onekommafive_optimization_decision) page.
