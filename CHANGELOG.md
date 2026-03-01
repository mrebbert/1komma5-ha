# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
