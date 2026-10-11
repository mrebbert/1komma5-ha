---
title: Diagnostics
description: Per-coordinator timestamp sensors, device-connectivity binaries, EMS auto-mode switch and the System Information Repair-Issue machinery.
---

# Diagnostics

Hidden by default (`entity_category: diagnostic`) — useful for troubleshooting.

## Per-coordinator timestamps

| Entity | Description |
|--------|-------------|
| `diag_live_update` | Last successful live data fetch |
| `diag_price_update` | Last successful price fetch |
| `diag_optimization_update` | Last optimization fetch |
| `diag_weather_update` | Last weather fetch |
| `diag_system_status_update` | Last site-status / asset-inventory fetch |
| `diag_energy_update` | Last daily-savings fetch |
| `diag_notification_update` | Last cloud-notifications fetch (v0.1.52) |
| `diag_heartbeat_prices_update` | Last heartbeat-prices fetch (v0.1.66; backs the §14a Modul 1 sensor) |

!!! note "Why these can sit at `unknown` right after a restart"
    Diagnostic timestamps only advance after the coordinator's first *post-add* refresh. Slow-interval coordinators (price 1 h, weather 1 h) can therefore sit at `unknown` for up to their interval after HA start. To prime immediately, call [`onekommafive.refresh_now`](../services.md#onekommafiverefresh_now) with the coordinator name.

## Device connectivity & feature flags

Binary sensors summarising cloud & asset health:

| Entity | Description |
|--------|-------------|
| `site_connected` | Aggregate — ON when the cloud reports the site as `CONNECTED` |
| `inverter_connected`, `heat_pump_connected`, `meter_connected`, `wallbox_connected` | Per-asset-type; AND-logic over all assets of the type. Only created when the cloud actually reports an asset of that type. |
| `wallbox_<id>_connected` | One per physical wallbox (multi-wallbox sites only, since v0.1.58). Reports the connection status of that specific wallbox — pair with the aggregate `wallbox_connected` to gate on "all healthy" vs. "this one down". |
| `dynamic_tariff_active`, `time_of_use_active`, `smart_charging_active` | Feature-flag Booleans from the customer-features API |
| `energy_trader_active` | ON when enrolled in 1KOMMA5°'s virtual power plant (energy trading). From `SystemDetails.energy_trader_active`, captured once at setup. |
| `dynamic_pulse_compatible` | ON when the site's hardware/contract qualifies for Dynamic Pulse |

Plus: `active_features` sensor (state = count; attributes = feature list) and `system_age_days` (days since earliest measurement).

## System Information panel

**Settings → System → Repairs → System Information** reports per-coordinator update status, API reachability, SDK version and resolved currency/country. **PII-safe** — use this for bug reports instead of the full diagnostics download.

## EMS auto-mode switch

`switch.<sys>_ems_auto_mode` (GRIDX backends only), diagnostic category — only created on GRIDX-backend installs; 1K5-backend installs skip it entirely from v0.1.57 on because the endpoint is not reachable there. See the [FAQ](../faq.md#why-is-the-ems-auto-mode-switch-unavailable) for the Repair Issue behaviour and `30401` log line.

!!! warning "Likely cosmetic"
    The EMS auto-mode switch POSTs to `/systems/{id}/ems/actions/set-manual-override`. The read model (`EmsSettings.manual_devices`) and the official 1KOMMA5° app both suggest there is no user-facing way to override automatic optimisation; the endpoint accepts writes without an observable side effect. Kept in the diagnostic category in case the cloud starts honouring it. See [Known limitations](../limitations.md).
