# 1KOMMA5° Home Assistant Integration

<img src="custom_components/onekommafive/brand/icon.png" align="right" width="100" alt="1KOMMA5° logo">

[![GitHub Release](https://img.shields.io/github/v/release/mrebbert/1komma5-ha?style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz)
[![Validate](https://img.shields.io/github/actions/workflow/status/mrebbert/1komma5-ha/validate.yml?label=Validate&style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

## Credits

Large parts of this project are inspired by and based on the work of [Alex Birkner](https://github.com/BirknerAlex) and his [hacs_1komma5grad](https://github.com/BirknerAlex/hacs_1komma5grad) integration. Many thanks for paving the way!

---

Unofficial [Home Assistant](https://www.home-assistant.io/) integration for the [1KOMMA5° Heartbeat](https://www.1komma5grad.com/) home energy platform. Exposes your PV system, battery storage, heat pump, EV charger and dynamic electricity prices as sensors and controls.

> **Note:** This is an unofficial integration based on a reverse-engineered API, built 100% vibe coded with AI assistance. It may break if 1KOMMA5° changes their backend. Use at your own risk.

---

## Features

### Power Sensors

| Entity | Description | Unit | Update |
|--------|-------------|------|--------|
| PV-Leistung | Solar generation | W | 30 s |
| Batterieleistung | Battery charge (+) / discharge (−) | W | 30 s |
| Batterieladung | Battery state of charge | % | 30 s |
| Netzleistung | Grid import (+) / export (−) | W | 30 s |
| Netzbezug | Raw grid import power (always ≥ 0) | W | 30 s |
| Netzeinspeisung | Raw grid export / feed-in power (always ≥ 0) | W | 30 s |
| Gesamtverbrauch | Total site consumption | W | 30 s |
| Haushaltsverbrauch | Base consumption (excl. smart devices) | W | 30 s |
| Ladeleistung Fahrzeuge | Aggregated EV charger power | W | 30 s |
| Wärmepumpenleistung | Aggregated heat pump power | W | 30 s |
| Klimaanlagenleistung | Aggregated AC power | W | 30 s |
| Autarkiegrad | Self-sufficiency ratio | % | 30 s |
| Aktueller Strompreis | Current all-in price (active 15-min slot) | EUR/kWh | 1 h |
| Durchschnittlicher Strompreis | Today's average all-in price | EUR/kWh | 1 h |
| Niedrigster Strompreis | Today's lowest all-in price | EUR/kWh | 1 h |
| Höchster Strompreis | Today's highest all-in price | EUR/kWh | 1 h |

### Energy Sensors

For every unidirectional power sensor an accompanying energy sensor (kWh) is automatically created. Energy is calculated via **trapezoidal integration** of the 30-second power samples and persisted across Home Assistant restarts. These sensors use `state_class: total_increasing` and are therefore directly compatible with the **Energy Dashboard**.

| Entity | Description | Unit |
|--------|-------------|------|
| PV-Energie | Cumulative solar energy produced | kWh |
| Netzbezug Energie | Cumulative energy drawn from grid | kWh |
| Eingespeiste Energie | Cumulative energy fed into grid | kWh |
| Gesamtverbrauch Energie | Cumulative total site consumption | kWh |
| Haushaltsverbrauch Energie | Cumulative base consumption | kWh |
| Ladeenergie Fahrzeuge | Cumulative EV charging energy | kWh |
| Wärmepumpenenergie | Cumulative heat pump energy | kWh |
| Klimaanlagenenergie | Cumulative AC energy | kWh |

> **Note:** `Batterieleistung` and `Netzleistung` are bidirectional (positive/negative) and therefore excluded — their respective directions are already covered by `Netzbezug Energie` and `Eingespeiste Energie`.

### Price Forecast & Cheapest Hour

The **Aktueller Strompreis** sensor carries several attributes updated every hour:

| Attribute | Description |
|-----------|-------------|
| `forecast` | Rolling 24-hour price forecast (list, see below) |
| `cheapest_future_hour` | ISO-8601 start timestamp of the cheapest upcoming slot |
| `cheapest_future_price` | Price (EUR/kWh) of that slot |

The sensor value always reflects the **active 15-minute slot** (latest slot whose start ≤ now), not just the price at the top of the hour. The `forecast` list covers up to **30 hours** ahead (today + all of tomorrow) and is compatible with [`apexcharts-card`](https://github.com/RomRider/apexcharts-card) and other custom cards that follow the Tibber/ENTSO-E format:

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
  label: Jetzt
header:
  show: true
  title: Strompreis (24h)
  show_states: true
  colorize_states: true
yaxis:
  - min: auto
    decimals: 4
series:
  - entity: sensor.SYSTEMNAME_aktueller_strompreis
    name: Strompreis
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

> Replace `SYSTEMNAME` with your actual entity ID — find it under **Settings → Devices & Services → 1KOMMA5°** on the "Aktueller Strompreis" entity. Adjust the `color_threshold` values to match your tariff.

**Example automation:** start a dishwasher when the cheapest hour is reached:

```yaml
trigger:
  - platform: template
    value_template: >
      {{ now().isoformat() >= state_attr('sensor.1komma5_aktueller_strompreis', 'cheapest_future_hour') }}
```

### EV Charger

One set of entities is created per connected EV charger.

#### Sensors

| Entity | Description | Unit | Update |
|--------|-------------|------|--------|
| Ziel-Akkustand | Current target SoC | % | 30 s |
| Lademodus (Sensor) | Active charging mode | — | 30 s |

#### Controls

| Entity | Type | Description |
|--------|------|-------------|
| Lademodus | Select | Set charging mode (SMART_CHARGE / QUICK_CHARGE / SOLAR_CHARGE) |
| Ziel-Akkustand | Number (0–100 %) | Set the desired target SoC |
| Abfahrtzeit | Time | Set the daily primary departure time |
| Fahrzeug-Akkustand (manuell) | Number (0–100 %) | Manually report current SoC (SMART_CHARGE only) |

#### Example automation: keep manual SoC in sync

The **Fahrzeug-Akkustand (manuell)** entity expects the current battery level to be reported manually to the 1KOMMA5° system. If your EV integration (e.g. Volkswagen WeConnect, Tesla, etc.) already exposes a sensor with the current battery level, you can automate this with the following automation.

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

### EMS Controls

| Entity | Type | Description |
|--------|------|-------------|
| EMS Automatikmodus | Switch | Toggle EMS auto / manual mode |

---

## Example Dashboard

The [`dashboard/`](dashboard/) directory contains a ready-to-use Home Assistant dashboard with two views — one for energy & grid data and one for EV charger control. All cards are native HA types, no extra frontend components needed.

→ [Dashboard README with screenshots](dashboard/README.md)

---

## Installation

### Via HACS (recommended)

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

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **1KOMMA5°**
3. Enter your 1KOMMA5° account e-mail and password
4. If you have multiple systems, select the one you want to integrate

Credentials are stored securely in the Home Assistant config entry.

---

## Requirements

- Home Assistant **2024.2** or newer
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

## Disclaimer

This project is not affiliated with or endorsed by 1KOMMA5°. The API is undocumented and may change without notice.

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
