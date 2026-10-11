---
title: Dashboards & blueprints
description: Two ready-to-import Lovelace dashboards (energy, EV charger) and nine automation blueprints for the 1KOMMA5° integration — all cards are native HA types.
---

# Dashboards & automation blueprints

## Dashboards

[`dashboard/`](https://github.com/mrebbert/1komma5-ha/tree/main/dashboard) in the repo contains two ready-to-import Home Assistant dashboards (energy & grid + EV charger). All cards are native HA types — no extra frontend components needed. See the [dashboard README](https://github.com/mrebbert/1komma5-ha/blob/main/dashboard/README.md) for screenshots and import instructions.

The showcase dashboard needs two custom Lovelace cards and one helper:

- `apexcharts-card` — the 30 h price-forecast chart in the "Preise und Kosten" view.
- `button-card` — the cost time-range switcher.
- `input_select.stromkosten_zeitspanne` (helper: `Täglich` / `Wöchentlich` / `Monatlich` / `Jährlich`) — drives the cost and per-consumer-cost charts.

The dashboard YAML carries two placeholders you fill in once at import: `SYSTEM_NAME` and `CAR_IDENTIFIER`.

## Automation blueprints

Nine importable blueprints in [`blueprints/automation/onekommafive/`](https://github.com/mrebbert/1komma5-ha/tree/main/blueprints/automation/onekommafive):

| Blueprint | What it does |
|-----------|-------------|
| **Run during cheapest window** | Schedules a switch for the cheapest N-min window daily (dishwasher, washer, EV). |
| **Follow cheap electricity** | Mirrors a switch to `binary_sensor…_cheap_electricity` for opportunistic loads. |
| **Notify on AI grid-charge decision** | Pings when the AI decides `BATTERY_CHARGE_FROM_GRID`. |
| **Notify on negative prices tomorrow** | Heads-up when tomorrow has ≥ N negative slots (fires ~13:00 CET). |
| **Notify when the grid pays you** | Instant alert on positive↔negative edge, built on the bus event. |
| **EV charge on PV surplus** | Toggles a switch ON when battery is full AND PV exceeds a threshold. |
| **Vehicle at wallbox** | Binds a vehicle profile when its plug-in sensor goes ON (one automation per car). |
| **Notify when a device goes offline** | Connectivity-based alerts with debounce. |
| **Forward 1KOMMA5° cloud notifications** | Passthrough for `onekommafive_notification` events with optional `type_filter`. |

See the [blueprints README](https://github.com/mrebbert/1komma5-ha/blob/main/blueprints/automation/onekommafive/README.md) for one-click import links.
