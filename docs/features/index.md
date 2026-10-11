---
title: Features overview
description: Overview of all sensor categories, services and bus events exposed by the 1KOMMA5° Home Assistant integration — 60+ entities across eight coordinators.
---

# Features

Entity names in Home Assistant follow your account language. Tables below use English keys; German (and five other locales) ship in the translations.

The 60+ entities group into nine functional areas:

<div class="grid cards" markdown>

- **[Live power & battery](live-power.md)**

    Twelve 30-second-cadence sensors covering PV, battery (power + SoC), grid (bidirectional + split import/export), household, EV charger, heat pump, AC and self-sufficiency.

- **[Dynamic electricity pricing](pricing.md)**

    Dynamischer Stromtarif with 15-minute resolution, 30-hour price forecast, cheapest-window scheduling sensors, negative-price counters and the Dynamic-Pulse price guarantee.

- **[Energy & cost](energy-cost.md)**

    Trapezoidal kWh integration of every unidirectional power channel plus per-consumer cost allocation (heat pump, EV, household, AC) that always sums to `electricity_cost`.

- **[§14a EnWG grid-fee](enwg14a.md)**

    Two meter-sub-device sensors tracking the BNetzA BK6-22-300 Modul 1 (annual rebate) and Modul 3 (variable HT/NT Netzentgelte) treatment of your account.

- **[Contract overview](contract.md)**

    Active subscriptions, 1KOMMA5°Care add-on eligibility, EMP backend enum — all PII-safe setup-time snapshots.

- **[AI optimization](ai-optimization.md)**

    Heartbeat's grid-charge / heat-pump-recommend decisions as sensors, binary sensors and bus events.

- **[EV charger & wallbox](ev-wallbox.md)**

    Per-vehicle-profile charging-mode / target-SoC / departure-time controls, plus wallbox-to-vehicle assignment selects for multi-car sites.

- **[Weather](weather.md)**

    48-hour hourly forecast and sunshine totals, co-tenant of the price coordinator.

- **[Diagnostics](diagnostics.md)**

    Per-coordinator timestamp sensors, EMS auto-mode switch (GRIDX only) and the Repair-Issue machinery.

</div>

## Data update cadence

Every polled endpoint is fronted by its own `DataUpdateCoordinator`; the interval is chosen for the endpoint's actual change rate, not a single global tick. All coordinators are non-blocking on setup, so the integration surface comes up even when one of them times out (typical on the price coordinator right after HA restart).

| Coordinator | Cadence | Fills |
|-------------|---------|-------|
| Live | 30 s | `live_overview`, `ev_chargers`, `ems_settings`, `wallboxes` |
| System status | 5 min | Site connectivity, asset inventory, active feature flags |
| Optimization | 15 min | Today's AI decision events + last-decision enum |
| Energy | 15 min | Daily-cumulative cloud figures (`daily_savings`, `co2_saved_today`) |
| Notifications | 5 min | New cloud push notifications → `onekommafive_notification` bus event |
| Price | 1 h | Today + tomorrow's dynamic tariff forecast (timestamps are slot ENDs) |
| Weather | 1 h | 48 h hourly forecast + sunshine totals |
| Heartbeat prices | 1 h | Five aggregation windows backing the §14a Modul 1 sensor (v0.1.66) |

The intervals are compile-time constants and can be temporarily overridden by calling [`onekommafive.refresh_now`](../services.md#onekommafiverefresh_now) from an automation or Developer Tools.

**Slot-boundary redraws.** A few sensors (`cheap_electricity`, `cheapest_hour_now`, the two `stable_electricity_price`-derived cost accumulators) re-evaluate at `:00`/`:15`/`:30`/`:45` even if no coordinator has refreshed yet. A shared `QuarterHourUpdateMixin` triggers those state writes from a single time-listener; individual coordinators do not re-poll on the quarter.
