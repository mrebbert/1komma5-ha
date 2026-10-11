---
title: §14a EnWG grid-fee reduction
description: BNetzA BK6-22-300 Modul 1 (flat annual rebate) and Modul 3 (variable Netzentgelte HT/NT) exposed as diagnostic sensors on the meter sub-device.
---

# §14a EnWG grid-fee reduction

Two diagnostic sensors on the meter sub-device for accounts that the 1KOMMA5° backend has provisioned under **BNetzA BK6-22-300** (iMSys plus a controllable consumption device: wallbox, heat pump, PV battery). Available since **v0.1.66**.

| Entity | Key | Semantic |
|--------|-----|----------|
| §14a Modul 1 (annual) | `module1_grid_fee_reduction_annual` | Annual **net** grid-fee reduction (EUR/year), from `HeartbeatPriceWindow.module1_savings_per_year_eur`. Diagnostic category. Stays `unavailable` on accounts without a provisioning date (no iMSys + SteuVE). |
| §14a Modul 3 (annual) | `module3_grid_fee_savings_annual` | Annual **net** savings from variable Netzentgelte (HT/NT), from `HeartbeatPriceWindow.module3_total_savings_eur`. Diagnostic category. Stays `unavailable` until the site opts into Modul 3. *New in v0.1.67.* |

## Modul 1 attributes

- `provisioning_date` — ISO date the Modul 1 bundle went live on the account.
- `gross_estimate_eur_assumption` — `value × 1.19`, flagged as an assumption pending a second-grid-area data point. Matches the published gross figure on the first observed account (121 EUR API net vs 144 EUR tariff-area gross).
- `basis` — `"§14a EnWG Modul 1 (BNetzA BK6-22-300); working hypothesis, net figure"`.

## Modul 3 attributes

- `comparison_grid_fee_eur_per_kwh` — the flat reference tariff the HT/NT tariff is compared against.
- `comparison_grid_fees_total_eur` — annual grid fees under the flat reference tariff.
- `variable_grid_fees_total_eur` — annual grid fees under the HT/NT tariff.
- `enwg14a_total_savings_eur` — combined Modul-1-plus-Modul-3 savings for the window.
- `gross_estimate_eur_assumption` — `value × 1.19` on the net savings.
- `basis` — `"§14a EnWG Modul 3 (BNetzA BK6-22-300, variable Netzentgelte HT/NT); net figure"`.

!!! warning "Why these stay separate from the cost sensors"
    Modul 1 is an annual rebate on the grid-fee position of the year-end bill; Modul 3 captures the delta from a hypothetical flat tariff. Linearising either onto `stable_electricity_price` or `electricity_cost` would misrepresent them.

## When the sensors show `unavailable`

The site has not been enrolled in Modul 3 by the 1KOMMA5° backend (or has no Modul 1 provisioning date). The underlying SDK fields stay `None` until that enrolment happens on the provider side — there is no customer-facing setting to toggle. Enrolment is driven by the Netzbetreiber's own HT/NT tariff rollout.

An `unavailable` state is therefore **not an integration bug** — it means your meter is still on a flat Netzentgelt.

## Related

The companion [SDK documentation](https://mrebbert.github.io/1komma5-api/enwg14a/) covers the raw endpoint, request parameters and the full BNetzA regulatory primer.
