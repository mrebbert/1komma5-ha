---
title: 1KOMMA5° Home Assistant Integration
description: Home Assistant custom integration for the 1KOMMA5° Heartbeat energy platform. Dynamic electricity pricing, 30-hour price forecast, AI optimization, EV wallbox, §14a EnWG grid-fee reduction, cloud push notifications. HACS Default Store, OAuth2 PKCE, works on both GridX and 1KOMMA5°-native backends.
---

# 1KOMMA5° Home Assistant Integration

![1KOMMA5° logo](https://raw.githubusercontent.com/mrebbert/1komma5-ha/main/custom_components/onekommafive/brand/icon.png){ width="128" align=right }

**1KOMMA5°** (also written **1komma5**, **1k5**) runs the **Heartbeat** energy platform for solar + battery + heat pump + EV wallbox setups. This is the Home Assistant integration for it, distributed via HACS at [github.com/mrebbert/1komma5-ha](https://github.com/mrebbert/1komma5-ha).

Dynamic electricity prices (dynamischer Stromtarif), 30-hour price forecast, AI optimization decisions, per-device cost allocation, cheapest-charging-window scheduling, weather forecast, and cloud push notifications — all as native HA sensors, services and bus events. Works on both 1KOMMA5°-backend accounts (`emp_type: "1K5"`, most newer installs) and legacy GridX-backed accounts (`emp_type: "GRIDX"`).

## Highlights

- **60+ sensors** across 8 coordinators covering power, energy, cost, dynamic prices, AI decisions, weather, system health, §14a grid-fee reduction and contract overview
- **Dynamic tariff support** with 30-hour price forecast, cheapest-window sensors, and per-consumer cost allocation
- **AI optimization events** — react to Heartbeat's grid-charge / heat-pump-recommend decisions in real time
- **Cloud notification bridge** (v0.1.52) — drive automations from the same push notifications the 1KOMMA5° mobile app receives
- **Seven locales** (DE, NL, FI, ES, DK, SE, AU) with per-market currency (EUR, DKK, SEK, AUD)
- **Energy Dashboard-ready** out of the box; no template sensors, no manual wiring
- **Available in the HACS Default Store** — no custom repository setup

## Install

--8<-- "snippets/install-hacs.md"

Then add the integration:

--8<-- "snippets/add-integration.md"

For the full configuration surface, see **[Install & setup](install.md)**.

## What's on this site

- **[Install & setup](install.md)** — HACS / manual install, config-entry options, re-authentication and reconfigure flows.
- **[Features](features/index.md)** — the 60+ sensors grouped by concern: [live power & battery](features/live-power.md), [dynamic pricing](features/pricing.md), [energy & cost](features/energy-cost.md), [§14a EnWG grid-fee](features/enwg14a.md), [contract overview](features/contract.md), [AI optimization](features/ai-optimization.md), [EV & wallbox](features/ev-wallbox.md), [weather](features/weather.md), [diagnostics](features/diagnostics.md).
- **[Services & bus events](services.md)** — `get_cheapest_window`, `refresh_now`, `get_heartbeat_metrics`, `assign_ev_to_wallbox`, plus the three automation bus events.
- **[Dashboards & blueprints](dashboards.md)** — nine importable blueprints and two ready-to-import Lovelace dashboards.
- **[Devices & entity structure](entity-structure.md)** — sub-devices, multi-wallbox topology, PII guardrails.
- **[Compatibility](compatibility.md)** — supported markets, HA version floor, OAuth2 flow.
- **[Known limitations](limitations.md)** — three cloud-API realities the integration cannot design around.
- **[FAQ](faq.md)** — `invalid_auth`, EMS switch, `30401` log line, HACS cache lag, Energy Dashboard wiring, §14a semantics.
- **[Changelog](changelog.md)** · **[Contributing](contributing.md)**

## About

Unofficial reverse-engineered integration maintained by the author against their own 1KOMMA5° system. The underlying Python client is published separately as [`onekommafive` on PyPI](https://pypi.org/project/onekommafive/) with its own [API reference](https://mrebbert.github.io/1komma5-api/). The API is undocumented and may change without notice — see [Disclaimer](compatibility.md#disclaimer).

Credits to [Alex Birkner](https://github.com/BirknerAlex) and the predecessor [hacs_1komma5grad](https://github.com/BirknerAlex/hacs_1komma5grad) integration.
