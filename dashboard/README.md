# Example Dashboard

This directory contains an example Home Assistant dashboard for the 1KOMMA5° integration. Most cards use native Home Assistant card types. The **Strompreisentwicklung** and **Monatliche Übersicht** sections additionally require the [apexcharts-card](https://github.com/RomRider/apexcharts-card) custom card (available via HACS).

## Views

### Netz (Energieverbrauch und -erzeugung)

![Energy & Grid view](1k5_energy.png)

The main view is split into two columns and covers:

| Section | Cards |
|---------|-------|
| Netz- und PV-Leistung | Gauge for grid power (bidirectional, colour-coded), PV generation, battery charge/discharge and battery state of charge |
| Verbrauch | Total consumption gauge plus individual gauges for household, heat pump, wallbox and AC |
| Energiebezug und -einspeisung | 7-day bar chart (daily delta) for PV energy, grid import and grid export; today's totals as statistic cards |
| Energieverbrauch | 7-day bar chart (daily delta) for total, household, EV and heat pump energy; today's totals as statistic cards |

The view also shows two **badges** in the header: EMS auto mode switch and self-sufficiency ratio.

### EV (Electric Vehicle)

![EV view](1k5_ev.png)

A focused view for controlling the EV charger, showing:

- Charging mode selector (Smart Charge / Quick Charge / Solar Charge)
- Manual battery level input, target battery level and daily departure time (visible in Smart Charge mode only)

### Preise und Kosten

![Prices & Costs view](1k5_costs.png)

An overview of dynamic electricity prices and accumulated costs, split into four sections:

| Section | Cards |
|---------|-------|
| Dynamische Strompreise | Cheapest future hour and price; line graphs for current, average, lowest and highest electricity price |
| Strompreisentwicklung | 30h price forecast bar chart with colour tiers (green / orange / red), powered by apexcharts-card |
| Stromkosten & Einspeisung | Accumulated electricity cost and feed-in revenue as statistic cards for today, this month and this year |
| Monatliche Übersicht | Grouped monthly bar chart for electricity cost and feed-in revenue over the last 12 months (apexcharts-card) |

## Usage

1. In Home Assistant go to **Settings → Dashboards → Add Dashboard** (or open an existing one in edit mode)
2. Click the ⋮ menu → **Edit Dashboard** → **Raw configuration editor**
3. Paste the content of [`dashboard.yaml`](dashboard.yaml)
4. Replace the two placeholders throughout the YAML:

| Placeholder | Replace with | Where to find it |
|-------------|-------------|-----------------|
| `SYSTEM_NAME` | Your system name prefix | **Settings → Devices & Services → 1KOMMA5°**, visible on any entity ID |
| `CAR_IDENTIFIER` | Your EV entity prefix | Same location, visible on EV charger entities (e.g. `volkswagen_id_4`) |

### Template sensors for cheapest hour & price

The `cheapest_future_hour` and `cheapest_future_price` entities used in the price section are template sensors that read from the `Aktueller Strompreis` attributes. Add the following to your `configuration.yaml` (or a dedicated template file):

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
