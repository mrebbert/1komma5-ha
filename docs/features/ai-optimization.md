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

## Bus event

Bus event `onekommafive_optimization_decision` fires per new decision — payload shape and example automation on the [Services & bus events](../services.md#onekommafive_optimization_decision) page.
