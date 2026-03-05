# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
- Example dashboard with two views (Netz/energy and EV charger controls), YAML and screenshots

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
- Sensor **Netzbezug** (`grid_consumption_power`): raw grid import power (always ≥ 0), in W
- Sensor **Netzeinspeisung** (`grid_feed_in_power`): raw grid export / feed-in power (always ≥ 0), in W
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
