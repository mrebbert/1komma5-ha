---
title: Contract overview
description: Active subscriptions, 1KOMMA5°Care add-on eligibility and the EMP backend enum — PII-safe setup-time snapshots on the system parent device.
---

# Contract overview

Three diagnostic sensors on the system parent that make the account's contract state addressable from automations and dashboards without raw API calls. Available since **v0.1.67**.

| Entity | Key | Semantic |
|--------|-----|----------|
| Active subscriptions | `active_subscriptions` | Count of contracts with `status == "ACTIVE"`. Attribute `contracts` lists every subscription's PII-safe fields (type, status, dates, notice period, renewal, billing frequency, price, currency, payment-method enum, country code). |
| Add-on eligibility | `subscription_eligibility` | Count of 1KOMMA5°Care add-ons the account qualifies for. Attributes split into `eligible` (list of product types) and `ineligible` (`{type, reason}` with the CRM-provided reason verbatim). |
| EMP backend | `emp_backend` | ENUM — `gridx`, `1k5`, or `unknown` (fallback). Previously only in the diagnostics dump. Lowercase keys to satisfy hassfest; translations map to "GridX" / "1KOMMA5°" in the UI. |

These are **setup-time snapshots** that mirror the `dynamic_pulse_price_guarantee` pattern: subscriptions change on contract events, not during runtime. Fetches are non-fatal — a failed `get_subscriptions` or `get_subscription_eligibility` skips its sensor; `emp_backend` always registers and falls back to `UNKNOWN`.

!!! info "PII guardrail"
    The `contracts` attribute whitelists fields explicitly. `customer_id`, `site_id`, `electricity_contract_number`, `market_location_id`, `terms_and_conditions_url` and the raw CRM record (IBAN, addresses, Zoho/Lumenaza IDs, status history) stay out by design.

## Using the sensors in automations

- `active_subscriptions > 0` tells you the account currently carries at least one 1KOMMA5° product (Dynamic Pulse, 1KOMMA5°Care, ...).
- `subscription_eligibility > 0` tells you which 1KOMMA5°Care add-ons are offerable without having to open the app.
- `emp_backend` is useful as a condition in automations that touch EMS-specific entities (which exist only on `gridx`).
