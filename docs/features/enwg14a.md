---
title: §14a EnWG grid-fee reduction
description: BNetzA BK6-22-300 Modul 1 (flat annual rebate) and Modul 3 (variable Netzentgelte HT/NT) exposed as diagnostic sensors on the meter sub-device, plus a live per-slot Modul-3 rate.
---

# §14a EnWG grid-fee reduction

Four sensors on the meter sub-device for accounts that the 1KOMMA5° backend has provisioned under **BNetzA BK6-22-300** (iMSys plus a controllable consumption device: wallbox, heat pump, PV battery). Base trio available since **v0.1.66**; live per-slot Modul-3 rate added in the v0.1.72 line.

| Entity | Key | Semantic |
|--------|-----|----------|
| §14a enrolment (authoritative) | `enwg14a_module` | ENUM diagnostic reading `SiteSystemInfo.enwg14a_module` from the dedicated `/api/v1/sites/{id}/system-info` endpoint. States: `none` (not enrolled), `module_1` (pauschale Reduktion), `module_3` (variable HT/NT), `unknown` (fetch failed or returned an unmapped slug). Always registers. *New in v0.1.69.* |
| §14a Modul 1 (annual) | `module1_grid_fee_reduction_annual` | Annual **net** grid-fee reduction (EUR/year), from `HeartbeatPriceWindow.module1_savings_per_year_eur`. Diagnostic category. Stays `unavailable` on accounts without a provisioning date (no iMSys + SteuVE). |
| §14a Modul 3 (annual) | `module3_grid_fee_savings_annual` | Annual **net** savings from variable Netzentgelte (HT/NT), from `HeartbeatPriceWindow.module3_total_savings_eur`. Diagnostic category. Stays `unavailable` until the site opts into Modul 3. *New in v0.1.67.* |
| §14a Modul 3 (live per slot) | `enwg14a_grid_fee_current` | Current 15-minute-slot net grid-fee rate (`€/kWh`), from `MarketPrices.enwg14a_grid_fee` (SDK 1.2.1+). Attribute `price_with_vat` carries the gross counterpart. Populated on **Modul 3** sites because Modul 3 is the time-of-day module; Modul 1 sites (flat annual rebate) see `unavailable` — Modul 1 has no per-slot component. **Not** a diagnostic entity, so automations can key off it directly. *New in v0.1.72.* |

The authoritative `enwg14a_module` sensor and the three value sensors are complementary: the ENUM is the explicit backend-side enrolment flag; the Modul-1-rebate and Modul-3-savings sensors read annual aggregates from the heartbeat-prices window; the live per-slot sensor reads the time-of-day Modul-3 rate from `/charts/market-prices`.

## Modul 1 attributes

- `provisioning_date` — ISO date the Modul 1 bundle went live on the account.
- `enwg14a_module_valid_from` — ISO-8601 date from `SiteSystemInfo.enwg14a_module.valid_from_date` (SDK v1.1.8+); `None` when the authoritative endpoint reports no enrolment. *New in v0.1.69.*
- `gross_estimate_eur_assumption` — `value × 1.19`, flagged as an assumption pending a second-grid-area data point. Matches the published gross figure on the first observed account (121 EUR API net vs 144 EUR tariff-area gross).
- `basis` — `"§14a EnWG Modul 1 (BNetzA BK6-22-300); working hypothesis, net figure"`.

## Modul 3 attributes

- `comparison_grid_fee_eur_per_kwh` — the flat reference tariff the HT/NT tariff is compared against.
- `comparison_grid_fees_total_eur` — annual grid fees under the flat reference tariff.
- `variable_grid_fee_eur_per_kwh` — effective variable (HT/NT) grid-fee rate per window, counterpart to `comparison_grid_fee_eur_per_kwh`. *New in v0.1.69.*
- `variable_grid_fees_total_eur` — annual grid fees under the HT/NT tariff.
- `enwg14a_total_savings_eur` — combined Modul-1-plus-Modul-3 savings for the window.
- `enwg14a_module_valid_from` — ISO-8601 date from the authoritative endpoint. *New in v0.1.69.*
- `gross_estimate_eur_assumption` — `value × 1.19` on the net savings.
- `basis` — `"§14a EnWG Modul 3 (BNetzA BK6-22-300, variable Netzentgelte HT/NT); net figure"`.

!!! warning "Why these stay separate from the cost sensors"
    Modul 1 is an annual rebate on the grid-fee position of the year-end bill; Modul 3 captures the delta from a hypothetical flat tariff. Linearising either onto `stable_electricity_price` or `electricity_cost` would misrepresent them.

## When the sensors show `unavailable`

- **`module1_grid_fee_reduction_annual`** stays `unavailable` on accounts without a Modul-1 provisioning date (no iMSys + SteuVE).
- **`module3_grid_fee_savings_annual`** stays `unavailable` until the site opts into Modul 3. Enrolment is driven by the Netzbetreiber's own HT/NT tariff rollout — there is no customer-facing setting to toggle.
- **`enwg14a_grid_fee_current`** stays `unavailable` on any site that is not Modul 3: Modul-1 sites by design (annual flat rebate, no per-slot component), Modul-2 and non-enrolled sites similarly. The backend returns an empty dict for the `enwg14aGridFee` key in that case.

An `unavailable` state is therefore **not an integration bug** — it means either your meter is still on a flat Netzentgelt or Modul 1 is the module you qualified for.

## Related

The companion [SDK documentation](https://mrebbert.github.io/1komma5-api/enwg14a/) covers the raw endpoint, request parameters and the full BNetzA regulatory primer.
