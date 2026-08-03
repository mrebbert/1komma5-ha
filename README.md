# 1KOMMA5° Home Assistant Integration

![1KOMMA5° logo](https://raw.githubusercontent.com/mrebbert/1komma5-ha/main/custom_components/onekommafive/brand/icon.png)

[![GitHub Release](https://img.shields.io/github/v/release/mrebbert/1komma5-ha?style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/releases)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://hacs.xyz)
[![Validate](https://img.shields.io/github/actions/workflow/status/mrebbert/1komma5-ha/validate.yml?label=Validate&style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/actions/workflows/validate.yml)
[![Tests](https://img.shields.io/github/actions/workflow/status/mrebbert/1komma5-ha/test.yml?label=Tests&style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://github.com/mrebbert/1komma5-ha/blob/main/LICENSE)

Bring your **1KOMMA5° Heartbeat** solar + battery + heat pump + EV wallbox platform into Home Assistant. Dynamic electricity prices (dynamischer Stromtarif), 30-hour price forecast, AI optimization decisions, per-device cost allocation, cheapest-charging-window scheduling, weather forecast, and cloud push notifications — all as native HA sensors, services and bus events. Fully compatible with the **Home Assistant Energy Dashboard**.

## Highlights

- ⚡ **60+ sensors** across 7 coordinators covering power, energy, cost, dynamic prices, AI decisions, weather and system health
- 💶 **Dynamic tariff support** with 30-hour price forecast, cheapest-window sensors, and per-consumer cost allocation
- 🤖 **AI optimization events** — react to Heartbeat's grid-charge / heat-pump-recommend decisions in real time
- 🔔 **Cloud notification bridge** (v0.1.52) — drive automations from the same push notifications the 1KOMMA5° mobile app receives
- 🌍 **Seven locales** (DE, NL, FI, ES, DK, SE, AU) with per-market currency (EUR, DKK, SEK, AUD)
- 🏠 **Energy Dashboard-ready** out of the box; no template sensors, no manual wiring
- 📥 **Available in the HACS Default Store** — no custom repository setup needed

## Table of Contents

- [Quick start](#quick-start)
- [Configuration](#configuration)
- [What you get](#what-you-get)
  - [Live power & battery](#live-power--battery)
  - [Dynamic electricity pricing](#dynamic-electricity-pricing)
  - [Energy accounting](#energy-accounting)
  - [Cost & revenue](#cost--revenue)
  - [AI optimization](#ai-optimization)
  - [EV charger / wallbox](#ev-charger--wallbox)
  - [Weather](#weather)
  - [Device connectivity & feature flags](#device-connectivity--feature-flags)
  - [Diagnostics](#diagnostics)
- [Services & bus events](#services--bus-events)
- [Ready-made dashboards & automation blueprints](#ready-made-dashboards--automation-blueprints)
- [Devices & entity structure](#devices--entity-structure)
- [Compatibility & requirements](#compatibility--requirements)
- [FAQ / troubleshooting](#faq--troubleshooting)
- [Contributing](#contributing)
- [Credits](#credits)
- [Disclaimer](#disclaimer)

---

## Quick start

### 1. Install via HACS

This integration is in the **HACS Default Store** — no custom repository setup required.

1. Open **HACS** in Home Assistant
2. Search for **1KOMMA5°**
3. Click **Download**
4. Restart Home Assistant

One-click open:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mrebbert&repository=1komma5-ha&category=integration)

<details>
<summary>Manual installation (without HACS)</summary>

1. Download the [latest release](https://github.com/mrebbert/1komma5-ha/releases/latest) (`onekommafive.zip`)
2. Extract and copy the `onekommafive/` folder to `<config>/custom_components/`
3. Restart Home Assistant
</details>

### 2. Add the integration

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=onekommafive)

1. **Settings → Devices & Services → Add Integration**
2. Search for **1KOMMA5°**
3. Enter your 1KOMMA5° account e-mail and password
4. If your account has multiple systems, pick the one you want

Credentials are stored securely in the Home Assistant config entry. Sensors appear within seconds.

---

## Configuration

### Options

Under **Settings → Devices & Services → 1KOMMA5° → Configure**:

| Option | Default | Description |
|--------|---------|-------------|
| Feed-in Tariff | 0.0803 €/kWh | Feed-in tariff used by the *Feed-in Revenue* sensor. Set to your actual contract rate incl. bonuses. |
| Charging-window duration | 60 min | Length of the *Cheapest charging window* sensors. Multiple of 15, 15–240 min. Raise to 90/120 for longer flexible loads (EV bulk charges, wash cycles); drop to 30 for short loads (boiler, quick dishwasher programme). Mid-day duration changes invalidate the lock-in so the next refresh re-picks. |

### Updating credentials

Two flows preserve all sensor history:

- **Re-authentication** — When 1KOMMA5° rejects auth (e.g. password change), HA shows a *Re-authentication required* notice. Click it, enter the new password, done.
- **Reconfigure** — Proactively via **Settings → Devices & Services → 1KOMMA5°** → ⋮ menu → **Reconfigure**.

Both preserve sensor history, restored states and Energy Dashboard configuration.

---

## What you get

Entity names in Home Assistant follow your account language. Tables below use English keys; German (and five other locales) are shipped in the translations.

### Live power & battery

| Entity | Key | Unit |
|--------|-----|------|
| PV Power | `pv_power` | W |
| Battery Power | `battery_power` | W (± bidirectional) |
| Battery SoC | `battery_soc` | % |
| Grid Power | `grid_power` | W (± bidirectional) |
| Grid Import Power | `grid_consumption_power` | W (≥ 0) |
| Grid Export Power | `grid_feed_in_power` | W (≥ 0) |
| Total Consumption | `consumption_power` | W |
| Household Consumption | `household_power` | W |
| EV Charger Power | `ev_chargers_power` | W |
| Heat Pump Power | `heat_pumps_power` | W |
| AC Power | `acs_power` | W |
| Self-Sufficiency | `self_sufficiency` | % |

**Update interval:** 30 s. All sensors use `state_class: measurement`, so Long-Term Statistics tracks hourly min/max/mean automatically.

> **Plotting self-sufficiency trends** — drop the entity into a `statistics-graph` card, or build a [Statistics Helper](https://www.home-assistant.io/integrations/statistics/) for rolling averages. No integration code needed.

### Dynamic electricity pricing

Dynamischer Stromtarif — 15-minute-resolution price data, 30-hour forecast, cheapest-window scheduling.

| Entity | Key | Unit | Update |
|--------|-----|------|--------|
| Current Electricity Price | `current_electricity_price` | EUR/kWh | 15 min |
| Last Valid Electricity Price | `stable_electricity_price` | EUR/kWh | 15 min |
| Average / Lowest / Highest Today | `average/lowest/highest_electricity_price` | EUR/kWh | 1 h |
| Average / Lowest / Highest Tomorrow | `tomorrow_average/lowest/highest_price` | EUR/kWh | 1 h |
| Negative Price Slots (today / tomorrow) | `negative_price_slots_today/tomorrow` | count | 1 h |
| Cheapest Charging Window Today | `cheapest_charging_window_today` | timestamp | 15 min |
| Cheapest Charging Window Tomorrow | `cheapest_charging_window_tomorrow` | timestamp | 15 min |

**Binary sensors:**

| Entity | ON when |
|--------|---------|
| `cheap_electricity` | Current price is below today's average |
| `cheapest_hour_now` | Current 15-min slot is the cheapest in the next ~30 h |

`stable_electricity_price` is the price source for cost sensors: it survives brief zero/unavailable API responses so cost accumulation doesn't skip. Tomorrow's price sensors are `unknown` until day-ahead prices are published (typically around 13:00 CET).

<details>
<summary>Price-forecast attributes & grid-cost decomposition</summary>

**Current Electricity Price** carries these attributes:

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

**Cheapest-window sensors** additionally expose `start`, `end`, `average_price`, `duration_minutes`, `slot_count`. The today-sensor locks in the pick (via RestoreSensor) so it doesn't wander mid-slot; the tomorrow-sensor re-picks on each refresh.

**Forecast list example** (compatible with Tibber / ENTSO-E-style cards like `apexcharts-card`):

```yaml
forecast:
  - start: "2026-02-28T14:00:00+00:00"
    end:   "2026-02-28T14:15:00+00:00"
    price: 0.284100
  - start: "2026-02-28T14:15:00+00:00"
    end:   "2026-02-28T14:30:00+00:00"
    price: 0.279300
  ...  # up to 120 slots (15-min resolution, up to 30 h ahead)

cheapest_future_hour: "2026-02-28T22:00:00+00:00"
cheapest_future_price: 0.198400
```

</details>

<details>
<summary>Ready-to-use apexcharts-card config</summary>

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
  title: Electricity Price (24 h)
  show_states: true
  colorize_states: true
yaxis:
  - min: auto
    decimals: 4
series:
  - entity: sensor.SYSTEMNAME_current_electricity_price
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

Replace `SYSTEMNAME` with your actual entity ID (find it under **Settings → Devices & Services → 1KOMMA5°**).
</details>

### Energy accounting

For every unidirectional power sensor an energy counterpart (kWh) is auto-created via trapezoidal integration of the 30 s power samples. All use `state_class: total_increasing` — direct **Energy Dashboard** compatibility.

| Category | Sensors |
|----------|---------|
| Solar | `pv_power_energy` |
| Grid | `grid_consumption_power_energy`, `grid_feed_in_power_energy` |
| Consumption | `consumption_power_energy`, `household_power_energy` |
| Devices | `ev_chargers_power_energy`, `heat_pumps_power_energy`, `acs_power_energy` |
| Battery | `battery_charge_power_energy`, `battery_discharge_power_energy` |

> **Battery Power and Grid Power are bidirectional** and therefore excluded from the general energy set. The battery is covered by dedicated Charge / Discharge energy sensors that split the signal into two `total_increasing` counters — required for the **Energy Dashboard** battery configuration.

See [`dashboard/ENERGY_DASHBOARD.md`](dashboard/ENERGY_DASHBOARD.md) for the slot-to-sensor mapping and the grid-cost / feed-in-revenue wiring steps.

### Cost & revenue

Monetary sensors integrating power flow × price. `state_class: total`, `device_class: monetary`, per-locale currency.

| Entity | Key | Semantic |
|--------|-----|----------|
| Electricity Cost | `electricity_cost` | Cumulative grid-import cost = grid import × stable price |
| Heat Pump Cost | `heat_pump_cost` | Allocation to heat pump = `heat_pumps_power / consumption_power × grid_consumption_power × stable_price` |
| EV Charger Cost | `ev_charger_cost` | Same allocation for EV charger(s) |
| Household Cost | `household_cost` | Same allocation for base household load |
| AC Cost | `ac_cost` | Same allocation for AC unit |
| Feed-in Revenue | `feed_in_revenue` | Grid export × configured feed-in tariff |
| Daily Savings | `daily_savings` | Cloud-computed daily savings (`get_energy_today`), resets at local midnight |

The four per-consumer cost sensors always sum to `electricity_cost`. When PV/battery cover all consumption the grid bill is zero and all five stop accumulating together. Set the feed-in tariff under **Settings → Devices & Services → 1KOMMA5° → Configure**.

### AI optimization

Heartbeat AI decisions surfaced as sensors and binary sensors, updated every 15 minutes.

| Entity | Key | Description |
|--------|-----|-------------|
| Optimization Decisions Today | `optimization_event_count` | Count of today's decisions; attribute holds the full list |
| Last Optimization Decision | `optimization_last_decision` | Most-recent decision (localized display, underlying enum stays lowercase for automation matching) |
| AI: Battery grid charging | `optimization_battery_grid_charge` | Binary — ON when the active BATTERY decision is `BATTERY_CHARGE_FROM_GRID` |
| AI: Heat pump recommended | `optimization_heat_pump_recommended` | Binary — ON when the active HEAT_PUMP decision is `HEATPUMP_RECOMMEND_ON` |

Available decision enum values: `BATTERY_CHARGE_FROM_GRID`, `BATTERY_NO_CHARGE`, `BATTERY_NO_DISCHARGE`, `HEATPUMP_RECOMMEND_ON`, `HEATPUMP_AUTO`.

> **Note:** `optimization_total_cost`, `optimization_energy_bought` and `optimization_energy_sold` exist but stay `unknown` — the API doesn't populate settlement data yet.

Bus event `onekommafive_optimization_decision` fires per new decision — see [Services & bus events](#services--bus-events).

### EV charger / wallbox

One set of entities per connected EV charger.

**Sensors:** `ev_target_soc` (%), `ev_charging_mode` (mode enum), `ev_battery_capacity` (kWh), `ev_scheduled_departure_soc` (%)

**Controls:**

| Entity | Type | Description |
|--------|------|-------------|
| Charging Mode | Select | `SMART_CHARGE` / `QUICK_CHARGE` / `SOLAR_CHARGE` |
| Target SoC | Number (0–100 %) | Desired battery target |
| Departure Time | Time | Daily primary departure |
| Vehicle SoC (Manual) | Number (0–100 %) | Manual current-SoC report (SMART_CHARGE only) |

<details>
<summary>Automation: sync manual SoC from your car integration</summary>

If your EV integration exposes a battery-level sensor (e.g. Volkswagen WeConnect, Tesla), mirror it into 1KOMMA5°:

```yaml
alias: "EV SoC sync: vehicle sensor → 1KOMMA5°"
trigger:
  - platform: state
    entity_id: sensor.EV_BATTERY_SENSOR
condition:
  - condition: template
    value_template: "{{ states('sensor.EV_BATTERY_SENSOR') | is_number }}"
  - condition: template
    value_template: "{{ not is_state('number.CAR_IDENTIFIER_fahrzeug_akkustand_manuell', 'unavailable') }}"
action:
  - service: number.set_value
    target:
      entity_id: number.CAR_IDENTIFIER_fahrzeug_akkustand_manuell
    data:
      value: "{{ states('sensor.EV_BATTERY_SENSOR') | int }}"
mode: single
```

Replace `EV_BATTERY_SENSOR` with your vehicle's battery sensor and `CAR_IDENTIFIER` with your EV charger prefix. The second condition ensures the automation only runs in `SMART_CHARGE` mode (the target entity is `unavailable` otherwise).
</details>

### Weather

- **Weather entity** (`weather.<system>`) — 48 h hourly forecast, `FORECAST_HOURLY` compatible
- **Sunshine sensors** — `weather_sunshine_today`, `weather_sunshine_tomorrow` (minutes)

### Device connectivity & feature flags

Binary sensors summarising cloud & asset health:

| Entity | Description |
|--------|-------------|
| `site_connected` | Aggregate — ON when the cloud reports the site as `CONNECTED` |
| `inverter_connected`, `heat_pump_connected`, `meter_connected`, `wallbox_connected` | Per-asset-type; AND-logic over all assets of the type. Only created when the cloud actually reports an asset of that type. |
| `dynamic_tariff_active`, `time_of_use_active`, `smart_charging_active` | Feature-flag Booleans from the customer-features API |
| `energy_trader_active` | ON when enrolled in 1KOMMA5°'s virtual power plant (energy trading). From `SystemDetails.energy_trader_active`, captured once at setup. |
| `dynamic_pulse_compatible` | ON when the site's hardware/contract qualifies for Dynamic Pulse |

Plus: `active_features` sensor (state = count; attributes = feature list) and `system_age_days` (days since earliest measurement).

### Diagnostics

Hidden by default (`entity_category: diagnostic`) — useful for troubleshooting.

| Entity | Description |
|--------|-------------|
| `diag_live_update` | Timestamp of the last successful live data fetch |
| `diag_price_update` | Timestamp of the last successful price fetch |
| `diag_optimization_update` | Timestamp of the last optimization fetch |
| `diag_weather_update` | Timestamp of the last weather fetch |
| `diag_system_status_update` | Timestamp of the last site-status / asset-inventory fetch |
| `diag_energy_update` | Timestamp of the last daily-savings fetch |
| `diag_notification_update` | Timestamp of the last cloud-notifications fetch (v0.1.52) |

**System Information** (**Settings → System → Repairs → System Information**) reports per-coordinator update status, API reachability, SDK version and resolved currency/country. **PII-safe** — no customer/system identifiers or addresses. Use this for bug reports instead of the full diagnostics download.

If your install has no DeviceGateway (no HEMS box) the EMS fields stay `unavailable`. After several consecutive failures the integration registers a **Repair Issue** in Settings → Repairs; it auto-resolves the moment EMS data returns.

**EMS auto-mode switch** (`ems_auto_mode`, diagnostic section) — kept in place in case it activates on some setups, but the official 1KOMMA5° app doesn't expose an equivalent override; the toggle is likely cosmetic on the cloud side.

---

## Services & bus events

### `onekommafive.get_cheapest_window` / `get_most_expensive_window`

Find the cheapest (or most expensive) contiguous slot in the price forecast — for scheduling flexible loads or load shedding.

| Field | Required | Description |
|-------|----------|-------------|
| `duration_minutes` | yes | Window length (multiple of 15) |
| `earliest_start` | no | Window must not start before |
| `latest_end` | no | Window must not end after |
| `config_entry_id` | no | Only required with multiple systems configured |

**Response:**

```yaml
found: true
start: "2026-04-27T01:30:00+00:00"
end: "2026-04-27T03:30:00+00:00"
average_price: 0.0823
slot_count: 8
```

<details>
<summary>Example: start the dishwasher at the cheapest 2-hour window before 7 AM</summary>

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
```

</details>

### `onekommafive.refresh_now`

Force an immediate refresh of one (or all) data coordinators. Useful after a power outage, for debugging, and as a reset hook in automations.

| Field | Default | Description |
|-------|---------|-------------|
| `coordinator` | `live` | One of `live`, `price`, `optimization`, `weather`, `system_status`, `energy`, `notifications`, `all` |
| `config_entry_id` | — | Only required with multiple systems configured |

Response: `{"refreshed": [...], "failed": [...]}`. `all` runs every coordinator in parallel; per-coordinator failures land in `failed` but don't raise.

### Bus event: `onekommafive_notification` (v0.1.52)

Fires once per newly-observed 1KOMMA5° cloud notification (energy market thresholds, system health alerts, dynamic-pulse events, …). Enables automations that react to the same push notifications the mobile app receives — no email/webhook/tap-detection needed.

**Event data (flat JSON):**

| Field | Type | Description |
|-------|------|-------------|
| `system_id` | string | System UUID |
| `notification_id` | string | Unique per notification |
| `type` | string | e.g. `ENERGY_MARKET_UPPER_TARGET_REACHED`, `SYSTEM_HEALTH` |
| `title` | string \| null | Already localized to your account language |
| `body` | string \| null | Already localized |
| `locale` | string \| null | e.g. `"de"` |
| `created_at` | string \| null | ISO-8601 |
| `meta` | dict | Type-specific extras (e.g. `meta.price.value` for price thresholds) |

**Semantics:** dedup state persists across HA restarts via `homeassistant.helpers.storage.Store` under `.storage/onekommafive.notifications.<entry_id>`. First refresh after a fresh install primes silently — no replay of history. Which notification types reach HA is controlled entirely by your **1KOMMA5° app** notification settings (Settings → Notifications); the API filters at source.

<details>
<summary>Example: surface every cloud notification as an HA persistent notification</summary>

```yaml
alias: 1KOMMA5° notification passthrough
trigger:
  - platform: event
    event_type: onekommafive_notification
action:
  - service: persistent_notification.create
    data:
      title: "1KOMMA5°: {{ trigger.event.data.title }}"
      message: "{{ trigger.event.data.body }}"
      notification_id: "onekommafive_{{ trigger.event.data.notification_id }}"
```

Filter by `type` (e.g. `event_data: {type: ENERGY_MARKET_UPPER_TARGET_REACHED}`) to react only to specific notification kinds.
</details>

### Bus event: `onekommafive_optimization_decision`

Fires per new Heartbeat AI decision (BATTERY / HEATPUMP). First refresh after HA start fires one event for the most recent decision so the wiring is immediately verifiable in Developer Tools → Events; earlier decisions of the day are not replayed.

| Field | Type | Description |
|-------|------|-------------|
| `system_id` | string | System UUID |
| `asset` | string | `BATTERY` or `HEATPUMP` |
| `decision` | string | `BATTERY_CHARGE_FROM_GRID`, `HEATPUMP_RECOMMEND_ON`, … |
| `from`, `to` | string | ISO-8601 slot range |
| `market_price` | float \| null | EUR/MWh |
| `market_price_currency` | string \| null | Typically `EUR` |
| `state_of_charge` | int \| null | Battery SoC at decision time (0–100) |

<details>
<summary>Example: turn on a non-essential load when the AI plans grid charging</summary>

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

</details>

### Bus events: `onekommafive_negative_price_started` / `onekommafive_negative_price_ended`

Fired on positive↔negative edges of the active 15-min slot. First refresh after HA start primes the tracker without firing. Granularity = coordinator interval (1 h).

**Event data:** `system_id` (string), `price` (float, EUR/kWh), `negative_price_slots_remaining` (int).

See the `notify_negative_price_started.yaml` blueprint for a ready-made notification automation.

---

## Ready-made dashboards & automation blueprints

**Dashboards** — [`dashboard/`](dashboard/) contains two ready-to-import Home Assistant dashboards (energy & grid + EV charger). All cards are native HA types, no extra frontend components needed. [Dashboard README with screenshots](dashboard/README.md).

**Automation blueprints** — seven importable blueprints in [`blueprints/automation/onekommafive/`](blueprints/automation/onekommafive/):

- **Run during cheapest window** — schedule a switch for the cheapest N-min window daily (dishwasher, washer, EV)
- **Follow cheap electricity** — mirror a switch to `binary_sensor…_cheap_electricity` for opportunistic loads
- **Notify on AI grid-charge decision** — ping on `BATTERY_CHARGE_FROM_GRID`
- **Notify on negative prices tomorrow** — heads-up when tomorrow has ≥ N negative slots (fires ~13:00 CET)
- **Notify when the grid pays you** — instant alert on positive↔negative edge, built on the bus event
- **EV charge on PV surplus** — toggle a switch ON when battery is full AND PV exceeds a threshold
- **Notify when a device goes offline** — connectivity-based alerts with debounce

→ [Blueprints README with import instructions](blueprints/automation/onekommafive/README.md)

---

## Devices & entity structure

Entities are grouped under one system parent device plus per-asset sub-devices — read off each hardware component's manufacturer, model and firmware version at a glance, assign areas / disable sensors per device:

```
1k5° System (parent)
├── Inverter        (Sungrow / SH6.0RT-V112 / …)
├── Battery         — entities live on the inverter sub-device (hybrid inverter)
├── Heat pump       (Stiebel Eltron / WPMsystem / …)
├── Smart meter     (Chint / DTSU666 / …)
├── Wallbox         (go-e / HOMEfix 11kW / …)
└── Vehicle         (Volkswagen / ID.5 / …)
```

Sub-device data is **PII-safe**: only `manufacturer`, `model`, `firmware` are pulled from the cloud `status_and_assets` payload; the Vehicle sub-device pulls `manufacturer` and `model` from the EV profile. Unclassified assets (`Asset.type = UNKNOWN`, e.g. a Shelly Pro 3EM CT-clamp meter behind the smart meter) stay attached to the parent — no empty placeholder devices.

`entity_id`s and `unique_id`s are stable across releases — long-term statistics, automations, Energy-Dashboard configuration and dashboard cards keep working without migration.

Installs missing an asset type (e.g. no heat pump, or grid-only without PV) have the corresponding sensors **disabled by default**. The entities still exist in the registry so history stays continuous if hardware is added later. Re-enable manually under **Settings → Devices & Services → 1KOMMA5° → Entities**.

---

## Compatibility & requirements

- **Home Assistant** 2024.10 or newer
- A **1KOMMA5° account** with at least one active system
- The [`onekommafive`](https://github.com/mrebbert/1komma5-api) Python library (installed automatically)

### Supported markets

1KOMMA5° operates in seven markets. The integration ships translations and per-locale currency for all of them, auto-detected from the site's country code:

| Locale | Translations | Currency |
|--------|--------------|----------|
| Germany, Austria | German | EUR |
| Netherlands | Dutch | EUR |
| Finland | Finnish | EUR |
| Spain | Spanish | EUR |
| Denmark | Danish | DKK |
| Sweden | Swedish | SEK |
| Australia | English | AUD |

Cost, revenue and price sensors render in the local currency without manual configuration.

> **Caveat:** end-to-end functional verification exists only for **Germany** (the developer's own setup). The SDK targets a single global API endpoint, so the integration *should* work in other markets — but auth flows, data shapes and feature availability may vary regionally. If something doesn't work in a non-DE market, please open a [GitHub issue](https://github.com/mrebbert/1komma5-ha/issues) with the diagnostics dump.

### Technical details

| Property | Value |
|----------|-------|
| API library | [mrebbert/1komma5-api](https://github.com/mrebbert/1komma5-api) |
| Authentication | OAuth2 PKCE (matches the official iOS app flow) |
| IoT class | `cloud_polling` |
| Coordinators | 7 (live 30 s, price 1 h, optimization 15 min, weather 1 h, system_status 5 min, energy 15 min, notifications 5 min) |
| HA domain | `onekommafive` |

---

## FAQ / troubleshooting

### Why does HACS not show the latest release yet?

HACS refreshes each user's cache roughly every 60–90 min. To force it immediately: open HACS in the HA UI, find **1KOMMA5°**, click the three-dot menu, and choose **Redownload** (or **Reload**). No harm in waiting an hour or two either.

### Why is the EMS auto-mode switch unavailable?

Your install has no DeviceGateway (no HEMS box). The integration registers a Repair Issue in **Settings → Repairs** after a few consecutive failures. It auto-resolves the moment EMS data returns.

### Why do some optimization sensors show `unknown`?

`optimization_total_cost`, `optimization_energy_bought`, and `optimization_energy_sold` depend on settlement data that the 1KOMMA5° cloud API does not currently populate. `optimization_event_count` and `optimization_last_decision` work independently.

### Why is `sensor.<system>_diag_price_update` stuck at `unknown` right after a restart?

Diagnostic timestamps only advance after the coordinator's first *post-add* refresh. Slow-interval coordinators (price 1 h, weather 1 h) can therefore sit at `unknown` for up to their interval after HA start. To prime immediately, call `onekommafive.refresh_now` with the coordinator name.

### Which notification types reach HA via `onekommafive_notification`?

Whatever the 1KOMMA5° cloud returns — which honours your per-type subscription settings in the 1KOMMA5° app (Settings → Notifications). Types you have disabled in the app don't produce HA events. There is no HA-side subscription control.

### My entity names look wrong ("1k5 …" prefix vs. plain name)

Entity naming is composed from `device.name + entity original_name` unless you renamed the entity in the HA UI. Mixed prefixes in one install typically mean some entities were renamed manually. The `entity_id` and long-term statistics are unaffected.

### The Energy Dashboard shows no data / wrong data

See [`dashboard/ENERGY_DASHBOARD.md`](dashboard/ENERGY_DASHBOARD.md) for the slot-to-sensor mapping. The two most common misconfigurations: (a) using `battery_power` (bidirectional) instead of `battery_charge_power_energy` + `battery_discharge_power_energy`; (b) using the raw `grid_power` instead of the split `grid_consumption_power_energy` + `grid_feed_in_power_energy`.

### How do I file a good bug report?

Grab the **System Information** dump from **Settings → System → Repairs → System Information** (PII-safe — no customer/system identifiers or addresses). Attach it to a [GitHub issue](https://github.com/mrebbert/1komma5-ha/issues) with a short reproducer.

---

## Contributing

For setup, PR workflow, code style and translation guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

<details>
<summary>Running the test suite</summary>

Pure-helper unit tests (no HA dependency):

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

Full integration tests (require HA):

```bash
.venv/bin/pip install -e ".[test-integration]"
.venv/bin/pytest tests/integration
```

With coverage:

```bash
.venv/bin/pytest --cov=custom_components/onekommafive --cov-report=term-missing
```

</details>

---

## Credits

Large parts of this project are inspired by and based on the work of [Alex Birkner](https://github.com/BirknerAlex) and his [hacs_1komma5grad](https://github.com/BirknerAlex/hacs_1komma5grad) integration. Many thanks for paving the way.

---

## Disclaimer

This project is **not affiliated with or endorsed by 1KOMMA5°**. The API is undocumented and may change without notice.

This is an unofficial integration based on a reverse-engineered API, built 100 % vibe-coded with AI assistance. It may break if 1KOMMA5° changes their backend. Use at your own risk.

The developer does not have the means to test broadly across hardware configurations — a lot of it is "it works for me". Personal test setup:

| Component | Model |
|-----------|-------|
| Hybrid Inverter | Sungrow SH6.0RT-V112 |
| Battery | Sungrow SBR256 |
| Wallbox | go-e homeFix 11 kW |
| EV | Volkswagen ID.5 |
| Heat pump | Stiebel Eltron WPL-A 10 HK 400 Premium |
| Smart meter | DTSU666 |
