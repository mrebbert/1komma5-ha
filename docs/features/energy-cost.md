---
title: Energy & cost
description: kWh energy counters (Energy Dashboard-ready) and per-consumer cost allocation (heat pump, EV, household, AC) with feed-in revenue and daily savings.
---

# Energy accounting

For every unidirectional power sensor an energy counterpart (kWh) is auto-created via trapezoidal integration of the 30 s power samples. All use `state_class: total_increasing` — direct **Energy Dashboard** compatibility.

| Category | Sensors |
|----------|---------|
| Solar | `pv_power_energy` |
| Grid | `grid_consumption_power_energy`, `grid_feed_in_power_energy` |
| Consumption | `consumption_power_energy`, `household_power_energy` |
| Devices | `ev_chargers_power_energy`, `heat_pumps_power_energy`, `acs_power_energy` |
| Battery | `battery_charge_power_energy`, `battery_discharge_power_energy` |

!!! info "Why battery and grid get the split treatment"
    `battery_power` and `grid_power` are bidirectional and therefore excluded from the general energy set. The battery is covered by dedicated Charge / Discharge energy sensors that split the signal into two `total_increasing` counters — required for the **Energy Dashboard** battery configuration.

See [`dashboard/ENERGY_DASHBOARD.md`](https://github.com/mrebbert/1komma5-ha/blob/main/dashboard/ENERGY_DASHBOARD.md) for the slot-to-sensor mapping and the grid-cost / feed-in-revenue wiring steps.

# Cost & revenue

Monetary sensors integrating power flow × price. `state_class: total`, `device_class: monetary`, per-locale currency (EUR, DKK, SEK, AUD depending on the site's country).

| Entity | Key | Semantic |
|--------|-----|----------|
| Electricity Cost | `electricity_cost` | Cumulative grid-import cost = grid import × stable price |
| Heat Pump Cost | `heat_pump_cost` | Allocation to heat pump = `heat_pumps_power / consumption_power × grid_consumption_power × stable_price` |
| EV Charger Cost | `ev_charger_cost` | Same allocation for EV charger(s) |
| Household Cost | `household_cost` | Same allocation for base household load |
| AC Cost | `ac_cost` | Same allocation for AC unit |
| Feed-in Revenue | `feed_in_revenue` | Grid export × configured feed-in tariff |
| Daily Savings | `daily_savings` | Cloud-computed daily savings (`get_energy_today`), resets at local midnight |

The four per-consumer cost sensors always sum to `electricity_cost`. When PV/battery cover all consumption the grid bill is zero and all five stop accumulating together.

Negative electricity prices are preserved: cost accumulators subtract value during negative slots so the net figure stays accurate.
