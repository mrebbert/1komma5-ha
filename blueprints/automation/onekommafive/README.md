# 1KOMMA5° automation blueprints

Eleven ready-to-import [Home Assistant blueprints][ha-blueprints] for the most
common automations on top of this integration.

## Importing

Each blueprint below carries a one-click import badge — clicking it opens
your own Home Assistant and prefills the import dialog. The underlying
`my.home-assistant.io` redirect works for any instance you've linked once.

Manual fallback: **Settings → Automations & Scenes → Blueprints → Import
Blueprint**, then paste the GitHub URL of the YAML file, e.g.

```
https://github.com/mrebbert/1komma5-ha/blob/main/blueprints/automation/onekommafive/cheapest_window.yaml
```

After import, click **Create automation** to instantiate it with your own
entities.

## Blueprints

### `cheapest_window.yaml` — Run during cheapest window

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fcheapest_window.yaml)

Schedules a switch (or `input_boolean`) to run for an exact duration during
the cheapest contiguous window in the price forecast. Calls
`onekommafive.get_cheapest_window` once per day at a planning time you choose.

Typical use: dishwasher, washing machine, dryer, water heater, EV manual run.

Inputs: switch entity, run duration (15 min steps), planning time, earliest
start (HH:MM), latest end (HH:MM).

### `follow_cheap_electricity.yaml` — Follow cheap electricity

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Ffollow_cheap_electricity.yaml)

Mirrors a switch's state to the `…_cheap_electricity` binary sensor —
opportunistic on/off whenever the current price is below today's average.

Typical use: domestic hot-water boost, pool pump, opportunistic battery
chargers (e-bike, power tools).

Inputs: cheap-electricity binary sensor, switch entity, optional
earliest/latest hour-of-day window.

### `ev_departure_from_calendar.yaml` — EV departure time from HA calendar

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fev_departure_from_calendar.yaml)

Automatically keeps `time.<sys>_<ev>_ev_departure_time` in sync with the next
relevant HA-calendar event. Reads the calendar twice daily (evening preplan +
morning reconfirm) and computes departure as `event.start − commute_buffer`.
The 1KOMMA5° AI then schedules charging to be ready in time, picking the
cheapest slots overnight.

Supports two match modes (dedicated commute calendar OR summary-keyword filter)
plus optional home-office suppression and optional live travel-time sensor
(waze_travel_time / google_travel_time / here_travel_time) that overrides the
static commute minutes with live traffic data.

Falls back to a configurable fixed time on days without a matching event
(weekend, holiday, vacation).

Inputs: EV departure-time entity, HA calendar, planning time (default 20:00),
reconfirm time (default 05:00), commute minutes (default 30), optional
travel-time sensor, optional summary/exclude keywords, fallback departure time.

### `ai_decision_calendar_trigger.yaml` — Act on any AI-decision calendar event

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fai_decision_calendar_trigger.yaml)

Universal calendar-driven trigger on the AI-decisions calendar
(`calendar.<system>_ai_decisions_calendar`, v0.1.73+). Pick one of the
eight event classes — the six AI decision types plus `proxy_cheap` /
`proxy_expensive` — choose `start` or `end`, add an optional offset, and
plug in any action sequence.

Match uses the event's stable `description` key, so the blueprint works
regardless of HA UI language.

Typical use: EV quick-charge during cheap proxy slots, run a script on
`optimization_heat_pump_recommended`, notify when the AI decides to
grid-charge the battery.

Inputs: calendar entity, decision key (dropdown), event phase
(start/end), offset (±60 min), action sequence.

### `notify_grid_charge.yaml` — Notify on AI grid-charge decision

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fnotify_grid_charge.yaml)

Fires a notification whenever the Heartbeat AI flips
`…_optimization_battery_grid_charge` to ON (i.e. it just decided that *now*
is the right time to buy power from the grid for the home battery).

This is rarer but more accurate than `cheap_electricity` — the AI considers
the full forecast and the current battery state.

Inputs: grid-charge binary sensor, notify service, title, message
(Jinja-templatable).

### `notify_negative_prices_tomorrow.yaml` — Notify on negative prices tomorrow

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fnotify_negative_prices_tomorrow.yaml)

Fires a notification when tomorrow's price forecast contains at least one
negative-price slot (i.e. the spot market pays you to consume). The price
coordinator picks up tomorrow's prices around 13:00 CET, so that's when the
heads-up usually arrives.

Configurable `minimum_slots` gate — raise from the default `1` if you only
want to hear about hour-or-longer negative windows (≥ 4 slots).

Inputs: `…_negative_price_slots_tomorrow` sensor, minimum slot count,
notify service, title, message (Jinja-templatable).

### `vehicle_at_wallbox.yaml` — Bind vehicle profile when it plugs in

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fvehicle_at_wallbox.yaml)

Watches a binary sensor that reads ON when *one specific vehicle* is plugged
into your wallbox. When it fires, calls `select.select_option` on the
wallbox's assignment select (`select.<sys>_<wallbox>_assigned_vehicle`,
v0.1.63) so 1KOMMA5° applies that vehicle's charging mode, target SoC and
departure schedule to the ongoing session.

Typical setup: one automation per vehicle. Each points at the connect-signal
that identifies its car (from the car integration, an OCPP wallbox sensor,
or a smart-plug's current draw). The 1KOMMA5° model is 1:1 exclusive — the
previously bound vehicle is released automatically in the same API call.

Inputs: vehicle-connected binary sensor, wallbox assignment select, vehicle
option slug (e.g. `bmw_i3`; look up in the select's `options` attribute).

### `ev_charge_on_pv_surplus.yaml` — EV charge on PV surplus

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fev_charge_on_pv_surplus.yaml)

Toggles a target switch (smart plug, `input_boolean`, or hand-off to the
wallbox charging-mode selector) ON when the home battery is full **AND**
PV power exceeds a threshold, OFF when either condition fails. A
deactivation delay smooths out brief cloud cover.

Typical use: opportunistic EV top-up from genuine solar surplus, without
draining the house battery.

Inputs: battery SoC sensor, battery-full threshold (default 95 %), PV
power sensor, PV surplus threshold (default 5 000 W), target switch,
deactivation delay (default 5 min).

### `notify_negative_price_started.yaml` — Notify when the grid pays you

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fnotify_negative_price_started.yaml)

Fires a notification the moment the active 15-min electricity price
becomes ≤ 0. Listens to the
`onekommafive_negative_price_started` bus event — granularity is the
price-coordinator refresh interval (default 1 h), so the alert may
arrive up to a refresh-cycle late.

Companion to `notify_negative_prices_tomorrow.yaml` (forecast-side
heads-up about *tomorrow's* negative slots).

Inputs: notify service, title, message (Jinja-templatable with
`trigger.event.data.price` and
`trigger.event.data.negative_price_slots_remaining`).

### `notify_cloud_notification.yaml` — Forward 1KOMMA5° cloud notifications

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fnotify_cloud_notification.yaml)

Fires a notification for each new `onekommafive_notification` bus event
(v0.1.52) — the same push notifications the 1KOMMA5° mobile app receives
(energy market thresholds, system health alerts, dynamic-pulse events).
Payload arrives pre-localized to your account language, so the default
title + message pass `title` and `body` straight through.

Optional `type_filter` restricts to a single notification type (e.g.
`ENERGY_MARKET_UPPER_TARGET_REACHED`) — leave empty for all types. Which
types reach HA is controlled by your 1KOMMA5° app's Settings →
Notifications.

Inputs: notify service, optional type filter, title, message
(Jinja-templatable with `trigger.event.data.title` / `.body` / `.type` /
`.meta`).

### `notify_connectivity_lost.yaml` — Notify when a device goes offline

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fmrebbert%2F1komma5-ha%2Fmain%2Fblueprints%2Fautomation%2Fonekommafive%2Fnotify_connectivity_lost.yaml)

Sends a notification when one of the v0.1.38 connectivity sensors (site,
inverter, heat pump, meter, wallbox) stays OFF for a debounce duration
(default 5 minutes). The default message uses `{{ trigger.to_state.name }}`
so a single import covers any of the five sensors — instantiate one
automation per sensor you want to watch.

Inputs: connectivity binary sensor, offline debounce duration, notify
service, title, message (Jinja-templatable).

## Note about the `entity.integration: onekommafive` selector

Some inputs use `selector.entity.integration: onekommafive` so the picker
only shows entities from this integration. This requires Home Assistant
2024.2 or newer (the integration filter on entity selectors).

[ha-blueprints]: https://www.home-assistant.io/docs/blueprint/
