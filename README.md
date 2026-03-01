# 1KOMMA5° Home Assistant Integration

[![GitHub Release](https://img.shields.io/github/v/release/mrebbert/1komma5-ha?style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz)
[![Validate](https://img.shields.io/github/actions/workflow/status/mrebbert/1komma5-ha/validate.yml?label=Validate&style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

> [!WARNING]
> **Early Beta — 100% Vibe Coded.** This integration was built entirely with AI assistance and has had very limited real-world testing. Expect rough edges, breaking changes and the occasional hallucinated feature. Use at your own risk.

## Credits

Large parts of this project are inspired by and based on the work of [Alex Birkner](https://github.com/BirknerAlex) and his [hacs_1komma5grad](https://github.com/BirknerAlex/hacs_1komma5grad) integration. Many thanks for paving the way!

---

Unofficial [Home Assistant](https://www.home-assistant.io/) integration for the [1KOMMA5° Heartbeat](https://www.1komma5grad.com/) home energy platform. Exposes your PV system, battery storage, heat pump, EV charger and dynamic electricity prices as sensors and controls.

> **Note:** This is an unofficial integration based on a reverse-engineered API. It may break if 1KOMMA5° changes their backend.

---

## Features

### Sensors

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
| Aktueller Strompreis | Current all-in electricity price | EUR/kWh | 1 h |
| Durchschnittlicher Strompreis | Today's average all-in price | EUR/kWh | 1 h |
| Niedrigster Strompreis | Today's lowest all-in price | EUR/kWh | 1 h |
| Höchster Strompreis | Today's highest all-in price | EUR/kWh | 1 h |
| Ziel-Akkustand | EV target SoC | % | 30 s |
| Lademodus (Sensor) | Current EV charging mode | — | 30 s |

### Price Forecast

The **Aktueller Strompreis** sensor carries a rolling 24-hour price forecast as the `forecast` attribute — compatible with [`apexcharts-card`](https://github.com/RomRider/apexcharts-card) and other custom cards that follow the Tibber/ENTSO-E format:

```yaml
forecast:
  - start: "2026-02-28T14:00:00+00:00"
    end:   "2026-02-28T14:15:00+00:00"
    price: 0.284100
  - start: "2026-02-28T14:15:00+00:00"
    end:   "2026-02-28T14:30:00+00:00"
    price: 0.279300
  ...  # up to 96 slots (15-minute resolution)
```

### Controls

| Entity | Type | Description |
|--------|------|-------------|
| EMS Automatikmodus | Switch | Toggle EMS auto / manual mode |
| Lademodus | Select | Set EV charging mode (SMART_CHARGE / QUICK_CHARGE / SOLAR_CHARGE) |
| Fahrzeug-Akkustand (manuell) | Number | Manually report EV SoC (SMART_CHARGE mode only) |

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
