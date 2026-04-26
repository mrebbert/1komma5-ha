# 1KOMMA5° Home Assistant Integration

<img src="custom_components/onekommafive/brand/icon.png" align="right" width="100" alt="1KOMMA5° logo">

[![GitHub Release](https://img.shields.io/github/v/release/mrebbert/1komma5-ha?style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz)
[![Validate](https://img.shields.io/github/actions/workflow/status/mrebbert/1komma5-ha/validate.yml?label=Validate&style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

Unofficial [Home Assistant](https://www.home-assistant.io/) integration for the [1KOMMA5° Heartbeat](https://www.1komma5grad.com/) home energy platform. Exposes your PV system, battery storage, heat pump, EV charger and dynamic electricity prices as sensors and controls.

---

## Disclaimer

This project is not affiliated with or endorsed by 1KOMMA5°. The API is undocumented and may change without notice.

This is an unofficial integration based on a reverse-engineered API, built 100% vibe coded with AI assistance. It may break if 1KOMMA5° changes their backend. Use at your own risk.

I do not have the means to test this integration broadly across different hardware configurations — a lot of it is "it works for me". My personal setup is:

| Component | Model |
|-----------|-------|
| Hybrid Inverter | Sungrow SH6.0RT-V112 |
| Battery | Sungrow SBR256 |
| Wallbox | go-e homeFix 11 kW |
| EV | Volkswagen ID.4 |
| Heat pump | Stiebel Eltron WPL-A 10 HK 400 Premium |
| Smart meter | DTSU666 |

For example, I do not have an air conditioning unit — yet the API returns AC values for my system. This appears to be a mock provided by the 1KOMMA5° backend for devices that are not physically present.

---

## Features

### Power Sensors

> **Note:** Entity names in Home Assistant depend on your language settings. The table below shows English names; German translations are provided via i18n.

| Entity | Key | Description | Unit | Update |
|--------|-----|-------------|------|--------|
| PV Power | `pv_power` | Solar generation | W | 30 s |
| Battery Power | `battery_power` | Battery charge (+) / discharge (−) | W | 30 s |
| Battery SoC | `battery_soc` | Battery state of charge | % | 30 s |
| Grid Power | `grid_power` | Grid import (+) / export (−) | W | 30 s |
| Grid Import Power | `grid_consumption_power` | Raw grid import power (always ≥ 0) | W | 30 s |
| Grid Export Power | `grid_feed_in_power` | Raw grid export / feed-in power (always ≥ 0) | W | 30 s |
| Total Consumption | `consumption_power` | Total site consumption | W | 30 s |
| Household Consumption | `household_power` | Base consumption (excl. smart devices) | W | 30 s |
| EV Charger Power | `ev_chargers_power` | Aggregated EV charger power | W | 30 s |
| Heat Pump Power | `heat_pumps_power` | Aggregated heat pump power | W | 30 s |
| AC Power | `acs_power` | Aggregated AC power | W | 30 s |
| Self-Sufficiency | `self_sufficiency` | Self-sufficiency ratio | % | 30 s |

### Price Sensors

| Entity | Key | Description | Unit | Update |
|--------|-----|-------------|------|--------|
| Current Electricity Price | `current_electricity_price` | Current all-in price (active 15-min slot) | EUR/kWh | 15 min |
| Last Valid Electricity Price | `stable_electricity_price` | Like above, but holds the last known valid value when the API returns zero or unavailable — used as stable price source for cost calculations | EUR/kWh | 15 min |
| Average Electricity Price | `average_electricity_price` | Today's average all-in price | EUR/kWh | 1 h |
| Lowest Electricity Price | `lowest_electricity_price` | Today's lowest all-in price | EUR/kWh | 1 h |
| Highest Electricity Price | `highest_electricity_price` | Today's highest all-in price | EUR/kWh | 1 h |
| Negative Price Slots Today | `negative_price_slots_today` | Number of 15-min slots today with negative all-in price | — | 1 h |
| Negative Price Slots Tomorrow | `negative_price_slots_tomorrow` | Number of 15-min slots tomorrow with negative all-in price | — | 1 h |
| Average Electricity Price Tomorrow | `tomorrow_average_price` | Tomorrow's average all-in price (available after ~13:00 CET) | EUR/kWh | 1 h |
| Lowest Electricity Price Tomorrow | `tomorrow_lowest_price` | Tomorrow's lowest all-in price | EUR/kWh | 1 h |
| Highest Electricity Price Tomorrow | `tomorrow_highest_price` | Tomorrow's highest all-in price | EUR/kWh | 1 h |

All price sensors use `state_class: measurement`, so Home Assistant automatically records **long-term statistics** (hourly min/max/mean). Price history is visible in the History panel and can be used for trend analysis.

> **Note:** Tomorrow's price sensors show "unknown" until the day-ahead prices are published (typically around 13:00 CET).

#### Price Forecast & Cheapest Hour

The **Current Electricity Price** sensor carries several attributes updated every hour:

| Attribute | Description |
|-----------|-------------|
| `forecast` | Rolling 24-hour price forecast (list, see below) |
| `cheapest_future_hour` | ISO-8601 start timestamp of the cheapest upcoming slot |
| `cheapest_future_price` | Price (EUR/kWh) of that slot |

The sensor value always reflects the **active 15-minute slot** (smallest slot end > now), not just the price at the top of the hour. The `forecast` list covers up to **30 hours** ahead (today + all of tomorrow) and is compatible with [`apexcharts-card`](https://github.com/RomRider/apexcharts-card) and other custom cards that follow the Tibber/ENTSO-E format:

```yaml
forecast:
  - start: "2026-02-28T14:00:00+00:00"
    end:   "2026-02-28T14:15:00+00:00"
    price: 0.284100
  - start: "2026-02-28T14:15:00+00:00"
    end:   "2026-02-28T14:30:00+00:00"
    price: 0.279300
  ...  # up to 120 slots (15-minute resolution, up to 30 h ahead)

cheapest_future_hour: "2026-02-28T22:00:00+00:00"
cheapest_future_price: 0.198400
```

**Visualisation with [apexcharts-card](https://github.com/RomRider/apexcharts-card):**

```yaml
type: custom:apexcharts-card
graph_span: 24h
span:
  start: hour
now:
  show: true
  label: Now
header:
  show: true
  title: Electricity Price (24h)
  show_states: true
  colorize_states: true
yaxis:
  - min: auto
    decimals: 4
series:
  - entity: sensor.SYSTEMNAME_aktueller_strompreis
    name: Electricity Price
    unit: EUR/kWh
    float_precision: 4
    type: column
    data_generator: |
      return entity.attributes.forecast.map(e => [
        new Date(e.start).getTime(),
        e.price
      ]);
    color_threshold:
      - value: 0
        color: "#4caf50"
      - value: 0.25
        color: "#ff9800"
      - value: 0.35
        color: "#f44336"
    show:
      legend_value: false
      name_in_header: false
```

> Replace `SYSTEMNAME` with your actual entity ID — find it under **Settings → Devices & Services → 1KOMMA5°** on the "Current Electricity Price" entity. Adjust the `color_threshold` values to match your tariff.

**Example automation:** start a dishwasher when the cheapest hour is reached:

```yaml
trigger:
  - platform: template
    value_template: >
      {{ now().isoformat() >= state_attr('sensor.SYSTEM_NAME_aktueller_strompreis', 'cheapest_future_hour') }}
```

### Energy Sensors

For every unidirectional power sensor an accompanying energy sensor (kWh) is automatically created. Energy is calculated via **trapezoidal integration** of the 30-second power samples and persisted across Home Assistant restarts. These sensors use `state_class: total_increasing` and are therefore directly compatible with the **Energy Dashboard**.

| Entity | Key | Description | Unit |
|--------|-----|-------------|------|
| PV Energy | `pv_power_energy` | Cumulative solar energy produced | kWh |
| Grid Import Energy | `grid_consumption_power_energy` | Cumulative energy drawn from grid | kWh |
| Grid Export Energy | `grid_feed_in_power_energy` | Cumulative energy fed into grid | kWh |
| Total Consumption Energy | `consumption_power_energy` | Cumulative total site consumption | kWh |
| Household Energy | `household_power_energy` | Cumulative base consumption | kWh |
| EV Charging Energy | `ev_chargers_power_energy` | Cumulative EV charging energy | kWh |
| Heat Pump Energy | `heat_pumps_power_energy` | Cumulative heat pump energy | kWh |
| AC Energy | `acs_power_energy` | Cumulative AC energy | kWh |
| Battery Charge Energy | `battery_charge_power_energy` | Cumulative energy charged into the battery (positive direction only) | kWh |
| Battery Discharge Energy | `battery_discharge_power_energy` | Cumulative energy discharged from the battery (negative direction only) | kWh |

> **Note:** Battery Power and Grid Power are bidirectional (positive/negative) and therefore excluded from the general energy sensors. The battery is covered by the dedicated Battery Charge Energy and Battery Discharge Energy sensors, which split the bidirectional signal into two `total_increasing` sensors — required for the **Energy Dashboard** battery storage configuration.

### Cost & Revenue Sensors

Accumulated monetary sensors derived from energy flow and dynamic pricing. Both use `state_class: total` and `device_class: monetary` and are compatible with the HA **Energy Dashboard**.

| Entity | Key | Description | Unit |
|--------|-----|-------------|------|
| Electricity Cost | `electricity_cost` | Cumulative electricity cost — integrates grid import power × current dynamic price (from *Last Valid Electricity Price*). Guards prevent accumulation when price is unavailable. | EUR |
| Feed-in Revenue | `feed_in_revenue` | Cumulative feed-in revenue — integrates grid export power × a fixed feed-in tariff (default: 0.0803 €/kWh, configurable). | EUR |

The feed-in tariff can be changed at any time under **Settings → Devices & Services → 1KOMMA5° → Configure**.

### Optimization Sensors

Sensors exposing the Heartbeat AI optimization decisions. Updated every 15 minutes.

| Entity | Key | Description | Unit |
|--------|-----|-------------|------|
| Optimization Decisions Today | `optimization_event_count` | Number of AI optimization decisions today. Attributes: list of all decisions with asset, time range and market price. | — |
| Optimization Cost/Savings | `optimization_total_cost` | Aggregated total cost from today's optimization events (if reported by API). | EUR |
| Optimization Energy Bought | `optimization_energy_bought` | Aggregated energy bought through optimizations (if reported by API). | kWh |
| Optimization Energy Sold | `optimization_energy_sold` | Aggregated energy sold through optimizations (if reported by API). | kWh |
| Last Optimization Decision | `optimization_last_decision` | Most recent AI decision (e.g. `BATTERY_CHARGE_FROM_GRID`, `HEATPUMP_RECOMMEND_ON`). Attributes: `asset`, `from`, `to`, `market_price`, `state_of_charge`. | — |

> **Note:** The cost, energy bought and energy sold fields depend on the 1KOMMA5° API providing settlement data. Currently, these fields are not yet populated by the API and the sensors will show "unknown".

### Binary Sensors

| Entity | Key | Description | Update |
|--------|-----|-------------|--------|
| Cheap Electricity | `cheap_electricity` | ON when the current electricity price is below today's average — useful as an automation condition for flexible loads (dishwasher, washing machine, heat pump). Attributes: `current_price`, `average_price`, `difference`. | 15 min |
| Cheapest Hour Now | `cheapest_hour_now` | ON when the current 15-minute slot is the cheapest in the next ~30 hours of forecast. Useful for triggering loads exactly at the cheapest moment. Attributes: `current_price`, `cheapest_price`, `cheapest_slot_start`. | 15 min |

### EV Charger

One set of entities is created per connected EV charger.

#### Sensors

| Entity | Key | Description | Unit | Update |
|--------|-----|-------------|------|--------|
| Target SoC | `ev_target_soc` | Current target SoC | % | 30 s |
| Charging Mode (Sensor) | `ev_charging_mode` | Active charging mode | — | 30 s |

#### Controls

| Entity | Key | Type | Description |
|--------|-----|------|-------------|
| Charging Mode | `ev_charging_mode` | Select | Set charging mode (SMART_CHARGE / QUICK_CHARGE / SOLAR_CHARGE) |
| Target SoC | `ev_target_soc_number` | Number (0–100 %) | Set the desired target SoC |
| Departure Time | `ev_departure_time` | Time | Set the daily primary departure time |
| Vehicle SoC (Manual) | `ev_current_soc` | Number (0–100 %) | Manually report current SoC (SMART_CHARGE only) |

#### Example automation: keep manual SoC in sync

The **Vehicle SoC (Manual)** entity expects the current battery level to be reported manually to the 1KOMMA5° system. If your EV integration (e.g. Volkswagen WeConnect, Tesla, etc.) already exposes a sensor with the current battery level, you can automate this with the following automation.

> **Prerequisite:** You need a sensor that provides the current battery level of your vehicle as a numeric percentage value. Not all EV integrations expose this.

```yaml
alias: "EV SoC sync: vehicle sensor → 1KOMMA5°"
trigger:
  - platform: state
    entity_id: sensor.EV_BATTERY_SENSOR
condition:
  - condition: template
    value_template: >
      {{ states('sensor.EV_BATTERY_SENSOR') | is_number }}
  - condition: template
    value_template: >
      {{ not is_state('number.CAR_IDENTIFIER_fahrzeug_akkustand_manuell', 'unavailable') }}
action:
  - service: number.set_value
    target:
      entity_id: number.CAR_IDENTIFIER_fahrzeug_akkustand_manuell
    data:
      value: "{{ states('sensor.EV_BATTERY_SENSOR') | int }}"
mode: single
```

Replace `EV_BATTERY_SENSOR` with your vehicle's battery sensor entity ID and `CAR_IDENTIFIER` with your EV charger prefix. The second condition ensures the automation only runs in `SMART_CHARGE` mode — the entity is unavailable otherwise.

### Service: `onekommafive.get_cheapest_window`

Find the cheapest contiguous time window in the price forecast — useful for scheduling flexible loads (dishwasher, washing machine, EV, heat pump). Returns the start/end timestamps and the average price.

**Parameters:**

| Field | Required | Description |
|-------|----------|-------------|
| `duration_minutes` | yes | Length of the desired window (multiple of 15) |
| `earliest_start` | no | The window must not start before this time |
| `latest_end` | no | The window must not end after this time |
| `config_entry_id` | no | Required only when multiple 1KOMMA5° systems are configured |

**Response:**

```yaml
found: true
start: "2026-04-27T01:30:00+00:00"
end: "2026-04-27T03:30:00+00:00"
average_price: 0.0823
slot_count: 8
```

**Example automation** — start the dishwasher at the cheapest 2-hour window before 7 AM:

```yaml
trigger:
  - platform: time
    at: "20:00:00"
action:
  - service: onekommafive.get_cheapest_window
    data:
      duration_minutes: 120
      latest_end: "{{ (now().replace(hour=7, minute=0, second=0) + timedelta(days=1)).isoformat() }}"
    response_variable: window
  - if: "{{ window.found }}"
    then:
      - service: switch.turn_on
        target:
          entity_id: switch.dishwasher_start
        # Or schedule via wait_until / time pattern using window.start
```

### EMS Controls

| Entity | Key | Type | Description |
|--------|-----|------|-------------|
| EMS Auto Mode | `ems_auto_mode` | Switch | Toggle EMS auto / manual mode |

### Diagnostic Sensors

These sensors are hidden by default (`entity_category: diagnostic`) and useful for troubleshooting API connectivity.

| Entity | Key | Description |
|--------|-----|-------------|
| Last Live Update | `diag_live_update` | Timestamp of the last successful live data fetch |
| Last Price Update | `diag_price_update` | Timestamp of the last successful price data fetch |
| Last Optimization Update | `diag_optimization_update` | Timestamp of the last successful optimization data fetch |

---

## Example Dashboard

The [`dashboard/`](dashboard/) directory contains a ready-to-use Home Assistant dashboard with two views — one for energy & grid data and one for EV charger control. All cards are native HA types, no extra frontend components needed.

→ [Dashboard README with screenshots](dashboard/README.md)

---

## Installation

### Via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mrebbert&repository=1komma5-ha&category=integration)

Or manually:

1. Open **HACS** → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/mrebbert/1komma5-ha` with category **Integration**
3. Search for **1KOMMA5°** and install it
4. Restart Home Assistant

### Manual

1. Download the [latest release](https://github.com/mrebbert/1komma5-ha/releases/latest) (`onekommafive.zip`)
2. Extract and copy the `onekommafive/` folder to `<config>/custom_components/`
3. Restart Home Assistant

---

## Configuration

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=onekommafive)

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **1KOMMA5°**
3. Enter your 1KOMMA5° account e-mail and password
4. If you have multiple systems, select the one you want to integrate

Credentials are stored securely in the Home Assistant config entry.

### Updating Credentials

Two flows handle credential changes without losing your sensor history:

- **Re-authentication** — If your 1KOMMA5° password changes (or the API rejects authentication), Home Assistant automatically detects this and shows a "Re-authentication required" notification. Click it, enter your new password, and the integration recovers seamlessly.
- **Reconfigure** — To proactively change credentials, go to **Settings → Devices & Services → 1KOMMA5°** → ⋮ menu → **Reconfigure**. Enter the new credentials; the integration reloads with the same `system_id`.

Both flows preserve all sensor history, restored states, and Energy Dashboard configuration.

### Options

After setup, additional options can be configured via **Settings → Devices & Services → 1KOMMA5° → Configure**:

| Option | Default | Description |
|--------|---------|-------------|
| Feed-in Tariff | 0.0803 €/kWh | Feed-in tariff used to calculate the *Feed-in Revenue* sensor. Set this to your actual contract rate (incl. all bonuses). |

---

## Requirements

- Home Assistant **2024.10** or newer
- A 1KOMMA5° account with at least one active system
- The [`onekommafive`](https://github.com/mrebbert/1komma5-api) Python library (installed automatically)

---

## Technical Details

| Property | Value |
|----------|-------|
| API library | [mrebbert/1komma5-api](https://github.com/mrebbert/1komma5-api) |
| Authentication | OAuth2 PKCE (matches the official iOS app flow) |
| IoT class | `cloud_polling` |
| Live data interval | 30 seconds |
| Price data interval | 1 hour |
| HA domain | `onekommafive` |

---

## Development

### Tests

Pure-helper unit tests (no Home Assistant dependency required):

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/pytest
```

Tests live in `tests/` and target the pure functions in `custom_components/onekommafive/helpers.py` (price slot lookup, forecast building, optimization aggregation, cheapest-window search).

To run with coverage:

```bash
.venv/bin/pytest --cov=custom_components/onekommafive --cov-report=term-missing
```

---

## Credits

Large parts of this project are inspired by and based on the work of [Alex Birkner](https://github.com/BirknerAlex) and his [hacs_1komma5grad](https://github.com/BirknerAlex/hacs_1komma5grad) integration. Many thanks for paving the way!
