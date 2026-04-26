# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
