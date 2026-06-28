# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed
- Per-asset connectivity binary sensors no longer duplicate the asset type in their display name. Since the v0.1.44 sub-device split, HA composed `<device-name> + <entity-name>` — so a sensor on the "Wechselrichter" sub-device whose translation said "Wechselrichter verbunden" rendered as "Wechselrichter Wechselrichter verbunden". The four asset-type translations (`inverter_connected` / `heat_pump_connected` / `meter_connected` / `wallbox_connected`) are now just the past-participle word ("Verbunden" / "Connected" / "Verbonden" / "Conectado" / "Forbundet" / "Ansluten" / "Yhdistetty") across all seven locales — the device name carries the noun. `site_connected` stays unchanged (lives on the parent device, not duplicated). `entity_id`s and `unique_id`s are unchanged; existing automations and dashboards keep working.

## [0.1.46] - 2026-06-28

### Changed
- The EV (vehicle) sub-device now follows the same naming convention as the asset sub-devices shipped in v0.1.44: a translated label ("Elektrofahrzeug" / "Vehicle") as the device name, with `manufacturer` and `model` carrying the actual vehicle make ("Volkswagen") and model ("Id.5") from the EV profile. Before this version the device was named after the specific car with `manufacturer="1KOMMA5°"` and `model="EV Charger"` — semantically wrong (the wallbox is the charger; 1KOMMA5° is the integration vendor, not the car maker) and inconsistent with the other sub-devices. `entity_id`s and `unique_id`s stay; long-term statistics, automations and Energy-Dashboard config are unaffected. **Existing installs** may need to disable + re-enable the integration once for the new naming to be picked up — a plain HA restart does not always re-merge the device registry.
- New `device.vehicle.name` translation key in all seven shipped locales (de/en/nl/es/da/sv/fi).

## [0.1.45] - 2026-06-27

### Added
- **Multi-currency support** — every monetary sensor (cost / per-consumer cost / feed-in revenue / electricity price) now picks its `unit_of_measurement` from the site's country code. Correct unit out of the box in DK (DKK), SE (SEK) and AU (AUD); EUR continues to be the default for the four eurozone markets and unknown countries. Existing installs see no change to their unit.
- **Per-feature binary sensors** — three new Booleans (`dynamic_tariff_active`, `time_of_use_active`, `smart_charging_active`) reflect the cloud's customer-feature flags. Lets automations gate on `condition: state binary_sensor.X is on` instead of parsing the `aktive_funktionen` attribute list. The counter sensor stays for backward compatibility.
- **EMS-unavailable Repair Issue** — when `get_ems_settings()` fails for several refreshes in a row (most commonly: install has no DeviceGateway / no HEMS box), HA registers a Repair Issue in Settings → Repairs explaining the cause. Auto-resolves the moment EMS data returns.
- **System Health page** — Settings → System → Repairs → System Information now surfaces per-coordinator status, API reachability, SDK version, resolved currency and country code. Useful as the "paste this into bug reports" panel; strictly PII-safe (no customer_id, no addresses, no system_id).
- **Five new translation locales** — `nl`, `es`, `da`, `sv`, `fi`. Together with the existing German + English files, every 1KOMMA5° market is now covered (English doubles for Australia). Community native-speaker PRs welcome.

### Changed
- `switch.<system>_ems_automatikmodus` moved to `entity_category=DIAGNOSTIC` so it sits in the device card's collapsible diagnostic section instead of the main controls. The toggle appears to be cosmetic on the cloud side (the official 1KOMMA5° app doesn't expose it and the API write seems no-op), so it stops competing for attention with the controls that actually do something. `entity_id`, `unique_id` and existing automations referring to it stay untouched.
- `sensor.<system>_letzte_optimierungsentscheidung` is now an enum sensor with locale-aware state labels — e.g. "Batterie aus Netz laden" (DE) / "Charge battery from grid" (EN) instead of the raw SDK enum string. State values automations match on are lowercase (e.g. `battery_charge_from_grid`); update your automations if you previously matched on the uppercase form.
- Entities for asset types that the cloud doesn't report on a given install (e.g. heat-pump entities on a setup without a heat pump) are now registered with `entity_registry_enabled_default=False`. They still exist in the registry so adding hardware later preserves history; re-enable them manually under Settings → Devices & Services → 1KOMMA5° → Entities if you want them visible without an asset.

## [0.1.44] - 2026-06-27

### Changed
- The single `1k5` device now splits into one parent device plus per-asset sub-devices (inverter, heat pump, meter, wallbox). Each sub-device carries its real `manufacturer`, `model` and `firmware` from the 1KOMMA5° cloud (PII-safe fields only). Long-term statistics, automations, dashboards and Energy-Dashboard config all keep working: entity `unique_id`s are unchanged, so existing `entity_id`s stay too. New installs will see sub-device names in `entity_id` slugs.
- New diagnostic sensors `letztes_wetter_update` / `letztes_konnektivitäts_update` cover the previously un-tracked weather and connectivity coordinators (5 update timestamps total).
- The system device now exposes `configuration_url = https://app.1komma5grad.com`; HA shows a "Visit device" link to the 1KOMMA5° portal.

## [0.1.43] - 2026-06-26

### Fixed
- `weather.<system>` (and the `condition` shown by HA) reported the wrong sky state — typically stuck on `clear-night` during the day. The entity always returned the first forecast slot, which is the midnight UTC bucket because the API delivers slots ordered from the start of the current day. The active 3-hour bucket (`period_start ≤ now`) is now selected instead, so `condition`, `native_temperature` and `native_wind_speed` reflect the current slot.

## [0.1.42] - 2026-06-25

### Fixed
- `cheapest_charging_window_today` flickered to the next 15-min slot at every quarter-hour boundary — on flat-price days the state moved forward by 15 minutes every 15 minutes, which made it useless as an automation trigger. The sensor now **locks in** the chosen window: once selected, it stays as state until its end has passed (or the day rolls over). After expiry the next-cheapest window of the remaining day is locked in; once less than 60 min remain today, state is `unknown` until midnight.

### Changed
- `cheapest_charging_window_today` is now restored across HA restarts via `RestoreSensor`. A previously-chosen window survives a restart as long as its end is still in the future and its start is still today.

## [0.1.41] - 2026-06-25

### Added
- New sensor `cheapest_charging_window_today` (timestamp + window attributes). State = start of the cheapest 60-minute window that still ends today (HA local time). Attributes: `start`, `end`, `average_price`, `duration_minutes`, `slot_count`. Re-evaluates at every quarter-hour boundary as the day shrinks. Drop straight into a "Charge at" automation trigger — no `get_cheapest_window` service call needed for the common case.

### Changed
- README installation section simplified — integration is now in the HACS default store, so the custom-repository workflow is no longer documented.
- Internal refactor — pure cleanup, no user-visible change: collapsed boilerplate across `entity.py`, `coordinator.py`, `binary_sensor.py` and the diagnostic-sensor wiring (-121 LOC). Five identical entity bases now share one generic; four asset-connectivity binary sensors are one parameterised class; coordinators are configured via class vars instead of duplicated `__init__` calls.

## [0.1.40] - 2026-06-04

### Added
- New blueprint `notify_connectivity_lost.yaml` — fires a notification when one of the v0.1.38 connectivity sensors (site, inverter, heat pump, meter, wallbox) stays OFF for a configurable debounce duration (default 5 min). Picker is filtered to `device_class=connectivity` from this integration; default message templates the friendly entity name so a single blueprint serves all five sensors.
- README **Energy Dashboard setup** section mapping every supported HA Energy Dashboard slot (grid import/export, solar, battery in/out, individual devices) to the friendly name + underlying translation_key, plus grid-pricing and feed-in-revenue sensor wiring.

### Changed
- Reordered the top-level README so installation and configuration come before the entity reference. Old order had a ~300-line "Features" section ahead of the install instructions, which buried both setup steps and the dashboard/blueprint links. New order: Disclaimer → Installation → Configuration → Energy Dashboard setup → Example Dashboard → Blueprints → Entities → Services & Events → Requirements / Tech / Development / Credits. The "Features" H2 was renamed to "Entities", and the services + bus event were lifted to their own "Services & Events" H2. No content was removed or shortened.
- Bumped `onekommafive` dependency to `>=0.1.22`. No new endpoints or fields consumed; the upstream release only adds an optional CLI token cache that this integration does not use. Pin reflects the current latest tested SDK version for clarity.

## [0.1.39] - 2026-06-04

### Changed
- Bundled the hDPI variant of the brand icon (`brand/icon@2x.png`, 512×512 RGBA) next to the existing `icon.png`. Home Assistant's brands proxy (HA ≥ 2026.3) serves both via `/api/brands/integration/onekommafive/`, replacing the grey "Icon not available" placeholder in HACS' list and integration views.
- README image references switched to absolute URLs so the corner logo and the License badge render correctly in HACS' README panel — the previous relative `<img src="custom_components/…">` was stripped by HACS' HTML sanitiser, and the relative License link target broke the entire `[![]()](…)` element under the same sanitiser.

### Removed
- `brand-prep/` working directory. `home-assistant/brands` no longer accepts PRs for custom integrations (2026-02-24 announcement); the directory was a staging area for that workflow and is now obsolete.

## [0.1.38] - 2026-05-19

### Added
- **Site connectivity** binary sensor (`site_connected`, `device_class=connectivity`) reflecting whether the 1KOMMA5° cloud sees the system as `CONNECTED`. Pairs cleanly with HA's standard "device unavailable" notifications.
- **Per-asset-type connectivity** binary sensors (`inverter_connected`, `heat_pump_connected`, `meter_connected`, `wallbox_connected`, all `device_class=connectivity`). Each is registered only when an asset of that type is observed in the cloud's inventory — installs without e.g. a heat pump don't get a permanently unavailable sensor. AND-logic for multi-asset installs: a single disconnected device flips the sensor OFF. Attributes carry redacted per-asset detail (manufacturer / model / firmware / connection_status) — no serial numbers, no local IPs, no opaque IDs, no device names.
- **Active features** diagnostic sensor (`active_features`, `entity_category=diagnostic`) exposing the customer's enabled Heartbeat feature flags (`DYNAMIC_TARIFF`, `TIME_OF_USE_OPTIMIZATION`, `SMART_CHARGING`, …). State is the count; the full list lives in the `features` attribute.
- Diagnostics download now includes a new `system` block with redacted `details` (emp_type, dynamic_pulse_compatible, energy_trader_active, electricity_contract_active, earliest_measurement, …) and `status_and_assets` (site_status, asset_count, per-asset manufacturer/model/firmware/connection_status, active_features). Customer info, addresses, lat/lon, gateway gridx start codes, gateway/asset serial numbers, asset network IPs and asset opaque IDs/names are explicitly redacted.

### Changed
- New `SystemStatusCoordinator` (5-minute interval) drives the connectivity sensors. Combines `system.get_status_and_assets()` and `system.get_active_features(customer_id)` in one refresh; failure of the second call is silently swallowed (features fall back to `[]`) so a partial outage doesn't take the connectivity sensors offline.
- `system.get_details()` is fetched once at config-entry setup. Its `customer_id` is the only input required for the active-features endpoint; the rest is surfaced as redacted diagnostics. Failure is non-fatal: `customer_id=None` simply means the active-features list stays empty.

## [0.1.37] - 2026-05-18

### Changed
- Bumped `onekommafive` dependency to `>=0.1.21`. New release exposes three documented endpoints on the `System` client (`get_active_features`, `get_details`, `get_status_and_assets`) that this integration does not yet consume — kept on the backlog for a future feature release.

## [0.1.36] - 2026-05-16

### Added
- **AI: Heat pump recommendation** binary sensor (`optimization_heat_pump_recommended`) — ON when the Heartbeat AI's currently active HEATPUMP decision is `HEATPUMP_RECOMMEND_ON`. Symmetric to the existing `optimization_battery_grid_charge` sensor; lets users automate the heat pump on AI-curated cheap slots without subscribing to the bus event. Off when the active HEATPUMP decision is `HEATPUMP_AUTO` or when no HEATPUMP event covers the current slot.
- **Diagnostics download** — Home Assistant's standard `diagnostics` platform is now wired up. Settings → Devices & Services → 1KOMMA5° → ⋮ → Download diagnostics produces a JSON dump useful for issue triage: redacted entry data (no username, password, system_id, unique_id), per-coordinator state snapshot (last_update_success, last_exception, update interval, summary of cached data), and the installed `onekommafive` SDK version. Three Tier-2 tests guard the redaction contract and JSON-serialisability.

## [0.1.35] - 2026-05-11

### Added
- **Per-consumer cost sensors** — four new sensors (`Stromkosten Wärmepumpe`, `Stromkosten Wallbox`, `Stromkosten Haushalt`, `Stromkosten Klimaanlage`) that allocate the grid-import cost proportionally to each consumer's share of total consumption (`consumer_power / consumption_power × grid_consumption_power × stable_price`). The four values sum to the existing `electricity_cost` sensor at every sample (invariant verified by a Tier-2 test). When PV/battery cover all consumption the grid bill is zero — all four sensors stop accumulating. Note: the API mocks `acs_power` even for users without an AC unit, so `Stromkosten Klimaanlage` may be non-zero in those setups (same quirk as the existing `acs_energy` sensor).
- **Automation blueprints** — three ready-to-import blueprints in `blueprints/automation/onekommafive/`:
  - `cheapest_window.yaml`: schedule a switch / `input_boolean` for the cheapest contiguous N-minute window in the price forecast (dishwasher, washing machine, EV manual run). Wraps the `onekommafive.get_cheapest_window` service.
  - `follow_cheap_electricity.yaml`: mirror a switch's state to `binary_sensor.…_cheap_electricity` with optional time-of-day window — opportunistic loads like a hot-water booster or pool pump.
  - `notify_grid_charge.yaml`: send a notification whenever the Heartbeat AI flips `binary_sensor.…_optimization_battery_grid_charge` to ON.
- **Weather forecast** — exposes `system.get_weather()`. The integration adds a `weather` entity backed by the location 1KOMMA5° already knows about, supporting the standard HA weather card and the `weather.get_forecasts` service (hourly, ~48 h horizon in 3-hour buckets). Two extra sensors `Sunshine today` / `Sunshine tomorrow` (minutes) cover the PV-relevant data the WeatherEntity schema can't carry — useful for "only run the dishwasher if there's enough sun today" automations. New 1-hour weather coordinator; failures are non-fatal and retried on the next interval.
- `CONTRIBUTING.md` covering local setup (venv, pre-commit, pytest), PR workflow, scope, translation guidelines and release process. Linked from the README development section.
- **Tier-2 integration tests** under `tests/integration/` using `pytest-homeassistant-custom-component`. New `[test-integration]` extras group in `pyproject.toml`; new `integration-tests` CI job runs them on every push/PR alongside the existing helper tests. The Tier-1 helper suite stays the day-to-day fast feedback loop. Coverage so far (27 tests):
  - **Config flow**: single-system success, multi-system picker, invalid auth, cannot connect
  - **Reauth flow**: success path, invalid credentials, system gone from account
  - **Reconfigure flow**: success path, cannot-connect error
  - **Coordinators**: EMS gateway missing falls back to `ems_settings=None`; price and optimization first refresh failures do not block setup
  - **Services**: `get_cheapest_window` finds minimum-average window, `get_most_expensive_window` finds maximum, "no integration configured" raises clear error, voluptuous rejects sub-15-minute durations
  - **Optimization bus events**: first refresh fires exactly one event for the latest decision; subsequent refreshes fire only events strictly newer than the last fired; idempotent on identical data
  - **Cost sensor**: accumulates trapezoidally with positive prices, decreases with negative prices, stays at zero when no stable price is available
  - **Options flow**: form pre-fills the current feed-in tariff, persists a new value, rejects values outside the [0.0, 0.5] range
  - **Stable price sensor**: holds the last valid price across an empty API payload — guards the cost-sensor multiplier
  - **Charging-mode select**: lowercase HA option `smart_charge` converts correctly to `ChargingMode.SMART_CHARGE` before the API call
  - **Weather entity & sunshine sensors**: the WeatherEntity reports the current 3-hour slot's mapped condition; `weather.get_forecasts` returns one entry per slot; the two sunshine sensors register with the expected per-day minute values
- `.github/PULL_REQUEST_TEMPLATE.md` — pre-fills new PRs with summary / type / how-tested / checklist sections.
- `.github/SECURITY.md` — vulnerability-reporting policy via GitHub Security Advisories; clarifies in-scope vs upstream-HA / upstream-1KOMMA5° issues.
- `.github/CODE_OF_CONDUCT.md` — adopts Contributor Covenant 2.1 by reference, with reporting channels matching the security policy.

### Changed
- Dashboard example expanded with monthly bar charts (grid import/export and consumption-per-device), a 24 h power-flow line chart, and a Tag/Woche/Monat/Jahr time-range switcher for the cost & feed-in chart. Two new badges (`Günstiger Strom`, `Aktueller Strompreis`) added to the Netz view header.
- Dashboard now requires the `button-card` HACS custom card and an `input_select.stromkosten_zeitspanne` helper (`Täglich` / `Wöchentlich` / `Monatlich` / `Jährlich`) for the new cost-time-range switcher. Both prerequisites are documented in `dashboard/README.md`.
- Dashboard screenshots optimised with `pngquant` (~60 % smaller, no perceptible quality loss).
- `dashboard/README.md` translated to fully English prose; literal config strings stay German on purpose.
- Dashboard cost view now has a second `statistics-graph` below the existing cost/feed-in chart that breaks `Stromkosten` into its four per-consumer slices (heat pump / wallbox / household / AC). Reuses the existing day/week/month/year switcher — no new helper needed.

## [0.1.34] - 2026-05-08

### Added
- **AI: Battery grid charging** binary sensor (`optimization_battery_grid_charge`) — ON when the Heartbeat AI's currently active BATTERY decision is `BATTERY_CHARGE_FROM_GRID`. AI-curated alternative to the simple price-vs-daily-average heuristic of `cheap_electricity` — fires when the HEMS has decided "now is the right grid-buy moment to bridge upcoming high-price periods", taking the full forecast and battery state into account.
- New pure helper `active_optimization_event(events, asset, now)` (with 6 unit tests) for finding the slot that is currently active for a given asset.

### Changed
- Bumped `onekommafive` dependency to `>=0.1.20` (internal refactor of authenticated HTTP calls; CLI cleanups; no public API change).

### Tooling
- New **CodeQL** workflow (`.github/workflows/codeql.yml`) — security and code-quality scan on push, PR, and weekly cron.
- New **lint** job in `test.yml` running ruff via `pre-commit/action`.
- `pre-commit` config (`.pre-commit-config.yaml`) and `ruff` settings in `pyproject.toml`.
- Repo-wide one-time ruff format pass; `datetime.timezone.utc` migrated to `datetime.UTC`.
- Resolved CodeQL findings: unused module-level `_LOGGER`s in `services.py` and `switch.py` removed; the empty `except` in `OneKomma5StablePriceSensor` now logs at debug instead of silently swallowing.

## [0.1.33] - 2026-05-05

### Added
- HA bus event `onekommafive_optimization_decision` is fired whenever a new optimization decision is observed. The event payload includes `system_id`, `asset`, `decision`, `from`, `to`, `market_price`, `market_price_currency` and `state_of_charge`. The first refresh after a Home Assistant restart fires one event for the most recent decision (so the wiring is immediately verifiable); the day's earlier decisions are not replayed.

### Tooling
- Debug log lines around the event-firing path so you can verify behaviour from the HA log without subscribing on the event bus first.

## [0.1.32] - 2026-04-26

### Added
- **Re-authentication flow**: when 1KOMMA5° credentials become invalid, HA automatically shows a "Re-authentication required" notification — enter new credentials in place without losing sensor history
- **Reconfigure flow**: proactive credential updates via Settings → Devices & Services → 1KOMMA5° → Reconfigure
- **Service `onekommafive.get_cheapest_window`**: find the cheapest contiguous N-minute window in the price forecast — returns start/end timestamps and average price for use in automations (dishwasher, washing machine, EV, heat pump scheduling)
- **Service `onekommafive.get_most_expensive_window`**: find the most expensive contiguous N-minute window — useful for load shedding automations
- **Negative Price Slots Tomorrow** sensor: count of 15-min slots tomorrow with negative price (available after ~13:00 CET)
- **Cheapest Hour Now** binary sensor: ON when the current 15-min slot is the cheapest in the next ~30h of forecast

### Changed
- Bumped minimum Home Assistant version to **2024.10** (required for `_get_reauth_entry`, `_get_reconfigure_entry`, and `data_updates` helper)
- **Cheap Electricity** binary sensor: now updates dynamically every 15 minutes (was previously only updated on coordinator refresh)
- **Refactor**: pure helper functions extracted into `helpers.py` (price slot lookup, forecast building, optimization aggregation, cheapest/most-expensive-window search, trapezoidal integration)
- **Refactor**: introduced `OneKomma5AccumulatingSensor` base class shared by Energy / Cost / Feed-in Revenue sensors
- **Refactor**: introduced `OneKomma5BaseCoordinator[T]` generic base shared by Live / Price / Optimization coordinators
- **Refactor**: introduced `QuarterHourUpdateMixin` and `system_device_info` helper to remove duplication across price sensors and binary sensors
- **Refactor**: split `sensor.py` into `sensor.py` (setup + descriptions tuples), `sensor_descriptions.py` (dataclass descriptions) and `sensor_entities.py` (entity classes)
- **Refactor**: consolidated reauth and reconfigure flows into a shared form handler

### Fixed
- Optimization aggregation sensors (`optimization_total_cost`, `optimization_energy_bought`, `optimization_energy_sold`) no longer declare `state_class: total`. They are daily snapshots that reset at midnight, and recording them as totals without a `last_reset` would feed Long-Term Statistics with a spurious midnight drop. Device classes (monetary / energy) are kept for unit formatting.

### Tooling
- Added **37 unit tests** covering all pure helpers + translation file consistency
- Added **GitHub Actions** workflow that runs the test suite on every push and pull request
- Added **GitHub issue templates** for bug reports and feature requests
- Switched build / test config to **`pyproject.toml`** (replaces `pytest.ini` and `requirements-test.txt`)

## [0.1.31] - 2026-04-26

### Added
- **Optimization sensors**: 5 new sensors exposing Heartbeat AI optimization decisions (event count, cost/savings, energy bought/sold, last decision) — updated every 15 minutes
- **Diagnostic sensors**: 3 new timestamp sensors tracking the last successful API update for each coordinator (live, price, optimization) — `entity_category: diagnostic`
- **Price statistics**: negative price slots today, tomorrow's average/lowest/highest price
- **Long-term statistics**: all price sensors now use `state_class: measurement`, enabling HA to record hourly min/max/mean automatically

### Fixed
- Negative electricity prices are now handled correctly — the stable price sensor accepts negative values and the cost sensor reduces accumulated costs during negative price periods
- Price coordinator first refresh is no longer fatal — if the initial fetch fails (e.g. API rate limit), the integration starts normally
- EMS `DeviceGateway not found` error no longer blocks integration setup — EMS switch becomes unavailable while other sensors continue working

### Changed
- Removed `device_class: monetary` from price sensors (incompatible with `state_class: measurement` in HA)
- Documentation: all entity names translated to English with translation key references

## [0.1.26] - 2026-03-21

### Changed
- Bumped `onekommafive` dependency to `>=0.1.15`
- API library 0.1.15 adds a new endpoint for 1KOMMA5° optimizations (not yet used by this integration)

## [0.1.25] - 2026-03-17

### Changed
- Bumped `onekommafive` dependency to `>=0.1.14`
- API library 0.1.14 updates the `/systems` endpoint to v4 (no breaking changes)

## [0.1.24] - 2026-03-08

### Fixed
- Options flow: replaced `NumberSelector` with plain `voluptuous` validation to fix 400 Bad Request error on HA versions < 2024.3

## [0.1.23] - 2026-03-08

### Added
- **Electricity Cost** sensor: accumulated grid import cost (dynamic price × kWh, integrates with HA Energy Dashboard)
- **Feed-in Revenue** sensor: accumulated feed-in revenue (configurable tariff)
- **Cheap Electricity** binary sensor: ON when current electricity price is below today's average
- **Battery Charge Energy** / **Battery Discharge Energy** sensors (split for HA Energy Dashboard)
- Options flow: feed-in tariff configurable via integration settings (default 0.0803 €/kWh)
- Dashboard: new "Prices and Costs" view with cost stats and monthly apexcharts chart

## [0.1.22] - 2026-03-07

### Removed
- README: removed stable electricity price section (superseded by dynamic price sensor)

## [0.1.21] - 2026-03-07

### Added
- Stable electricity price sensor with hold-last-valid logic (retains last known price on API gaps)

## [0.1.20] - 2026-03-06

### Changed
- Relaxed `onekommafive` dependency to `>=0.1.10` (was pinned to exact version)
- Switched to PyPI package `onekommafive` (replaces direct GitHub dependency)

## [0.1.19] - 2026-03-06

### Changed
- README: restructured with disclaimer at top and credits at bottom
- README: added "vibe coded" note to disclaimer
- README: use `SYSTEM_NAME` placeholder in automation example

## [0.1.18] - 2026-03-06

### Changed
- Dashboard: updated with apexcharts price chart and new screenshots

## [0.1.17] - 2026-03-06

### Changed
- Dashboard: updated EV view screenshot

## [0.1.16] - 2026-03-05

### Fixed
- Dashboard: replaced hardcoded heat pump sensor entity ID with `SYSTEM_NAME` placeholder

## [0.1.15] - 2026-03-05

### Added
- README: EV SoC sync automation example (keep manual SoC entity in sync with actual vehicle SoC)

## [0.1.14] - 2026-03-05

### Changed
- `hacs.json`: added `render_readme: true` and minimum HA version `2024.2`
- Dashboard: replaced hardcoded car entity prefix with `CAR_IDENTIFIER` placeholder

## [0.1.13] - 2026-03-05

### Added
- Dashboard README: template sensor code for `cheapest_future_hour` and `cheapest_future_price`

## [0.1.12] - 2026-03-05

### Changed
- Dashboard: replaced hardcoded system entity prefix with `SYSTEM_NAME` placeholder

## [0.1.11] - 2026-03-05

### Added
- Example dashboard with two views (grid/energy and EV charger controls), YAML and screenshots

## [0.1.10] - 2026-03-05

### Changed
- README: reorganised with a dedicated EV Charger section

## [0.1.9] - 2026-03-05

### Fixed
- EV departure time: use correct `primary_schedule_departure_time()` getter and `'HH:MM'` string format

## [0.1.8] - 2026-03-05

### Added
- **EV target SoC** number entity (0–100 %, available in SMART_CHARGE mode)
- **EV departure time** time entity (primary schedule departure time)

## [0.1.7] - 2026-03-02

### Changed
- README: documented 15-minute slot accuracy for the current electricity price sensor

## [0.1.6] - 2026-03-02

### Fixed
- Current electricity price now reflects the active 15-minute slot (`start ≤ now`) instead of rounding to the full hour

## [0.1.5] - 2026-03-01

### Changed
- Price forecast horizon extended from 24 h to 30 h

## [0.1.4] - 2026-03-01

### Added
- `cheapest_future_hour` and `cheapest_future_price` as attributes of the electricity price sensor

## [0.1.3] - 2026-03-01

### Added
- Energy sensors (kWh, `TOTAL_INCREASING`) for all 8 unidirectional power sensors using trapezoidal integration

## [0.1.2] - 2026-03-01

### Added
- Sensor **Grid Import Power** (`grid_consumption_power`): raw grid import power (always ≥ 0), in W
- Sensor **Grid Export Power** (`grid_feed_in_power`): raw grid export / feed-in power (always ≥ 0), in W
- Requires `onekommafive` API library ≥ commit `2283880`

## [0.1.1] - 2026-03-01

### Fixed
- Brand icon: correct dimensions (256×256 px, RGBA) and transparent background
- HACS validation: sorted manifest keys, fixed brand asset path, pinned action version
- License badge replaced with static badge to avoid GitHub camo cache issue

### Changed
- README: added early-beta / vibe-coded disclaimer
- README: added credits to [BirknerAlex/hacs_1komma5grad](https://github.com/BirknerAlex/hacs_1komma5grad)

## [0.1.0] - 2026-02-28

### Added
- Initial release
- Live energy sensors: PV power, battery power & SoC, grid power, consumption, household, EV charger, heat pump, AC, self-sufficiency
- Dynamic electricity price sensors (15-minute resolution): current, average, lowest, highest
- Rolling 24-hour price forecast as `forecast` attribute (Tibber/ENTSO-E compatible format)
- EMS auto mode switch
- EV charging mode selector (SMART_CHARGE / QUICK_CHARGE / SOLAR_CHARGE)
- EV manual SoC number entity (SMART_CHARGE mode only)
- UI config flow with automatic system selection for multi-system accounts
- German and English translations
