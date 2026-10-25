# Showcase Dashboard

This directory ships one ready-to-import Home Assistant dashboard for the 1KOMMA5° integration: [`dashboard-showcase.yaml`](dashboard-showcase.yaml), six views (Grid / Vehicle / Prices & costs / Optimization / Weather / System) that exercise the full integration surface. The YAML is intentionally kept in German (the integration's primary audience); this README is fully in English.

| Grid (Netz) | Vehicle (Fahrzeug) | Prices & costs (Preise und Kosten) |
|-------------|--------------------|------------------------------------|
| ![Grid view](showcase-netz.png) | ![Vehicle view](showcase-fahrzeug.png) | ![Prices & costs view](showcase-preise-kosten.png) |

| Optimization (Optimierung) | Weather (Wetter) | System |
|----------------------------|------------------|--------|
| ![Optimization view](showcase-optimierung.png) | ![Weather view](showcase-wetter.png) | ![System view](showcase-system.png) |

## Views

| View | What's on it |
|------|--------------|
| Grid (Netz) | Gauges for grid power (bidirectional, colour-coded), PV generation, battery charge/discharge and battery state of charge. Total consumption plus per-consumer gauges (household, heat pump, wallbox). 24-hour power-flow line chart, 7-day grid-import/export and consumption bar charts (daily + monthly deltas) and the battery charge/discharge split. |
| Vehicle (Fahrzeug) | Wallbox-to-vehicle assignment selector (since v0.1.63), charging-mode selector (Smart / Quick / Solar), Smart-Charge settings (current SoC, target SoC, daily departure time), live charging-power gauge plus today's and this month's charged energy and wallbox cost. |
| Prices & costs (Preise und Kosten) | Today's and tomorrow's price extremes, 30-hour price-forecast bar chart with colour tiers (green / orange / red, powered by `apexcharts-card`), accumulated electricity cost and feed-in revenue as statistic cards, a `button-card` time-range switcher (day / week / month / year) driving both the total cost graph and a per-consumer cost graph (heat pump / wallbox / household). |
| Optimization (Optimierung) | Last AI decision (locale-aware enum since v0.1.45), all six AI-decision binaries since v0.1.66 (battery grid charge/discharge, battery no-charge/no-discharge, EV grid charge, heat-pump recommendation), the full AI-decisions timeline as a native Lovelace calendar card (`calendar.SYSTEM_NAME_ai_decisions_calendar`, v0.1.73+ with historical blocks plus a 30 h price-based proxy), today's decision count, and a pointer to the universal calendar-trigger blueprint. |
| Weather (Wetter) | The `weather.SYSTEM_NAME` entity rendered as a full forecast card plus sunshine-duration sensors for today and tomorrow. |
| System | Site + per-asset connectivity binaries, three "active feature" binaries (dynamic tariff / time-of-use / smart charging), all eight diagnostic update-timestamp sensors (live / price / optimization / weather / system_status / energy / notification / heartbeat-prices, since v0.1.65), the §14a-EnWG grid-fee block (enwg14a_module + current rate + Modul-1/Modul-3 annual, v0.1.66–v0.1.72), the contract-overview block (EMP backend, active subscriptions, add-on eligibility, DP price guarantee, energy-trader status, system age; v0.1.68+), and the EMS auto-mode switch (diagnostic-categorised since v0.1.46, GRIDX-backend installs only from v0.1.57 on). |

Every view's header carries context badges (AI status, cheap-now indicator, EMS switch, self-sufficiency ratio, etc.). The cheapest-charging-window value comes from `sensor.SYSTEM_NAME_cheapest_charging_window_today` (`RestoreSensor` lock-in since v0.1.42, no flickering on flat-price days).

## Frontend dependencies

Most cards use native Home Assistant card types. Two custom cards from HACS → Frontend are needed:

| Custom card | Used for | Install |
|-------------|----------|---------|
| [`apexcharts-card`](https://github.com/RomRider/apexcharts-card) | 30-hour price-forecast chart in the Prices & costs view | HACS → Frontend → search "apexcharts-card" |
| [`button-card`](https://github.com/custom-cards/button-card) | Time-range switcher (day / week / month / year) on the cost chart | HACS → Frontend → search "button-card" |

Without these the corresponding sections render as `Custom element doesn't exist`; the rest of the dashboard still works.

## Required Home Assistant helper

The cost view's time-range switcher reads from an `input_select` helper. Create it once via **Settings → Devices & Services → Helpers → Create helper → Dropdown**:

| Property | Value |
|----------|-------|
| Name | `Stromkosten Zeitspanne` |
| Icon | `mdi:calendar` (any) |
| Options | `Täglich`, `Wöchentlich`, `Monatlich`, `Jährlich` |

The option labels and the helper name are German on purpose because the dashboard YAML compares against these literal strings. The resulting `entity_id` must be `input_select.stromkosten_zeitspanne`. Set its initial state (for example `Täglich`) so the chart renders on first load.

## Usage

1. In Home Assistant: **Settings → Dashboards → Add Dashboard** (or open an existing one in edit mode).
2. Click the ⋮ menu → **Edit Dashboard** → **Raw configuration editor**.
3. Paste the contents of [`dashboard-showcase.yaml`](dashboard-showcase.yaml).
4. Replace the placeholders throughout the YAML:

   | Placeholder | Replace with | Where to find it |
   |-------------|-------------|-----------------|
   | `SYSTEM_NAME` | Your system name prefix | **Settings → Devices & Services → 1KOMMA5°**, visible on any entity ID |
   | `WALLBOX` | The wallbox sub-device slug | `wallbox` on single-wallbox sites; the wallbox-name slug on multi-wallbox sites (visible in `select.SYSTEM_NAME_<wallbox>_assigned_vehicle`) |
   | `EV_1_PREFIX`, `EV_2_PREFIX`, … | Entity prefix per EV | Visible on the EV's own entities (`volkswagen_id_4`, or the long `<owner>_<uuid>` for backend test profiles) |
   | `EV_1_SLUG`, `EV_2_SLUG`, … | Slug per EV in the assignment selector | Read `attributes.options` on `select.SYSTEM_NAME_<wallbox>_assigned_vehicle` (e.g. `id_5`, `dummy`) |

   Duplicate the two conditional blocks (Lademodus + Smart-Charge-Einstellungen) once per EV. Sites with a single EV need only the `EV_1_*` block.

   If your 1KOMMA5° device is assigned to a Home Assistant *area*, HA may prefix new entity_ids with the area slug (e.g. `garage_SYSTEM_NAME_…`). Use whatever your install actually generates: Settings → Devices & Services → 1KOMMA5° → click an entity to see its ID.

   **Upgrading from a pre-v0.1.50 install?** Before v0.1.50 the suffix after `SYSTEM_NAME_` was the HA-language-translated entity name (e.g. `..._pv_leistung` in German, `..._pv_power` in English), and sub-device entities carried the translated sub-device name instead of `SYSTEM_NAME`. The showcase uses the stable English code suffix (`_pv_power`, `_heat_pumps_power`, `_electricity_cost`, `_feed_in_revenue`, …) for every entity. Home Assistant preserves your existing entity_ids across upgrades, so on a pre-v0.1.50 install you either rename the sensors under **Settings → Devices & Services → 1KOMMA5° → Entities** to match the showcase, or sed-replace the code suffix in the YAML back to whatever your registry actually holds.

5. Make sure the two custom cards (`apexcharts-card`, `button-card`) and the `input_select.stromkosten_zeitspanne` helper described above exist.
6. The gauge `min` / `max` values default to a typical 6 kW PV / 7 kWh battery / 11 kW wallbox setup — tune them to your hardware. See the comment block at the top of `dashboard-showcase.yaml` for the full list.
