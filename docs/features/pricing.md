---
title: Dynamic electricity pricing
description: Dynamischer Stromtarif — 15-minute spot prices, 30-hour forecast, cheapest-charging-window sensors, negative-price counters and the Dynamic-Pulse price guarantee.
---

# Dynamic electricity pricing

Dynamischer Stromtarif: 15-minute-resolution price data, 30-hour forecast, cheapest-window scheduling. Price slots carry an END-timestamp; `get_current_price()` picks the smallest end greater than now.

| Entity | Key | Unit | Update |
|--------|-----|------|--------|
| Current Electricity Price | `current_electricity_price` | EUR/kWh | 15 min |
| Last Valid Electricity Price | `stable_electricity_price` | EUR/kWh | 15 min |
| Average / Lowest / Highest Today | `average/lowest/highest_electricity_price` | EUR/kWh | 1 h |
| Average / Lowest / Highest Tomorrow | `tomorrow_average/lowest/highest_price` | EUR/kWh | 1 h |
| Negative Price Slots (today / tomorrow) | `negative_price_slots_today/tomorrow` | count | 1 h |
| Cheapest Charging Window Today | `cheapest_charging_window_today` | timestamp | 15 min |
| Cheapest Charging Window Tomorrow | `cheapest_charging_window_tomorrow` | timestamp | 15 min |

## Binary sensors

| Entity | ON when |
|--------|---------|
| `cheap_electricity` | Current price is below today's average |
| `cheapest_hour_now` | Current 15-min slot is the cheapest in the next ~30 h |

`stable_electricity_price` is the price source for cost sensors: it survives brief zero/unavailable API responses so cost accumulation does not skip. Tomorrow's price sensors are `unknown` until day-ahead prices are published (typically around 13:00 CET).

## Price-forecast attributes

`current_electricity_price` carries these attributes:

| Attribute | Description |
|-----------|-------------|
| `forecast` | Rolling 24–30 h price list (each entry `{start, end, price}`) |
| `cheapest_future_hour` | ISO-8601 start of the cheapest upcoming slot |
| `cheapest_future_price` | EUR/kWh of that slot |
| `spot_price` | Market/exchange price of the active slot (net, ex grid costs & VAT) |
| `grid_costs` | Net grid-cost adder (energy tax + purchasing + fixed tariff + dynamic markup + feed-in adjustment) |
| `grid_cost_components` | Per-component breakdown (all net / ex-VAT) |
| `vat_rate` | VAT rate applied (e.g. `0.19`) |
| `uses_fallback_grid_costs` | `true` when grid costs are estimated rather than contract-exact |

Decomposition is exact: `all_in = (spot_price + grid_costs) × (1 + vat_rate)`. `spot_price` varies per 15-min slot; grid-cost components are flat daily constants.

Cheapest-window sensors additionally expose `start`, `end`, `average_price`, `duration_minutes`, `slot_count`. The today-sensor locks in the pick (via RestoreSensor) so it does not wander mid-slot; the tomorrow-sensor re-picks on each refresh.

### Forecast list example

Compatible with Tibber / ENTSO-E-style cards like `apexcharts-card`:

```yaml
forecast:
  - start: "2026-02-28T14:00:00+00:00"
    end:   "2026-02-28T14:15:00+00:00"
    price: 0.284100
  - start: "2026-02-28T14:15:00+00:00"
    end:   "2026-02-28T14:30:00+00:00"
    price: 0.279300
  # up to 120 slots (15-min resolution, up to 30 h ahead)

cheapest_future_hour: "2026-02-28T22:00:00+00:00"
cheapest_future_price: 0.198400
```

For a ready-made 30-hour price-forecast chart (`apexcharts-card`, `color_threshold`-coloured), see the "Preise und Kosten" view in [`dashboard/dashboard-showcase.yaml`](https://github.com/mrebbert/1komma5-ha/blob/main/dashboard/dashboard-showcase.yaml). Copy the `custom:apexcharts-card` block, replace the entity prefix, done.

## Dynamic-Pulse price guarantee

DP contract only. `sensor.<sys>_dynamic_pulse_price_guarantee` exposes the raw `price_guarantee_value` from your DP subscription in EUR/kWh. The guarantee comes with terms and conditions on the 1KOMMA5° side that this integration does not (and cannot) model, so treat the value as informational.

!!! warning "Not a hard price cap"
    The guarantee is **not** the maximum price per kWh you will pay. See the [FAQ](../faq.md#is-dynamic_pulse_price_guarantee-the-max-price-ill-pay-per-kwh).

## Negative-price edges

The `negative_price_slots_today` / `_tomorrow` counters land as sensor values; the positive↔negative edge of the *active* slot additionally fires the [`onekommafive_negative_price_started` / `_ended`](../services.md#negative-price-edges) bus event.
