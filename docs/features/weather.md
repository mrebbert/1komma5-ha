---
title: Weather
description: 48-hour hourly forecast and sunshine totals from the 1KOMMA5° cloud, co-tenant of the price coordinator.
---

# Weather

The weather coordinator (1 h cadence) exposes:

- **Weather entity** — `weather.<system>`, 48 h hourly forecast, `FORECAST_HOURLY` compatible.
- **Sunshine sensors** — `weather_sunshine_today`, `weather_sunshine_tomorrow` (minutes).

The forecast resolves to the current 3-hour bucket via `period_start ≤ now`, so a value is always available even if the coordinator has not refreshed for the current hour.

## Example — show the forecast in a Lovelace card

```yaml
type: weather-forecast
entity: weather.your_site_name
forecast_type: hourly
```

Any `weather`-compatible card works out of the box, including `apexcharts-card` on `attributes.forecast` for custom plots.
