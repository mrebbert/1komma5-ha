# Example Dashboard

This directory contains an example Home Assistant dashboard for the 1KOMMA5° integration. The dashboard YAML itself is intentionally kept in German (the integration's primary audience), but this README is fully in English.

## Frontend dependencies

Most cards use native Home Assistant card types. The dashboard additionally requires two custom cards (both available via HACS → Frontend):

| Custom card | Used for | HACS link |
|-------------|----------|-----------|
| [`apexcharts-card`](https://github.com/RomRider/apexcharts-card) | Price-forecast section — 30-hour bar chart with colour tiers | search "apexcharts-card" |
| [`button-card`](https://github.com/custom-cards/button-card) | Time-range switcher (day / week / month / year) on the cost chart | search "button-card" |

Without those cards installed the corresponding sections render as `Custom element doesn't exist` errors; the rest of the dashboard still works.

## Required Home Assistant helpers

The cost view's time-range switcher reads from an `input_select` helper. Create it once via **Settings → Devices & Services → Helpers → Create helper → Dropdown**:

| Property | Value |
|----------|-------|
| Name | `Stromkosten Zeitspanne` |
| Icon | `mdi:calendar` (any) |
| Options | `Täglich`, `Wöchentlich`, `Monatlich`, `Jährlich` |

The option labels and the helper name are German on purpose because the dashboard YAML compares against these literal strings. The resulting `entity_id` must be `input_select.stromkosten_zeitspanne`. After creating it, set its initial state (for example to `Täglich`) so the chart renders on first load.

## Views

### Grid (energy use and generation)

![Home Assistant Energy & Grid dashboard view](1komma5-home-assistant-energy.png)

The main view groups gauges, daily/monthly bar charts and a 24-hour line chart:

| Section | Cards |
|---------|-------|
| Grid and PV power | Gauges for grid power (bidirectional, colour-coded), PV generation, battery charge/discharge and battery state of charge |
| Consumption | Total consumption gauge plus individual gauges for household, heat pump, wallbox and AC |
| Daily grid import / export | 7-day bar chart (daily delta) for PV energy, grid import and grid export; today's totals as statistic cards |
| Daily consumption | 7-day bar chart (daily delta) for total, household, EV and heat pump energy; today's totals as statistic cards |
| Monthly grid import / export | 6-month bar chart (monthly delta); current-month totals as statistic cards |
| 24-hour power flow | Full-width line chart of grid power, battery power, PV power and total consumption over the last 24 hours, sampled every 5 min |
| Monthly consumption | 6-month bar chart for consumption per device class; current-month totals as statistic cards |

The view header shows four **badges**: EMS auto mode switch, self-sufficiency ratio, the `Cheap electricity` binary sensor and the current electricity price.

### EV (electric vehicle)

![Home Assistant EV charging dashboard view](1komma5-home-assistant-ev.png)

A focused view for controlling the EV charger:

- Charging mode selector (Smart Charge / Quick Charge / Solar Charge)
- Manual battery level input, target battery level and daily departure time (visible in Smart Charge mode only)

### Prices and costs

![Home Assistant dynamic electricity prices & costs dashboard view](1komma5-home-assistant-costs.png)

An overview of dynamic electricity prices and accumulated costs, split into four sections:

| Section | Cards |
|---------|-------|
| Dynamic electricity prices | Cheapest future hour and price; line graphs for current, average, lowest and highest electricity price |
| Price forecast | 30-hour price-forecast bar chart with colour tiers (green / orange / red), powered by `apexcharts-card` |
| Cost / feed-in totals | Accumulated electricity cost and feed-in revenue as statistic cards for today, this month and this year |
| Cost & feed-in (switcher) | `button-card` row to switch between day / week / month / year; below it a `statistics-graph` that follows the selected range |
| Per-consumer costs | Same switcher drives a second `statistics-graph` showing the four per-consumer cost sensors (heat pump / wallbox / household / AC) for the same range |

## Usage

1. In Home Assistant go to **Settings → Dashboards → Add Dashboard** (or open an existing one in edit mode).
2. Click the ⋮ menu → **Edit Dashboard** → **Raw configuration editor**.
3. Paste the contents of [`dashboard.yaml`](dashboard.yaml).
4. Replace the two placeholders throughout the YAML:

   | Placeholder | Replace with | Where to find it |
   |-------------|-------------|-----------------|
   | `SYSTEM_NAME` | Your system name prefix | **Settings → Devices & Services → 1KOMMA5°**, visible on any entity ID |
   | `CAR_IDENTIFIER` | Your EV entity prefix | Same location, visible on EV charger entities (e.g. `volkswagen_id_4`) |

5. Make sure the two custom cards (`apexcharts-card`, `button-card`) and the `input_select.stromkosten_zeitspanne` helper described above exist.

### Template sensors for the cheapest hour and price

The `cheapest_future_hour` and `cheapest_future_price` entities used in the price section are template sensors that read from the current-electricity-price sensor's attributes. Add the following to your `configuration.yaml` (or a dedicated template file):

```yaml
template:
  - sensor:
      - name: "Cheapest future hour"
        unique_id: cheapest_future_hour
        icon: mdi:clock-outline
        availability: >
          {{ state_attr('sensor.SYSTEM_NAME_aktueller_strompreis', 'cheapest_future_hour') is not none }}
        state: >
          {{ state_attr('sensor.SYSTEM_NAME_aktueller_strompreis', 'cheapest_future_hour')
            | as_datetime | as_timestamp | timestamp_custom('%d.%m. %H:%M') }}

      - name: "Cheapest future price"
        unique_id: cheapest_future_price
        icon: mdi:currency-eur
        unit_of_measurement: EUR/kWh
        availability: >
          {{ state_attr('sensor.SYSTEM_NAME_aktueller_strompreis', 'cheapest_future_price') is not none }}
        state: >
          {{ state_attr('sensor.SYSTEM_NAME_aktueller_strompreis', 'cheapest_future_price')
            | round(4) }}
```

Replace `SYSTEM_NAME` with your system name prefix, then restart Home Assistant.
