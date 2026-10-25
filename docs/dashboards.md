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

### AI decisions calendar card

Since v0.1.73 the integration ships a `calendar.<system>_ai_decisions_calendar` entity. Drop this native HA card anywhere in Lovelace to see the full AI-decision timeline plus the 30 h price proxy:

```yaml
type: calendar
title: KI-Entscheidungen
initial_view: listWeek
entities:
  - calendar.<system>_ai_decisions_calendar
```

`initial_view` accepts `listWeek` (compact agenda, best for mobile), `dayGridMonth` (month overview), or `timeGridDay` (hourly day view). The card is included in HA core — no extra frontend components.

## Automation blueprints

Eleven importable blueprints in [`blueprints/automation/onekommafive/`](https://github.com/mrebbert/1komma5-ha/tree/main/blueprints/automation/onekommafive):

| Blueprint | What it does |
|-----------|-------------|
| **EV departure time from HA calendar** | Automatically keeps `time.<sys>_<ev>_ev_departure_time` in sync with the next relevant HA-calendar event. Evening preplan (20:00) + morning reconfirm (05:00). Static commute buffer or live travel-time sensor. Fallback for event-free days. |
| **AI decision calendar trigger** | Universal trigger on the AI-decisions calendar — pick one of eight event classes (six AI decisions + `proxy_cheap` / `proxy_expensive`), choose `start` or `end` with optional ±60 min offset, plug in any action. Matches the event's stable `description` key, so the automation stays language-independent. |
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
