---
title: EV charger & wallbox
description: Per-vehicle-profile charging-mode / target-SoC / departure-time controls plus the wallbox-to-vehicle assignment select for multi-car sites. Covers go-e, MENNEKES, Enphase and KEBA wallboxes.
---

# EV charger & wallbox

One set of entities per **vehicle profile** registered in the 1KOMMA5° app.

!!! info "Requires a vehicle profile"
    These entities model the car (`SMART_CHARGE` target, SoC, departure time), not the wallbox — they come from the SDK's `/v2/sites/{id}/assets/evs` endpoint (site-scoped since SDK v0.2.0), which returns the vehicles configured under *Settings → Vehicles* in the 1KOMMA5° app. Without a vehicle profile the endpoint returns an empty list and no charging-mode / SoC / departure-time entities are created. The wallbox device itself still appears, backed by connectivity + aggregate `ev_chargers_power` / `ev_charger_cost` sensors from other endpoints.

## Sensors

`ev_target_soc` (%), `ev_charging_mode` (mode enum), `ev_battery_capacity` (kWh), `ev_scheduled_departure_soc` (%).

## Controls

| Entity | Type | Description |
|--------|------|-------------|
| Charging Mode | Select | `SMART_CHARGE` / `QUICK_CHARGE` / `SOLAR_CHARGE` |
| Target SoC | Number (0–100 %) | Desired battery target |
| Departure Time | Time | Daily primary departure |
| Vehicle SoC (Manual) | Number (0–100 %) | Manual current-SoC report (SMART_CHARGE only) |
| Assigned Vehicle | Select (per wallbox) | Which vehicle profile is currently paired with the wallbox (see below) |

## Wallbox → vehicle assignment (since v0.1.63)

Sites with more than one vehicle profile in the 1KOMMA5° app get one `select.<sys>_<wallbox>_assigned_vehicle` per physical wallbox, parented on the wallbox sub-device.

- Options are the site's vehicles as lowercase name slugs (`bmw_i3`, `tesla_model_y`, ...).
- State reflects `Wallbox.assigned_ev_id`.
- Selecting an option binds that vehicle to the wallbox — the same switch the 1KOMMA5° app offers.
- The backend is **1:1 exclusive**: setting the assignment on one vehicle automatically releases whichever vehicle was previously bound to the same wallbox.
- There is **no unassign option** (the app UI has none either).
- Single-vehicle sites see the entity but have nothing to switch — no UI breakage, just an inert control.

Automation shortcut: the [`vehicle_at_wallbox.yaml` blueprint](https://github.com/mrebbert/1komma5-ha/blob/main/blueprints/automation/onekommafive/vehicle_at_wallbox.yaml) flips the select automatically when a "car plugged in" binary sensor (from your car integration or a smart-plug helper) goes ON. One import per vehicle.

Id-addressed alternative for scripts: the [`onekommafive.assign_ev_to_wallbox` service](../services.md#onekommafiveassign_ev_to_wallbox).

## Mirror your car's battery sensor

Trigger on your EV integration's battery-level sensor, assert `is_number`, and `number.set_value` on `number.<car>_fahrzeug_akkustand_manuell`. The target entity is `unavailable` outside `SMART_CHARGE` mode, so the condition `not is_state(target, 'unavailable')` keeps the automation idle in the other modes.

## Multi-wallbox topology

Sites with more than one physical wallbox (since v0.1.58) get one sub-device per wallbox, each carrying its own manufacturer / model / firmware and the per-wallbox `wallbox_<id>_connected` binary sensor. The aggregate `wallbox` sub-device still exists and carries `ev_chargers_power`, `ev_charger_cost` and the aggregate `wallbox_connected`. See [Devices & entity structure](../entity-structure.md#multi-wallbox).

## Supported wallbox hardware

Observed from live installs: go-e (`HOMEfix 11kW`), MENNEKES (`AMTRON`), Enphase (`EVSE_IQ2`), KEBA. Any hardware that 1KOMMA5° reports through the standard `status_and_assets` endpoint surfaces automatically; no allowlist inside the integration.
