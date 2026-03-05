# Example Dashboard

This directory contains an example Home Assistant dashboard for the 1KOMMA5° integration. All cards use **native Home Assistant card types** — no custom frontend components required.

## Views

### Netz (Energy & Grid)

![Energy & Grid view](1k5_energy.png)

The main view is split into two columns and covers:

| Section | Cards |
|---------|-------|
| Netz- und PV-Leistung | Gauge for grid power (bidirectional, colour-coded) and PV generation; tiles for grid import and export |
| Batterieleistung | Gauge for battery charge/discharge power and state of charge |
| Verbrauch | Total consumption gauge plus individual gauges for household, heat pump, wallbox and AC |
| Energiebezug und -einspeisung | 7-day bar chart (daily delta) for PV energy, grid import and grid export |
| Gesamtverbrauch Energie | 7-day bar chart (daily delta) for total, household, EV and heat pump energy |
| Dynamische Strompreise | Cheapest future hour and price; line graphs for current, average, lowest and highest electricity price |

The view also shows two **badges** in the header: EMS auto mode switch and self-sufficiency ratio.

### EV (Electric Vehicle)

![EV view](1k5_ev.png)

A focused view for controlling the EV charger, showing:

- Charging mode selector (Smart Charge / Quick Charge / Solar Charge)
- Manual battery level input
- Daily departure time
- Target battery level

## Usage

1. In Home Assistant go to **Settings → Dashboards → Add Dashboard** (or open an existing one in edit mode)
2. Click the ⋮ menu → **Edit Dashboard** → **Raw configuration editor**
3. Paste the content of [`dashboard.yaml`](dashboard.yaml)
4. **Adapt all entity IDs** to match your installation — replace `SYSTEM_NAME` with your own system name prefix (visible on each entity in **Settings → Devices & Services → 1KOMMA5°**)

> The `cheapest_future_hour` and `cheapest_future_price` entities referenced in the price section are template sensors — see the [price forecast documentation](../README.md#price-forecast--cheapest-hour) for setup instructions.
