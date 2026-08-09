# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.52] - 2026-08-09

### Added
- **Notifications event bridge.** New bus event `onekommafive_notification` fires for each newly-observed 1KOMMA5° cloud notification (energy market thresholds, system health alerts, dynamic-pulse events, …). Payload is a flat dict with `system_id`, `notification_id`, `type`, `title`, `body` (both already localized to the account language), `locale`, `created_at`, and `meta` (e.g. `meta.price.value`). Enables automations that react to the same push notifications the 1KOMMA5° mobile app receives. Dedup state persists across HA restarts via `homeassistant.helpers.storage.Store` under `.storage/onekommafive.notifications.<entry_id>`; the first refresh after a fresh install primes silently (no replay of history).
- New diagnostic timestamp `sensor.<sys>_diag_notification_update` (`entity_category=diagnostic`) tracks the notifications coordinator's last successful refresh.
- `onekommafive.refresh_now` service now accepts `coordinator: notifications` (and `coordinator: all` includes it).
- **`sensor.<sys>_dynamic_pulse_price_guarantee`** — raw `price_guarantee_value` from a DYNAMIC_PULSE subscription (via SDK 0.1.44's `get_subscriptions`), exposed in `EUR/kWh`. Informational only — the guarantee is bound to 1KOMMA5°-side terms this integration doesn't model. Sensor is only created when a DP contract is present.
- **`onekommafive.get_heartbeat_metrics(window)` service** — on-demand fetch of aggregated Heartbeat metrics for one of `day` / `week` / `month` / `half_year` / `year` (via SDK 0.1.44's `get_heartbeat_prices`). Returns a flat dict with all ~22 populated fields: PV / grid kWh, tariffs, €-amounts, VAT, plus a couple of composite fields the caller can choose to ignore. Absent windows respond `{"window": ..., "available": false}` so callers can branch on it. Response order follows the SDK model — useful for sanity-checking cloud-side aggregates against locally-integrated Long-Term Statistics.

### Changed
- Bump the `onekommafive` SDK pin to `>=0.1.45,<0.2` (from `>=0.1.43,<0.2`). Upstream `0.1.44` adds `system.get_heartbeat_prices()` and `system.get_subscriptions(customer_id)`, both consumed by the two new surfaces above. Upstream `0.1.45` is a marginal dependency-metadata change (`PyJWT[cryptography]` extra split into direct `cryptography>=41` requirement) to silence pip's cryptography-mismatch warning; no API-surface change.
- Internal refactor sweep: `_resolve_config_entry` helper deduplicated across the four services that resolve a config entry, `dir(win)` reflection in the heartbeat-metrics handler replaced with `dataclasses.asdict()` (fail-loud instead of fail-silent on SDK method additions), dead `PriceData.current_price_with_grid_costs` and `PriceData.grid_prices` fields removed (zero readers repo-wide), tomorrow-window date math simplified from a 6-line `datetime.replace(...)` to `dt_util.start_of_local_day() + timedelta(days=1)`, `ApiError` and `issue_registry` late imports hoisted out of hot paths, docstring / comment bloat trimmed (net -90 lines across the coordinator + service + sensor files). Behavior unchanged; 224 tests still pass.
- Live power / weather / optimization sensors share a new `_DescriptionValueSensor` mixin instead of hand-rolling the same `native_value = description.value_fn(coord.data)` guard three times. `OneKomma5PriceSensor` and `OneKomma5EVSensor` stay bespoke — they carry real added behavior (breakdown attributes + quarter-hour update on the price side, `_get_ev()` indirection on the EV side).

## [0.1.51] - 2026-08-02

### Fixed
- `onekommafive.refresh_now` accepts `coordinator: energy`. The energy coordinator (added in v0.1.48 to back `sensor.<sys>_daily_savings`) was never registered in the service, so it could not be force-refreshed and `all` refreshed only five of the six coordinators. Selector, schema, service handler and the DE user-facing description are all in sync now.

### Changed
- Bump the `onekommafive` SDK pin to `>=0.1.43,<0.2` (from `>=0.1.23,<0.2`). Upstream `0.1.24` was a maintenance release (Auth0 login-state parsing hardened via regex, DRY refactors). `0.1.25` added `system.get_energy_savings(from_date, to_date)` — aggregated Heartbeat savings (€) over a date range. `0.1.30 → 0.1.43` added a large batch of read-only endpoints: `get_impact_overview` (CO2), `get_energy_trader` (trading status + savings), `get_heartbeat_ai_summary(resolution)`, `get_monthly_trading_savings`, `get_price_customizations` / `get_comparison_price` / `get_price_guarantee(customer_id)`, `get_wallboxes`, `get_smart_meter`, `get_site_details`, `get_self_sufficiency_events(start, end)`, `get_customer(customer_id)`, `get_notifications`, `get_notification_settings`, plus new fields on `HeartbeatAiSummary` (peak-price-avoided) and `SystemDetails` (customer info). The new endpoints are not yet surfaced as Home Assistant entities. Every existing entity keeps its `unique_id`, `entity_id` and translation key.
- Internal refactor across `entity.py` and `binary_sensor.py`: `apply_stable_entity_ids` helper now takes the platform domain string directly (call sites go from `f"{DOMAIN}.{{}}"` to `DOMAIN`); `OneKomma5DiagnosticSensor` hangs off the generic `_BaseSystemEntity` instead of duplicating `CoordinatorEntity` boilerplate; the four near-clone binary sensors (Optimization Battery/HeatPump decision, EnergyTrader/DynamicPulse details flags) collapse into two spec-driven classes (`OneKomma5OptimizationDecisionSensor`, `OneKomma5DetailsFlagSensor`); shared plumbing of the today/tomorrow cheapest-window sensors extracted into `_ChargingWindowBase`. No unique_id or translation-key changes — existing entities keep their state, statistics and dashboards untouched. Net -66 lines across the two files.

## [0.1.50] - 2026-07-28

### Fixed
- **Fresh-install entity_ids are now stable** — every entity in the integration exposes `sensor.<system>_<code_suffix>` / `binary_sensor.<system>_<code_suffix>` / etc. on new installs regardless of Home Assistant's language and regardless of whether the entity is parented on the system parent or on a per-asset sub-device (inverter / heat_pump / meter / wallbox / vehicle). Before this fix HA composed sub-device entity_ids as `<device_slug>_<entity_slug>` from the translated device name, so a German fresh install landed on `binary_sensor.wechselrichter_verbunden` while an English install landed on `binary_sensor.inverter_connected` — the shipped `dashboard/dashboard.yaml` `SYSTEM_NAME` placeholder covered neither case. Achieved via a small `apply_stable_entity_ids` shim called from each platform's `async_setup_entry`; existing entity_ids in the registry are preserved (HA registry looks up by `unique_id` first). Fixes issue #8.

### Changed
- `dashboard/dashboard.yaml` and `dashboard/dashboard-showcase.yaml` now reference the stable English code suffixes (`_pv_power`, `_heat_pumps_power`, `_electricity_cost`, `_feed_in_revenue`, `_diag_live_update`, `_cheap_electricity`, …) instead of the previous DE-translated slugs. The `SYSTEM_NAME` placeholder alone is enough for any HA language on a fresh install. Upgrading users whose registry still carries pre-fix DE-translated entity_ids should either rename their entities under Settings → Devices & Services → 1KOMMA5° → Entities, or sed the code suffix back to whatever their registry actually holds — see `dashboard/README.md` for the migration note.

## [0.1.49] - 2026-07-19

### Changed
- Pin the `onekommafive` SDK to `>=0.1.23,<0.2`. Home Assistant installs the requirement automatically on every install, so an upper bound stops a breaking SDK release from shipping untested to all users. Raise the cap deliberately when adopting a new SDK minor.

### Fixed
- Hardening: every coordinator fetch is now wrapped in a 30 s timeout (`OneKomma5BaseCoordinator._fetch_timeout_seconds`). Previously a hung SDK HTTP call could pin a coordinator (and an executor thread) indefinitely, since `DataUpdateCoordinator` imposes no timeout of its own. A timeout now surfaces as a normal failed update — the entity goes unavailable and the next interval retries.

## [0.1.48] - 2026-07-12

### Added
- `sensor.<sys>_daily_savings` — today's cloud-computed energy savings (€), read from the previously-unused `get_energy_today()` endpoint (`EnergyData.savings_eur`). Daily running total that resets at local midnight (`state_class=total`, `last_reset` = start of local day), so Long-Term Statistics records one cycle per day. New `OneKomma5EnergyCoordinator` (15-min interval) backs it, with a matching `diag_energy_update` diagnostic timestamp. Currency follows the resolved account currency.
- `sensor.<sys>_ev_battery_capacity` — the vehicle's nominal battery capacity (kWh), from the EV profile's `capacity_wh`.
- `sensor.<sys>_ev_scheduled_departure_soc` — the departure schedule's target SoC (%), distinct from the manual `ev_target_soc`. Read-only.
- Grid-cost breakdown attributes on `sensor.<sys>_current_electricity_price`: `spot_price`, `grid_costs`, `grid_cost_components`, `vat_rate`, `uses_fallback_grid_costs`. Decomposes the all-in price as `(spot + net grid costs) × (1 + vat)` — components are net (ex-VAT); the SDK's VAT-inclusive `grid_costs_total` is intentionally not surfaced.
- Translations for all new entities across all seven shipped locales.

## [0.1.47] - 2026-07-05

### Added
- Configurable duration on `sensor.<sys>_cheapest_charging_window_today` — options-flow dropdown, 15-240 min in 15-min steps, default 60. Existing lock-in semantic preserved at the chosen duration.
- `sensor.<sys>_cheapest_charging_window_tomorrow` — twin of the today-sensor for tomorrow's forecast slots. Same duration option. `unknown` until tomorrow's prices arrive (~13:00 CET).
- `onekommafive.refresh_now` service — schema `coordinator: live | price | optimization | weather | system_status | all` (default `live`), optional `config_entry_id`. Returns `{"refreshed": [...], "failed": [...]}`.
- Bus events `onekommafive_negative_price_started` / `_ended` on positive↔negative edges of the active 15-min slot. Payload: `system_id`, `price`, `negative_price_slots_remaining`. Granularity = coordinator refresh interval (1 h by default).
- Three `SystemDetails`-backed entities: `binary_sensor.<sys>_energy_trader_active`, `binary_sensor.<sys>_dynamic_pulse_compatible`, `sensor.<sys>_system_age_days` (diagnostic, unit `d`).
- Three blueprints: `notify_negative_prices_tomorrow.yaml`, `notify_negative_price_started.yaml`, `ev_charge_on_pv_surplus.yaml`.
- `dashboard/dashboard-showcase.yaml` — six-view showcase variant exercising the full integration surface. Original `dashboard.yaml` stays as the compact layout.
- Translations for all new entities and options-flow fields across all seven shipped locales.

### Fixed
- Per-asset connectivity binaries no longer duplicate the asset noun ("Wechselrichter Wechselrichter verbunden" → "Wechselrichter Verbunden"). Translations on `inverter_connected` / `heat_pump_connected` / `meter_connected` / `wallbox_connected` reduced to the past-participle word in all seven locales. `site_connected` unchanged. `entity_id` / `unique_id` unchanged.

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
