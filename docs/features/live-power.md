---
title: Live power & battery
description: 30-second-cadence live power sensors (PV, battery, grid, household, EV charger, heat pump) and the derived self-sufficiency metric.
---

# Live power & battery

The twelve live sensors poll the `live_overview` endpoint every 30 seconds. All use `state_class: measurement`, so Long-Term Statistics tracks hourly min/max/mean automatically.

| Entity | Key | Unit |
|--------|-----|------|
| PV Power | `pv_power` | W |
| Battery Power | `battery_power` | W (± bidirectional) |
| Battery SoC | `battery_soc` | % |
| Grid Power | `grid_power` | W (± bidirectional) |
| Grid Import Power | `grid_consumption_power` | W (≥ 0) |
| Grid Export Power | `grid_feed_in_power` | W (≥ 0) |
| Total Consumption | `consumption_power` | W |
| Household Consumption | `household_power` | W |
| EV Charger Power | `ev_chargers_power` | W |
| Heat Pump Power | `heat_pumps_power` | W |
| AC Power | `acs_power` | W |
| Self-Sufficiency | `self_sufficiency` | % |

!!! tip "Self-sufficiency trends"
    Drop the entity into a `statistics-graph` card, or build a [Statistics Helper](https://www.home-assistant.io/integrations/statistics/) for rolling averages. No integration code needed.

## Why `grid_power` is bidirectional

`grid_power` is the raw signed value from the inverter: positive on import, negative on export. The split `grid_consumption_power` / `grid_feed_in_power` channels are the ≥ 0 projections that back the `*_energy` counters and the Energy Dashboard wiring. Pick the one that matches your downstream consumer.

## Battery sensors

- `battery_power` is bidirectional (positive on discharge, negative on charge in the HA convention used by the Energy Dashboard). Not integrated into kWh directly — see [Energy & cost](energy-cost.md) for the split `battery_charge_power_energy` / `battery_discharge_power_energy` channels.
- `battery_soc` is 0–100 %.
- Hybrid-inverter installs (Sungrow, Enphase) carry both entities on the inverter sub-device. FoxESS and other PV-plus-battery-split installs get a separate `battery` sub-device.
