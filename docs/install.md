---
title: Install & setup
description: HACS install, manual install, config-entry creation, credential update (re-authentication and reconfigure) for the 1KOMMA5° Home Assistant integration.
---

# Install & setup

## 1. Install via HACS

--8<-- "snippets/install-hacs.md"

??? note "Manual installation (without HACS)"

    1. Download the [latest release](https://github.com/mrebbert/1komma5-ha/releases/latest) (`onekommafive.zip`)
    2. Extract and copy the `onekommafive/` folder to `<config>/custom_components/`
    3. Restart Home Assistant

## 2. Add the integration

--8<-- "snippets/add-integration.md"

## 3. Options

Under **Settings → Devices & Services → 1KOMMA5° → Configure**:

| Option | Default | Description |
|--------|---------|-------------|
| Feed-in Tariff | 0.0803 EUR/kWh | Feed-in tariff used by the *Feed-in Revenue* sensor. Set to your actual contract rate incl. bonuses. |
| Charging-window duration | 60 min | Length of the *Cheapest charging window* sensors. Multiple of 15, 15–240 min. Raise to 90/120 for longer flexible loads (EV bulk charges, wash cycles); drop to 30 for short loads (boiler, quick dishwasher programme). Mid-day duration changes invalidate the lock-in so the next refresh re-picks. |

## 4. Updating credentials

Two flows preserve sensor history, restored states and Energy Dashboard configuration:

- **Re-authentication** — When 1KOMMA5° rejects auth (e.g. after a password change), HA shows a *Re-authentication required* notice. Click it, enter the new password, done.
- **Reconfigure** — Proactively via **Settings → Devices & Services → 1KOMMA5°** → ⋮ menu → **Reconfigure**.

Both flows reuse the shared `_async_credentials_step` and preserve the `system_id` of the entry; HA raises a clear error if the account no longer has that system.

## Removing the integration

Under **Settings → Devices & Services → 1KOMMA5° → ⋮ → Delete**. HA cleans up all entities, sub-devices and stored credentials — the integration owns nothing else on your machine.

Individual sub-devices (Wallbox, Vehicle, Heat pump, …) can also be removed one at a time from the device view (**Devices → click the sub-device → ⋮ → Delete device**), useful when a wallbox is retired: the parent device stays put and the entities come back if the cloud reports the hardware again on the next reload.
