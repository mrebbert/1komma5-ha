# 1KOMMA5° automation blueprints

Three ready-to-import [Home Assistant blueprints][ha-blueprints] for the most
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

## Note about the `entity.integration: onekommafive` selector

Some inputs use `selector.entity.integration: onekommafive` so the picker
only shows entities from this integration. This requires Home Assistant
2024.2 or newer (the integration filter on entity selectors).

[ha-blueprints]: https://www.home-assistant.io/docs/blueprint/
