---
title: Known limitations
description: Four cloud-API and HA realities the integration cannot design around — optimization binaries mirror the Cloud recommendation (not the HEMS), settlement fields are empty, EMS override is likely cosmetic, and the AI-decisions calendar drops the DST fall-back ambiguous hour.
---

# Known limitations

Four cloud-API and HA realities the integration cannot design around. Documenting them here so nobody wastes time modelling them as bugs.

## Optimization binaries reflect the Cloud recommendation, not the local HEMS

`binary_sensor.<sys>_optimization_battery_grid_charge` and `binary_sensor.<sys>_heatpump_recommendation` mirror the latest `Decision` returned by the AI endpoint: what 1KOMMA5°'s Cloud AI thinks *should* happen. The Heartbeat HEMS decides locally whether to act; the two can diverge for days. Owner-verified example (2026-09-10): heat-pump-recommended stayed `off` while SG-Ready ran the pump anyway. Automations that assume `recommended = on ⇔ device runs` will be wrong.

## Optimization settlement fields are permanently `unknown`

`optimization_total_cost`, `optimization_energy_bought`, `optimization_energy_sold` come from `OptimizationEvent` fields the backend does not populate ("or None when not settled yet" per the SDK docstring, never seen non-`null` in the wild). The sensors stay because they are semantically correct and would start reporting if 1KOMMA5° ever ships settlement data; the showcase dashboard parks them in a commented-out block.

## The EMS auto-mode switch is likely cosmetic

`switch.<sys>_ems_auto_mode` (GRIDX backends only) POSTs to `/systems/{id}/ems/actions/set-manual-override`. The read model (`EmsSettings.manual_devices`) and the official 1KOMMA5° app both suggest there is no user-facing way to override automatic optimisation; the endpoint accepts writes without an observable side effect. Kept as diagnostic-category in case the cloud starts honouring it.

## The AI-decisions calendar drops the DST fall-back ambiguous hour

`calendar.<sys>_ai_decisions_calendar` deliberately skips the local hour that repeats at Oktober fall-back (02:00–03:00 in Europe/Berlin, appearing once CEST and once CET on the Sunday of the switch). HA's calendar validator (`has_min_duration`) computes `end - start` on `as_local_timezone`-converted datetimes; when both carry the same `ZoneInfo` but different UTC offsets, Python subtracts the naive wall clocks and rejects the event as "duration 0:00:00". Even without the validator, two different UTC instants with identical wall clocks cannot be rendered unambiguously in a local-time calendar. The trade-off: one hour of decisions per year is lost in exchange for a clean, overlap-free display. Spring-forward is unaffected.
