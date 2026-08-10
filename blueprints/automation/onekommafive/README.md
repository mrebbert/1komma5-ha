# 1KOMMA5° automation blueprints

Eight ready-to-import [Home Assistant blueprints][ha-blueprints] for the most
common automations on top of this integration.

## Importing

In Home Assistant: **Settings → Automations & Scenes → Blueprints → Import
Blueprint**, then paste the URL of the YAML file you want.

For example, for the cheapest-window blueprint:

```
https://github.com/mrebbert/1komma5-ha/blob/main/blueprints/automation/onekommafive/cheapest_window.yaml
```

After import, click **Create automation** to instantiate it with your own
entities.

## Blueprints

### `cheapest_window.yaml` — Run during cheapest window
Schedules a switch (or `input_boolean`) to run for an exact duration during
the cheapest contiguous window in the price forecast. Calls
`onekommafive.get_cheapest_window` once per day at a planning time you choose.

Typical use: dishwasher, washing machine, dryer, water heater, EV manual run.

Inputs: switch entity, run duration (15 min steps), planning time, earliest
start (HH:MM), latest end (HH:MM).

### `follow_cheap_electricity.yaml` — Follow cheap electricity
Mirrors a switch's state to the `…_cheap_electricity` binary sensor —
opportunistic on/off whenever the current price is below today's average.

Typical use: domestic hot-water boost, pool pump, opportunistic battery
chargers (e-bike, power tools).

Inputs: cheap-electricity binary sensor, switch entity, optional
earliest/latest hour-of-day window.

### `notify_grid_charge.yaml` — Notify on AI grid-charge decision
Fires a notification whenever the Heartbeat AI flips
`…_optimization_battery_grid_charge` to ON (i.e. it just decided that *now*
is the right time to buy power from the grid for the home battery).

This is rarer but more accurate than `cheap_electricity` — the AI considers
the full forecast and the current battery state.

Inputs: grid-charge binary sensor, notify service, title, message
(Jinja-templatable).

### `notify_negative_prices_tomorrow.yaml` — Notify on negative prices tomorrow
Fires a notification when tomorrow's price forecast contains at least one
negative-price slot (i.e. the spot market pays you to consume). The price
coordinator picks up tomorrow's prices around 13:00 CET, so that's when the
heads-up usually arrives.

Configurable `minimum_slots` gate — raise from the default `1` if you only
want to hear about hour-or-longer negative windows (≥ 4 slots).

Inputs: `…_negative_price_slots_tomorrow` sensor, minimum slot count,
notify service, title, message (Jinja-templatable).

### `ev_charge_on_pv_surplus.yaml` — EV charge on PV surplus
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
