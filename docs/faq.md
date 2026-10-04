# FAQ / troubleshooting

Common questions when installing or running the 1KOMMA5° Home Assistant integration. See the main [README](../README.md) for setup and feature overviews.

## Why does HACS not show the latest release yet?

HACS refreshes each user's cache roughly every 60–90 min. To force it immediately: open HACS in the HA UI, find **1KOMMA5°**, click the three-dot menu, and choose **Redownload** (or **Reload**). No harm in waiting an hour or two either.

## Why is the EMS auto-mode switch unavailable?

Your install has no DeviceGateway. The integration registers a Repair Issue in **Settings → Repairs** after a few consecutive failures. It auto-resolves the moment EMS data returns. On 1K5-backend installs (`emp_type: "1K5"` in the diagnostics), the switch is intentionally **not created** as of v0.1.58 — the EMS endpoint is not reachable on that backend, so the switch would be permanently unavailable.

## Why are the charging-mode / target-SoC / departure-time entities missing?

Since v0.1.58 (with SDK 0.2.0), the wallbox / EV endpoints use the site-scoped v2 route, which works on both `GRIDX` and `1K5` backends. If the entities are still missing, download diagnostics (**Settings → Devices & Services → 1KOMMA5° → ⋮ → Download diagnostics**) and check `data.system.wallboxes[]`:

- **`assigned_ev_id_present: false`** — a vehicle profile isn't paired to the wallbox in the 1KOMMA5° app. Assign it under *Settings → Vehicles* in the app, then restart Home Assistant.
- **`assigned_ev_id_present: true`** but entities still missing — open an issue with the diagnostics dump attached. The remaining `emp_type_1k5_native_hint` flag (v0.1.57+) is kept as a triage marker for edge cases.

Not a Home Assistant misconfiguration in either branch.

## Why do some optimization sensors show `unknown`?

`optimization_total_cost`, `optimization_energy_bought`, and `optimization_energy_sold` depend on settlement data that the 1KOMMA5° cloud API does not currently populate. `optimization_event_count` and `optimization_last_decision` work independently.

## Why is `sensor.<system>_diag_price_update` stuck at `unknown` right after a restart?

Diagnostic timestamps only advance after the coordinator's first *post-add* refresh. Slow-interval coordinators (price 1 h, weather 1 h) can therefore sit at `unknown` for up to their interval after HA start. To prime immediately, call `onekommafive.refresh_now` with the coordinator name.

## Which notification types reach HA via `onekommafive_notification`?

Whatever the 1KOMMA5° cloud returns — which honours your per-type subscription settings in the 1KOMMA5° app (Settings → Notifications). Types you have disabled in the app don't produce HA events. There is no HA-side subscription control.

## Is `dynamic_pulse_price_guarantee` the max price I'll pay per kWh?

**No.** The guarantee is bound to terms and conditions on the 1KOMMA5° side that this integration doesn't model. Treat the sensor as informational; don't wire automations that assume "current price ≤ guarantee" semantics.

## My entity names look wrong ("1k5 …" prefix vs. plain name)

Entity naming is composed from `device.name + entity original_name` unless you renamed the entity in the HA UI. Mixed prefixes in one install typically mean some entities were renamed manually. The `entity_id` and long-term statistics are unaffected.

## The Energy Dashboard shows no data / wrong data

See [`dashboard/ENERGY_DASHBOARD.md`](../dashboard/ENERGY_DASHBOARD.md) for the slot-to-sensor mapping. The two most common misconfigurations: (a) using `battery_power` (bidirectional) instead of `battery_charge_power_energy` + `battery_discharge_power_energy`; (b) using the raw `grid_power` instead of the split `grid_consumption_power_energy` + `grid_feed_in_power_energy`.

## The log shows repeated `30401` errors for `/ems`

That means your account runs on the newer **1K5-native** backend, which serves the `EmsSettings` payload as an empty document (`30401`) rather than the GRIDX shape the SDK expects. Since v0.1.58 the integration detects this via `emp_type_1k5_native_hint` and stops registering the EMS switch, so the log entry should be silent on affected installs. If you still see it after upgrading, download diagnostics and open an issue with `data.system.emp_type` and `emp_type_1k5_native_hint` attached; that's the triage evidence.

## How do I file a good bug report?

Grab the **System Information** dump from **Settings → System → Repairs → System Information** (PII-safe — no customer/system identifiers or addresses). Attach it to a [GitHub issue](https://github.com/mrebbert/1komma5-ha/issues) with a short reproducer.
