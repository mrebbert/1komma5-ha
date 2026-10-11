---
title: Devices & entity structure
description: System parent device, per-asset sub-devices (inverter, battery, heat pump, meter, wallbox, vehicle), multi-wallbox topology and PII guardrails.
---

# Devices & entity structure

Entities are grouped under one **system parent device** plus **per-asset sub-devices** — read off each hardware component's manufacturer, model and firmware version at a glance; assign areas / disable sensors per device.

```text
1k5° System (parent)
├── Inverter        (Sungrow / SH6.0RT-V112 / …)
├── Battery         — entities live on the inverter sub-device (hybrid inverter)
├── Heat pump       (Stiebel Eltron / WPMsystem / …)
├── Smart meter     (Chint / DTSU666 / …)
├── Wallbox         (go-e / HOMEfix 11kW / …)
└── Vehicle         (Volkswagen / ID.5 / …)
```

## Multi-wallbox

**Since v0.1.58:** sites with more than one physical wallbox get one sub-device per wallbox, each with its own manufacturer / model / firmware; vehicles parent under the wallbox they are actually paired to (via `Wallbox.assigned_ev_id ↔ EVCharger.assigned_charger_id`):

```text
1k5° System (parent)
├── … (inverter / heat pump / meter as above)
├── Wallbox (aggregate)           — carries the aggregate ev_chargers_power / _cost / wallbox_connected sensors
├── Wallbox Garage  (go-e / HOMEfix / 60.5)
│   └── Vehicle     (Volkswagen / ID.5 / …)
└── Wallbox Carport (Enphase / EVSE_IQ2 / 1.2.3)
    └── Vehicle     (Tesla / Model 3 / …)
```

Single-wallbox sites (the historical default) keep the exact sub-device identifier and label they had before v0.1.58: no migration, no renamed entities, no broken area assignments.

## PII guardrails

Sub-device data is **PII-safe**: only `manufacturer`, `model`, `firmware` are pulled from the cloud `status_and_assets` payload; the Vehicle sub-device pulls `manufacturer` and `model` from the EV profile. Unclassified assets (`Asset.type = UNKNOWN`, e.g. a Shelly Pro 3EM CT-clamp meter behind the smart meter) stay attached to the parent — no empty placeholder devices.

Account identifiers never surface in entities or attributes: `customer_id`, `site_id`, `electricity_contract_number`, `market_location_id`, `terms_and_conditions_url` and the raw CRM record stay out of the integration surface by design.

## Stable identifiers

`entity_id`s and `unique_id`s are **stable across releases** — long-term statistics, automations, Energy-Dashboard configuration and dashboard cards keep working without migration. The sub-device key is deliberately not part of `unique_id`, so a device-topology change (e.g. splitting a hybrid inverter) does not break history.

## Missing-asset handling

Installs missing an asset type (e.g. no heat pump, or grid-only without PV) have the corresponding sensors **disabled by default**. The entities still exist in the registry so history stays continuous if hardware is added later. Re-enable manually under **Settings → Devices & Services → 1KOMMA5° → Entities**.

## Supported hardware

The integration exposes whatever the 1KOMMA5° cloud reports for your site: every device it recognises comes through the shared `status_and_assets` endpoint, so any hardware 1KOMMA5° has certified for the Heartbeat platform surfaces automatically. **No allowlist inside the integration.**

Observed from live installs:

| Sub-device | Manufacturers seen | Notes |
|---|---|---|
| Inverter (`HYBRID` asset) | Sungrow (`SH*RT-V112`), Enphase | Hybrid inverters carry the battery entities on the same sub-device |
| Inverter + separate battery | FoxESS | Reports `PV_SYSTEM` + `BATTERY` split; `battery` sub-device is created only in that case |
| Heat pump | Stiebel Eltron (`WPMsystem`), Vaillant, Buderus | Optional; sub-device only when 1KOMMA5° reports it |
| Smart meter | Chint (`DTSU666`), Iskra | Backs the meter connectivity + feed-in revenue sensors |
| Wallbox | go-e (`HOMEfix 11kW`), MENNEKES (`AMTRON`), Enphase (`EVSE_IQ2`), KEBA | Multi-wallbox sites get one sub-device per wallbox since v0.1.58 |
| Vehicle profile | Any brand configured in the 1KOMMA5° app (Volkswagen, BMW, Tesla, Škoda, …) | Managed in the app under *Settings → Vehicles*; no HA-side pairing |

**Unrecognised assets** (`Asset.type = UNKNOWN`) stay attached to the system parent; the integration deliberately does not create empty placeholder sub-devices for hardware it cannot classify.

If your hardware is not on this list, that is expected: the entry surfaces the same way as long as 1KOMMA5° reports it. Please attach a diagnostics dump to an [issue](https://github.com/mrebbert/1komma5-ha/issues) if a fresh device shows up as `UNKNOWN` or landed on the wrong sub-device.
