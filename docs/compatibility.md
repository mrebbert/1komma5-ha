---
title: Compatibility
description: Home Assistant version floor, supported markets (DE, NL, FI, ES, DK, SE, AU), OAuth2 PKCE authentication flow and technical details.
---

# Compatibility & requirements

- **Home Assistant** 2024.10 or newer
- A **1KOMMA5° account** with at least one active system
- The [`onekommafive`](https://github.com/mrebbert/1komma5-api) Python library (installed automatically)

## Supported markets

1KOMMA5° operates in seven markets. The integration ships translations and per-locale currency for all of them, auto-detected from the site's country code:

| Locale | Translations | Currency |
|--------|--------------|----------|
| Germany, Austria | German | EUR |
| Netherlands | Dutch | EUR |
| Finland | Finnish | EUR |
| Spain | Spanish | EUR |
| Denmark | Danish | DKK |
| Sweden | Swedish | SEK |
| Australia | English | AUD |

Cost, revenue and price sensors render in the local currency without manual configuration.

!!! info "Caveat"
    End-to-end functional verification exists only for **Germany** (the developer's own setup). The SDK targets a single global API endpoint, so the integration *should* work in other markets, but auth flows, data shapes and feature availability may vary regionally. If something does not work in a non-DE market, please open a [GitHub issue](https://github.com/mrebbert/1komma5-ha/issues) with the diagnostics dump.

## Technical details

| Property | Value |
|----------|-------|
| API library | [mrebbert/1komma5-api](https://github.com/mrebbert/1komma5-api) ([docs](https://mrebbert.github.io/1komma5-api/)) |
| Authentication | OAuth2 PKCE against `auth.1komma5grad.com` (the current Auth0 flow, matches the official iOS app). Accounts that still sign in only via `my.1komma5.io` are not supported; the EMP backend behind the account (GridX or 1KOMMA5°-native) is independent and both work. |
| IoT class | `cloud_polling` |
| Coordinators | 8 (live 30 s, price 1 h, optimization 15 min, weather 1 h, system_status 5 min, energy 15 min, notifications 5 min, heartbeat_prices 1 h) |
| HA domain | `onekommafive` |

## Disclaimer

This project is **not affiliated with or endorsed by 1KOMMA5°**. The API is undocumented and may change without notice.

This is an unofficial integration based on a reverse-engineered API, built 100 % vibe-coded with AI assistance. It may break if 1KOMMA5° changes their backend. Use at your own risk.

The developer does not have the means to test broadly across hardware configurations — a lot of it is "it works for me". Personal test setup:

| Component | Model |
|-----------|-------|
| Hybrid Inverter | Sungrow SH6.0RT-V112 |
| Battery | Sungrow SBR256 |
| Wallbox | go-e homeFix 11 kW |
| EV | Volkswagen ID.5 |
| Heat pump | Stiebel Eltron WPL-A 10 HK 400 Premium |
