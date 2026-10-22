---
title: Troubleshooting
description: Common setup and runtime issues with the 1KOMMA5° integration and how to resolve them.
---

# Troubleshooting

For issues not covered here, open a bug report at
[github.com/mrebbert/1komma5-ha/issues](https://github.com/mrebbert/1komma5-ha/issues).
Attach the diagnostics download (**Settings → Devices & Services → 1KOMMA5° →
three-dot menu → Download diagnostics**) — it is PII-redacted and gives the
fastest path to a diagnosis.

## Login failures

**Symptom:** config flow rejects credentials with `invalid_auth`.

**Checks:**

1. Verify the credentials by logging into the 1KOMMA5° mobile app with the
   same user and password.
2. Check `home-assistant.log` for the WARNING line emitted since v0.1.68 —
   it carries the SDK's error context (which OAuth2/PKCE step failed, HTTP
   status, redacted body). A `[HTML body suppressed, N bytes]` tag indicates
   that step 2 of the flow returned the Auth0 Universal Login page, which
   means the credentials were rejected server-side.
3. The integration speaks the 1KOMMA5° Auth0 tenant only. Accounts migrated
   from the legacy GridX tenant need to re-register through the mobile app
   first.

## Integration stays unavailable after Home Assistant restart

**Symptom:** entities report `unavailable`; the log shows
`'coroutine' object has no attribute …`.

**Cause:** The installed integration version pre-dates v0.1.65 (sync-era) and
is running against the current async SDK v1.x.

**Fix:** Open HACS, select the integration, choose **Redownload** and pick the
latest release. Restart Home Assistant afterwards.

## Optimization settlement sensors stuck on `unknown`

**Symptom:** `sensor.<sys>_optimization_total_cost`,
`optimization_energy_bought`, `optimization_energy_sold` show `unknown` even
though `optimization_event_count` is non-zero.

**Cause:** The 1KOMMA5° cloud returns the decision stream but no settlement
figures. `None` is intentional — the integration refuses to render these
fields as `0.0` so that automations do not confuse "no data" with "zero cost".

**Workaround:** None at the integration side. The data is not available until
1KOMMA5° exposes it on the API; track upstream progress in
[`project_api_dead_ends`](https://github.com/mrebbert/1komma5-ha/blob/main/README.md).

## "Cheapest hour now" never flips ON

**Fixed in v0.1.70.** Pre-v0.1.70, the sensor compared the current price
against the global minimum of the full 30 h forecast (today + tomorrow), so a
marginally cheaper slot on the next day kept it stuck at OFF. v0.1.70 bounds
the comparison to the next 24 h.

If you are still on an earlier version, upgrade via HACS and reload the
integration.

## Service `get_cheapest_window` returns `found: false`

**Symptom:** the service call completes but reports no window.

**Checks:**

1. Prices for the requested horizon must be available: today's slots arrive
   with the morning price update; tomorrow's typically around 13:00 CET.
2. Check `earliest_start` and `latest_end`: a `latest_end` in the past or an
   `earliest_start` beyond the forecast horizon leaves no valid search space.
3. For the service call: `duration` must be a multiple of 15 minutes and
   match the slot grid of the forecast.

## Enabling debug logging

Add this to `configuration.yaml` and restart:

```yaml
logger:
  default: info
  logs:
    custom_components.onekommafive: debug
    onekommafive: debug
```

Collect `home-assistant.log` after reproducing the issue and attach it to the
bug report along with the diagnostics download.

## System Information panel

**Settings → System → Repairs → System Information** reports per-coordinator
update status, API reachability, SDK version and the resolved currency and
country. The panel is PII-safe and is a better first attachment to bug
reports than the full diagnostics download.
