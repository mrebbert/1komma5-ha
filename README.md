# 1KOMMA5° Home Assistant Integration

![1KOMMA5° logo](https://raw.githubusercontent.com/mrebbert/1komma5-ha/main/custom_components/onekommafive/brand/icon.png)

[![GitHub Release](https://img.shields.io/github/v/release/mrebbert/1komma5-ha?style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz)
[![Validate](https://img.shields.io/github/actions/workflow/status/mrebbert/1komma5-ha/validate.yml?label=Validate&style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/actions/workflows/validate.yml)
[![Tests](https://img.shields.io/github/actions/workflow/status/mrebbert/1komma5-ha/test.yml?label=Tests&style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/blob/main/LICENSE)

Unofficial [Home Assistant](https://www.home-assistant.io/) integration for the [1KOMMA5° Heartbeat](https://www.1komma5grad.com/) home energy platform, distributed via [HACS](https://hacs.xyz). Exposes your PV system, battery storage, heat pump, EV wallbox, dynamic electricity prices and weather forecast as Home Assistant sensors, services and dashboard cards — fully compatible with the Home Assistant Energy Dashboard.

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
| EV | Volkswagen ID.5 |
| Heat pump | Stiebel Eltron WPL-A 10 HK 400 Premium |
| Smart meter | DTSU666 |

---

## Supported devices

This integration surfaces the following components from the 1KOMMA5° Heartbeat platform in Home Assistant:

- **PV / Solar** — production, energy totals
- **Battery storage** (Batteriespeicher) — power, SoC, charge/discharge totals
- **Heat pump** (Wärmepumpe) — power, energy, cost allocation
- **EV wallbox** — charging mode, target SoC, departure time
- **Smart meter** — grid import/export, household consumption
- **Dynamic electricity tariff** (dynamischer Stromtarif) — 30 h price forecast, cheapest-charging-window sensor
- **Weather forecast** — 48 h hourly forecast, sunshine duration

### Localisation

1KOMMA5° currently operates in seven markets (DE, NL, FI, ES, DK, SE, AU). The integration ships UI translations and per-locale currency mappings for all of them, auto-detected from the site's country code:

| Locale | Translations | Currency |
|--------|--------------|----------|
| Germany, Austria | German | EUR |
| Netherlands | Dutch | EUR |
| Finland | Finnish | EUR |
| Spain | Spanish | EUR |
| Denmark | Danish | DKK |
| Sweden | Swedish | SEK |
| Australia | English | AUD |

Cost, revenue and price sensors render in the local currency without any manual configuration.

> **Caveat:** end-to-end functional verification only exists for **Germany** (the developer's own setup). The SDK targets a single global API endpoint, so the integration *should* work in the other markets — but auth flows, data shapes and feature availability may vary regionally. If you're in a non-DE market and something doesn't work, please open a [GitHub issue](https://github.com/mrebbert/1komma5-ha/issues) with the diagnostics dump.

---

## Installation via HACS

This integration is part of the **HACS default store** — no custom repository setup required.

1. Open **HACS** in Home Assistant
2. Search for **1KOMMA5°**
3. Click **Download**
4. Restart Home Assistant

One-click open in HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mrebbert&repository=1komma5-ha&category=integration)

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
| Charging-window duration | 60 min | Length of the *Cheapest charging window today* sensor. Multiple of 15, between 15 and 240 minutes. Raise to 90/120 for longer flexible loads (wash cycles, EV bulk charges); drop to 30 for short loads (boiler, dishwasher quick programmes). Mid-day duration changes invalidate the existing lock-in so the next refresh re-picks with the new length. |

---

## Home Assistant Energy Dashboard setup

All energy sensors use `state_class: total_increasing` and the cost/revenue sensors use `state_class: total` + `device_class: monetary`, so they drop straight into Home Assistant's **Energy Dashboard** with no helper sensors needed.

**Settings → Dashboards → Energy → Add Source** — pick by friendly name:

| Energy Dashboard slot | Friendly name | Underlying key |
|---|---|---|
| Grid consumption (import) | *Grid Import Energy* | `grid_consumption_power_energy` |
| Return to grid (export) | *Grid Export Energy* | `grid_feed_in_power_energy` |
| Solar production | *PV Energy* | `pv_power_energy` |
| Home battery → Energy going in | *Battery Charge Energy* | `battery_charge_power_energy` |
| Home battery → Energy coming out | *Battery Discharge Energy* | `battery_discharge_power_energy` |
| Individual device → Heat pump | *Heat Pump Energy* | `heat_pumps_power_energy` |
| Individual device → EV charger | *EV Charging Energy* | `ev_chargers_power_energy` |
| Individual device → AC | *AC Energy* | `acs_power_energy` |
| Individual device → Household | *Household Energy* | `household_power_energy` |

**Grid pricing:**
On the grid-import source, pick *Use a sensor tracking the total costs* and select **Electricity Cost** (`electricity_cost`). It already integrates the live dynamic price (incl. negative slots), so no static price field needed.

**Return-to-grid revenue:**
On the grid-export source, pick *Use a sensor tracking the total costs* and select **Feed-in Revenue** (`feed_in_revenue`). The underlying tariff is configurable under **Settings → Devices & Services → 1KOMMA5° → Configure**.

> The Battery Power and Grid Power sensors are bidirectional and therefore not Energy-Dashboard-compatible. Use the dedicated charge/discharge and import/export pairs above instead.

---

## Example Home Assistant Dashboard

The [`dashboard/`](dashboard/) directory contains a ready-to-use Home Assistant dashboard with two views — one for energy & grid data and one for EV charger control. All cards are native HA types, no extra frontend components needed.

→ [Dashboard README with screenshots](dashboard/README.md)

---

## Home Assistant Automation Blueprints

Six ready-to-import blueprints in [`blueprints/automation/onekommafive/`](blueprints/automation/onekommafive/):

- **Run during cheapest window** — schedules a switch for the cheapest N-minute window each day (dishwasher, washing machine, EV)
- **Follow cheap electricity** — mirrors a switch to `binary_sensor…_cheap_electricity` for opportunistic loads (water heater, pool pump)
- **Notify on AI grid-charge decision** — pings you whenever the Heartbeat AI starts charging the battery from the grid
- **Notify on negative prices tomorrow** — heads-up when tomorrow's forecast contains at least N negative-price slots (fires around 13:00 CET when tomorrow's prices arrive)
- **EV charge on PV surplus** — toggles a switch ON when the home battery is full AND PV power exceeds a threshold, OFF when either condition fails
- **Notify when a device goes offline** — alerts you when site, inverter, heat pump, meter or wallbox connectivity sensor stays OFF for a configurable debounce

→ [Blueprints README with import instructions](blueprints/automation/onekommafive/README.md)

---

## Devices

Entities are grouped under one system parent device plus per-asset sub-devices, so you can read off each hardware component's manufacturer, model and firmware version at a glance — and assign areas / disable sensors per device:

```
1k5° System (parent)
├── Inverter        (Sungrow / SH6.0RT-V112 / …)
├── Battery         — entities live on the inverter sub-device (hybrid inverter)
├── Heat pump       (Stiebel Eltron / WPMsystem / …)
├── Smart meter     (Chint / DTSU666 / …)
├── Wallbox         (go-e / HOMEfix 11kW / …)
└── Vehicle         (Volkswagen / ID.5 / …)
```

Every sub-device follows the same naming convention: a translated category label as the device name (Inverter / Heat pump / Smart meter / Wallbox / Vehicle), with `manufacturer` and `model` carrying the real hardware values. The asset sub-devices pull from the 1KOMMA5° cloud's `status_and_assets` payload (PII-safe — manufacturer, model, firmware only); the Vehicle sub-device pulls from the EV profile (manufacturer, model). Devices the platform doesn't classify (`Asset.type = UNKNOWN`, e.g. a Shelly Pro 3EM CT-clamp meter behind the smart meter) stay attached to the parent — no empty placeholder devices.

`entity_id`s and `unique_id`s are unchanged versus earlier versions, so long-term statistics, automations, Energy-Dashboard configuration and dashboard cards keep working without any migration.

Installations missing one of the four asset types (e.g. no heat pump, or a grid-only install without PV) have the corresponding sensors **disabled by default**. The entities still exist in the registry so history stays continuous if hardware is added later, but they don't clutter the device list. Re-enable them manually in **Settings → Devices & Services → 1KOMMA5° → Entities** if you want them visible without an asset.

---

## Entities

> **Note:** Entity names in Home Assistant depend on your language settings. The tables below show English names; German translations are provided via i18n.

### Power Sensors

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

### Dynamic price sensors (dynamischer Stromtarif)

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
| Cheapest Charging Window Today | `cheapest_charging_window_today` | Start timestamp of the cheapest contiguous 60-min window remaining today. Attributes: `start`, `end`, `average_price`, `duration_minutes`, `slot_count`. Returns "unknown" once less than 60 min remain today. | timestamp | 15 min |

All price sensors use `state_class: measurement`, so Home Assistant automatically records **long-term statistics** (hourly min/max/mean). Price history is visible in the History panel and can be used for trend analysis.

> **Note:** Tomorrow's price sensors show "unknown" until the day-ahead prices are published (typically around 13:00 CET).

#### Price forecast & cheapest charging window

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
| Heat Pump Cost | `heat_pump_cost` | Cumulative grid-import cost share allocated to the heat pump (`heat_pumps_power / consumption_power × grid_consumption_power × stable_price`). | EUR |
| EV Charger Cost | `ev_charger_cost` | Same allocation for the EV charger(s). | EUR |
| Household Cost | `household_cost` | Same allocation for all remaining household appliances. | EUR |
| AC Cost | `ac_cost` | Same allocation for the air-conditioning unit. The API currently mocks `acs_power` for systems without an AC — this sensor may be non-zero even then. | EUR |
| Feed-in Revenue | `feed_in_revenue` | Cumulative feed-in revenue — integrates grid export power × a fixed feed-in tariff (default: 0.0803 €/kWh, configurable). | EUR |

The four per-consumer cost sensors always sum to `electricity_cost` — when PV/battery cover all consumption, the grid bill is zero and all five sensors stop accumulating together.

The feed-in tariff can be changed at any time under **Settings → Devices & Services → 1KOMMA5° → Configure**.

### Optimization Sensors

Sensors exposing the Heartbeat AI optimization decisions. Updated every 15 minutes.

| Entity | Key | Description | Unit |
|--------|-----|-------------|------|
| Optimization Decisions Today | `optimization_event_count` | Number of AI optimization decisions today. Attributes: list of all decisions with asset, time range and market price. | — |
| Optimization Cost/Savings | `optimization_total_cost` | Aggregated total cost from today's optimization events (if reported by API). | EUR |
| Optimization Energy Bought | `optimization_energy_bought` | Aggregated energy bought through optimizations (if reported by API). | kWh |
| Optimization Energy Sold | `optimization_energy_sold` | Aggregated energy sold through optimizations (if reported by API). | kWh |
| Last Optimization Decision | `optimization_last_decision` | Most recent AI decision. Displayed in your HA locale (e.g. "Batterie aus Netz laden" / "Charge battery from grid") — the underlying state value (`battery_charge_from_grid`, `heatpump_recommend_on`, …) is what automations match on (lowercase, since the underlying enum is lowercased to satisfy HA's translation-key rules). Attributes: `asset`, `from`, `to`, `market_price`, `state_of_charge`. | — |

> **Note:** The cost, energy bought and energy sold fields depend on the 1KOMMA5° API providing settlement data. Currently, these fields are not yet populated by the API and the sensors will show "unknown".

### Binary Sensors

| Entity | Key | Description | Update |
|--------|-----|-------------|--------|
| Cheap Electricity | `cheap_electricity` | ON when the current electricity price is below today's average — useful as an automation condition for flexible loads (dishwasher, washing machine, heat pump). Attributes: `current_price`, `average_price`, `difference`. | 15 min |
| Cheapest Hour Now | `cheapest_hour_now` | ON when the current 15-minute slot is the cheapest in the next ~30 hours of forecast. Useful for triggering loads exactly at the cheapest moment. Attributes: `current_price`, `cheapest_price`, `cheapest_slot_start`. | 15 min |
| AI: Battery grid charging | `optimization_battery_grid_charge` | ON when the AI's currently active BATTERY decision is `BATTERY_CHARGE_FROM_GRID` — the HEMS has decided to pull from the grid right now to bridge upcoming high-price periods. Attributes: `decision`, `from`, `to`, `market_price`, `state_of_charge`. | 15 min |
| AI: Heat pump recommended | `optimization_heat_pump_recommended` | ON when the AI's currently active HEAT_PUMP decision is `HEATPUMP_RECOMMEND_ON` — the HEMS suggests running the heat pump in this slot. Attributes: `decision`, `from`, `to`, `market_price`. | 15 min |
| Site connectivity | `site_connected` | ON when the 1KOMMA5° cloud reports the site as `CONNECTED`. Aggregate signal. Attributes: `site_status`, `asset_count`. | 5 min |
| Inverter / Heat pump / Meter / Wallbox connectivity | `inverter_connected`, `heat_pump_connected`, `meter_connected`, `wallbox_connected` | One ON/OFF per asset type — only registered when the cloud actually reports an asset of that type. AND-logic: ON only when every asset of the type is `CONNECTED`. Attributes: `count`, `connected_count`, `assets` (manufacturer / model / firmware, PII-safe). | 5 min |
| Active features | `dynamic_tariff_active`, `time_of_use_active`, `smart_charging_active` | One Boolean per feature flag returned by the 1KOMMA5° customer-features API. Lets you gate automations on `condition: state binary_sensor.<…>_active is on` without parsing the `aktive_funktionen` attribute list. | 5 min |
| Energy trading active | `energy_trader_active` | ON when the site is enrolled in 1KOMMA5°'s virtual power plant (energy trading). Sourced from `SystemDetails.energy_trader_active`, captured once at setup. | static |
| Dynamic Pulse compatible | `dynamic_pulse_compatible` | ON when the site's hardware/contract qualifies for Dynamic Pulse (dynamic-tariff optimisation). Sourced from `SystemDetails.dynamic_pulse_compatible`. | static |

### EV Charger / Wallbox

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

### EMS Controls

| Entity | Key | Type | Description |
|--------|-----|------|-------------|
| EMS Auto Mode | `ems_auto_mode` | Switch | Toggle EMS auto / manual mode. **Lives in the device card's diagnostic section** — the official 1KOMMA5° app doesn't expose this override, so the toggle is likely cosmetic on the cloud side. Kept in place in case it activates on some setups. |

### Diagnostic Sensors

These sensors are hidden by default (`entity_category: diagnostic`) and useful for troubleshooting API connectivity.

| Entity | Key | Description |
|--------|-----|-------------|
| Last Live Update | `diag_live_update` | Timestamp of the last successful live data fetch |
| Last Price Update | `diag_price_update` | Timestamp of the last successful price data fetch |
| Last Optimization Update | `diag_optimization_update` | Timestamp of the last successful optimization data fetch |
| Last Weather Update | `diag_weather_update` | Timestamp of the last successful weather data fetch |
| Last Connectivity Update | `diag_system_status_update` | Timestamp of the last successful site-status / asset-inventory fetch |
| System age | `system_age_days` | Days since `SystemDetails.earliest_measurement` — i.e. how long the 1KOMMA5° cloud has been collecting data for this site. Unit `d`, `state_class=measurement`. Recomputed on every system-status refresh so it advances by 1 within minutes of midnight. Clamped to 0 on clock skew; `unknown` if `earliest_measurement` is missing or unparseable. |

The integration also reports a structured summary in **Settings → System → Repairs → System Information**: per-coordinator update status, API reachability, SDK version, resolved currency + country code. Use this for bug reports instead of running the full diagnostics download — it's PII-safe (no customer/system identifiers, no addresses).

If your installation has no DeviceGateway (no HEMS box), the EMS auto-mode switch and related EMS fields stay `unavailable`. After several consecutive failures, the integration registers a **Repair Issue** in Settings → Repairs explaining the cause, so you don't need to dig through the logs. The notice auto-resolves the moment EMS data returns.

---

## Services & Events

### Services: `onekommafive.get_cheapest_window` / `get_most_expensive_window`

Find the cheapest (or most expensive) contiguous time window in the price forecast.

- **`get_cheapest_window`** — useful for scheduling flexible loads (dishwasher, washing machine, EV, heat pump) at the cheapest moment.
- **`get_most_expensive_window`** — useful for load shedding (turning loads off during peak prices).

Both services accept the same parameters and return the same shape.

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

### Service: `onekommafive.refresh_now`

Force an immediate refresh of one (or all) data coordinators. Useful after a power outage, for debugging, and as a reset hook in automations (e.g. "after closing the breaker, re-poll live data right away instead of waiting up to 30 s").

**Parameters:**

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `coordinator` | no | `live` | One of `live`, `price`, `optimization`, `weather`, `system_status`, or `all` |
| `config_entry_id` | no | — | Required only when multiple 1KOMMA5° systems are configured |

**Response** (returned only when the caller uses `response_variable:`):

```yaml
refreshed: ["live"]
failed: []
```

`all` refreshes every coordinator in parallel; per-coordinator failures land in `failed` but don't raise — the service always returns the breakdown so callers can branch on it.

**Example automation** — refresh live data when a manual button is pressed:

```yaml
trigger:
  - platform: state
    entity_id: input_button.poll_now
action:
  - service: onekommafive.refresh_now
    data:
      coordinator: all
    response_variable: refresh
  - if: "{{ refresh.failed | length > 0 }}"
    then:
      - service: notify.persistent_notification
        data:
          message: "1KOMMA5° refresh failed: {{ refresh.failed }}"
```

### Bus event: `onekommafive_optimization_decision`

Whenever the integration sees a new optimization decision from the Heartbeat AI, it fires a Home Assistant bus event so you can drive automations from it. The first refresh after a Home Assistant restart fires **one** event for the most recent decision (so the wiring is immediately verifiable in Developer Tools → Events); the day's earlier decisions are not replayed.

**Event data:**

| Field | Type | Description |
|-------|------|-------------|
| `system_id` | string | The 1KOMMA5° system UUID — useful in multi-system setups |
| `asset` | string | `BATTERY` or `HEATPUMP` |
| `decision` | string | `BATTERY_CHARGE_FROM_GRID`, `BATTERY_NO_CHARGE`, `BATTERY_NO_DISCHARGE`, `HEATPUMP_RECOMMEND_ON`, `HEATPUMP_AUTO`, … |
| `from` | string | ISO-8601 start of the optimisation slot |
| `to` | string | ISO-8601 end of the slot |
| `market_price` | float \| null | Market price at decision time, in EUR/MWh |
| `market_price_currency` | string \| null | Typically `EUR` |
| `state_of_charge` | int \| null | Battery SoC at decision time (0–100) |

**Example automation** — turn on a non-essential load whenever the AI plans grid charging (i.e. very cheap or negative prices ahead):

```yaml
trigger:
  - platform: event
    event_type: onekommafive_optimization_decision
    event_data:
      decision: BATTERY_CHARGE_FROM_GRID
action:
  - service: switch.turn_on
    target:
      entity_id: switch.dishwasher
```

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

For setup, PR workflow, code style and translation guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Tests

Pure-helper unit tests (no Home Assistant dependency required):

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

Tests live in `tests/` and target:
- the pure functions in `custom_components/onekommafive/helpers.py` (price slot lookup, forecast building, optimization aggregation, cheapest-window search, trapezoidal integration)
- translation file consistency (`strings.json` ↔ `translations/*.json`)

To run with coverage:

```bash
.venv/bin/pytest --cov=custom_components/onekommafive --cov-report=term-missing
```

---

## Credits

Large parts of this project are inspired by and based on the work of [Alex Birkner](https://github.com/BirknerAlex) and his [hacs_1komma5grad](https://github.com/BirknerAlex/hacs_1komma5grad) integration. Many thanks for paving the way!
